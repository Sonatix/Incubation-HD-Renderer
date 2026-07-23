#!/usr/bin/env python3
"""hd_tool.py - HD texture pipeline for Incubation (extract -> your AI upscaler -> pack).

Workflow:
  1) python tools/hd_tool.py extract
        Decodes every unique in-game 256x256 texture to hd_work/source/<fnv8>.png
        (filename = the FNV-1a hash the glide2x wrapper looks up at runtime).
  2) Upscale hd_work/source/*.png with ANY tool you like (Real-ESRGAN, Upscayl,
        chaiNNer, ...). Put the results in hd_work/upscaled/ KEEPING THE FILENAMES
        (a suffix after the 8 hex chars is fine, e.g. 025f4383_out.png).
  3) python tools/hd_tool.py pack
        Converts hd_work/upscaled/* into hd_pack_hd/<fnv8>.rgba which the game
        (via our OpenGlide fork) picks up live. Launch via `Incubation HD.bat`.

Most people should just use the GUI launcher (`Incubation HD.bat`), which drives
all of these commands and the game itself.

  python tools/hd_tool.py status   -> shows extracted / upscaled / packed counts.

extract MUST run under 32-bit Python (decoding uses the game's Eng3d.dll);
pack/status run under any Python with Pillow.
"""
import os, sys, re, json, glob, struct, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SKIP_DIRS = ("gamedata", "backup", "export", "out_test", "hd_work")
WORK_DIR   = "hd_work"
SOURCE_DIR = os.path.join(WORK_DIR, "source")
UP_DIR     = os.path.join(WORK_DIR, "upscaled")
PACK_DIR   = "hd_pack_hd"
MANIFEST   = os.path.join(WORK_DIR, "manifest.json")
MAX_DIM    = 4096          # hd_inject.cpp rejects anything larger
IMG_EXTS   = (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tga", ".tif", ".tiff")

def fnv1a(b):
    h = 2166136261
    for x in b:
        h = ((h ^ x) * 16777619) & 0xFFFFFFFF
    return h

# ---------------------------------------------------------------- extract
def find_containers(root):
    seen, libs = set(), []
    for p in glob.glob(os.path.join(root, "**", "texture.lib"), recursive=True):
        key = os.path.normcase(os.path.abspath(p))
        rel = os.path.relpath(p, root).replace("\\", "/").lower()
        if key in seen or any(rel.startswith(d + "/") for d in SKIP_DIRS):
            continue
        seen.add(key); libs.append(p)
    return sorted(libs)

def cmd_extract(args):
    import incu_lib as L
    from PIL import Image
    dec = L.Decoder()
    root = L.GAME_DIR
    os.makedirs(SOURCE_DIR, exist_ok=True)

    manifest = {}          # fnv8 -> {"sources": [...]}
    n_records = n_other = 0
    for lib in find_containers(root):
        rel = os.path.relpath(lib, root).replace("\\", "/")
        try:
            ents = L.load_toc(lib)
        except FileNotFoundError:
            continue
        data = open(lib, "rb").read()
        for e in ents:
            rec = data[e.off:e.off + e.size]
            if rec[:4] != b"VISN":
                continue
            n_records += 1
            try:
                w, h, raw = dec.decode_record(rec)
            except Exception as ex:
                print("  ! %s/%s: %s" % (rel, e.name, ex)); continue
            if w != 256 or h != 256:
                n_other += 1   # the wrapper only intercepts 256x256 uploads
                continue
            key = "%08x" % fnv1a(raw)
            src = "%s/%s" % (rel, e.name)
            if key in manifest:
                manifest[key]["sources"].append(src)
                continue
            manifest[key] = {"w": w, "h": h, "sources": [src]}
            Image.frombytes("RGB", (w, h), L.rgb565_to_rgb_bytes(raw)).save(
                os.path.join(SOURCE_DIR, key + ".png"))
    with open(MANIFEST, "w") as f:
        json.dump(manifest, f, indent=1)
    os.makedirs(UP_DIR, exist_ok=True)
    print("scanned %d VISN records; %d unique 256x256 textures -> %s"
          % (n_records, len(manifest), SOURCE_DIR))
    if n_other:
        print("(%d records of other sizes skipped - the wrapper replaces only 256x256)"
              % n_other)
    print("next: upscale %s\\*.png into %s\\ then run: hd_tool.py pack"
          % (SOURCE_DIR, UP_DIR))

# ---------------------------------------------------------------- pack
def key_from_name(fname):
    m = re.match(r"([0-9a-fA-F]{8})", os.path.basename(fname))
    return m.group(1).lower() if m else None

def iter_images(folder):
    for f in sorted(os.listdir(folder)):
        if f.lower().endswith(IMG_EXTS):
            yield os.path.join(folder, f)

# ---------------------------------------------------------------- normal maps (bump)
NORMAL_STRENGTH = 2.0    # default height->normal gain

def _gen_normal_img(img, out_rgba, strength=NORMAL_STRENGTH):
    """PIL image -> tangent-space normal map from luminance, saved as
    <w,h> + RGBA (RGB = encoded normal). Returns True on success."""
    try:
        import numpy as np
    except ImportError:
        print("  ! numpy needed for normal maps - skipped"); return False
    a = np.asarray(img.convert("RGB"), dtype=np.float32) / 255.0
    h = 0.299*a[:, :, 0] + 0.587*a[:, :, 1] + 0.114*a[:, :, 2]
    gx = np.zeros_like(h); gy = np.zeros_like(h)
    gx[:, 1:-1] = (h[:, 2:] - h[:, :-2]) * 0.5
    gy[1:-1, :] = (h[2:, :] - h[:-2, :]) * 0.5
    nx, ny, nz = -gx*strength, -gy*strength, np.ones_like(h)
    ln = np.sqrt(nx*nx + ny*ny + nz*nz)
    rgb = np.stack([nx/ln*0.5+0.5, ny/ln*0.5+0.5, nz/ln*0.5+0.5], axis=-1)
    rgba = np.concatenate([rgb, np.ones((*h.shape, 1), np.float32)], axis=-1)
    H, W = h.shape
    with open(out_rgba, "wb") as f:
        f.write(struct.pack("<II", W, H))
        f.write((np.clip(rgba, 0, 1) * 255).astype(np.uint8).tobytes())
    return True

def cmd_normalmap(args):
    from PIL import Image
    if not os.path.isdir(UP_DIR):
        sys.exit("no %s (run extract, upscale, then this)" % UP_DIR)
    os.makedirs(PACK_DIR, exist_ok=True)
    want = args.hash.lower() if args.hash else None
    targets = []
    for path in iter_images(UP_DIR):
        key = key_from_name(path)
        if key and (not want or key == want):
            targets.append((key, path))
    if not targets:
        sys.exit("nothing to do (no matching image in %s)" % UP_DIR)

    total, n = len(targets), 0
    print("generating %d normal map(s), strength %.1f ..." % (total, args.strength))
    for i, (key, path) in enumerate(targets, 1):
        print("  [%d/%d] %s" % (i, total, key))
        if _gen_normal_img(Image.open(path), os.path.join(PACK_DIR, key + "_n.rgba"),
                           args.strength):
            n += 1
    print("done: %d normal map(s) -> %s" % (n, PACK_DIR))
    print("turn bump on with the Bump slider in the launcher; delete a "
          "<hash>_n.rgba to drop bump on that texture.")

def cmd_pack(args):
    from PIL import Image
    src = args.input
    if not os.path.isdir(src):
        sys.exit("input folder not found: %s (run extract, then put upscaled images there)" % src)
    known = set()
    if os.path.exists(MANIFEST):
        known = set(json.load(open(MANIFEST)))
    os.makedirs(args.out, exist_ok=True)
    if args.clean:
        for f in glob.glob(os.path.join(args.out, "*.rgba")):
            os.remove(f)
        print("cleaned %s" % args.out)

    files = list(iter_images(src))
    print("packing %d image(s) from %s ..." % (len(files), src))
    n = skipped = nrefreshed = 0
    for idx, path in enumerate(files, 1):
        key = key_from_name(path)
        if key:
            print("  [%d/%d] %s" % (idx, len(files), key))
        if not key:
            print("  ? %s: name must start with the 8-hex-digit hash, skipped"
                  % os.path.basename(path)); skipped += 1; continue
        if known and key not in known:
            print("  ? %s: hash not in manifest (stale file?), skipped"
                  % os.path.basename(path)); skipped += 1; continue
        img = Image.open(path).convert("RGBA")
        w, h = img.size
        if max(w, h) > MAX_DIM:
            s = MAX_DIM / max(w, h)
            img = img.resize((max(1, int(w*s)), max(1, int(h*s))), Image.LANCZOS)
            print("  ~ %s: %dx%d exceeds %d, downscaled to %dx%d"
                  % (os.path.basename(path), w, h, MAX_DIM, *img.size))
            w, h = img.size
        with open(os.path.join(args.out, key + ".rgba"), "wb") as f:
            f.write(struct.pack("<II", w, h))
            f.write(img.tobytes())
        n += 1
        # Keep an EXISTING normal map in sync: if this texture has a <key>_n.rgba
        # and the source is newer, regenerate it (so editing a texture + repack
        # refreshes its bump automatically). Textures without one are untouched -
        # create one first with `hd_tool normalmap`.
        nrm = os.path.join(args.out, key + "_n.rgba")
        if os.path.exists(nrm) and os.path.getmtime(path) > os.path.getmtime(nrm):
            if _gen_normal_img(img, nrm):
                nrefreshed += 1
    print("done: packed %d texture(s) -> %s%s%s" % (n, args.out,
          (", %d skipped" % skipped) if skipped else "",
          (", %d normal map(s) refreshed" % nrefreshed) if nrefreshed else ""))
    if n:
        print("launch the game from the launcher (Incubation HD.bat) to see them.")

# ---------------------------------------------------------------- 2D UI (Libs/*.LIB)
WORK_2D    = "hd_work_2d"
SOURCE_2D  = os.path.join(WORK_2D, "source")
UP_2D      = os.path.join(WORK_2D, "upscaled")
PACK_2D    = "hd_pack_2d"
MANIFEST_2D = os.path.join(WORK_2D, "manifest.json")

def _pal_index():
    """basename(lower, no ext) -> Graphics/<x>.pal path."""
    idx = {}
    for p in glob.glob(os.path.join("Graphics", "*.pal")):
        idx[os.path.splitext(os.path.basename(p))[0].lower()] = p
    return idx

def _pal_for(lib_name, idx):
    n = lib_name.lower()
    if n in idx:
        return idx[n]
    if n.startswith("item_") and "_" in n:          # item_w2 -> items_w
        cand = "items_" + n.split("_")[1][0]
        if cand in idx:
            return idx[cand]
    if n == "uicons2" and "uicons" in idx:
        return idx["uicons"]
    return None

def _load_palette(pal_path):
    """A .pal is a BMP; its 256-colour table (BGRA) is at file offset 54."""
    d = open(pal_path, "rb").read()
    tbl = d[54:54 + 256 * 4]
    pal = []
    for i in range(256):
        b, g, r = tbl[i*4], tbl[i*4+1], tbl[i*4+2]
        pal += [r, g, b]
    return pal

def cmd_extract2d(args):
    from PIL import Image
    libs = sorted(glob.glob(os.path.join("Libs", "**", "*.LIB"), recursive=True))
    pals = _pal_index()
    os.makedirs(SOURCE_2D, exist_ok=True)
    os.makedirs(UP_2D, exist_ok=True)
    manifest, n_sprites, no_pal = [], 0, []
    for lib in libs:
        d = open(lib, "rb").read()
        magic, count, fsz, hdr, dataoff = struct.unpack_from("<5I", d, 0)
        if magic != 0xFF:
            print("  ? %s: unexpected magic %08x, skipped" % (lib, magic)); continue
        name = os.path.splitext(os.path.basename(lib))[0]
        pal_path = _pal_for(name, pals)
        pal = _load_palette(pal_path) if pal_path else None
        if not pal:
            no_pal.append(name)
        outsub = os.path.join(SOURCE_2D, name)
        os.makedirs(outsub, exist_ok=True)
        off = dataoff
        for i in range(count):
            typ, w, h = struct.unpack_from("<3I", d, 20 + i*36)[:3]
            npix = w * h
            pix = d[off:off + npix]; off += npix
            if w == 0 or h == 0 or len(pix) < npix:
                continue
            im = Image.frombytes("P", (w, h), pix)
            if pal:
                im.putpalette(pal); im = im.convert("RGB")
            else:
                im = im.convert("L")     # no palette yet: show intensity
            fn = "%s_%03d_%dx%d.png" % (name, i, w, h)
            im.save(os.path.join(outsub, fn))
            manifest.append(dict(lib=os.path.relpath(lib).replace("\\", "/"),
                                 name=name, index=i, w=w, h=h,
                                 palette=os.path.basename(pal_path) if pal_path else None,
                                 png="%s/%s" % (name, fn)))
            n_sprites += 1
    with open(MANIFEST_2D, "w") as f:
        json.dump(manifest, f, indent=1)
    print("done: extracted %d sprites from %d .LIB files -> %s"
          % (n_sprites, len(libs), SOURCE_2D))
    if no_pal:
        print("no palette (extracted as grayscale): %s" % ", ".join(sorted(set(no_pal))))
    print("note: these are for reference / native-size edits. Per-widget HD injection is NOT")
    print("possible - the game composites its whole UI itself and hands the renderer only the")
    print("finished 640x480 frame. In-game 2D is improved by the sharpen slider instead.")

# ---------------------------------------------------------------- on / off (A/B test)
OFF_DIR = PACK_DIR + ".off"

def cmd_off(args):
    if os.path.isdir(OFF_DIR):
        print("already OFF (%s exists)" % OFF_DIR); return
    if not os.path.isdir(PACK_DIR):
        print("nothing to disable: no %s" % PACK_DIR); return
    os.rename(PACK_DIR, OFF_DIR)
    print("HD pack DISABLED (renamed %s -> %s). Launch the game to see originals."
          % (PACK_DIR, OFF_DIR))

def cmd_on(args):
    if os.path.isdir(PACK_DIR):
        print("already ON (%s exists)" % PACK_DIR); return
    if not os.path.isdir(OFF_DIR):
        print("nothing to enable: no %s" % OFF_DIR); return
    os.rename(OFF_DIR, PACK_DIR)
    print("HD pack ENABLED (renamed %s -> %s)." % (OFF_DIR, PACK_DIR))

# ---------------------------------------------------------------- status
def keys_in(folder, exts):
    out = set()
    if os.path.isdir(folder):
        for f in os.listdir(folder):
            if f.lower().endswith(exts):
                k = key_from_name(f)
                if k: out.add(k)
    return out

def cmd_status(args):
    src  = keys_in(SOURCE_DIR, IMG_EXTS)
    up   = keys_in(UP_DIR, IMG_EXTS)
    pack = keys_in(PACK_DIR, (".rgba",))
    print("extracted : %4d  (%s)" % (len(src), SOURCE_DIR))
    print("upscaled  : %4d  (%s)" % (len(up), UP_DIR))
    print("packed    : %4d  (%s)" % (len(pack), PACK_DIR))
    if os.path.isdir(OFF_DIR):
        print("!! HD pack is DISABLED (%s exists) - run: hd_tool.py on" % OFF_DIR)
    if src:
        miss_up   = src - up
        miss_pack = up - pack
        if miss_up:
            print("not yet upscaled: %d texture(s)" % len(miss_up))
        if miss_pack:
            print("upscaled but not packed: %d -> run: hd_tool.py pack" % len(miss_pack))
        if not miss_up and not miss_pack and up:
            print("all extracted textures are upscaled and packed.")

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("extract", help="decode game textures -> %s" % SOURCE_DIR)
    p = sub.add_parser("pack", help="images from %s -> %s" % (UP_DIR, PACK_DIR))
    p.add_argument("-i", "--input", default=UP_DIR, help="folder with upscaled images")
    p.add_argument("-o", "--out", default=PACK_DIR, help="pack output folder")
    p.add_argument("--clean", action="store_true", help="delete existing .rgba first")
    pn = sub.add_parser("normalmap", help="generate bump normal maps from %s" % UP_DIR)
    pn.add_argument("hash", nargs="?", help="only this 8-hex texture (default: all)")
    pn.add_argument("--strength", type=float, default=NORMAL_STRENGTH,
                    help="height->normal gain (default %.1f)" % NORMAL_STRENGTH)
    sub.add_parser("status", help="show pipeline progress")
    sub.add_parser("off", help="disable the HD pack (A/B test: see original textures)")
    sub.add_parser("on", help="re-enable the HD pack")
    sub.add_parser("extract2d", help="extract Libs/*.LIB UI sprites -> %s" % SOURCE_2D)
    args = ap.parse_args()
    os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    if not args.cmd:                 # no command -> help + current progress
        ap.print_help()
        print("\ncurrent progress:")
        cmd_status(args)
        return
    {"extract": cmd_extract, "pack": cmd_pack, "status": cmd_status,
     "off": cmd_off, "on": cmd_on, "extract2d": cmd_extract2d,
     "normalmap": cmd_normalmap}[args.cmd](args)

if __name__ == "__main__":
    main()
