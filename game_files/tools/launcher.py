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
import os, sys, json, queue, ctypes, threading, subprocess
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
    if not os.path.exists(g):
        return "missing"
    size = os.path.getsize(g)
    for which, label in (("dgvoodoo", "dgVoodoo (stock, no HD)"),
                         ("openglide", "OpenGlide (HD)")):
        b = os.path.join(BACKUP, "glide2x.dll.%s" % which)
        if os.path.exists(b) and size == os.path.getsize(b):
            return label
    return "OpenGlide (dev build)"

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
ORIG_HINT = ("Runs Incubation.exe -3dfx through the stock dgVoodoo wrapper — the vanilla "
             "3dfx renderer, no HD substitution, no sharpen/bump, no resolution change. "
             "Use this for A/B and to see vanilla texture mods (tab 3).")

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

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        nb.add(self._tab_play(nb), text="  Play  ")
        nb.add(self._tab_hd(nb), text="  HD textures  ")
        nb.add(self._tab_vanilla(nb), text="  Vanilla textures  ")
        nb.add(self._tab_debug(nb), text="  Debug  ")
        nb.bind("<<NotebookTabChanged>>", lambda e: self._on_tab_change())

        self.status = ttk.Label(self, text="", anchor="w", relief="sunken", padding=(6, 2))
        self.status.pack(fill="x", padx=8, pady=(0, 8))
        self._set_status("Ready — installed renderer: %s" % active_renderer())

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
        ttk.Radiobutton(f, text="Original  —  vanilla 3dfx via stock dgVoodoo, no enhancements",
                        variable=self.mode_var, value="orig", command=self.on_mode_change
                        ).grid(row=1, column=1, columnspan=3, sticky="w")
        self.mode_hint = ttk.Label(f, text="", foreground="#666", wraplength=660,
                                   justify="left")
        self.mode_hint.grid(row=2, column=1, columnspan=3, sticky="w", pady=(4, 0))

        ttk.Separator(f, orient="horizontal").grid(row=3, column=0, columnspan=4,
                                                   sticky="ew", pady=10)

        ttk.Label(f, text="Resolution").grid(row=4, column=0, sticky="w", pady=4)
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
        self.res_combo.grid(row=4, column=1, columnspan=3, sticky="w")
        ttk.Label(f, text="HD mode only; restored automatically when the game exits. "
                          "In Vanilla mode dgVoodoo manages the display itself.",
                  foreground="#666").grid(row=5, column=1, columnspan=3, sticky="w")

        # --- aspect: the game renders a fixed 640x480 (4:3) frame, so on a
        # widescreen monitor something has to give — bars or distortion.
        ttk.Label(f, text="Aspect").grid(row=6, column=0, sticky="w", pady=(8, 4))
        self.stretch_var = tk.BooleanVar(value=bool(self.cfg.get("stretch", False)))
        self.aspect_43 = ttk.Radiobutton(
            f, text="Keep 4:3 — black bars left and right, correct proportions",
            variable=self.stretch_var, value=False)
        self.aspect_43.grid(row=6, column=1, columnspan=3, sticky="w", pady=(8, 0))
        self.aspect_stretch = ttk.Radiobutton(
            f, text="Stretch to fill — no bars, image ~33 % wider on 16:9",
            variable=self.stretch_var, value=True)
        self.aspect_stretch.grid(row=7, column=1, columnspan=3, sticky="w")
        self.aspect_note = ttk.Label(f, text="", foreground="#666", wraplength=660,
                                     justify="left")
        self.aspect_note.grid(row=8, column=1, columnspan=3, sticky="w")

        ttk.Separator(f, orient="horizontal").grid(row=9, column=0, columnspan=4,
                                                   sticky="ew", pady=10)
        self.play_btn = ttk.Button(f, text="", command=self.launch)
        self.play_btn.grid(row=10, column=0, columnspan=4, sticky="ew", ipady=6)
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
        ttk.Button(f, text="Install OpenGlide (HD)", width=30,
                   command=lambda: self.manual_swap("openglide")
                   ).grid(row=7, column=0, columnspan=2, pady=4, sticky="w")
        ttk.Button(f, text="Install dgVoodoo (stock, no HD)", width=30,
                   command=lambda: self.manual_swap("dgvoodoo")
                   ).grid(row=8, column=0, columnspan=2, pady=4, sticky="w")
        ttk.Label(f, text="Normally you never touch these — the Play switch installs the "
                          "right one at launch. A dev build of OpenGlide that matches "
                          "neither backup is stashed to backup/glide2x.dll.openglide "
                          "before dgVoodoo replaces it, so builds are never lost.",
                  foreground="#666", wraplength=640, justify="left"
                  ).grid(row=9, column=0, columnspan=4, sticky="w")

        ttk.Separator(f, orient="horizontal").grid(row=10, column=0, columnspan=4,
                                                   sticky="ew", pady=10)
        ttk.Button(f, text="Open game folder",
                   command=lambda: self.open_folder(".")).grid(row=11, column=0, sticky="w")
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
        self.status.config(text=msg)

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

    def ensure_renderer(self, which):
        """Make sure the right glide wrapper is installed before launch.

        A dll that matches neither backup is assumed to be a fresh OpenGlide dev
        build: for an HD launch it is simply kept; before dgVoodoo replaces it,
        it is stashed as the new canonical .openglide backup so a build is never
        lost."""
        tgt = os.path.join(GAME_DIR, "glide2x.dll")
        src = os.path.join(BACKUP, "glide2x.dll.%s" % which)
        if not os.path.exists(src):
            messagebox.showerror("Missing backup", "Not found:\n%s" % src)
            return False
        try:
            cur = os.path.getsize(tgt) if os.path.exists(tgt) else -1
            if cur == os.path.getsize(src):
                return True
            known = [os.path.getsize(p) for p in
                     (os.path.join(BACKUP, "glide2x.dll.openglide"),
                      os.path.join(BACKUP, "glide2x.dll.dgvoodoo"))
                     if os.path.exists(p)]
            if cur > 0 and cur not in known:
                if which == "openglide":
                    return True          # unknown dll here = a newer fork build
                _copy(tgt, os.path.join(BACKUP, "glide2x.dll.openglide"))
            _copy(src, tgt)
        except PermissionError:
            messagebox.showerror("In use", "Close the game first.")
            return False
        self.rend_lbl.config(text=active_renderer())
        return True

    def manual_swap(self, which):
        if self.ensure_renderer(which):
            self._set_status("Renderer installed: %s" % active_renderer())

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
                       "stretch": bool(self.stretch_var.get())})

    def launch(self):
        if self.busy:
            return
        mode = self.mode_var.get()
        if not os.path.exists(GAME_EXE):
            messagebox.showerror("Not found", GAME_EXE)
            return
        if not self.ensure_renderer("openglide" if mode == "hd" else "dgvoodoo"):
            return
        self.busy = True
        self.play_btn.config(state="disabled")

        # Both modes launch Incubation.exe -3dfx: the -3dfx arg skips the game's
        # 1997 CD check (bare Incubation.exe would hit it) and needs no elevation
        # (GOG's launcher.exe does, via Windows' installer-name heuristic). The
        # ONLY difference is the renderer and the HD env — HD uses our OpenGlide
        # with INCU_* and a resolution change; Original uses stock dgVoodoo with
        # none of that.
        env = os.environ.copy()
        for k in ("INCU_SHARP", "INCU_BUMP", "INCU_STRETCH", "__COMPAT_LAYER"):
            env.pop(k, None)
        if mode == "hd":
            env["__COMPAT_LAYER"] = "HIGHDPIAWARE"      # true physical resolution
            bump = 99.0 if self.diag_var.get() else self.bump_var.get()
            env["INCU_SHARP"] = "%.3f" % self.sharp_var.get()
            env["INCU_BUMP"] = "%.3f" % bump
            env["INCU_STRETCH"] = "1" if self.stretch_var.get() else "0"
        args = [GAME_EXE, "-3dfx"]

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
