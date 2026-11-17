"""Pieces found by colour, pixel by pixel, learned from Harrison's own pieces.

Two lessons from the first try (cutting out every patch that differs from the empty board,
then naming each patch): white plastic on a pale land differs from the board only faintly,
so patches came out as fragments; and pieces that touch came out as one patch.

So here every pixel is named first, from its colour in the photo next to the colour of the
empty board at that spot (both after evening out the light, land by land):
board (including shadows), white plastic, Dahan wood, blight, presence. The pixel model is
trained on the training photos, which hold one kind of piece each: the pixels that differ
from the empty board in a "dahan" photo are Dahan wood, and so on.

Then pieces are counted per land from the named pixels: wooden discs and presence by area
(the median area of one, from training), white plastic by blob, each blob named explorer,
town or city by its shape and size (a second small model), and counted by area too when
two touch.

    python -m spirit_island.piece_pixels train
    python -m spirit_island.piece_pixels test <truth folder>
"""

from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import cv2
import numpy as np

from .piece_model import DEV, KINDS, TRAIN, Board

MODEL = DEV / "piece_pixels.pkl"
MIXED = DEV / "train_mixed"   # layouts of mixed pieces, each with truth.json (land -> counts)
COLOURS = ["board", "white", "dahan", "blight", "presence"]
OF_KIND = {"explorers": 1, "towns": 1, "cities": 1, "dahan": 2, "blight": 3, "presence": 4}
WHITE = ["explorers", "towns", "cities"]
CUT = 40
WHITE_CLOSE = 5
HOG = cv2.HOGDescriptor((CUT, CUT), (16, 16), (8, 8), (8, 8), 9)


def lab_pair(b: Board, now: np.ndarray):
    """Lab of the empty board and of the photo, the photo's light evened out land by land."""
    ref = cv2.cvtColor(cv2.GaussianBlur(b.empty, (5, 5), 0), cv2.COLOR_BGR2LAB).astype(np.float32)
    new = cv2.cvtColor(cv2.GaussianBlur(now, (5, 5), 0), cv2.COLOR_BGR2LAB).astype(np.float32)
    sel = b.region > 0
    for z in np.unique(b.labels):
        m = (b.labels == z) & sel
        if z == 0 or m.sum() < 400:
            continue
        for c in range(3):
            new[..., c][m] -= float(np.median(new[..., c][m] - ref[..., c][m]))
    return ref, new


def pixel_features(ref, new, sel):
    """Each pixel's colour, the empty board's colour there, and the same over its
    surroundings (a disc-sized neighbourhood), so a pixel is named in context: the lit top
    of a Dahan on sand is pale like white plastic, but sits in a smooth tan patch."""
    key = (id(ref), id(new))
    if _CTX.get("key") != key:
        d = new - ref
        L = new[..., 0]
        m = cv2.GaussianBlur(L, (0, 0), 2)
        _CTX.update(key=key,
                    near=cv2.GaussianBlur(new, (0, 0), 6),
                    dnear=cv2.GaussianBlur(d, (0, 0), 6),
                    dfar=cv2.GaussianBlur(d, (0, 0), 12),
                    smooth=np.sqrt(cv2.GaussianBlur((L - m) ** 2, (0, 0), 3)),
                    smooth_ref=np.sqrt(cv2.GaussianBlur((ref[..., 0] - cv2.GaussianBlur(ref[..., 0], (0, 0), 2)) ** 2, (0, 0), 3)))
    c = _CTX
    r, n = ref[sel], new[sel]
    d = n - r
    chroma = np.hypot(n[:, 1] - 128, n[:, 2] - 128)[:, None]
    return np.hstack([n, r, d, chroma, np.linalg.norm(d, axis=1, keepdims=True),
                      c["near"][sel], c["dnear"][sel], c["dfar"][sel],
                      c["smooth"][sel][:, None], c["smooth_ref"][sel][:, None]]).astype(np.float32)


_CTX: dict = {}


def changed(ref, new, region):
    d = new - ref
    d[..., 0] *= 0.5
    m = cv2.GaussianBlur(np.sqrt((d ** 2).sum(-1)), (0, 0), 2)
    return (m > 9) & (region > 0)


def is_shadow(ref, new):
    """Darker than the empty board but the same colour: a shadow, not a piece."""
    d = new - ref
    # (Blight is dark too, but much darker than any shadow.)
    return (d[..., 0] < -5) & (d[..., 0] > -30) & (np.abs(d[..., 1]) < 4.5) & (np.abs(d[..., 2]) < 4.5)


def white_features(b: Board, white: np.ndarray, gray: np.ndarray, bbox) -> np.ndarray:
    x, y, w, h = bbox
    s = max(w, h)
    cx, cy = x + w // 2, y + h // 2
    half = int(0.7 * s) + 3
    x0, y0 = max(0, cx - half), max(0, cy - half)
    x1, y1 = min(gray.shape[1], cx + half), min(gray.shape[0], cy + half)
    g = cv2.resize(gray[y0:y1, x0:x1], (CUT, CUT), interpolation=cv2.INTER_AREA)
    m = cv2.resize(white[y0:y1, x0:x1].astype(np.uint8) * 255, (CUT, CUT), interpolation=cv2.INTER_AREA)
    area = white.sum() / b.area * 1000
    pts = cv2.findNonZero(white.astype(np.uint8))
    rect = cv2.minAreaRect(pts)
    hull = cv2.contourArea(cv2.convexHull(pts))
    return np.concatenate([[area, max(rect[1]) / max(1.0, min(rect[1])), white.sum() / max(1.0, hull),
                            w / b.area ** 0.5 * 100, h / b.area ** 0.5 * 100],
                           HOG.compute(g).ravel(), HOG.compute(m).ravel() * 0.5]).astype(np.float32)


def white_blobs(b: Board, white: np.ndarray):
    m = cv2.morphologyEx(white.astype(np.uint8), cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (WHITE_CLOSE, WHITE_CLOSE)))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
    return [(lab == i, tuple(int(v) for v in st[i][:4])) for i in range(1, n) if st[i][4] / b.area > 0.0006]


def inner(b: Board) -> np.ndarray:
    """The board without a band along its outline: the photo and the empty board never line
    up exactly at the edge, and the board's pale rim then looks like white plastic."""
    if not hasattr(b, "_inner"):
        b._inner = cv2.erode(b.region, np.ones((17, 17), np.uint8))
    return b._inner


def discs(mask: np.ndarray, r: float) -> int:
    """How many round discs of radius r make up this patch: touching discs still each have
    a centre far from the patch's edge, so count those centres."""
    dt = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 5)
    peak = (dt >= cv2.dilate(dt, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (int(r) | 1, int(r) | 1)))) & (dt > 0.55 * r)
    peak = cv2.dilate(peak.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (int(0.8 * r) | 1,) * 2))
    return max(1, cv2.connectedComponents(peak)[0] - 1)


def name_pixels(model, b, now):
    ref, new = lab_pair(b, now)
    fg = changed(ref, new, inner(b)) & ~is_shadow(ref, new)
    out = np.zeros(fg.shape, np.uint8)
    if fg.any():
        out[fg] = model.predict(pixel_features(ref, new, fg))
    # Tidy: a piece is a solid patch, not scattered pixels.
    tidy = np.zeros_like(out)
    for c in range(1, len(COLOURS)):
        m = cv2.morphologyEx((out == c).astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        tidy[m > 0] = c
    return tidy


def train():
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.model_selection import StratifiedKFold, cross_val_score
    rng = np.random.default_rng(0)
    b = Board()
    X, y = [], []
    photos = [(k, f) for k in KINDS for f in sorted((TRAIN / k).glob("*.jpg"))]
    aligned = {}
    for kind, f in photos + [("empty", TRAIN / "empty.jpg")]:
        now = b.align(cv2.imread(str(f)))
        if now is None:
            print("could not line up", f)
            continue
        aligned[f] = (kind, now)
        ref, new = lab_pair(b, now)
        fg = changed(ref, new, inner(b))
        shadow = is_shadow(ref, new)
        piece = fg & ~shadow
        near = cv2.dilate(piece.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool)
        board = (((~fg) & ~near) | shadow) & (b.region > 0)
        for sel, label, n in ((piece, OF_KIND.get(kind, 0), 6000), (board, 0, 3000)):
            if kind == "empty" and sel is piece:
                continue
            idx = np.flatnonzero(sel)
            if len(idx) == 0:
                continue
            pick = np.zeros(sel.size, bool)
            pick[rng.choice(idx, min(n, len(idx)), replace=False)] = True
            X.append(pixel_features(ref, new, pick.reshape(sel.shape)))
            y.append(np.full(int(pick.sum()), label))
    first = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.1).fit(np.vstack(X), np.concatenate(y))

    # Mixed layouts: in a land holding white pieces and one other colour, the pixels the
    # first model doesn't call white are that colour (this is where Dahan on sand come from).
    mixed = []
    for folder in sorted(MIXED.glob("*/truth.json")):
        lands = json.loads(folder.read_text())["lands"]
        for f in sorted(folder.parent.glob("*.jpg")):
            now = b.align(cv2.imread(str(f)))
            if now is None:
                continue
            mixed.append((f, lands, now))
            ref, new = lab_pair(b, now)
            fg = changed(ref, new, inner(b)) & ~is_shadow(ref, new)
            guess = np.zeros(fg.shape, np.uint8)
            if fg.any():
                guess[fg] = first.predict(pixel_features(ref, new, fg))
            for n, counts in lands.items():
                colours = {OF_KIND[k] for k, v in counts.items() if v}
                other = colours - {1}
                if len(other) > 1:
                    continue
                here = fg & (b.labels == b.names.index(n) + 1)
                parts = [(here & (guess == 1), 1)] if 1 in colours else []
                if other:
                    parts.append((here & (guess != 1), other.pop()))
                for sel, label in parts:
                    idx = np.flatnonzero(sel)
                    if len(idx) < 20:
                        continue
                    pick = np.zeros(sel.size, bool)
                    pick[rng.choice(idx, min(1500, len(idx)), replace=False)] = True
                    X.append(pixel_features(ref, new, pick.reshape(sel.shape)))
                    y.append(np.full(int(pick.sum()), label))
    X, y = np.vstack(X), np.concatenate(y)
    print("pixels:", {c: int((y == i).sum()) for i, c in enumerate(COLOURS)})
    pix = HistGradientBoostingClassifier(max_iter=250, learning_rate=0.1).fit(X, y)

    # Second model: explorer / town / city, from white blobs in the white-piece photos.
    WX, Wy, sizes = [], [], {k: [] for k in KINDS}
    CX, Cy = [], []  # how many of each a white blob holds (bunched pieces make one blob)
    for f, (kind, now) in aligned.items():
        if kind == "empty":
            continue
        names = name_pixels(pix, b, now)
        if kind in WHITE:
            gray = cv2.cvtColor(now, cv2.COLOR_BGR2GRAY)
            found = white_blobs(b, names == 1)
            if not found:
                continue
            one = float(np.median([m.sum() for m, _ in found]))
            for m, bbox in found:
                c = [0, 0, 0]
                c[WHITE.index(kind)] = max(1, int(round(m.sum() / one)))
                CX.append(white_features(b, m, gray, bbox))
                Cy.append(c)
                if 0.6 * one < m.sum() < 1.5 * one:
                    WX.append(white_features(b, m, gray, bbox))
                    Wy.append(WHITE.index(kind))
                    sizes[kind].append(m.sum() / b.area)
        else:
            m = cv2.morphologyEx((names == OF_KIND[kind]).astype(np.uint8), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
            n, lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
            areas = [st[i][4] for i in range(1, n) if st[i][4] / b.area > 0.0006]
            if areas:
                one = float(np.median(areas))
                sizes[kind] += [a / b.area for a in areas if 0.6 * one < a < 1.5 * one]
    sizes = {k: float(np.median(v)) for k, v in sizes.items()}
    # Mixed layouts: a land with a single white blob shows what a bunch looks like.
    model = PixelPieces.__new__(PixelPieces)
    model.pix, model.sizes, model.boards = pix, sizes, {}
    for f, lands, now in mixed:
        names = name_pixels(pix, b, now)
        gray = cv2.cvtColor(now, cv2.COLOR_BGR2GRAY)
        by_land = {}
        for m, bbox in model.white_pieces(b, names):
            by_land.setdefault(model.land_of(b, m), []).append((m, bbox))
        for n, counts in lands.items():
            blobs = by_land.get(n, [])
            want = [counts.get(k, 0) for k in WHITE]
            if len(blobs) == 1 and sum(want):
                m, bbox = blobs[0]
                for _ in range(3):  # count these real bunches more
                    CX.append(white_features(b, m, gray, bbox))
                    Cy.append(want)
    WX, Wy = np.array(WX), np.array(Wy)
    print("white examples:", {k: int((Wy == i).sum()) for i, k in enumerate(WHITE)},
          "sizes", {k: round(v * 1000, 2) for k, v in sizes.items()})
    wclf = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.08)
    cv = cross_val_score(wclf, WX, Wy, cv=StratifiedKFold(5, shuffle=True, random_state=0))
    print("white shape cross-validated:", round(float(cv.mean()), 3))
    wclf.fit(WX, Wy)
    from sklearn.ensemble import HistGradientBoostingRegressor
    CX, Cy = np.array(CX), np.array(Cy, float)
    print("white bunches:", len(CX))
    count = [HistGradientBoostingRegressor(max_iter=200, learning_rate=0.08).fit(CX, Cy[:, i]) for i in range(3)]
    MODEL.write_bytes(pickle.dumps({"pix": pix, "white": wclf, "count": count, "sizes": sizes}))
    print("saved", MODEL)


class PixelPieces:
    def __init__(self, path: Path = MODEL):
        d = pickle.loads(Path(path).read_bytes())
        self.pix, self.white, self.sizes = d["pix"], d["white"], d["sizes"]
        # The bunch counter (d["count"]) fitted its own training layouts but did worse on
        # unseen ones (layout B), so pieces are read one per white blob.
        self.count = None
        self.boards = {}

    def land_of(self, b, mask):
        vals = b.labels[mask]
        vals = vals[vals > 0]
        if not len(vals):
            return None
        name = b.names[int(np.bincount(vals).argmax()) - 1]
        return None if name == "ocean" else name

    def white_pieces(self, b, names):
        """White blobs that are plastic pieces (not a disc's shine, not the board's edge)."""
        # The shine on top of a wooden disc can look like white plastic: white right on a
        # disc belongs to the disc.
        wood = np.isin(names, (OF_KIND["dahan"], OF_KIND["presence"])).astype(np.uint8)
        r = int(np.sqrt(self.sizes["dahan"] * b.area / np.pi))
        wood = cv2.dilate(wood, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (int(1.4 * r) | 1,) * 2)) > 0
        out = []
        for m, bbox in white_blobs(b, names == 1):
            if (m & wood).sum() > 0.3 * m.sum():
                continue
            pts = cv2.findNonZero(m.astype(np.uint8))
            (_, _), (w, h), _ = cv2.minAreaRect(pts)
            if max(w, h) > 3.2 * max(1.0, min(w, h)):
                continue  # a thin sliver: the board's edge, not a piece
            out.append((m, bbox))
        return out

    def read_aligned(self, b, now, letter="C"):
        names = name_pixels(self.pix, b, now)
        out = {f"{letter}{n}": {k: 0 for k in KINDS} for n in range(1, 9)}
        found = []
        for kind in ("dahan", "blight", "presence"):
            m = cv2.morphologyEx((names == OF_KIND[kind]).astype(np.uint8), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
            n, lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
            r = float(np.sqrt(self.sizes[kind] * b.area / np.pi))  # one disc's radius
            for i in range(1, n):
                k = st[i][4] / b.area / self.sizes[kind]
                if k < 0.45:
                    continue
                land = self.land_of(b, lab == i)
                if land:
                    c = discs(lab == i, r) if k > 1.3 else 1
                    out[f"{letter}{land}"][kind] += c
                    found.append((kind, c, tuple(int(v) for v in st[i][:4])))
        gray = cv2.cvtColor(now, cv2.COLOR_BGR2GRAY)
        for m, bbox in self.white_pieces(b, names):
            land = self.land_of(b, m)
            if not land:
                continue
            f = white_features(b, m, gray, bbox)
            c = None
            if self.count is not None:
                c = [max(0, int(round(float(r.predict([f])[0])))) for r in self.count]
                if sum(c) < 2:
                    c = None  # one piece: the one-piece model names it better
            if c is not None:
                # Several pieces bunched together into one blob.
                if not sum(c):
                    if m.sum() / b.area < 0.3 * self.sizes["explorers"]:
                        continue
                    c[int(self.white.predict([f])[0])] = 1
            else:
                kind = WHITE[int(self.white.predict([f])[0])]
                k = m.sum() / b.area / self.sizes[kind]
                if k < 0.22:
                    continue
                c = [0, 0, 0]
                c[WHITE.index(kind)] = max(1, min(3, int(round(k))))
            for kind, n in zip(WHITE, c):
                if n:
                    out[f"{letter}{land}"][kind] += n
                    found.append((kind, n, bbox))
        return out, names, found

    def read(self, image, letter="C"):
        if letter not in self.boards:
            self.boards[letter] = Board(letter)
        b = self.boards[letter]
        now = b.align(image)
        if now is None:
            return None
        return self.read_aligned(b, now, letter)[0]


def test(folder):
    from .eval_detect import score
    m = PixelPieces()
    return score(Path(folder), reader=lambda image, letter: m.read(image, letter))


if __name__ == "__main__":
    train() if sys.argv[1] == "train" else test(sys.argv[2])
