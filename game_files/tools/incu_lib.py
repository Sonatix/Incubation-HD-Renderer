#!/usr/bin/env python3
"""incu_lib.py - Incubation (Blue Byte, 1997) .lib texture toolkit.

Commands:
    python incu_lib.py list    <file.lib>
    python incu_lib.py extract <file.lib> -o out/   [--raw]
    python incu_lib.py preview <file.lib> -o grid.png

The .lib is a concatenation of "VISN" picture records; the record table lives in the
sibling <name>.dir (plain text) / .din (binary). VISN is a custom JPEG-like DCT codec
that outputs 16-bit RGB565. We decode by calling the game's own decoder in Eng3d.dll,
so THIS SCRIPT MUST RUN UNDER 32-BIT PYTHON (Eng3d.dll is a PE32/x86 DLL).

See docs/format.md for the full format writeup.
"""
import os, sys, struct, argparse, ctypes
from ctypes import c_void_p, c_int, c_char

# ---------------------------------------------------------------- game decoder
GAME_DIR = os.environ.get("INCU_GAME_DIR",
    r"F:\GOG Games\Battle Isle Platinum\Incubation")
COLOR_DESCRIPTOR = 0x565   # RGB565 (use 0x555 for RGB555)

class Decoder:
    """Thin wrapper over Eng3d.dll's _E3D_decode_picture."""
    def __init__(self, game_dir=GAME_DIR, descriptor=COLOR_DESCRIPTOR):
        if struct.calcsize("P") != 4:
            raise RuntimeError("Must run under 32-bit Python (Eng3d.dll is PE32).")
        dll_path = os.path.join(game_dir, "Eng3d.dll")
        if not os.path.exists(dll_path):
            raise FileNotFoundError(dll_path)
        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(game_dir)
        self._cwd = os.getcwd(); os.chdir(game_dir)
        self.dll = ctypes.CDLL(dll_path)
        self.dll._E3D_init_vision.restype = None
        self.dll._E3D_init_vision.argtypes = [c_int]
        self.dll._E3D_init_vision(descriptor)   # builds RGB565 colour tables
        self.decode = self.dll._E3D_decode_picture
        self.decode.restype = None
        self.decode.argtypes = [c_void_p, c_void_p, c_int]

    def decode_record(self, rec):
        """rec = raw VISN bytes -> (w, h, rgb565_bytes)."""
        if rec[:4] != b"VISN":
            raise ValueError("not a VISN record (magic=%r)" % rec[:4])
        w, h = struct.unpack_from("<HH", rec, 4)
        src = (c_char * len(rec)).from_buffer_copy(rec)
        dst = (c_char * (w * h * 2))()
        self.decode(src, dst, w)
        return w, h, bytes(dst)

# ---------------------------------------------------------------- directory / TOC
class Entry:
    __slots__ = ("name", "type", "idx", "off", "size", "mtime")
    def __init__(self, name, type, idx, off, size, mtime):
        self.name, self.type, self.idx = name, type, idx
        self.off, self.size, self.mtime = off, size, mtime

def parse_dir(dir_path):
    entries = []
    with open(dir_path, "rb") as f:
        text = f.read().decode("latin-1")
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        name = parts[0].strip()
        rest = parts[-1].split()
        if len(rest) == 5 and all(p.lstrip("-").isdigit() for p in rest):
            typ, idx, off, size, mtime = map(int, rest)
            entries.append(Entry(name, typ, idx, off, size, mtime))
    return entries

def load_toc(lib_path):
    base = os.path.splitext(lib_path)[0]
    for ext in (".dir", ".DIR"):
        if os.path.exists(base + ext):
            return parse_dir(base + ext)
    raise FileNotFoundError("no .dir TOC next to " + lib_path)

# ---------------------------------------------------------------- rgb conversion
def rgb565_to_rgb_bytes(buf, descriptor=COLOR_DESCRIPTOR):
    n = len(buf) // 2
    px = struct.unpack("<%dH" % n, buf)
    out = bytearray(n * 3)
    if descriptor == 0x555:
        for i, v in enumerate(px):
            r = (v >> 10) & 0x1f; g = (v >> 5) & 0x1f; b = v & 0x1f
            out[3*i] = (r<<3)|(r>>2); out[3*i+1] = (g<<3)|(g>>2); out[3*i+2] = (b<<3)|(b>>2)
    else:  # 565
        for i, v in enumerate(px):
            r = (v >> 11) & 0x1f; g = (v >> 5) & 0x3f; b = v & 0x1f
            out[3*i] = (r<<3)|(r>>2); out[3*i+1] = (g<<2)|(g>>4); out[3*i+2] = (b<<3)|(b>>2)
    return bytes(out)

def image_from_record(dec, rec):
    from PIL import Image
    w, h, raw = dec.decode_record(rec)
    return Image.frombytes("RGB", (w, h), rgb565_to_rgb_bytes(raw))

# ---------------------------------------------------------------- commands
def cmd_list(args):
    entries = load_toc(args.lib)
    total = os.path.getsize(args.lib)
    print("%-14s %5s %10s %8s %12s" % ("name", "idx", "offset", "size", "mtime"))
    for e in entries:
        print("%-14s %5d %10d %8d %12d" % (e.name, e.idx, e.off, e.size, e.mtime))
    last = entries[-1]
    print("-- %d records, lib=%d bytes, last off+size=%d (%s)" % (
        len(entries), total, last.off + last.size,
        "OK" if last.off + last.size == total else "MISMATCH"))

def cmd_extract(args):
    entries = load_toc(args.lib)
    data = open(args.lib, "rb").read()
    os.makedirs(args.out, exist_ok=True)
    dec = Decoder()
    ok = fail = 0
    for e in entries:
        rec = data[e.off:e.off + e.size]
        if args.raw:
            open(os.path.join(args.out, e.name + ".visn"), "wb").write(rec)
        try:
            img = image_from_record(dec, rec)
            img.save(os.path.join(args.out, e.name + ".png"))
            ok += 1
        except Exception as ex:
            print("  ! %s: %s" % (e.name, ex)); fail += 1
    if args.raw:
        # copy the original text TOC so `pack` can rebuild byte-identically
        import shutil
        base = os.path.splitext(args.lib)[0]
        src_dir = base + ".dir" if os.path.exists(base + ".dir") else base + ".DIR"
        shutil.copy(src_dir, os.path.join(args.out, "texture.dir"))
    print("extracted %d PNG(s), %d failed -> %s" % (ok, fail, args.out))

def _build_din(entries):
    """Rebuild the binary DBIN TOC.

    Header: "DBIN" + uint32 count. Then one 25-byte record per entry:
        uint32 index; char name[13] (NUL-padded); uint32 offset; uint32 size.
    """
    out = bytearray(b"DBIN")
    out += struct.pack("<I", len(entries))
    for e in entries:
        nm = e.name.encode("latin-1")[:13].ljust(13, b"\0")
        out += struct.pack("<I", e.idx) + nm + struct.pack("<II", e.off, e.size)
    return bytes(out)

def cmd_pack(args):
    """Rebuild a .lib (+ .dir/.din) from a directory of raw .visn records.

    The directory must contain the per-record `<name>.visn` files and the original
    `texture.dir` (both produced by `extract --raw`). Offsets/sizes are recomputed, so
    editing a `.visn` of a different length still produces a consistent container.
    """
    src_entries = parse_dir(os.path.join(args.dir, "texture.dir"))
    out_lib = open(args.out, "wb")
    new_entries = []
    off = 0
    for e in src_entries:
        rec_path = os.path.join(args.dir, e.name + ".visn")
        rec = open(rec_path, "rb").read()
        out_lib.write(rec)
        new_entries.append(Entry(e.name, e.type, e.idx, off, len(rec), e.mtime))
        off += len(rec)
    out_lib.close()
    # rewrite text TOC with recomputed offsets/sizes
    base = os.path.splitext(args.out)[0]
    with open(base + ".dir", "w", newline="") as f:
        f.write("3DI\r\n[DIRECTORY]\r\n")
        for e in new_entries:
            f.write("%s\t\t%d %d %d %d %d\r\n" % (e.name, e.type, e.idx, e.off, e.size, e.mtime))
        f.write("ENDDIR\r\n[END3DI]\r\n")
    with open(base + ".din", "wb") as f:
        f.write(_build_din(new_entries))
    print("packed %d records -> %s (%d bytes)" % (len(new_entries), args.out, off))

def cmd_preview(args):
    from PIL import Image, ImageDraw
    entries = load_toc(args.lib)
    data = open(args.lib, "rb").read()
    dec = Decoder()
    thumbs = []
    for e in entries:
        rec = data[e.off:e.off + e.size]
        try:
            img = image_from_record(dec, rec)
        except Exception:
            img = Image.new("RGB", (64, 64), (64, 0, 0))
        thumbs.append((e.name, img))
    cell = args.cell
    cols = args.cols
    rows = (len(thumbs) + cols - 1) // cols
    pad, label = 4, 12
    W = cols * (cell + pad) + pad
    H = rows * (cell + pad + label) + pad
    grid = Image.new("RGB", (W, H), (24, 24, 24))
    draw = ImageDraw.Draw(grid)
    for i, (name, img) in enumerate(thumbs):
        r, c = divmod(i, cols)
        x = pad + c * (cell + pad)
        y = pad + r * (cell + pad + label)
        th = img.copy(); th.thumbnail((cell, cell))
        grid.paste(th, (x + (cell - th.width)//2, y + (cell - th.height)//2))
        draw.text((x, y + cell + 1), name[:14], fill=(200, 200, 200))
    grid.save(args.out)
    print("preview grid (%d tiles) -> %s" % (len(thumbs), args.out))

def main():
    p = argparse.ArgumentParser(description="Incubation .lib texture toolkit")
    sub = p.add_subparsers(dest="cmd", required=True)
    pl = sub.add_parser("list"); pl.add_argument("lib"); pl.set_defaults(func=cmd_list)
    pe = sub.add_parser("extract"); pe.add_argument("lib")
    pe.add_argument("-o", "--out", default="out"); pe.add_argument("--raw", action="store_true")
    pe.set_defaults(func=cmd_extract)
    pp = sub.add_parser("preview"); pp.add_argument("lib")
    pp.add_argument("-o", "--out", default="grid.png")
    pp.add_argument("--cell", type=int, default=128); pp.add_argument("--cols", type=int, default=8)
    pp.set_defaults(func=cmd_preview)
    pk = sub.add_parser("pack"); pk.add_argument("dir")
    pk.add_argument("-o", "--out", default="rebuilt.lib"); pk.set_defaults(func=cmd_pack)
    args = p.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
