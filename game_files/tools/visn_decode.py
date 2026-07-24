"""32-bit host: call the game's own Eng3d.dll _E3D_decode_picture to decode VISN records.

Must be run with 32-bit Python because Eng3d.dll is a PE32 (x86) DLL.
"""
import os, sys, ctypes, struct
from ctypes import c_void_p, c_int, c_char

# Derived from this file's own location (tools/ sits inside the game folder), so
# it works wherever the game is installed. INCU_GAME_DIR overrides if needed.
GAME_DIR = os.environ.get(
    "INCU_GAME_DIR",
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DLL_PATH = os.path.join(GAME_DIR, "Eng3d.dll")

def load_decoder():
    # let dependent Engwlib.dll resolve from the game dir
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(GAME_DIR)
    os.chdir(GAME_DIR)
    dll = ctypes.CDLL(DLL_PATH)
    # _E3D_init_vision builds the IDCT / dequant / colour tables and the DC
    # predictor pointers the decoder relies on. Must run once before decoding.
    init = dll._E3D_init_vision
    init.restype = None
    init.argtypes = [c_int]
    init(0)
    fn = dll._E3D_decode_picture
    fn.restype = None
    fn.argtypes = [c_void_p, c_void_p, c_int]
    return fn

def parse_dir(dirpath):
    entries = []
    with open(dirpath, "rb") as f:
        text = f.read().decode("latin-1")
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        name = parts[0].strip()
        rest = parts[-1].split()
        if len(rest) == 5 and all(p.lstrip("-").isdigit() for p in rest):
            typ, idx, off, size, mtime = map(int, rest)
            entries.append(dict(name=name, type=typ, idx=idx, off=off, size=size))
    return entries

def decode_record(fn, rec):
    assert rec[:4] == b"VISN", rec[:4]
    w = struct.unpack_from("<H", rec, 4)[0]
    h = struct.unpack_from("<H", rec, 6)[0]
    sel8 = rec[8]; sel9 = rec[9]
    src = (c_char * len(rec)).from_buffer_copy(rec)
    dst = (c_char * (w * h * 2))()
    fn(src, dst, w)
    return w, h, sel8, sel9, bytes(dst)

def rgb565_to_rgb(buf, w, h):
    from PIL import Image
    px = struct.unpack("<%dH" % (w*h), buf)
    out = bytearray(w*h*3)
    for i, v in enumerate(px):
        r = (v >> 11) & 0x1f; g = (v >> 5) & 0x3f; b = v & 0x1f
        out[3*i]   = (r << 3) | (r >> 2)
        out[3*i+1] = (g << 2) | (g >> 4)
        out[3*i+2] = (b << 3) | (b >> 2)
    return Image.frombytes("RGB", (w, h), bytes(out))

def rgb555_to_rgb(buf, w, h):
    from PIL import Image
    px = struct.unpack("<%dH" % (w*h), buf)
    out = bytearray(w*h*3)
    for i, v in enumerate(px):
        r = (v >> 10) & 0x1f; g = (v >> 5) & 0x1f; b = v & 0x1f
        out[3*i]   = (r << 3) | (r >> 2)
        out[3*i+1] = (g << 3) | (g >> 2)
        out[3*i+2] = (b << 3) | (b >> 2)
    return Image.frombytes("RGB", (w, h), bytes(out))

def main():
    lib = sys.argv[1]
    which = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    outdir = sys.argv[3] if len(sys.argv) > 3 else "out_test"
    os.makedirs(outdir, exist_ok=True)
    entries = parse_dir(os.path.splitext(lib)[0] + ".dir")
    data = open(lib, "rb").read()
    fn = load_decoder()
    e = entries[which]
    rec = data[e["off"]:e["off"]+e["size"]]
    w, h, s8, s9, raw = decode_record(fn, rec)
    print(f"{e['name']}: {w}x{h} sel8={s8} sel9={s9} rawlen={len(raw)}")
    open(os.path.join(outdir, f"{e['name']}.raw565"), "wb").write(raw)
    rgb565_to_rgb(raw, w, h).save(os.path.join(outdir, f"{e['name']}_565.png"))
    rgb555_to_rgb(raw, w, h).save(os.path.join(outdir, f"{e['name']}_555.png"))
    print("saved PNGs to", outdir)

if __name__ == "__main__":
    main()
