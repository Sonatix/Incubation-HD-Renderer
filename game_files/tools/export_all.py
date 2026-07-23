#!/usr/bin/env python3
"""export_all.py - decode EVERY VISN texture in the game to PNG + a hash manifest.

The content hash is md5 of the raw RGB565 bytes the game itself decodes and uploads to
Glide (we reproduce those exact bytes via Eng3d.dll). That hash is the key a Glide texture-
replacement wrapper will use at runtime to look up the HD replacement for each texture.

    python export_all.py [game_root] [-o export_dir]

Run under 32-bit Python (uses Eng3d.dll). Reads game files read-only; never writes to them.
"""
import os, sys, json, glob, struct, hashlib, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import incu_lib as L

SKIP_DIRS = ("gamedata", "backup", "export", "out_test")

def find_containers(root):
    # Windows glob is case-insensitive, so a single pattern already matches
    # texture.lib / Texture.lib / TEXTURE.LIB. Dedupe by canonical path so the
    # same physical file isn't processed multiple times.
    seen, libs = set(), []
    for p in glob.glob(os.path.join(root, "**", "texture.lib"), recursive=True):
        key = os.path.normcase(os.path.abspath(p))
        rel = os.path.relpath(p, root).replace("\\", "/").lower()
        if key in seen or any(rel.startswith(d + "/") for d in SKIP_DIRS):
            continue
        seen.add(key); libs.append(p)
    return sorted(libs)

def records_from_dir(lib):
    """Prefer the .dir TOC; fall back to scanning VISN magic if absent."""
    base = os.path.splitext(lib)[0]
    for ext in (".dir", ".DIR"):
        if os.path.exists(base + ext):
            return [(e.name, e.off, e.size) for e in L.parse_dir(base + ext)]
    data = open(lib, "rb").read()               # fallback: carve by magic
    offs = []
    i = data.find(b"VISN")
    while i >= 0:
        offs.append(i); i = data.find(b"VISN", i + 4)
    recs = []
    for k, o in enumerate(offs):
        end = offs[k + 1] if k + 1 < len(offs) else len(data)
        recs.append(("visn_%04d" % k, o, end - o))
    return recs

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", nargs="?", default=L.GAME_DIR)
    ap.add_argument("-o", "--out", default="export")
    ap.add_argument("--no-png", action="store_true", help="hash/manifest only, skip PNGs")
    args = ap.parse_args()

    dec = L.Decoder()
    containers = find_containers(args.root)
    print("found %d VISN container(s) under %s" % (len(containers), args.root))
    manifest, by_hash = [], {}
    total = ok = fail = 0
    for lib in containers:
        rel = os.path.relpath(lib, args.root).replace("\\", "/")
        data = open(lib, "rb").read()
        recs = records_from_dir(lib)
        if not recs or data[recs[0][1]:recs[0][1] + 4] != b"VISN":
            continue  # not a VISN container (e.g. Libs/*.LIB)
        outsub = os.path.join(args.out, os.path.dirname(rel))
        os.makedirs(outsub, exist_ok=True)
        for idx, (name, off, size) in enumerate(recs):
            rec = data[off:off + size]
            if rec[:4] != b"VISN":
                continue
            total += 1
            try:
                w, h, raw = dec.decode_record(rec)
            except Exception as ex:
                fail += 1; print("  ! %s/%s: %s" % (rel, name, ex)); continue
            digest = hashlib.md5(raw).hexdigest()
            png_rel = None
            if not args.no_png:
                from PIL import Image
                png_rel = os.path.join(os.path.dirname(rel), "%s.png" % name)
                Image.frombytes("RGB", (w, h), L.rgb565_to_rgb_bytes(raw)).save(
                    os.path.join(args.out, png_rel))
            manifest.append(dict(container=rel, name=name, index=idx,
                                 w=w, h=h, hash=digest,
                                 png=png_rel.replace("\\", "/") if png_rel else None))
            by_hash.setdefault(digest, []).append("%s/%s" % (rel, name))
            ok += 1
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    uniq = len(by_hash)
    dups = sum(1 for v in by_hash.values() if len(v) > 1)
    print("\ndecoded %d ok, %d failed, of %d records" % (ok, fail, total))
    print("unique textures by content hash: %d  (%d hashes shared by >1 record)" % (uniq, dups))
    print("manifest -> %s" % os.path.join(args.out, "manifest.json"))

if __name__ == "__main__":
    main()
