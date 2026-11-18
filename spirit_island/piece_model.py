"""A recogniser for Harrison's own pieces, trained on photos of them on the board.

Training photos hold one kind of piece each (recordings/detect_dev/train/<kind>/*.jpg),
plus train/empty.jpg. Each photo is lined up to the board's empty reference; every patch
that differs from the empty board is cut out as an example of that kind.

Each example is described by:
- its colours, in Lab, relative to the board right around it (so the light and the
  land's own colour matter less): a small histogram of the piece's pixels;
- its shape: HOG on a straightened, fixed-size cut-out (HOG = edge directions, which see
  a town's roof, a city's towers, a disc's round rim);
- its size and how solid it is.

A classifier (gradient boosting) learns to tell the six kinds apart. On a new photo,
patches are found the same way; a patch too big for one piece of its kind is counted as
several (by the median size of that kind in training).

    python -m spirit_island.piece_model train      # train and save the model
    python -m spirit_island.piece_model test <truth folder>
"""

from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import cv2
import numpy as np

from vision.changes import change_map
from vision.register import register, warp_to_reference

from .perception import lands as land_map

DEV = Path(r"C:/Users/harri/Desktop/home_automation_capture/spirit_island/recordings/detect_dev")
TRAIN = DEV / "train"
BOARDS = DEV / "boards"
MODEL = DEV / "piece_model.pkl"
KINDS = ["explorers", "towns", "cities", "dahan", "blight", "presence"]
WORK = 1600
CUT = 48
HOG = cv2.HOGDescriptor((CUT, CUT), (16, 16), (8, 8), (8, 8), 9)


class Board:
    def __init__(self, letter: str = "C"):
        d = BOARDS / letter
        self.reference = cv2.imread(str(d / "reference.jpg"))
        self.mask = cv2.imread(str(d / "board_mask.png"), cv2.IMREAD_GRAYSCALE)
        labels, self.names = land_map.load(d)
        self.k = WORK / max(self.reference.shape[:2])
        sm = lambda m, i: cv2.resize(m, None, fx=self.k, fy=self.k, interpolation=i)  # noqa: E731
        self.labels = sm(labels, cv2.INTER_NEAREST)
        self.region = cv2.erode(sm(self.mask, cv2.INTER_NEAREST), np.ones((7, 7), np.uint8))
        self.empty = sm(self.reference, cv2.INTER_AREA)
        self.area = max(1, int((self.region > 0).sum()))

    def align(self, image):
        reg = register(self.reference, image, reference_mask=self.mask)
        if reg is None or not reg.ok:
            return None
        al = warp_to_reference(image, reg, self.reference.shape)
        return cv2.resize(al, None, fx=self.k, fy=self.k, interpolation=cv2.INTER_AREA)


def blobs(b: Board, now: np.ndarray, base: np.ndarray | None = None):
    """Patches where `now` differs from the empty board (or `base`): [(mask, bbox)]."""
    base = b.empty if base is None else base
    diff = change_map(base, now, b.region, zones=b.labels)
    inside = diff[b.region > 0]
    med = float(np.median(inside))
    mad = float(np.median(np.abs(inside - med))) + 1e-6
    m = ((diff > max(15.0, med + 8 * mad)) & (b.region > 0)).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    out = []
    for i in range(1, n):
        share = stats[i][4] / b.area
        if share < 0.0009 or share > 0.03:
            continue
        mask = lab == i
        if cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 3).max() < 0.009 * np.sqrt(b.area):
            continue
        out.append((mask, tuple(int(v) for v in stats[i][:4])))
    return out


def features(b: Board, now: np.ndarray, mask: np.ndarray, bbox) -> np.ndarray:
    x, y, w, h = bbox
    pad = int(0.25 * max(w, h)) + 4
    x0, y0 = max(0, x - pad), max(0, y - pad)
    x1, y1 = min(now.shape[1], x + w + pad), min(now.shape[0], y + h + pad)
    lab = cv2.cvtColor(now, cv2.COLOR_BGR2LAB).astype(np.float32)
    ring = cv2.dilate(mask.astype(np.uint8), np.ones((15, 15), np.uint8)) > 0
    ring &= ~cv2.dilate(mask.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    ring &= b.region > 0
    around = lab[ring].mean(0) if ring.sum() > 10 else lab[mask].mean(0)
    px = lab[mask] - around  # colours relative to the land right around the piece
    hist = []
    for c, (lo, hi) in enumerate(((-80, 120), (-40, 40), (-40, 50))):
        hgram, _ = np.histogram(px[:, c], bins=8, range=(lo, hi))
        hist.append(hgram / max(1, len(px)))
    absolute = lab[mask]
    hsv = cv2.cvtColor(now[mask].reshape(-1, 1, 3), cv2.COLOR_BGR2HSV).reshape(-1, 3).astype(np.float32)
    stats = [absolute[:, 0].mean(), absolute[:, 1].mean(), absolute[:, 2].mean(), absolute[:, 0].std(),
             hsv[:, 1].mean(), (hsv[:, 1] > 110).mean(), ((hsv[:, 0] > 92) & (hsv[:, 0] < 128) & (hsv[:, 1] > 100)).mean(),
             ((hsv[:, 1] < 70) & (hsv[:, 2] > 120)).mean(), (hsv[:, 2] < 110).mean()]
    crop = now[y0:y1, x0:x1]
    g = cv2.resize(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), (CUT, CUT), interpolation=cv2.INTER_AREA)
    hog = HOG.compute(g).ravel()
    area = mask.sum() / b.area
    thick = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 3).max() / np.sqrt(b.area)
    rect = cv2.minAreaRect(cv2.findNonZero(mask.astype(np.uint8)))
    elong = max(rect[1]) / max(1.0, min(rect[1]))
    fill = mask.sum() / max(1.0, rect[1][0] * rect[1][1])
    return np.concatenate([np.concatenate(hist), stats, [area * 1000, thick * 100, elong, fill], hog]).astype(np.float32)


def collect(b: Board):
    X, y, sizes = [], [], {k: [] for k in KINDS}
    for kind in KINDS:
        for f in sorted((TRAIN / kind).glob("*.jpg")):
            now = b.align(cv2.imread(str(f)))
            if now is None:
                print("could not line up", f)
                continue
            found = blobs(b, now)
            areas = [m.sum() for m, _ in found]
            if not areas:
                continue
            one = float(np.median(areas))
            for mask, bbox in found:
                if mask.sum() > 1.7 * one:
                    continue  # two pieces touching: not a clean example
                X.append(features(b, now, mask, bbox))
                y.append(KINDS.index(kind))
                sizes[kind].append(mask.sum() / b.area)
            print(f"{kind}/{f.name}: {len(found)} pieces")
    return np.array(X), np.array(y), {k: float(np.median(v)) if v else 0.0 for k, v in sizes.items()}


def train():
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.model_selection import GroupKFold, cross_val_score
    b = Board()
    X, y, sizes = collect(b)
    print("examples:", {k: int((y == i).sum()) for i, k in enumerate(KINDS)})
    clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.08)
    # Hold out whole photos at a time: pieces in one photo share the light.
    groups = np.arange(len(y)) // 6
    scores = cross_val_score(clf, X, y, cv=GroupKFold(5), groups=groups)
    print("cross-validated accuracy per piece:", round(float(scores.mean()), 3))
    clf.fit(X, y)
    MODEL.write_bytes(pickle.dumps({"clf": clf, "sizes": sizes}))
    print("saved", MODEL, "sizes", {k: round(v, 4) for k, v in sizes.items()})


class PieceModel:
    def __init__(self, path: Path = MODEL):
        d = pickle.loads(Path(path).read_bytes())
        self.clf, self.sizes = d["clf"], d["sizes"]
        self.board = None

    def read(self, image, letter: str = "C") -> dict | None:
        if self.board is None:
            self.board = Board(letter)
        b = self.board
        now = b.align(image)
        if now is None:
            return None
        out = {f"{letter}{n}": {k: 0 for k in KINDS} for n in range(1, 9)}
        for mask, bbox in blobs(b, now):
            vals = b.labels[mask]
            vals = vals[vals > 0]
            if not len(vals):
                continue
            land = b.names[int(np.bincount(vals).argmax()) - 1]
            if land == "ocean":
                continue
            p = self.clf.predict_proba([features(b, now, mask, bbox)])[0]
            kind = KINDS[int(p.argmax())]
            n = max(1, round((mask.sum() / b.area) / max(1e-6, self.sizes[kind])))
            out[f"{letter}{land}"][kind] += min(n, 3)
        return out


def test(folder: str):
    from .eval_detect import score
    m = PieceModel()
    return score(Path(folder), reader=lambda image, letter: m.read(image, letter))


if __name__ == "__main__":
    if sys.argv[1] == "train":
        train()
    else:
        test(sys.argv[2])
