#!/usr/bin/env python3
"""Build a labelled contact sheet from a folder of PNGs, so you can pick a texture by eye.

    python contact_sheet.py <png_dir> -o sheet.png [--cell 128] [--cols 8]
"""
import argparse
import os
import sys


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dir")
    ap.add_argument("-o", "--out", default="contact_sheet.png")
    ap.add_argument("--cell", type=int, default=128)
    ap.add_argument("--cols", type=int, default=8)
    args = ap.parse_args()

    from PIL import Image, ImageDraw

    names = sorted(f for f in os.listdir(args.dir) if f.lower().endswith(".png"))
    if not names:
        sys.exit("no PNGs in " + args.dir)

    cell, cols, pad, label = args.cell, args.cols, 6, 14
    rows = (len(names) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (cell + pad) + pad,
                              rows * (cell + pad + label) + pad), (20, 20, 24))
    draw = ImageDraw.Draw(sheet)

    for i, name in enumerate(names):
        r, c = divmod(i, cols)
        x = pad + c * (cell + pad)
        y = pad + r * (cell + pad + label)
        th = Image.open(os.path.join(args.dir, name)).convert("RGB")
        th.thumbnail((cell, cell))
        sheet.paste(th, (x + (cell - th.width) // 2, y + (cell - th.height) // 2))
        draw.text((x, y + cell + 2), os.path.splitext(name)[0][:18], fill=(210, 210, 210))

    sheet.save(args.out)
    print("contact sheet: %d textures -> %s" % (len(names), args.out))


if __name__ == "__main__":
    main()
