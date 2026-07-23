#!/usr/bin/env python3
"""make_pack.py - build a hd_pack/ folder of replacement textures keyed by the FNV-1a
hash the glide2x proxy computes at runtime over each uploaded 256x256 RGB565 texture.

Modes:
  marker   : every texture -> one solid bright colour (proves in-flight substitution)
  enhance  : every texture -> upscaled-then-downscaled 256 (denoise/sharpen, still 256)
  fromdir  : take replacements from a folder of PNGs named <container>__<name>.png

Files are written as hd_pack/<fnv8hex>.bin (raw 256x256 RGB565, 131072 bytes).
Run under 32-bit Python (uses Eng3d.dll to decode).
"""
import os, sys, glob, struct, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import incu_lib as L

def fnv1a(b):
    h = 2166136261
    for x in b:
        h = ((h ^ x) * 16777619) & 0xFFFFFFFF
    return h

def rgb888_to_565_bytes(img):
    """PIL RGB image -> raw RGB565 little-endian bytes (vectorised)."""
    import numpy as np
    a = np.asarray(img.convert("RGB"), dtype=np.uint16).reshape(-1, 3)
    v = ((a[:, 0] >> 3) << 11) | ((a[:, 1] >> 2) << 5) | (a[:, 2] >> 3)
    return v.astype("<u2").tobytes()

def iter_records():
    """yield (container_rel, name, raw565) for every VISN record, de-duped by raw bytes."""
    dec = L.Decoder()
    root = L.GAME_DIR
    seen = set()
    libs = []
    for p in glob.glob(os.path.join(root, "**", "texture.lib"), recursive=True):
        key = os.path.normcase(os.path.abspath(p))
        rel = os.path.relpath(p, root).replace("\\", "/").lower()
        if key in seen or any(rel.startswith(d + "/") for d in ("gamedata","backup","export","out_test")):
            continue
        seen.add(key); libs.append(p)
    seen_raw = set()
    for lib in sorted(libs):
        try:
            ents = L.load_toc(lib)
        except Exception:
            continue
        data = open(lib, "rb").read()
        rel = os.path.relpath(lib, root).replace("\\", "/")
        for e in ents:
            rec = data[e.off:e.off+e.size]
            if rec[:4] != b"VISN":
                continue
            try:
                w, h, raw = dec.decode_record(rec)
            except Exception:
                continue
            if w != 256 or h != 256:
                continue
            k = hash(raw)
            if k in seen_raw:
                continue
            seen_raw.add(k)
            yield rel, e.name, raw

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["marker","enhance"], default="marker")
    ap.add_argument("--color", default="F81F", help="marker colour, RGB565 hex (default magenta)")
    ap.add_argument("-o", "--out", default="hd_pack")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    marker = None
    if args.mode == "marker":
        v = int(args.color, 16)
        marker = struct.pack("<H", v) * (256*256)

    n = 0
    for rel, name, raw in iter_records():
        fnv = fnv1a(raw)
        if args.mode == "marker":
            payload = marker
        else:  # enhance: upscale x4 (lanczos) then back to 256 -> cleaner edges
            from PIL import Image
            img = Image.frombytes("RGB", (256,256), L.rgb565_to_rgb_bytes(raw))
            big = img.resize((1024,1024), Image.LANCZOS)
            small = big.resize((256,256), Image.LANCZOS)
            payload = rgb888_to_565_bytes(small)
        open(os.path.join(args.out, "%08x.bin" % fnv), "wb").write(payload)
        n += 1
    print("wrote %d replacement textures to %s (mode=%s)" % (n, args.out, args.mode))

if __name__ == "__main__":
    main()
