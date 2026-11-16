"""Printable ArUco markers for measuring scale (and, in later stages, rectifying the table).

    python -m vision.markers --out markers.svg --size-mm 40

Writes an SVG laid out in real millimetres on an A4/Letter-safe page. Print it at
100% scale ("actual size", not "fit to page"), then measure one printed marker's
black square with a ruler and pass that number as --marker-mm to the probe.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2

from vision.quality import ARUCO_DICT

PAGE_W_MM, PAGE_H_MM = 200, 270  # fits inside both A4 and US Letter margins


def marker_bits(marker_id: int):
    """The marker as a small 0/255 grid including its black border (6x6 for 4x4 markers)."""
    dictionary = cv2.aruco.getPredefinedDictionary(ARUCO_DICT)
    cells = dictionary.markerSize + 2
    return cv2.aruco.generateImageMarker(dictionary, marker_id, cells)


def markers_svg(ids=(0, 1, 2, 3), size_mm: float = 40.0) -> str:
    gap = max(15.0, size_mm * 0.5)  # quiet white zone between markers
    cols = max(1, int((PAGE_W_MM + gap) // (size_mm + gap)))
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{PAGE_W_MM}mm" height="{PAGE_H_MM}mm" '
        f'viewBox="0 0 {PAGE_W_MM} {PAGE_H_MM}">',
        f'<rect width="{PAGE_W_MM}" height="{PAGE_H_MM}" fill="white"/>',
    ]
    for n, marker_id in enumerate(ids):
        row, col = divmod(n, cols)
        x0 = col * (size_mm + gap) + gap / 2
        y0 = row * (size_mm + gap + 8) + gap / 2
        if y0 + size_mm > PAGE_H_MM:
            raise ValueError("Too many markers for one page at this size")
        bits = marker_bits(marker_id)
        cell = size_mm / bits.shape[0]
        for r in range(bits.shape[0]):
            for c in range(bits.shape[1]):
                if bits[r, c] == 0:
                    parts.append(
                        f'<rect x="{x0 + c * cell:.3f}" y="{y0 + r * cell:.3f}" '
                        f'width="{cell + 0.01:.3f}" height="{cell + 0.01:.3f}" fill="black"/>'
                    )
        parts.append(
            f'<text x="{x0:.1f}" y="{y0 + size_mm + 5:.1f}" font-size="3.5" font-family="sans-serif">'
            f"id {marker_id}, {size_mm:g} mm</text>"
        )
    parts.append("</svg>")
    return "\n".join(parts)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", default="markers.svg")
    p.add_argument("--size-mm", type=float, default=40.0, help="side of the black square, in mm")
    p.add_argument("--ids", default="0,1,2,3", help="comma-separated marker ids (0-49)")
    args = p.parse_args(argv)
    ids = [int(i) for i in args.ids.split(",")]
    Path(args.out).write_text(markers_svg(ids, args.size_mm))
    print(f"Wrote {args.out}. Print at 100% scale, then measure a marker and pass --marker-mm.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
