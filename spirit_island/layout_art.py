"""Pictures of two island boards fitted together, for the island setup step.

Two boards join along their inland edges with the oceans on opposite sides: the second
board is turned half a turn and slid against the first until their outlines touch.
"""

import os

import numpy as np
from PIL import Image


def _fit(a, b, scale=8):
    """Smallest sideways offset (and the vertical nudge) where b's outline meets a's."""
    am = np.array(a.resize((a.width // scale, a.height // scale)))[:, :, 3] > 128
    bm = np.array(b.resize((b.width // scale, b.height // scale)))[:, :, 3] > 128
    h, w = am.shape
    best = None
    for dy in range(-h // 6, h // 6 + 1):
        bb = np.roll(bm, dy, axis=0)
        for off in range(w // 3, w):
            if (am[:, off:] & bb[:, : w - off]).sum() <= 30 / scale:
                if best is None or off < best[0]:
                    best = (off, dy)
                break
    return best[0] * scale, best[1] * scale


def two_board_layout(boards_dir, first, second, out_path, width=1600):
    if os.path.exists(out_path):
        return out_path
    a = Image.open(os.path.join(boards_dir, f"{first}.png")).convert("RGBA")
    b = Image.open(os.path.join(boards_dir, f"{second}.png")).convert("RGBA").rotate(180)
    off, dy = _fit(a, b)
    top = max(0, -dy)
    out = Image.new("RGBA", (off + b.width, max(a.height, b.height) + abs(dy)), (0, 0, 0, 0))
    out.alpha_composite(a, (0, top))
    out.alpha_composite(b, (off, top + dy))
    out = out.convert("RGB")
    out.thumbnail((width, width))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    out.save(out_path, quality=85)
    return out_path
