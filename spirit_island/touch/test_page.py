"""Stage 2 touch test: a live TV page that shows what the camera thinks your hand is
doing, asks for gestures one at a time, and scores each try.

    python -m spirit_island.touch.test_page --camera http://192.168.1.60:8080/video
    python -m spirit_island.touch.test_page --camera 0             # a USB webcam
    python -m spirit_island.touch.test_page --camera clip.mp4      # replay a recording

Open http://<this computer>:5056/ on the TV. Keyboard on the TV page: Enter or
right arrow skips a prompt, R restarts. Each run is saved to
spirit_island/games/touch_tests/<time>.json, and with --record the raw video too, so
the gesture rules can be tuned against your real hands and light.
"""

from __future__ import annotations

import argparse
import json
import os
import threading
import time

import cv2
import numpy as np
from flask import Flask, Response, jsonify, request

from vision.capture import Camera

from . import mat as matmod
from .gestures import GestureReader, fingers_up, palm_size
from .hands import HandFinder, draw_hand

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(BASE, "games", "touch_tests")

# (what to ask, what counts as a pass)
PROMPTS = [
    ("Hold up 1 finger", {"kind": "hold", "count": 1}),
    ("Hold up 2 fingers", {"kind": "hold", "count": 2}),
    ("Hold up 3 fingers", {"kind": "hold", "count": 3}),
    ("Hold up 4 fingers", {"kind": "hold", "count": 4}),
    ("Hold up 5 fingers (whole hand)", {"kind": "hold", "count": 5}),
    ("Hold up 3 fingers again", {"kind": "hold", "count": 3}),
    ("Hold up 2 fingers again", {"kind": "hold", "count": 2}),
    ("Two hands: 7 fingers", {"kind": "hold", "count": 7}),
    ("Double tap with ONE finger (Next)", {"kind": "double_tap", "fingers": 1}),
    ("Double tap with one finger again", {"kind": "double_tap", "fingers": 1}),
    ("Double tap with one finger once more", {"kind": "double_tap", "fingers": 1}),
    ("Double tap with one finger, fourth time", {"kind": "double_tap", "fingers": 1}),
    ("Double tap with TWO fingers (Back)", {"kind": "double_tap", "fingers": 2}),
    ("Double tap with two fingers again", {"kind": "double_tap", "fingers": 2}),
    ("Double tap with two fingers once more", {"kind": "double_tap", "fingers": 2}),
    ("Double tap with two fingers, fourth time", {"kind": "double_tap", "fingers": 2}),
    ("Point at any land and hold still", {"kind": "hold", "count": 1, "tip": True}),
    ("Point at a different land and hold", {"kind": "hold", "count": 1, "tip": True}),
    ("Rest: move a few pieces around normally for 15 seconds. No double taps should fire.", {"kind": "rest", "seconds": 15}),
]
TIMEOUT_S = 12.0


class Session:
    def __init__(self, back_is="left", only=None):
        self.lock = threading.Lock()
        self.prompts = [p for p in PROMPTS if not only or p[1]["kind"] in only]
        self.back_is = back_is  # image direction of a back swipe, set by --back
        self.restart()

    def restart(self):
        with self.lock:
            self.i = 0
            self.started = time.time()
            self.prompt_t = time.time()
            self.results = []
            self.extra = []   # events that matched nothing, outside rest
            self.frames = []  # per-frame hand readings during tap prompts, for tuning
            self.rest_hits = []
            self.last_event = None
            self.stamp = time.strftime("%Y%m%d-%H%M%S")

    def current(self):
        return self.prompts[self.i] if self.i < len(self.prompts) else None

    def log_frame(self, t, hands):
        """Keep what the tracker saw while a tap is asked for: enough to tune taps from."""
        cur = self.current()
        if not cur or cur[1]["kind"] != "double_tap":
            return
        row = {"t": round(t, 3), "prompt": self.i}
        if hands:
            m = max(hands, key=palm_size)
            row.update({"fingers": [int(x) for x in fingers_up(m)], "hands": len(hands),
                        "pts": [[round(x, 1), round(y, 1)] for (x, y) in m]})
        with self.lock:
            self.frames.append(row)

    def _matches(self, want, ev):
        if want["kind"] != ev["kind"]:
            return False
        if want["kind"] == "hold":
            return ev["count"] == want["count"] and (not want.get("tip") or ev.get("tip") is not None)
        if want["kind"] == "double_tap":
            return ev.get("fingers") == want["fingers"]
        if want["kind"] == "swipe":
            back = ev["direction"] == self.back_is
            return (want["direction"] == "back") == back
        return True

    def _advance(self, outcome, ev=None):
        text, want = self.prompts[self.i]
        self.results.append({"prompt": text, "outcome": outcome,
                             "latency_s": round(time.time() - self.prompt_t, 2), "event": _plain(ev)})
        self.i += 1
        self.prompt_t = time.time()
        self.save()

    def on_event(self, ev):
        with self.lock:
            self.last_event = {**_plain(ev), "t": time.time()}
            cur = self.current()
            if cur is None:
                return
            text, want = cur
            if want["kind"] == "rest":
                self.rest_hits.append(_plain(ev))
                return
            if self._matches(want, ev):
                tries = sum(1 for x in self.extra if x["prompt"] == text)
                self._advance("pass" if not tries else f"pass after {tries} wrong", ev)
            else:
                self.extra.append({"prompt": text, "event": _plain(ev)})
                # A wrong reading is recorded but doesn't move on: you can try again until
                # the prompt times out (moving on put the test a step ahead of the hand).

    def tick(self):
        with self.lock:
            cur = self.current()
            if cur is None:
                return
            text, want = cur
            limit = want.get("seconds", TIMEOUT_S)
            if time.time() - self.prompt_t >= limit:
                self._advance("rest" if want["kind"] == "rest" else "missed")

    def skip(self):
        with self.lock:
            if self.current() is not None:
                self._advance("skipped")

    def summary(self):
        with self.lock:
            r = [x for x in self.results if x["outcome"] != "rest"]
            passed = [x for x in r if x["outcome"].startswith("pass")]
            by_kind = {}
            for x, (_, want) in zip(self.results, self.prompts):
                if want["kind"] == "rest":
                    continue
                k = {"hold": "fingers" if not want.get("tip") else "point", "swipe": "swipe",
                     "double_tap": f"double tap, {want.get('fingers', 1)} finger"}[want["kind"]]
                d = by_kind.setdefault(k, {"pass": 0, "of": 0, "latency": []})
                d["of"] += 1
                if x["outcome"].startswith("pass"):
                    d["pass"] += 1
                    d["latency"].append(x["latency_s"])
            cur = self.current()
            return {"prompt": cur[0] if cur else None, "index": self.i, "total": len(self.prompts),
                    "seconds_left": round(max(0.0, (cur[1].get("seconds", TIMEOUT_S) if cur else 0)
                                              - (time.time() - self.prompt_t)), 1),
                    "passed": len(passed), "tried": len(r), "by_kind": by_kind,
                    "false_in_rest": len(self.rest_hits), "results": self.results[-6:],
                    "last_event": self.last_event, "back_is": self.back_is}

    def save(self):
        os.makedirs(OUT_DIR, exist_ok=True)
        with open(os.path.join(OUT_DIR, f"{self.stamp}.json"), "w", encoding="utf-8") as f:
            json.dump({"started": self.started, "results": self.results, "extra": self.extra,
                       "frames": self.frames,
                       "rest_hits": self.rest_hits, "back_is": self.back_is}, f, indent=1)


def _plain(ev):
    if not ev:
        return None
    return {k: (list(v) if isinstance(v, tuple) else v) for k, v in ev.items() if k != "card"}


class Runner:
    """Reads frames, finds hands, turns them into events, draws the live picture."""

    def __init__(self, source, session, record=None, work_width=480, use_mat=False):
        self.use_mat = use_mat
        self.cam = Camera(source)
        self.finder = HandFinder(work_width=work_width)
        self.reader = GestureReader()
        self.cards = matmod.CardWatch()
        self.session = session
        self.jpeg = b""
        self.status = {}
        self.record = record
        self._writer = None
        self._stop = threading.Event()
        self.fps = 0.0

    def start(self):
        self.cam.start()
        threading.Thread(target=self._run, daemon=True).start()
        return self

    def _run(self):
        last_idx, frames, t0, last_mat_t, mat = -1, 0, time.time(), 0.0, None
        while not self._stop.is_set():
            pkt = self.cam.wait_for_frame(after_index=last_idx, timeout=2.0)
            if pkt is None:
                self.status = {"camera": "no frames"}
                continue
            last_idx = pkt.index
            img, t = pkt.image, pkt.timestamp
            if self.record:
                if self._writer is None:
                    h, w = img.shape[:2]
                    self._writer = cv2.VideoWriter(self.record, cv2.VideoWriter_fourcc(*"mp4v"), 15, (w, h))
                self._writer.write(img)
            hands = self.finder.find(img, t)
            if self.use_mat and time.time() - last_mat_t > 1.0:
                found = matmod.find_mat(img, hands)
                mat = found or mat if hands else found  # keep the last mat while a hand covers it
                last_mat_t = time.time()
            self.session.log_frame(t, hands)
            events = self.reader.update(t, hands, mat)
            if mat:
                events += self.cards.update(t, matmod.find_cards(img, mat, hands))
            for ev in events:
                self.session.on_event(ev)
            self.session.tick()
            frames += 1
            if time.time() - t0 >= 1.0:
                self.fps, frames, t0 = frames / (time.time() - t0), 0, time.time()
            self._draw(img, hands, mat, events)

    def _draw(self, img, hands, mat, events):
        out = img.copy()
        if mat:
            cv2.polylines(out, [np.array(mat["box"], np.int32)], True, (90, 200, 255), 3)
        for lm in hands:
            draw_hand(out, lm)
        prog = self.reader.progress()
        if hands and prog["count"]:
            lm = max(hands, key=palm_size)
            c = tuple(int(v) for v in lm[9])
            r = int(palm_size(lm) * 1.1)
            cv2.circle(out, c, r, (80, 80, 80), 4)
            cv2.ellipse(out, c, (r, r), -90, 0, 360 * prog["fraction"], (80, 220, 255), 8)
            cv2.putText(out, str(prog["count"]), (c[0] - 20, c[1] + 20), cv2.FONT_HERSHEY_SIMPLEX, 2.2,
                        (255, 255, 255), 5, cv2.LINE_AA)
        h, w = out.shape[:2]
        scale = min(1.0, 960 / w)
        if scale < 1:
            out = cv2.resize(out, (int(w * scale), int(h * scale)))
        ok, buf = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if ok:
            self.jpeg = buf.tobytes()
        self.status = {"camera": "ok", "fps": round(self.fps, 1), "hands": len(hands),
                       "detect_ms": round(self.finder.ms, 1), "mat": bool(mat),
                       "progress": prog, "frame": [w, h]}


PAGE = """<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Touch test</title><style>
:root{--bg:#0f1512;--ink:#eef3ef;--quiet:#9aa8a0;--ok:#6fd08c;--bad:#ff7b6b;--hi:#ffd166}
body{margin:0;background:var(--bg);color:var(--ink);font:20px/1.35 system-ui,sans-serif}
.wrap{display:grid;grid-template-columns:3fr 2fr;gap:24px;padding:24px;height:100vh;box-sizing:border-box}
img{width:100%;border-radius:12px;background:#000}
.prompt{font-size:54px;font-weight:700;line-height:1.1;margin:8px 0 4px}
.sub{color:var(--quiet)}
.big{font-size:30px}
.ev{font-size:34px;color:var(--hi);min-height:46px}
table{border-collapse:collapse;width:100%;margin-top:12px}td{padding:6px 4px;border-bottom:1px solid #26302b}
[class^=pass]{color:var(--ok)}.wrong,.missed{color:var(--bad)}
@media (max-width:900px){.wrap{grid-template-columns:1fr;height:auto}.prompt{font-size:36px}}
</style></head><body><div class=wrap>
<div><img id=live alt="live camera with the hand drawn over it"><div class=sub id=cam></div></div>
<div><div class=sub id=step></div><div class=prompt id=prompt>Starting...</div><div class="sub big" id=left></div>
<div class=sub style="margin-top:18px">Last thing I saw</div><div class=ev id=ev></div>
<div class=big id=score style="margin-top:14px"></div><table id=kinds></table><table id=recent></table>
<div class=sub style="margin-top:14px">Enter = skip this one, R = start over</div></div></div>
<script>
const $=id=>document.getElementById(id);
const say=e=>!e?"":e.kind=="hold"?(e.count+" finger"+(e.count==1?"":"s")+(e.tip?" (pointing)":"")):
  e.kind=="swipe"?("swipe "+e.direction):e.kind=="double_tap"?("double tap, "+e.fingers+" finger"+(e.fingers==1?" (Next)":"s (Back)")):e.kind=="card_down"?"card laid down":e.kind=="card_up"?"card picked up":e.kind;
async function tick(){try{const s=await (await fetch("/state")).json();const q=s.session,c=s.camera;
$("cam").textContent=c.camera=="ok"?`camera ${c.fps} fps, hand finding ${c.detect_ms} ms, ${c.hands} hand(s)`:"camera: "+(c.camera||"starting");
$("step").textContent=q.prompt?`Test ${q.index+1} of ${q.total}`:"";
$("prompt").textContent=q.prompt||"Done. Thanks!";
$("left").textContent=q.prompt?`${q.seconds_left}s`:"";
const ev=q.last_event;$("ev").textContent=ev&&Date.now()/1000-ev.t<4?say(ev):"";
$("score").textContent=`Passed ${q.passed} of ${q.tried}`+(q.false_in_rest?` · ${q.false_in_rest} false alarm(s) while resting`:"");
$("kinds").innerHTML=Object.entries(q.by_kind).map(([k,d])=>`<tr><td>${k}</td><td>${d.pass}/${d.of}</td><td class=sub>${d.latency.length?(d.latency.reduce((a,b)=>a+b,0)/d.latency.length).toFixed(1)+" s avg":""}</td></tr>`).join("");
$("recent").innerHTML=q.results.slice().reverse().map(r=>`<tr><td class="${r.outcome.split(' ')[0]}">${r.outcome}</td><td>${r.prompt}</td><td class=sub>${r.event?say(r.event):""}</td></tr>`).join("");
}catch(e){}}
setInterval(tick,250);tick();
// The live picture: one JPEG at a time, the next asked for as soon as one arrives. Steadier in
// Chrome than a multipart stream, and it can't fall behind.
const live=$("live");let n=0;
function nextFrame(){const im=new Image();im.onload=()=>{live.src=im.src;setTimeout(nextFrame,30)};
  im.onerror=()=>setTimeout(nextFrame,500);im.src="/frame.jpg?n="+(n++)}
nextFrame();
addEventListener("keydown",e=>{if(e.key=="Enter"||e.key=="ArrowRight")fetch("/skip",{method:"POST"});if(e.key=="r"||e.key=="R")fetch("/restart",{method:"POST"});});
</script></body></html>"""


def create_app(runner, session):
    app = Flask(__name__)

    @app.get("/")
    def page():
        return Response(PAGE, mimetype="text/html")

    @app.get("/state")
    def state():
        return jsonify({"session": session.summary(), "camera": runner.status})

    @app.post("/skip")
    def skip():
        session.skip()
        return jsonify(ok=True)

    @app.post("/restart")
    def restart():
        session.restart()
        runner.reader.reset()
        return jsonify(ok=True)

    @app.post("/back")
    def back():
        """{"is": "left"|"right"}: which way a back swipe goes in the camera's picture."""
        session.back_is = (request.get_json(silent=True) or {}).get("is", "left")
        return jsonify(ok=True)

    @app.get("/frame.jpg")
    def frame():
        if not runner.jpeg:
            return Response("no picture yet", status=503)
        return Response(runner.jpeg, mimetype="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.get("/stream.mjpg")
    def stream():
        def gen():
            last = None
            while True:
                j = runner.jpeg
                if j and j is not last:
                    last = j
                    yield b"--f\r\nContent-Type: image/jpeg\r\n\r\n" + j + b"\r\n"
                time.sleep(0.05)
        return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=f")

    return app


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--camera", required=True, help="phone video URL, webcam index or video file")
    ap.add_argument("--port", type=int, default=5056)
    ap.add_argument("--back", default="left", choices=["left", "right"],
                    help="which way a back swipe moves in the camera picture")
    ap.add_argument("--record", help="also save the raw video to this file (mp4)")
    ap.add_argument("--only", help="only these prompt kinds, e.g. double_tap or hold,double_tap")
    ap.add_argument("--mat", action="store_true", help="look for the dark input mat (and cards on it)")
    ap.add_argument("--work-width", type=int, default=480, help="frame width used for hand finding")
    args = ap.parse_args(argv)
    session = Session(back_is=args.back, only=args.only.split(",") if args.only else None)
    runner = Runner(args.camera, session, record=args.record, work_width=args.work_width,
                    use_mat=args.mat).start()
    app = create_app(runner, session)
    print(f"Touch test on port {args.port}: open http://<this computer>:{args.port}/ on the TV")
    app.run(host="0.0.0.0", port=args.port, threaded=True, debug=False)


if __name__ == "__main__":
    main()
