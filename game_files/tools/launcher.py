#!/usr/bin/env python3
"""Incubation HD launcher.

One place to launch the game and drive the HD pipeline:
  * pick a display resolution (restored reliably when the game exits)
  * toggle the HD texture pack, 2D sharpen (INCU_SHARP), bump (INCU_BUMP)
  * run the hd_tool steps (extract / pack / normalmap / extract2d)
  * swap between our OpenGlide (HD) and the dgVoodoo fallback (no HD)

Run with the 32-bit Python (hd_tool's `extract` needs it). Settings persist to
launcher.json in the game folder.
"""
import os, sys, json, queue, ctypes, threading, subprocess
from ctypes import wintypes
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

GAME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HD_TOOL  = os.path.join(GAME_DIR, "tools", "hd_tool.py")
SETTINGS = os.path.join(GAME_DIR, "launcher.json")
GAME_EXE = os.path.join(GAME_DIR, "Incubation.exe")
BACKUP   = os.path.join(GAME_DIR, "backup")
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

# ------------------------------------------------------------------ helpers
def hd_pack_enabled():
    return os.path.isdir(os.path.join(GAME_DIR, "hd_pack_hd"))

def active_renderer():
    g = os.path.join(GAME_DIR, "glide2x.dll")
    if not os.path.exists(g):
        return "missing"
    size = os.path.getsize(g)
    dgv = os.path.join(BACKUP, "glide2x.dll.dgvoodoo")
    if os.path.exists(dgv) and size == os.path.getsize(dgv):
        return "dgVoodoo (no HD)"
    return "OpenGlide (HD)"

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

# ------------------------------------------------------------------ GUI
class Launcher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Incubation HD")
        self.resizable(False, False)
        self.cfg = load_settings()
        self.saved_mode = current_mode()
        self.q = queue.Queue()
        self.busy = False

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        nb.add(self._tab_play(nb), text="  Play  ")
        nb.add(self._tab_textures(nb), text="  Textures  ")
        nb.add(self._tab_advanced(nb), text="  Advanced  ")

        self.status = ttk.Label(self, text="", anchor="w", relief="sunken", padding=(6, 2))
        self.status.pack(fill="x", padx=8, pady=(0, 8))
        self._set_status("Ready — %s" % active_renderer())

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(100, self._pump)

    # ---------------- Play tab
    def _tab_play(self, parent):
        f = ttk.Frame(parent, padding=12)

        ttk.Label(f, text="Resolution").grid(row=0, column=0, sticky="w", pady=4)
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
        ttk.Combobox(f, textvariable=self.res_var, values=self.res_values,
                     state="readonly", width=34).grid(row=0, column=1, columnspan=3, sticky="w")
        ttk.Label(f, text="Resolution is restored automatically when the game exits.",
                  foreground="#666").grid(row=1, column=1, columnspan=3, sticky="w")

        ttk.Separator(f, orient="horizontal").grid(row=2, column=0, columnspan=4,
                                                   sticky="ew", pady=10)

        self.hd_var = tk.BooleanVar(value=hd_pack_enabled())
        ttk.Checkbutton(f, text="HD textures", variable=self.hd_var,
                        command=self.toggle_hd).grid(row=3, column=0, columnspan=2, sticky="w")
        ttk.Label(f, text="(off = original 256×256 textures, for A/B)",
                  foreground="#666").grid(row=3, column=2, columnspan=2, sticky="w")

        self.sharp_var = tk.DoubleVar(value=float(self.cfg.get("sharp", 0.15)))
        self._slider(f, 4, "2D sharpen", self.sharp_var, 0.0, 0.60,
                     "menus / briefings — 0 = off")
        self.bump_var = tk.DoubleVar(value=float(self.cfg.get("bump", 1.0)))
        self._slider(f, 5, "Bump strength", self.bump_var, 0.0, 2.0,
                     "needs a <hash>_n.rgba normal map — 0 = off")

        self.diag_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(f, text="Bump diagnostic (render the normal map)",
                        variable=self.diag_var).grid(row=6, column=1, columnspan=3, sticky="w")

        ttk.Separator(f, orient="horizontal").grid(row=7, column=0, columnspan=4,
                                                   sticky="ew", pady=10)
        self.play_btn = ttk.Button(f, text="▶  Launch game", command=self.launch)
        self.play_btn.grid(row=8, column=0, columnspan=4, sticky="ew", ipady=6)
        return f

    @staticmethod
    def _fmt(v):
        return "off" if v < 0.005 else "%.2f" % v

    def _slider(self, f, row, label, var, lo, hi, hint):
        """label | slider | numeric value (own column, so it can't be hidden) | hint"""
        ttk.Label(f, text=label).grid(row=row, column=0, sticky="w", pady=4)
        val = ttk.Label(f, text=self._fmt(var.get()), width=4, anchor="e",
                        font=("Consolas", 9))
        ttk.Scale(f, from_=lo, to=hi, variable=var, length=200,
                  command=lambda _v, l=val: l.config(text=self._fmt(float(_v)))
                  ).grid(row=row, column=1, sticky="w")
        val.grid(row=row, column=2, sticky="w", padx=(8, 0))
        ttk.Label(f, text=hint, foreground="#666").grid(row=row, column=3, sticky="w", padx=(10, 0))

    # ---------------- Textures tab
    def _tab_textures(self, parent):
        f = ttk.Frame(parent, padding=12)
        steps = [
            ("1. Extract textures",  ["extract"],   "game → hd_work/source (306 PNGs)"),
            ("2. Pack upscaled",     ["pack"],      "hd_work/upscaled → hd_pack_hd (+ refresh normal maps)"),
            ("Generate normal maps", ["normalmap"], "for bump; from hd_work/upscaled"),
            ("Extract 2D UI",        ["extract2d"], "Libs/*.LIB sprites → hd_work_2d/source"),
            ("Show status",          ["status"],    "extracted / upscaled / packed counts"),
        ]
        for i, (text, args, hint) in enumerate(steps):
            ttk.Button(f, text=text, width=22,
                       command=lambda a=args: self.run_tool(a)).grid(row=i, column=0, pady=3, sticky="w")
            ttk.Label(f, text=hint, foreground="#666").grid(row=i, column=1, sticky="w", padx=8)

        ttk.Separator(f, orient="horizontal").grid(row=9, column=0, columnspan=2,
                                                   sticky="ew", pady=8)
        folders = ttk.Frame(f); folders.grid(row=10, column=0, columnspan=2, sticky="w")
        for text, path in (("Open source", "hd_work/source"),
                           ("Open upscaled", "hd_work/upscaled"),
                           ("Open pack", "hd_pack_hd")):
            ttk.Button(folders, text=text,
                       command=lambda p=path: self.open_folder(p)).pack(side="left", padx=(0, 6))

        self.log = scrolledtext.ScrolledText(f, height=12, width=76, state="disabled",
                                             font=("Consolas", 9))
        self.log.grid(row=11, column=0, columnspan=2, pady=(10, 0))
        return f

    # ---------------- Advanced tab
    def _tab_advanced(self, parent):
        f = ttk.Frame(parent, padding=12)
        ttk.Label(f, text="Renderer").grid(row=0, column=0, sticky="w")
        self.rend_lbl = ttk.Label(f, text=active_renderer(), foreground="#0a0")
        self.rend_lbl.grid(row=0, column=1, sticky="w", padx=8)

        ttk.Button(f, text="Use OpenGlide (HD textures)", width=30,
                   command=lambda: self.swap_renderer("openglide")).grid(row=1, column=0,
                                                                        columnspan=2, pady=4, sticky="w")
        ttk.Button(f, text="Use dgVoodoo (no HD, fallback)", width=30,
                   command=lambda: self.swap_renderer("dgvoodoo")).grid(row=2, column=0,
                                                                        columnspan=2, pady=4, sticky="w")
        ttk.Label(f, text="dgVoodoo is only a safety fallback — it cannot do HD textures.",
                  foreground="#666").grid(row=3, column=0, columnspan=2, sticky="w")

        ttk.Separator(f, orient="horizontal").grid(row=4, column=0, columnspan=2,
                                                   sticky="ew", pady=10)
        ttk.Button(f, text="Open game folder",
                   command=lambda: self.open_folder(".")).grid(row=5, column=0, sticky="w")
        ttk.Label(f, text="The game must run with -3dfx; the launcher does that for you.",
                  foreground="#666").grid(row=6, column=0, columnspan=2, sticky="w", pady=(10, 0))
        return f

    # ---------------- actions
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
        self.after(100, self._pump)

    def open_folder(self, rel):
        path = os.path.join(GAME_DIR, rel.replace("/", os.sep))
        os.makedirs(path, exist_ok=True)
        os.startfile(path)

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

    def toggle_hd(self):
        self.run_tool(["on"] if self.hd_var.get() else ["off"])

    def swap_renderer(self, which):
        src = os.path.join(BACKUP, "glide2x.dll.%s" % which)
        if not os.path.exists(src):
            messagebox.showerror("Missing backup", "Not found:\n%s" % src)
            return
        try:
            with open(src, "rb") as a, open(os.path.join(GAME_DIR, "glide2x.dll"), "wb") as b:
                b.write(a.read())
        except PermissionError:
            messagebox.showerror("In use", "Close the game first.")
            return
        self.rend_lbl.config(text=active_renderer())
        self._set_status("Renderer: %s" % active_renderer())

    def launch(self):
        if self.busy or not os.path.exists(GAME_EXE):
            if not os.path.exists(GAME_EXE):
                messagebox.showerror("Not found", GAME_EXE)
            return
        self.busy = True
        self.play_btn.config(state="disabled")

        bump = 99.0 if self.diag_var.get() else self.bump_var.get()
        env = os.environ.copy()
        env["__COMPAT_LAYER"] = "HIGHDPIAWARE"      # true physical resolution
        env["INCU_SHARP"] = "%.3f" % self.sharp_var.get()
        env["INCU_BUMP"]  = "%.3f" % bump

        save_settings({"res_label": self.res_var.get(),
                       "sharp": round(self.sharp_var.get(), 3),
                       "bump": round(self.bump_var.get(), 3)})

        want = self.res_map.get(self.res_var.get())
        changed = bool(want) and want != self.saved_mode[:2] and set_mode(*want)
        self.q.put(("status", "playing%s ..." % (" @ %dx%d" % want if changed else "")))

        def work():
            try:
                subprocess.Popen([GAME_EXE, "-3dfx"], cwd=GAME_DIR, env=env).wait()
            except Exception as e:
                self.q.put(("log", "launch error: %s\n" % e))
            finally:
                if changed:                      # always put the desktop back
                    restore_mode(self.saved_mode)
                self.q.put(("status", "Ready — %s" % active_renderer()))
                self.q.put(("done", None))

        threading.Thread(target=work, daemon=True).start()

    def on_close(self):
        restore_mode(self.saved_mode)            # never leave the desktop switched
        self.destroy()

if __name__ == "__main__":
    os.chdir(GAME_DIR)
    Launcher().mainloop()
