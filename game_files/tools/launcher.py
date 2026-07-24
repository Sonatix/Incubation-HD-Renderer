#!/usr/bin/env python3
"""Incubation launcher — one window for everything.

Tabs:
  Play              HD (our OpenGlide fork) or the game's ORIGINAL launcher, one switch
  HD textures       the HD pack pipeline + sharpen / bump (renderer-side; HD mode only)
  Vanilla textures  decode / edit / repack the game's own texture.lib (no renderer)
  Debug             test-map swap, -debugx developer tools, renderer override

Run with the 32-bit Python (hd_tool's `extract` needs it). Settings persist to
launcher.json in the game folder. Manuals live in docs/MANUAL_*.md and open from
the tabs' Manual buttons.
"""
import os, sys, json, queue, ctypes, threading, subprocess, webbrowser
from ctypes import wintypes
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from visn_gui import VisnFrame, hd_pack_enabled

GAME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HD_TOOL  = os.path.join(GAME_DIR, "tools", "hd_tool.py")
SETTINGS = os.path.join(GAME_DIR, "launcher.json")
GAME_EXE = os.path.join(GAME_DIR, "Incubation.exe")
BACKUP   = os.path.join(GAME_DIR, "backup")
DOCS     = os.path.join(GAME_DIR, "docs")
PY       = sys.executable

# ------------------------------------------------------------------ display
CDS_FULLSCREEN = 0x00000004
DISP_CHANGE_SUCCESSFUL = 0

class DEVMODE(ctypes.Structure):
    _fields_ = [("dmDeviceName", wintypes.WCHAR * 32),
                ("dmSpecVersion", wintypes.WORD), ("dmDriverVersion", wintypes.WORD),
                ("dmSize", wintypes.WORD), ("dmDriverExtra", wintypes.WORD),
                ("dmFields", wintypes.DWORD),
                ("dmPositionX", ctypes.c_long), ("dmPositionY", ctypes.c_long),
                ("dmDisplayOrientation", wintypes.DWORD), ("dmDisplayFixedOutput", wintypes.DWORD),
                ("dmColor", ctypes.c_short), ("dmDuplex", ctypes.c_short),
                ("dmYResolution", ctypes.c_short), ("dmTTOption", ctypes.c_short),
                ("dmCollate", ctypes.c_short), ("dmFormName", wintypes.WCHAR * 32),
                ("dmLogPixels", wintypes.WORD), ("dmBitsPerPel", wintypes.DWORD),
                ("dmPelsWidth", wintypes.DWORD), ("dmPelsHeight", wintypes.DWORD),
                ("dmDisplayFlags", wintypes.DWORD), ("dmDisplayFrequency", wintypes.DWORD),
                ("dmICMMethod", wintypes.DWORD), ("dmICMIntent", wintypes.DWORD),
                ("dmMediaType", wintypes.DWORD), ("dmDitherType", wintypes.DWORD),
                ("dmReserved1", wintypes.DWORD), ("dmReserved2", wintypes.DWORD),
                ("dmPanningWidth", wintypes.DWORD), ("dmPanningHeight", wintypes.DWORD)]

_u32 = ctypes.windll.user32

def current_mode():
    dm = DEVMODE(); dm.dmSize = ctypes.sizeof(DEVMODE)
    _u32.EnumDisplaySettingsW(None, -1, ctypes.byref(dm))
    return int(dm.dmPelsWidth), int(dm.dmPelsHeight), int(dm.dmDisplayFrequency)

def list_modes():
    """Distinct 32-bit (w,h), widest first."""
    dm = DEVMODE(); dm.dmSize = ctypes.sizeof(DEVMODE)
    seen, i = set(), 0
    while _u32.EnumDisplaySettingsW(None, i, ctypes.byref(dm)):
        if dm.dmBitsPerPel == 32 and dm.dmPelsWidth >= 640:
            seen.add((int(dm.dmPelsWidth), int(dm.dmPelsHeight)))
        i += 1
    return sorted(seen, reverse=True)

def set_mode(w, h):
    """Switch to w x h at the highest refresh that mode supports."""
    dm = DEVMODE(); dm.dmSize = ctypes.sizeof(DEVMODE)
    best, i = None, 0
    while _u32.EnumDisplaySettingsW(None, i, ctypes.byref(dm)):
        if (dm.dmPelsWidth, dm.dmPelsHeight, dm.dmBitsPerPel) == (w, h, 32):
            if best is None or dm.dmDisplayFrequency > best[0]:
                best = (int(dm.dmDisplayFrequency), DEVMODE.from_buffer_copy(dm))
        i += 1
    if not best:
        return False
    target = best[1]
    return _u32.ChangeDisplaySettingsExW(None, ctypes.byref(target), None,
                                         CDS_FULLSCREEN, None) == DISP_CHANGE_SUCCESSFUL

def restore_mode(saved):
    """Explicitly re-apply the mode we started with (safer than a NULL reset)."""
    if not saved:
        return
    w, h, _ = saved
    if (w, h) != current_mode()[:2]:
        set_mode(w, h)

# ------------------------------------------------- Windows 10/11 sound patch
# Stock Incubation hangs at startup on Windows 10/11: its sound layer never
# returns, so the process sits in Task Manager with no window. The community
# "Windows 10 Patch" (part of the 25th Anniversary Mod) replaces audio.dll and
# sound.dll with a fixed build -- the same file under both names. It is not
# ours to redistribute, so all we can do is detect it and point at it.
#
# The check is deliberately phrased as "could not confirm" rather than "not
# installed": a future revision of the patch would have a different hash, and
# claiming it is missing when it is merely newer would be worse than useless.
WIN10_PATCH_MD5 = "88e3333beda14ed61f1ca394c43f7413"
WIN10_PATCH_URL = ("https://www.moddb.com/mods/"
                   "incubation-blue-byte-25-years-anniversary-mod/downloads/"
                   "incubation-windows-10-patch")

def win10_patch_applied():
    """True only when both DLLs are exactly the known patched build."""
    import hashlib
    for name in ("audio.dll", "sound.dll"):
        p = os.path.join(GAME_DIR, name)
        try:
            with open(p, "rb") as fh:
                if hashlib.md5(fh.read()).hexdigest() != WIN10_PATCH_MD5:
                    return False
        except OSError:
            return False
    return True

# ------------------------------------------------------------------ renderer
def openglide_supports(feature):
    """Does our OpenGlide build know an INCU_* switch?

    The env-var name is a plain string literal in the DLL, so its presence is a
    reliable capability probe. We look at the *backup* copy, because whichever
    wrapper is installed right now depends on the last Play mode used.
    """
    for p in (os.path.join(BACKUP, "glide2x.dll.openglide"),
              os.path.join(GAME_DIR, "glide2x.dll")):
        try:
            with open(p, "rb") as fh:
                if feature.encode() in fh.read():
                    return True
        except OSError:
            pass
    return False


def active_renderer():
    g = os.path.join(GAME_DIR, "glide2x.dll")
    kind = classify_glide(g)
    if kind == "ours":
        return "OpenGlide (HD)"
    if kind == "thirdparty":
        return "dgVoodoo (stock, no HD)"
    if kind is None and os.path.exists(g):
        return "unknown glide2x.dll"
    return "missing"


def classify_glide(path):
    """What kind of Glide2x wrapper is this file? -> 'ours' | 'thirdparty' | None.

    The signature is `_ConvertAndDownloadRle@64` -- the first symbol the game's
    ENG3DFX.DLL imports from glide2x.dll, and one that is specific to a Glide 2.x
    wrapper. This is NOT the same as merely exporting grGlideInit: the game also
    ships stock 3dfx `glide.dll` and `glide3x.dll` (Glide 1.x / 3.x) that export
    grGlideInit but lack this symbol, and installing one of those as glide2x.dll
    makes the game fail with "entry point _ConvertAndDownloadRle@64 not found".
    Ours additionally carries the INCU_ env-var strings; a valid glide2x that
    does not is a third-party wrapper (dgVoodoo, nGlide, real 3dfx glide2x)."""
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError:
        return None
    if b"_ConvertAndDownloadRle@64" not in data:
        return None
    return "ours" if b"INCU_SHARP" in data else "thirdparty"


def secure_our_build():
    """Copy the shipped glide2x.dll into backup/glide2x.dll.openglide at startup,
    before anything can overwrite it.

    This matters because of a Windows gotcha: 'glide2x.dll' and 'Glide2x.dll' are
    the SAME file on a case-insensitive filesystem, so dropping dgVoodoo's
    Glide2x.dll into the game folder overwrites our build. If our build is already
    in the backup, HD mode can always restore it; if it were only in the live
    slot, that overwrite would lose it for good."""
    dst = os.path.join(BACKUP, "glide2x.dll.openglide")
    live = os.path.join(GAME_DIR, "glide2x.dll")
    if os.path.exists(dst):
        return
    if classify_glide(live) == "ours":
        try:
            os.makedirs(BACKUP, exist_ok=True)
            _copy(live, dst)
        except OSError:
            pass


# --------------------------------------------------------------- dgVoodoo dir
# One clearly-named folder is the ONLY place a user drops dgVoodoo. We never
# scan the game folder for "some glide wrapper" any more -- that used to grab
# the game's own stock glide.dll/glide3x.dll (Glide 1.x/3.x, not glide2x) and
# crash the game. Here the deal is explicit and self-documenting.
DGV_DIR = os.path.join(GAME_DIR, "dgVoodoo")
DGV_README = os.path.join(DGV_DIR, "READ ME - put dgVoodoo here.txt")
DGV_README_TEXT = (
    "dgVoodoo folder\r\n"
    "===============\r\n\r\n"
    "This is where the launcher looks for dgVoodoo, and NOWHERE else.\r\n\r\n"
    "WHAT IT IS FOR\r\n"
    "  Vanilla mode (Play tab) is meant to render the game the plain 3dfx way,\r\n"
    "  without our HD renderer, so you can compare against HD or see edits made\r\n"
    "  on the Vanilla textures tab.\r\n\r\n"
    "WHAT TO PUT HERE\r\n"
    "  Both of dgVoodoo's 32-bit DLLs, from its MS\\x86 folder:\r\n\r\n"
    "    ddraw.dll     -> Vanilla via DirectX  (Incubation.exe -directx)\r\n"
    "    Glide2x.dll   -> Vanilla via Glide    (Incubation.exe -3dfx)\r\n\r\n"
    "  You do not need to rename them; the launcher checks the contents. Pick\r\n"
    "  the path on the Play tab under \"Vanilla via\". dgVoodoo is not bundled\r\n"
    "  because its licence forbids redistribution -- get it from\r\n"
    "  https://dege.freeweb.hu/\r\n\r\n"
    "  THE TRADE-OFF: -directx is the game's own ENG3D.DLL software rasterizer\r\n"
    "  (the path the GOG launcher uses), -3dfx is ENG3DFX.DLL, the 3dfx renderer\r\n"
    "  the game was built around and the better-looking one. But the mouse only\r\n"
    "  works on the DirectX path: the game reads\r\n"
    "  the cursor in screen coordinates while assuming a 640x480 screen, and\r\n"
    "  dgVoodoo's cursor handling belongs to its DirectX path -- dgVoodoo.conf\r\n"
    "  documents SystemHookFlags as x86-DX only. On the Glide path nothing\r\n"
    "  converts those coordinates, so the whole game screen maps into the top\r\n"
    "  left 640x480 pixels of your display. The dgVoodoo logo at startup means\r\n"
    "  the DirectX path is live; the 3dfx logo means the Glide one is.\r\n\r\n"
    "  The launcher copies ddraw.dll into the game folder only for the run and\r\n"
    "  removes it again afterwards, so nothing is left behind.\r\n\r\n"
    "IF YOU LEAVE THIS FOLDER EMPTY\r\n"
    "  That is fine. Vanilla mode still works: it runs our own renderer with the\r\n"
    "  HD texture pack switched off for that session, which looks like the plain\r\n"
    "  game and is all you need for A/B and for checking vanilla texture mods.\r\n\r\n"
    "Only dgVoodoo's real 32-bit DLLs are accepted here: a Glide 2.x wrapper and\r\n"
    "a DirectDraw one. The game's own glide.dll and glide3x.dll are different\r\n"
    "(Glide 1.x/3.x) and are ignored, as is anything else dropped in by mistake.\r\n")


def ensure_dirs():
    """Create the folders the launcher relies on, and drop the dgVoodoo readme.
    Done once at startup so a fresh install is never missing a needed folder."""
    for d in (BACKUP, DGV_DIR):
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            pass
    # Rewrite the readme whenever its text changed, not just when it is missing:
    # an install made by an older version would otherwise keep stale advice
    # forever. newline="" on both sides, so the \r\n in the text is not doubled.
    try:
        try:
            with open(DGV_README, "r", newline="") as f:
                current = f.read()
        except OSError:
            current = None
        if current != DGV_README_TEXT:
            with open(DGV_README, "w", newline="") as f:
                f.write(DGV_README_TEXT)
    except OSError:
        pass


def user_dgvoodoo():
    """Path to a valid 32-bit glide2x wrapper the user placed in dgVoodoo/, or
    None. Accepts any filename; validates by content, so stock glide.dll dropped
    in by mistake is ignored rather than installed and crashed against."""
    try:
        names = os.listdir(DGV_DIR)
    except OSError:
        return None
    for name in names:
        if not name.lower().endswith(".dll"):
            continue
        p = os.path.join(DGV_DIR, name)
        if classify_glide(p) == "thirdparty":
            return p
    return None

# ------------------------------------------------------- dgVoodoo DirectDraw
# The game has TWO renderer switches: -3dfx goes through ENG3DFX.DLL to a Glide
# wrapper, -directx goes through DDRAW.DLL to DirectDraw. They are not equal for
# dgVoodoo: its cursor handling lives on the DirectX side (dgVoodoo.conf itself
# documents SystemHookFlags as "x86-DX only"), so with -3dfx and dgVoodoo's
# Glide2x.dll the game's 640x480 cursor coordinates are never converted and the
# whole screen maps into the top-left 640x480 pixels. Through -directx with
# dgVoodoo's ddraw.dll the cursor tracks correctly -- verified on 2026-07-24.
# The dgVoodoo logo appears on the DirectX path, the 3dfx logo on the Glide one,
# which is a quick way to tell which one is live.
DDRAW_BACKUP = os.path.join(BACKUP, "ddraw.dll.orig")
DDRAW_MARKER = os.path.join(BACKUP, "ddraw_installed.txt")

def classify_ddraw(path):
    """-> 'dgvoodoo' | 'other' | None. A DirectDraw DLL must export
    DirectDrawCreate; dgVoodoo's own build additionally names itself.

    That name lives in the PE version resource, which is UTF-16, so an ASCII-only
    search silently classifies a genuine dgVoodoo ddraw.dll as 'other'."""
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError:
        return None
    if b"DirectDrawCreate" not in data:
        return None
    name = "dgVoodoo"
    if name.encode() in data or name.encode("utf-16-le") in data:
        return "dgvoodoo"
    return "other"

def user_dgvoodoo_ddraw():
    """dgVoodoo's ddraw.dll in dgVoodoo/, or None. Validated by content, so the
    name it was unzipped under does not matter."""
    try:
        names = os.listdir(DGV_DIR)
    except OSError:
        return None
    for name in names:
        if not name.lower().endswith(".dll"):
            continue
        p = os.path.join(DGV_DIR, name)
        if classify_ddraw(p) == "dgvoodoo":
            return p
    return None

def live_ddraw():
    """The game folder's ddraw.dll whatever its capitalisation ('ddraw.dll' and
    'DDraw.dll' are one file on Windows), or None."""
    try:
        for name in os.listdir(GAME_DIR):
            if name.lower() == "ddraw.dll":
                return os.path.join(GAME_DIR, name)
    except OSError:
        pass
    return None

def install_ddraw(src):
    """Put dgVoodoo's ddraw.dll into the game folder for one -directx run.

    Anything already sitting there is kept in backup/ddraw.dll.orig, and a marker
    records that we installed ours, so a crashed run is repaired at the next
    start instead of leaving a foreign DLL behind."""
    try:
        os.makedirs(BACKUP, exist_ok=True)
        live = live_ddraw()
        if live and not os.path.exists(DDRAW_MARKER):
            if classify_ddraw(live) == "dgvoodoo":
                pass                      # already dgVoodoo's, nothing to save
            else:
                _copy(live, DDRAW_BACKUP)
        _copy(src, live or os.path.join(GAME_DIR, "ddraw.dll"))
        with open(DDRAW_MARKER, "w") as f:
            f.write("dgVoodoo ddraw.dll installed for a -directx run\n")
        return True
    except PermissionError:
        messagebox.showerror("In use", "Close the game first.")
        return False
    except OSError as e:
        messagebox.showerror("dgVoodoo DirectDraw", str(e))
        return False

def restore_ddraw():
    """Undo install_ddraw: put back whatever was there, or remove ours."""
    if not os.path.exists(DDRAW_MARKER):
        return
    try:
        live = live_ddraw()
        if os.path.exists(DDRAW_BACKUP):
            _copy(DDRAW_BACKUP, live or os.path.join(GAME_DIR, "ddraw.dll"))
            os.remove(DDRAW_BACKUP)
        elif live:
            os.remove(live)
        os.remove(DDRAW_MARKER)
    except OSError:
        pass

# ----------------------------------------------------------------- test map
# A campaign always opens on its first map, so dropping another mission's files
# into that slot starts it straight away instead of replaying everything before
# it. Map and script share a stem (_C_144.lev + _C_144.lcl) and BOTH are
# swapped — swapping only the .lev would pair new terrain with the old script.
#
# Only the ORIGINAL campaign is offered. The disc also carries the Wilderness
# Missions add-on (_C_140..180) with its own briefings and entry point — an
# add-on map dropped into this slot comes up with a broken pre-mission screen.
# Multiplayer/skirmish/upgrade maps are reached through other menus entirely.
#
# 34 maps make up 29 missions: the campaign forks three times and the player
# picks a route, so five missions exist in an a/b pair. The branch choice is NOT
# in the mission data — every .lev names exactly one next_map (the a-route), and
# the game offers the alternative on its own screen between missions. Numbering
# below follows fadden.com/gaming/incubation/ocampaign.html.
# _C_YYY closes the chain but is empty (no units, no placefields), so it is not
# a mission. _C_140..180 is the separate Wilderness add-on campaign.
MISSIONS   = os.path.join(GAME_DIR, "Missions")
MAP_BACKUP = os.path.join(BACKUP, "maps")
MAP_MARKER = os.path.join(MAP_BACKUP, "swapped.txt")
MAP_PARTS  = (".lev", ".lcl")
MAP_SLOT   = "_C_100"
CAMPAIGN = (("01", "_C_100"), ("02", "_C_101"), ("03a", "_C_102"), ("03b", "_C_103"),
            ("04", "_C_104"), ("05", "_C_105"), ("06", "_C_106"), ("07", "_C_107"),
            ("08a", "_C_108"), ("08b", "_C_109"), ("09a", "_C_110"), ("09b", "_C_111"),
            ("10", "_C_112"), ("11", "_C_113"), ("12", "_C_114"), ("13", "_C_115"),
            ("14", "_C_116"), ("15", "_C_117"), ("16", "_C_118"), ("17", "_C_119"),
            ("18a", "_C_120"), ("18b", "_C_121"), ("19a", "_C_122"), ("19b", "_C_123"),
            ("20", "_C_124"), ("21", "_C_125"), ("22", "_C_126"), ("23", "_C_127"),
            ("24", "_C_128"), ("25", "_C_129"), ("26", "_C_130"), ("27", "_C_131"),
            ("28", "_C_132"), ("29", "_C_133"))
CAMPAIGN_STEMS = tuple(s for _, s in CAMPAIGN)

def list_maps():
    """Campaign missions present on disk, in play order."""
    try:
        names = set(os.listdir(MISSIONS))
    except OSError:
        return []
    return [s for s in CAMPAIGN_STEMS
            if all(s + e in names or s + e.upper() in names for e in MAP_PARTS)]

def map_label(stem):
    """Dropdown text: mission number makes a walkthrough easy to follow, and
    the a/b suffix shows which route fork the map belongs to."""
    for num, s in CAMPAIGN:
        if s == stem:
            return "%-3s %s" % (num, stem)
    return stem

def swapped_map():
    """Stem currently sitting in the campaign slot, or None if pristine."""
    try:
        with open(MAP_MARKER) as f:
            return f.read().strip() or None
    except OSError:
        return None

def _copy(src, dst):
    with open(src, "rb") as a, open(dst, "wb") as b:
        b.write(a.read())

def backup_slot():
    """Stash the pristine slot files once. Never overwrites an existing backup:
    that would capture an already-swapped map and lose the originals."""
    os.makedirs(MAP_BACKUP, exist_ok=True)
    for ext in MAP_PARTS:
        dst = os.path.join(MAP_BACKUP, MAP_SLOT + ext)
        if not os.path.exists(dst):
            _copy(os.path.join(MISSIONS, MAP_SLOT + ext), dst)

def restore_maps():
    """Put the original first mission back. No-op when nothing is swapped."""
    if not swapped_map():
        return
    for ext in MAP_PARTS:
        src = os.path.join(MAP_BACKUP, MAP_SLOT + ext)
        if os.path.exists(src):
            _copy(src, os.path.join(MISSIONS, MAP_SLOT + ext))
    try:
        os.remove(MAP_MARKER)
    except OSError:
        pass

def apply_map(stem):
    """Drop `stem` into the campaign's entry slot. Always copies from the
    untouched sources, so repeated swaps cannot chain-corrupt the originals."""
    restore_maps()
    if not stem or stem == MAP_SLOT or stem not in CAMPAIGN_STEMS:
        return
    backup_slot()
    for ext in MAP_PARTS:
        _copy(os.path.join(MISSIONS, stem + ext),
              os.path.join(MISSIONS, MAP_SLOT + ext))
    with open(MAP_MARKER, "w") as f:
        f.write(stem)

# --------------------------------------------------- temporary HD-pack pause
# Vanilla mode means "no HD substitution". With dgVoodoo installed that is
# automatic. Without it we fall back to our own renderer, which would still
# swap in pack textures -- so the pack is paused for the duration of the run.
# A marker makes the pause recoverable: if the game or the launcher dies, the
# next start puts the pack back instead of leaving it silently disabled.
PACK_DIR_PATH = os.path.join(GAME_DIR, "hd_pack_hd")
PACK_OFF_PATH = PACK_DIR_PATH + ".off"
PACK_MARKER = os.path.join(BACKUP, "hd_pack_paused.txt")

def pause_hd_pack():
    """Returns True if it actually paused the pack (so it must be resumed)."""
    if not os.path.isdir(PACK_DIR_PATH):
        return False
    try:
        os.makedirs(BACKUP, exist_ok=True)
        os.rename(PACK_DIR_PATH, PACK_OFF_PATH)
        with open(PACK_MARKER, "w") as f:
            f.write("paused for a vanilla-mode run\n")
        return True
    except OSError:
        return False

def resume_hd_pack():
    if not os.path.exists(PACK_MARKER):
        return
    try:
        if os.path.isdir(PACK_OFF_PATH) and not os.path.isdir(PACK_DIR_PATH):
            os.rename(PACK_OFF_PATH, PACK_DIR_PATH)
        os.remove(PACK_MARKER)
    except OSError:
        pass

# ------------------------------------------------------------------ misc
def load_settings():
    try:
        with open(SETTINGS) as f:
            return json.load(f)
    except Exception:
        return {}

def save_settings(d):
    try:
        with open(SETTINGS, "w") as f:
            json.dump(d, f, indent=1)
    except Exception:
        pass

HD_HINT = ("Launches straight into -3dfx through our OpenGlide fork: HD texture pack "
           "(when enabled on the HD tab), native fullscreen, MSAA 8x, 2D sharpen and "
           "bump. This is the enhanced way to play.")
ORIG_HINT = ("The plain game: no HD substitution, no sharpen/bump, no resolution change — "
             "for A/B and for seeing vanilla texture mods (tab 3). Uses dgVoodoo if you "
             "placed its DLLs in the dgVoodoo\\ folder, otherwise our renderer with the "
             "HD pack paused. Pick the renderer path below.")

# ------------------------------------------------------------------ GUI
class Launcher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Incubation")
        self.minsize(1010, 740)
        self.cfg = load_settings()
        self.saved_mode = current_mode()
        self.q = queue.Queue()
        self.busy = False
        # a swap left over from a crashed run would otherwise sit in the
        # campaign slot forever — a swap is only ever meant to last one launch
        try:
            restore_maps()
        except OSError:
            pass
        ensure_dirs()      # backup/ and dgVoodoo/ (+ its readme) always present
        resume_hd_pack()   # a crashed vanilla run must not leave the pack off
        restore_ddraw()    # ... nor leave dgVoodoo's ddraw.dll in the game folder
        secure_our_build() # capture our glide2x.dll before anything overwrites it

        # The status bar must EXIST before any tab is built: a tab can report
        # status while it is still being constructed (VisnFrame does, on a fresh
        # install where nothing has been extracted yet). It is packed further
        # down so the layout is unchanged.
        self.status = ttk.Label(self, text="", anchor="w", relief="sunken", padding=(6, 2))

        # A missing Windows 10 patch means the game hangs with no window at all,
        # which is impossible to diagnose from the symptom. Say so up front,
        # across the whole window, rather than burying it in one tab.
        if not win10_patch_applied():
            warn = ttk.Frame(self, padding=(8, 6))
            warn.pack(fill="x", padx=8, pady=(8, 0))
            ttk.Label(warn, foreground="#b00000", wraplength=820, justify="left",
                      text="The Windows 10/11 sound patch does not look like it is applied. "
                           "Without it the stock game hangs at startup with no window — the "
                           "process just sits in Task Manager. Apply the patch first "
                           "(audio.dll + sound.dll), then relaunch."
                      ).pack(side="left")
            ttk.Button(warn, text="Get the patch",
                       command=lambda: webbrowser.open(WIN10_PATCH_URL)).pack(side="right")

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        nb.add(self._tab_play(nb), text="  Play  ")
        nb.add(self._tab_hd(nb), text="  HD textures  ")
        nb.add(self._tab_vanilla(nb), text="  Vanilla textures  ")
        nb.add(self._tab_debug(nb), text="  Debug  ")
        nb.add(self._tab_links(nb), text="  Links  ")
        nb.bind("<<NotebookTabChanged>>", lambda e: self._on_tab_change())

        self.status.pack(fill="x", padx=8, pady=(0, 8))

        # Pillow is what every texture tool reads and writes PNGs with. It can
        # easily end up installed into a *different* interpreter than the one
        # running us, so check here and quote the exact command for THIS one
        # rather than leaving people to guess which Python pip meant.
        try:
            import PIL  # noqa: F401
            self._set_status("Ready — installed renderer: %s" % active_renderer())
        except ImportError:
            msg = ("Pillow is missing — the texture tabs will not work. Install it into "
                   "THIS Python:   \"%s\" -m pip install Pillow" % PY)
            self._set_status(msg)
            self._log("\n! %s\n" % msg)

        self.on_mode_change()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(100, self._pump)

    # ---------------- Play tab
    def _tab_play(self, parent):
        f = ttk.Frame(parent, padding=12)

        ttk.Label(f, text="Mode").grid(row=0, column=0, sticky="nw", pady=4)
        self.mode_var = tk.StringVar(value=self.cfg.get("mode", "hd"))
        ttk.Radiobutton(f, text="HD  —  OpenGlide fork: HD textures, 2K fullscreen, MSAA",
                        variable=self.mode_var, value="hd", command=self.on_mode_change
                        ).grid(row=0, column=1, columnspan=3, sticky="w")
        ttk.Radiobutton(f, text="Original  —  plain 3dfx, no enhancements (via dgVoodoo if you supply one)",
                        variable=self.mode_var, value="orig", command=self.on_mode_change
                        ).grid(row=1, column=1, columnspan=3, sticky="w")
        self.mode_hint = ttk.Label(f, text="", foreground="#666", wraplength=660,
                                   justify="left")
        self.mode_hint.grid(row=2, column=1, columnspan=3, sticky="w", pady=(4, 0))

        # Which of the game's two renderer switches Vanilla mode uses. It matters
        # for dgVoodoo: only the DirectX path maps the mouse correctly.
        self.api_var = tk.StringVar(value=self.cfg.get("vanilla_api", "glide"))
        self.api_lbl = ttk.Label(f, text="Vanilla via")
        self.api_lbl.grid(row=3, column=0, sticky="w", pady=(8, 0))
        self.api_dx = ttk.Radiobutton(
            f, text="DirectX  —  the game's software renderer; with dgVoodoo the mouse works",
            variable=self.api_var, value="directx", command=self.on_mode_change)
        self.api_dx.grid(row=3, column=1, columnspan=3, sticky="w", pady=(8, 0))
        self.api_glide = ttk.Radiobutton(
            f, text="Glide  —  the 3dfx renderer, better picture; cursor is off under dgVoodoo",
            variable=self.api_var, value="glide", command=self.on_mode_change)
        self.api_glide.grid(row=4, column=1, columnspan=3, sticky="w")
        self.api_note = ttk.Label(f, text="", foreground="#666", wraplength=660,
                                  justify="left")
        self.api_note.grid(row=5, column=1, columnspan=3, sticky="w")

        ttk.Separator(f, orient="horizontal").grid(row=6, column=0, columnspan=4,
                                                   sticky="ew", pady=10)

        ttk.Label(f, text="Resolution").grid(row=7, column=0, sticky="w", pady=4)
        w, h, hz = self.saved_mode
        self.res_values = ["Native — don't change (%dx%d @ %dHz)" % (w, h, hz)]
        self.res_map = {self.res_values[0]: None}
        for mw, mh in list_modes():
            label = "%d x %d" % (mw, mh)
            self.res_values.append(label)
            self.res_map[label] = (mw, mh)
        self.res_var = tk.StringVar(value=self.cfg.get("res_label", self.res_values[0]))
        if self.res_var.get() not in self.res_map:
            self.res_var.set(self.res_values[0])
        self.res_combo = ttk.Combobox(f, textvariable=self.res_var, values=self.res_values,
                                      state="readonly", width=34)
        self.res_combo.grid(row=7, column=1, columnspan=3, sticky="w")
        ttk.Label(f, text="HD mode only; restored automatically when the game exits. "
                          "In Vanilla mode the wrapper manages the display itself.",
                  foreground="#666").grid(row=8, column=1, columnspan=3, sticky="w")

        # --- aspect: the game renders a fixed 640x480 (4:3) frame, so on a
        # widescreen monitor something has to give — bars or distortion.
        ttk.Label(f, text="Aspect").grid(row=9, column=0, sticky="w", pady=(8, 4))
        self.stretch_var = tk.BooleanVar(value=bool(self.cfg.get("stretch", False)))
        self.aspect_43 = ttk.Radiobutton(
            f, text="Keep 4:3 — black bars left and right, correct proportions",
            variable=self.stretch_var, value=False)
        self.aspect_43.grid(row=9, column=1, columnspan=3, sticky="w", pady=(8, 0))
        self.aspect_stretch = ttk.Radiobutton(
            f, text="Stretch to fill — no bars, image ~33 % wider on 16:9",
            variable=self.stretch_var, value=True)
        self.aspect_stretch.grid(row=10, column=1, columnspan=3, sticky="w")
        self.aspect_note = ttk.Label(f, text="", foreground="#666", wraplength=660,
                                     justify="left")
        self.aspect_note.grid(row=11, column=1, columnspan=3, sticky="w")

        ttk.Separator(f, orient="horizontal").grid(row=12, column=0, columnspan=4,
                                                   sticky="ew", pady=10)
        self.play_btn = ttk.Button(f, text="", command=self.launch)
        self.play_btn.grid(row=13, column=0, columnspan=4, sticky="ew", ipady=6)
        f.columnconfigure(3, weight=1)
        return f

    def on_mode_change(self):
        """The Play switch is the single source of truth: it decides which of the
        two texture workflows is live and greys the other one out, so there is
        never a second toggle competing with it."""
        hd = self.mode_var.get() == "hd"
        self.mode_hint.config(text=HD_HINT if hd else ORIG_HINT)
        self.res_combo.state(["!disabled", "readonly"] if hd else ["disabled"])
        self.play_btn.config(text="▶   Launch HD game" if hd
                             else "▶   Launch vanilla game")

        # Vanilla renderer switch. DirectX needs dgVoodoo's ddraw.dll, so the
        # option only offers itself when one is actually there -- and if the
        # setting was left on DirectX from a machine that had it, fall back to
        # Glide rather than launching into a path that cannot work.
        dx_ok = user_dgvoodoo_ddraw() is not None
        self.api_dx.state(["!disabled"] if (not hd and dx_ok) else ["disabled"])
        self.api_glide.state(["!disabled"] if not hd else ["disabled"])
        self.api_lbl.state(["!disabled"] if not hd else ["disabled"])
        if not dx_ok and self.api_var.get() == "directx":
            self.api_var.set("glide")
        if hd:
            self.api_note.config(text="")
        elif not dx_ok:
            self.api_note.config(
                text="DirectX needs dgVoodoo's ddraw.dll in the dgVoodoo\\ folder (same MS\\x86 "
                     "folder as its Glide2x.dll). Without it only the Glide path is available, "
                     "where dgVoodoo does not convert the game's cursor coordinates.")
        elif self.api_var.get() == "directx":
            self.api_note.config(
                text="Incubation.exe -directx: the game's own ENG3D.DLL software rasterizer, "
                     "presented through dgVoodoo's DirectDraw — the path the GOG launcher uses. "
                     "You should see the dgVoodoo logo. The ddraw.dll is copied in for the run "
                     "and removed when the game exits.")
        else:
            self.api_note.config(
                text="Incubation.exe -3dfx: ENG3DFX.DLL, the 3dfx renderer the game was built "
                     "around and the better-looking one (the 3dfx logo). With dgVoodoo the mouse "
                     "will not line up — its cursor handling is on the DirectX path.")

        # aspect is ours to control only in HD mode, and only if the installed
        # OpenGlide build actually understands the switch
        can_stretch = openglide_supports("INCU_STRETCH")
        for w in (self.aspect_43, self.aspect_stretch):
            w.state(["!disabled"] if (hd and can_stretch) else ["disabled"])
        if not hd:
            self.aspect_note.config(
                text="Vanilla mode: aspect is dgVoodoo's setting, not ours "
                     "(dgVoodoo.conf / dgVoodooCpl.exe).")
        elif not can_stretch:
            self.aspect_note.config(
                text="The installed OpenGlide build predates this option — it always keeps "
                     "4:3. The source supports it; rebuild glide2x.dll to enable the switch.")
        else:
            self.aspect_note.config(text="")

        if hasattr(self, "hd_widgets"):
            for w in self.hd_widgets:
                try:
                    w.state(["!disabled"] if hd else ["disabled"])
                except tk.TclError:
                    pass
            self.hd_note.config(
                text="" if hd else
                "Inactive — Play mode is set to Vanilla, which renders through stock "
                "dgVoodoo and ignores the HD pack. Switch Play to HD to use this tab.")
        if hasattr(self, "visn"):
            self.visn.set_enabled(not hd)
            self.van_note.config(
                text="" if not hd else
                "Inactive — Play mode is set to HD, where our renderer substitutes the "
                "HD pack and your .lib edits would not be visible. Switch Play to "
                "Vanilla to use this tab.")

    # ---------------- HD textures tab
    def _tab_hd(self, parent):
        f = ttk.Frame(parent, padding=12)

        top = ttk.Frame(f)
        top.grid(row=0, column=0, columnspan=4, sticky="ew")
        ttk.Label(top, text="The game keeps loading its 256×256 originals; our OpenGlide "
                            "substitutes your upscaled art at draw time, keyed by texture "
                            "hash. Everything on this tab applies to HD mode only.",
                  foreground="#444", wraplength=620, justify="left").pack(side="left")
        ttk.Button(top, text="Manual",
                   command=lambda: self.show_manual("MANUAL_HD_TEXTURES.md",
                                                    "HD textures — manual")
                   ).pack(side="right", anchor="n")

        self.hd_note = ttk.Label(f, text="", foreground="#b00000", wraplength=620,
                                 justify="left")
        self.hd_note.grid(row=1, column=0, columnspan=4, sticky="w", pady=(8, 0))

        self.hd_var = tk.BooleanVar(value=hd_pack_enabled())
        self.hd_check = ttk.Checkbutton(f, text="HD textures", variable=self.hd_var,
                                        command=self.toggle_hd)
        self.hd_check.grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Label(f, text="(off = original 256×256 textures, for A/B)",
                  foreground="#666").grid(row=2, column=2, columnspan=2,
                                          sticky="w", pady=(10, 0))

        self.sharp_var = tk.DoubleVar(value=float(self.cfg.get("sharp", 0.15)))
        sharp_scale = self._slider(f, 3, "2D sharpen", self.sharp_var, 0.0, 0.60,
                                   "menus / briefings — 0 = off; HD mode only")
        self.bump_var = tk.DoubleVar(value=float(self.cfg.get("bump", 1.0)))
        bump_scale = self._slider(f, 4, "Bump strength", self.bump_var, 0.0, 2.0,
                                  "needs a <hash>_n.rgba normal map — 0 = off")

        self.diag_var = tk.BooleanVar(value=False)
        diag_check = ttk.Checkbutton(f, text="Bump diagnostic (render the normal map)",
                                     variable=self.diag_var)
        diag_check.grid(row=5, column=1, columnspan=3, sticky="w")

        ttk.Separator(f, orient="horizontal").grid(row=6, column=0, columnspan=4,
                                                   sticky="ew", pady=10)

        steps = [
            ("1. Extract textures",  ["extract"],   "game → hd_work/source (306 PNGs)"),
            ("2. Pack upscaled",     ["pack"],      "hd_work/upscaled → hd_pack_hd (+ refresh normal maps)"),
            ("Generate normal maps", ["normalmap"], "for bump; from hd_work/upscaled"),
            ("Extract 2D UI",        ["extract2d"], "Libs/*.LIB sprites → hd_work_2d/source"),
            ("Show status",          ["status"],    "extracted / upscaled / packed counts"),
        ]
        step_btns = []
        for i, (text, args, hint) in enumerate(steps):
            b = ttk.Button(f, text=text, width=22, command=lambda a=args: self.run_tool(a))
            b.grid(row=7 + i, column=0, pady=3, sticky="w")
            step_btns.append(b)
            ttk.Label(f, text=hint, foreground="#666"
                      ).grid(row=7 + i, column=1, columnspan=3, sticky="w", padx=8)

        ttk.Separator(f, orient="horizontal").grid(row=12, column=0, columnspan=4,
                                                   sticky="ew", pady=8)
        folders = ttk.Frame(f)
        folders.grid(row=13, column=0, columnspan=4, sticky="w")
        folder_btns = []
        for text, path in (("Open source", "hd_work/source"),
                           ("Open upscaled", "hd_work/upscaled"),
                           ("Open pack", "hd_pack_hd")):
            b = ttk.Button(folders, text=text, command=lambda p=path: self.open_folder(p))
            b.pack(side="left", padx=(0, 6))
            folder_btns.append(b)

        self.log = scrolledtext.ScrolledText(f, height=10, width=80, state="disabled",
                                             font=("Consolas", 9))
        self.log.grid(row=14, column=0, columnspan=4, pady=(10, 0), sticky="nsew")
        f.rowconfigure(14, weight=1)
        f.columnconfigure(3, weight=1)

        # everything the Play switch greys out when Vanilla mode is selected
        # (the Manual button deliberately stays live — reading is always fine)
        self.hd_widgets = [self.hd_check, sharp_scale, bump_scale,
                           diag_check] + step_btns + folder_btns
        return f

    @staticmethod
    def _fmt(v):
        return "off" if v < 0.005 else "%.2f" % v

    def _slider(self, f, row, label, var, lo, hi, hint):
        """label | slider | numeric value (own column, so it can't be hidden) | hint"""
        ttk.Label(f, text=label).grid(row=row, column=0, sticky="w", pady=4)
        val = ttk.Label(f, text=self._fmt(var.get()), width=4, anchor="e",
                        font=("Consolas", 9))
        scale = ttk.Scale(f, from_=lo, to=hi, variable=var, length=200,
                          command=lambda _v, l=val: l.config(text=self._fmt(float(_v))))
        scale.grid(row=row, column=1, sticky="w")
        val.grid(row=row, column=2, sticky="w", padx=(8, 0))
        ttk.Label(f, text=hint, foreground="#666").grid(row=row, column=3, sticky="w", padx=(10, 0))
        return scale

    # ---------------- Vanilla textures tab
    def _tab_vanilla(self, parent):
        f = ttk.Frame(parent, padding=(12, 12, 12, 0))
        bar = ttk.Frame(f)
        bar.pack(fill="x")
        ttk.Label(bar, text="Edit the game's own 256×256 textures and repack them into "
                            "texture.lib — the mod works in the vanilla game, no custom "
                            "renderer needed.",
                  foreground="#444", wraplength=560, justify="left").pack(side="left")
        ttk.Button(bar, text="Manual",
                   command=lambda: self.show_manual("MANUAL_VANILLA_TEXTURES.md",
                                                    "Vanilla textures — manual")
                   ).pack(side="right", anchor="n")

        self.van_note = ttk.Label(f, text="", foreground="#b00000", wraplength=900,
                                  justify="left")
        self.van_note.pack(fill="x", pady=(6, 0))

        # the Play switch owns the HD/Vanilla decision, so no second HD toggle here
        self.visn = VisnFrame(f, status_cb=self._set_status, show_hd_toggle=False)
        self.visn.pack(fill="both", expand=True)
        return f

    # ---------------- Debug tab
    def _tab_debug(self, parent):
        f = ttk.Frame(parent, padding=12)

        ttk.Label(f, text="Test map").grid(row=0, column=0, sticky="w", pady=4)
        self.map_labels = {map_label(s): s for s in list_maps()}
        want = self.cfg.get("map", MAP_SLOT)
        self.map_var = tk.StringVar(
            value=next((l for l, s in self.map_labels.items() if s == want),
                       map_label(MAP_SLOT)))
        ttk.Combobox(f, textvariable=self.map_var, values=list(self.map_labels),
                     state="readonly", width=14).grid(row=0, column=1, sticky="w")
        ttk.Button(f, text="Restore originals", command=self.restore_map_slot
                   ).grid(row=0, column=2, sticky="w", padx=(8, 0))
        ttk.Label(f, text="start a New Campaign to play it — the mission is swapped into "
                          "the %s slot at launch and restored on exit; works in both HD "
                          "and Original modes" % MAP_SLOT,
                  foreground="#666", wraplength=640, justify="left"
                  ).grid(row=1, column=1, columnspan=3, sticky="w")

        ttk.Separator(f, orient="horizontal").grid(row=2, column=0, columnspan=4,
                                                   sticky="ew", pady=10)

        ttk.Label(f, text="Developer tools").grid(row=3, column=0, sticky="w")
        ttk.Button(f, text="Original launcher with -debugx", width=30,
                   command=self.launch_debugx).grid(row=3, column=1, columnspan=2, sticky="w")
        ttk.Label(f, text="Blue Byte's own in-exe tools: Debug A, Librarytool, MapDesigner, "
                          "Systeminfos. Uses whatever renderer is installed; no map swap, "
                          "no resolution change.",
                  foreground="#666", wraplength=640, justify="left"
                  ).grid(row=4, column=1, columnspan=3, sticky="w")

        ttk.Separator(f, orient="horizontal").grid(row=5, column=0, columnspan=4,
                                                   sticky="ew", pady=10)

        ttk.Label(f, text="Renderer installed").grid(row=6, column=0, sticky="w")
        self.rend_lbl = ttk.Label(f, text=active_renderer(), foreground="#0a0")
        self.rend_lbl.grid(row=6, column=1, sticky="w", padx=8)
        ttk.Button(f, text="Set dgVoodoo from a file…", width=30,
                   command=self.install_dgvoodoo_file
                   ).grid(row=7, column=0, columnspan=2, pady=4, sticky="w")
        ttk.Button(f, text="Open the dgVoodoo folder", width=30,
                   command=lambda: self.open_folder("dgVoodoo")
                   ).grid(row=7, column=2, sticky="w", padx=(8, 0))
        ttk.Label(f, text="Vanilla mode uses dgVoodoo only if you place its 32-bit DLLs in "
                          "the dgVoodoo\\ folder (see the readme there): ddraw.dll for "
                          "\"Vanilla via DirectX\", Glide2x.dll for \"Vanilla via Glide\". "
                          "Otherwise Vanilla runs our renderer with the HD pack paused. "
                          "The Play switch installs whichever is needed at launch — you "
                          "normally never touch this.",
                  foreground="#666", wraplength=640, justify="left"
                  ).grid(row=8, column=0, columnspan=4, sticky="w", pady=(4, 0))

        ttk.Separator(f, orient="horizontal").grid(row=10, column=0, columnspan=4,
                                                   sticky="ew", pady=10)
        ttk.Button(f, text="Open game folder",
                   command=lambda: self.open_folder(".")).grid(row=11, column=0, sticky="w")
        ttk.Button(f, text="What the launcher does automatically",
                   command=lambda: self.show_manual("MANUAL_LAUNCHER.md",
                                                    "Launcher — automatic behaviour")
                   ).grid(row=11, column=1, columnspan=2, sticky="w", padx=(8, 0))
        ttk.Label(f, text="Every check, swap, rename and rollback the launcher performs on "
                          "its own — worth reading before debugging anything odd.",
                  foreground="#666", wraplength=640, justify="left"
                  ).grid(row=12, column=0, columnspan=4, sticky="w", pady=(4, 0))
        return f

    # ---------------- Links tab
    def _tab_links(self, parent):
        f = ttk.Frame(parent, padding=12)
        ttk.Label(f, text="Everything this mod can need, from its author's own site. "
                          "Avoid look-alike sites and \"free download\" mirrors.",
                  foreground="#444", wraplength=880, justify="left"
                  ).pack(anchor="w", pady=(0, 10))

        groups = [
            ("Required", [
                ("Windows 10/11 sound patch",
                 "Stock Incubation hangs at startup on Win10/11. Apply this FIRST — it "
                 "replaces audio.dll and sound.dll. Part of the 25th Anniversary Mod.",
                 WIN10_PATCH_URL),
                ("Python for Windows (32-bit)",
                 "Any 3.8+, but it must be the 32-bit build; keep \"tcl/tk and IDLE\" ticked. "
                 "The HD pipeline loads the game's 32-bit Eng3d.dll.",
                 "https://www.python.org/downloads/windows/"),
                ("Incubation (Battle Isle Platinum)",
                 "The game itself — this mod ships none of it.",
                 "https://www.gog.com/en/game/battle_isle_platinum"),
            ]),
            ("For the HD texture pipeline", [
                ("Pillow (PNG support)",
                 "Every texture read/write. Install with:  py -3-32 -m pip install Pillow",
                 "https://pypi.org/project/pillow/"),
                ("NumPy (optional)",
                 "Only for \"Generate normal maps\" (the bump effect). Everything else "
                 "works without it.",
                 "https://pypi.org/project/numpy/"),
                ("Upscayl — AI upscaler",
                 "The easiest way to make the bigger textures. Any upscaler works.",
                 "https://upscayl.org"),
                ("Real-ESRGAN / chaiNNer",
                 "Other upscalers, more control.",
                 "https://github.com/chaiNNer-org/chaiNNer"),
            ]),
            ("Optional", [
                ("dgVoodoo 2 (Dege)",
                 "The stock wrapper Vanilla mode can use. Cannot be bundled — its licence "
                 "forbids redistribution. Take both 32-bit DLLs from MS\\x86: ddraw.dll "
                 "(DirectX path, the one where the mouse works) and Glide2x.dll.",
                 "https://dege.freeweb.hu/"),
                ("OpenGlide",
                 "The renderer this fork is built on.",
                 "https://openglide.sourceforge.net/"),
            ]),
            ("This project", [
                ("Incubation HD Renderer",
                 "Releases, source, format documentation, issue reports.",
                 "https://github.com/Sonatix/Incubation-HD-Renderer"),
            ]),
        ]

        for title, items in groups:
            box = ttk.LabelFrame(f, text=title, padding=8)
            box.pack(fill="x", pady=(0, 8))
            for row, (name, why, url) in enumerate(items):
                ttk.Button(box, text=name, width=30,
                           command=lambda u=url: webbrowser.open(u)
                           ).grid(row=row, column=0, sticky="w", pady=2)
                ttk.Label(box, text=why, foreground="#666", wraplength=620, justify="left"
                          ).grid(row=row, column=1, sticky="w", padx=10)
        return f

    # ---------------- shared plumbing
    def _on_tab_change(self):
        """Cheap cross-tab sync: the HD-pack folder and the installed dll can be
        changed from more than one place."""
        try:
            self.hd_var.set(hd_pack_enabled())
            self.rend_lbl.config(text=active_renderer())
            if hasattr(self, "visn") and hasattr(self.visn, "refresh_state"):
                self.visn.refresh_state()
        except tk.TclError:
            pass

    def _set_status(self, msg):
        # Belt and braces: a child frame may call back during construction or
        # after the window is destroyed, when there is nothing to write to.
        status = getattr(self, "status", None)
        if status is None:
            return
        try:
            status.config(text=msg)
        except tk.TclError:
            pass

    def _log(self, line):
        self.log.config(state="normal")
        self.log.insert("end", line)
        self.log.see("end")
        self.log.config(state="disabled")

    def _pump(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self._log(payload)
                elif kind == "status":
                    self._set_status(payload)
                elif kind == "done":
                    self.busy = False
                    self.play_btn.config(state="normal")
                    self.hd_var.set(hd_pack_enabled())
                    self.rend_lbl.config(text=active_renderer())
        except queue.Empty:
            pass
        except tk.TclError:
            return
        self.after(100, self._pump)

    def open_folder(self, rel):
        path = os.path.join(GAME_DIR, rel.replace("/", os.sep))
        os.makedirs(path, exist_ok=True)
        os.startfile(path)

    def show_manual(self, name, title):
        path = os.path.join(DOCS, name)
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError as e:
            messagebox.showerror("Manual", "Could not open %s:\n%s" % (path, e))
            return
        win = tk.Toplevel(self)
        win.title(title)
        st = scrolledtext.ScrolledText(win, width=100, height=40, wrap="word",
                                       font=("Segoe UI", 10), padx=12, pady=8)
        st.insert("1.0", text)
        st.config(state="disabled")
        st.pack(fill="both", expand=True)

    def run_tool(self, args):
        if self.busy:
            return
        self.busy = True
        self.q.put(("status", "running: hd_tool %s ..." % " ".join(args)))
        self._log("\n$ hd_tool %s\n" % " ".join(args))

        def work():
            try:
                # -u: unbuffered, so progress lines stream in live instead of
                # arriving all at once when the child exits.
                p = subprocess.Popen([PY, "-u", HD_TOOL] + args, cwd=GAME_DIR,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, bufsize=1,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
                for line in p.stdout:
                    self.q.put(("log", line))
                p.wait()
                self.q.put(("status", "hd_tool %s finished (exit %d)" % (args[0], p.returncode)))
            except Exception as e:
                self.q.put(("log", "ERROR: %s\n" % e))
                self.q.put(("status", "failed"))
            self.q.put(("done", None))

        threading.Thread(target=work, daemon=True).start()

    # ---------------- actions
    def toggle_hd(self):
        self.run_tool(["on"] if self.hd_var.get() else ["off"])

    def restore_map_slot(self):
        try:
            restore_maps()
        except OSError as e:
            messagebox.showerror("In use", "%s\n\nClose the game first." % e)
            return
        self.map_var.set(map_label(MAP_SLOT))
        self._set_status("Original mission files restored")

    def our_build_path(self):
        """Path to our OpenGlide build, making sure it is in the backup first.
        Returns None only if it is nowhere to be found (a broken install)."""
        dst = os.path.join(BACKUP, "glide2x.dll.openglide")
        if os.path.exists(dst) and classify_glide(dst) == "ours":
            return dst
        live = os.path.join(GAME_DIR, "glide2x.dll")
        if classify_glide(live) == "ours":
            try:
                os.makedirs(BACKUP, exist_ok=True)
                _copy(live, dst)
                return dst
            except OSError:
                return live
        return None

    def install_glide(self, src):
        """Copy `src` over the live glide2x.dll. Secures our own build into the
        backup first, so a swap can never lose it."""
        if not src or not os.path.exists(src):
            return False
        tgt = os.path.join(GAME_DIR, "glide2x.dll")
        try:
            if (os.path.exists(tgt)
                    and os.path.getsize(tgt) == os.path.getsize(src)
                    and open(tgt, "rb").read() == open(src, "rb").read()):
                return True                      # already installed
            secure_our_build()
            _copy(src, tgt)
        except PermissionError:
            messagebox.showerror("In use", "Close the game first.")
            return False
        except OSError as e:
            messagebox.showerror("Renderer", str(e))
            return False
        self.rend_lbl.config(text=active_renderer())
        return True

    def _no_build_error(self):
        messagebox.showerror(
            "Renderer missing",
            "Our glide2x.dll could not be found. Re-copy game_files\\glide2x.dll "
            "from the download into the game folder, then try again.")

    def install_dgvoodoo_file(self):
        """Pick dgVoodoo's Glide2x.dll or ddraw.dll from wherever it was unzipped,
        validate it by content and copy it into the dgVoodoo/ folder.

        Both are useful and they serve different Vanilla paths: Glide2x.dll for
        -3dfx, ddraw.dll for -directx (the one where the mouse maps correctly)."""
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Select dgVoodoo's Glide2x.dll or ddraw.dll (32-bit, from MS\\x86)",
            filetypes=[("dgVoodoo DLL", "*.dll"), ("All files", "*.*")])
        if not path:
            return
        kind = classify_glide(path)
        if kind == "ours":
            messagebox.showerror(
                "That is our renderer",
                "This file is our OpenGlide build, not dgVoodoo. Pick dgVoodoo's own "
                "Glide2x.dll or ddraw.dll.")
            return
        if kind == "thirdparty":
            target, what = "Glide2x.dll", "Vanilla via Glide will use it."
        elif classify_ddraw(path) == "dgvoodoo":
            target, what = "ddraw.dll", "Vanilla via DirectX will use it."
        else:
            messagebox.showerror(
                "Not a dgVoodoo DLL",
                "%s is neither a Glide 2.x wrapper nor dgVoodoo's DirectDraw. In the "
                "dgVoodoo download pick MS\\x86\\Glide2x.dll or MS\\x86\\ddraw.dll — the "
                "32-bit ones, not x64, and not Glide.dll or Glide3x.dll."
                % os.path.basename(path))
            return
        try:
            ensure_dirs()
            _copy(path, os.path.join(DGV_DIR, target))
        except OSError as e:
            messagebox.showerror("Install failed", str(e))
            return
        self.on_mode_change()                    # DirectX may have become available
        self._set_status("dgVoodoo %s installed — %s" % (target, what))
        messagebox.showinfo("dgVoodoo installed", what)

    def launch_debugx(self):
        if not os.path.exists(GAME_EXE):
            messagebox.showerror("Not found", GAME_EXE)
            return
        try:
            subprocess.Popen([GAME_EXE, "-debugx"], cwd=GAME_DIR)
            self._set_status("Started Incubation.exe -debugx")
        except OSError as e:
            messagebox.showerror("Launch failed", str(e))

    def _save(self):
        save_settings({"res_label": self.res_var.get(),
                       "sharp": round(self.sharp_var.get(), 3),
                       "bump": round(self.bump_var.get(), 3),
                       "map": self.map_labels.get(self.map_var.get(), MAP_SLOT),
                       "mode": self.mode_var.get(),
                       "vanilla_api": self.api_var.get(),
                       "stretch": bool(self.stretch_var.get())})

    def launch(self):
        if self.busy:
            return
        mode = self.mode_var.get()
        if not os.path.exists(GAME_EXE):
            messagebox.showerror("Not found", GAME_EXE)
            return
        paused_pack = False
        installed_ddraw = False
        if mode == "hd":
            src = self.our_build_path()
            if not src or not self.install_glide(src):
                if not src:
                    self._no_build_error()
                return
        elif self.api_var.get() == "directx" and user_dgvoodoo_ddraw():
            # Vanilla via DirectX: the game's own -directx path, wrapped by
            # dgVoodoo's ddraw.dll. glide2x is irrelevant here and is left alone.
            if not install_ddraw(user_dgvoodoo_ddraw()):
                return
            installed_ddraw = True
        else:
            # Vanilla via Glide: dgVoodoo's Glide2x.dll if the user provided one
            # in dgVoodoo/, otherwise our own renderer with the HD pack paused
            # (looks like the plain game and never installs a wrong DLL). We never
            # touch the game's stock glide.dll/glide3x.dll.
            dgv = user_dgvoodoo()
            if dgv:
                if not self.install_glide(dgv):
                    return
            else:
                src = self.our_build_path()
                if not src or not self.install_glide(src):
                    if not src:
                        self._no_build_error()
                    return
                paused_pack = pause_hd_pack()
        self.busy = True
        self.play_btn.config(state="disabled")

        # The game takes its renderer from the command line: -3dfx goes through
        # ENG3DFX.DLL to a Glide wrapper, -directx through DDRAW.DLL. Either one
        # skips the 1997 CD check that bare Incubation.exe still performs, and
        # neither needs elevation (GOG's launcher.exe does, via Windows'
        # installer-name heuristic). HD is always -3dfx, since our fork is a Glide
        # wrapper; Vanilla follows the Play tab's "Vanilla via" switch.
        env = os.environ.copy()
        for k in ("INCU_SHARP", "INCU_BUMP", "INCU_STRETCH", "__COMPAT_LAYER"):
            env.pop(k, None)
        if mode == "hd":
            env["__COMPAT_LAYER"] = "HIGHDPIAWARE"      # true physical resolution
            bump = 99.0 if self.diag_var.get() else self.bump_var.get()
            env["INCU_SHARP"] = "%.3f" % self.sharp_var.get()
            env["INCU_BUMP"] = "%.3f" % bump
            env["INCU_STRETCH"] = "1" if self.stretch_var.get() else "0"
        args = [GAME_EXE, "-directx" if installed_ddraw else "-3dfx"]

        self._save()

        # swap the chosen mission into the campaign slot for this run only
        try:
            apply_map(self.map_labels.get(self.map_var.get()))
        except OSError as e:
            self.busy = False
            self.play_btn.config(state="normal")
            messagebox.showerror("Map swap failed",
                                 "%s\n\nClose the game if it is running." % e)
            return

        changed = False
        want = None
        if mode == "hd":
            want = self.res_map.get(self.res_var.get())
            changed = bool(want) and want != self.saved_mode[:2] and set_mode(*want)
        self.q.put(("status", "playing%s ..." % (" @ %dx%d" % want if changed else "")))

        def work():
            try:
                subprocess.Popen(args, cwd=GAME_DIR, env=env).wait()
            except Exception as e:
                self.q.put(("log", "launch error: %s\n" % e))
            finally:
                if changed:                      # always put the desktop back
                    restore_mode(self.saved_mode)
                try:                             # ... and the original mission
                    restore_maps()
                except OSError as e:
                    self.q.put(("log", "map restore failed: %s\n" % e))
                if paused_pack:                  # ... and the HD pack
                    resume_hd_pack()
                if installed_ddraw:              # ... and the game's own ddraw
                    restore_ddraw()
                self.q.put(("status", "Ready — installed renderer: %s" % active_renderer()))
                self.q.put(("done", None))

        threading.Thread(target=work, daemon=True).start()

    def on_close(self):
        self._save()
        restore_mode(self.saved_mode)            # never leave the desktop switched
        self.destroy()

if __name__ == "__main__":
    os.chdir(GAME_DIR)
    Launcher().mainloop()
