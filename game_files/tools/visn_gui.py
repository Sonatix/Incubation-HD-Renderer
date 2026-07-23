#!/usr/bin/env python3
"""Incubation texture modding — the VANILLA path.

Decode the game's own textures, paint on them in any editor, and repack them back
into `texture.lib` so the unmodified game renders them. No renderer, no DLLs.

`VisnFrame` is an embeddable ttk.Frame (the unified launcher hosts it as its
"Vanilla textures" tab); running this file standalone wraps it in its own window
(`Texture Mod.bat`).

  * pick a texture library (World_A00 is what the first campaign missions use)
  * browse every texture as a thumbnail, side by side original vs your edit
  * one click to copy a texture into the edit folder and open it in your editor
  * install into the game (originals backed up once, repack always from pristine)
  * restore with one click
  * warns when the HD pack is on — it would hide your edit behind an HD substitute

The codec (tools/visn.py) is pure Python; any Python with Pillow works.
"""
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import visn  # noqa: F401  (imported for the subprocess path check at startup)

GAME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VISN_PY = os.path.join(GAME_DIR, "tools", "visn.py")
WORK = os.path.join(GAME_DIR, "visn_work")
BACKUP = os.path.join(GAME_DIR, "backup")
PACK_DIR = os.path.join(GAME_DIR, "hd_pack_hd")
PACK_OFF = PACK_DIR + ".off"

def _pick_python():
    """Interpreter to run visn.py with.

    The codec is pure Python, so a 64-bit interpreter is preferred purely for
    speed — but only if it actually has Pillow. The setup instructions tell
    people to install Pillow into the 32-bit Python (the launcher needs 32-bit
    for hd_tool), so a bare 64-bit install would fail on the first decode.
    Whatever is running this GUI is always a safe fallback.
    """
    cand = os.path.join(os.environ.get("LOCALAPPDATA", ""),
                        "Programs", "Python", "Python312", "python.exe")
    if os.path.exists(cand) and cand.lower() != sys.executable.lower():
        try:
            if subprocess.run([cand, "-c", "import PIL"],
                              creationflags=subprocess.CREATE_NO_WINDOW,
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=15).returncode == 0:
                return cand
        except (OSError, subprocess.SubprocessError):
            pass
    return sys.executable


PY = _pick_python()

THUMB = 224


# ------------------------------------------------------------------ libraries
def find_libs():
    """(label, lib_path, slug) for every VISN library in the install."""
    out = []
    ws = os.path.join(GAME_DIR, "WorldSet")
    if os.path.isdir(ws):
        for w in sorted(os.listdir(ws)):
            lib = os.path.join(ws, w, "TEXTURES", "texture.lib")
            if os.path.exists(lib):
                note = "  — first campaign missions" if w == "World_A00" else ""
                out.append((w + note, lib, w))
    vid = os.path.join(GAME_DIR, "Video")
    if os.path.isdir(vid):
        for v in sorted(os.listdir(vid)):
            for sub in ("Textures", "TEXTURES"):
                lib = os.path.join(vid, v, sub, "Texture.lib")
                if os.path.exists(lib):
                    out.append(("Video / " + v, lib, "Video_" + v))
                    break
    return out


def hd_pack_enabled():
    return os.path.isdir(PACK_DIR)


class VisnFrame(ttk.Frame):
    """The whole vanilla-texture workflow as one embeddable frame."""

    def __init__(self, parent, status_cb=None, show_hd_toggle=True):
        super().__init__(parent, padding=10)
        self.status_cb = status_cb
        # Standalone, the HD-pack state is worth warning about here. Embedded in
        # the launcher the Play switch already owns it, so the duplicate control
        # is hidden — two toggles for one thing is just confusing.
        self.show_hd_toggle = show_hd_toggle
        self.enabled = True
        self.q = queue.Queue()
        self.busy = False
        self.libs = find_libs()
        self.thumbs = {}          # keep PhotoImage refs alive
        self.names = []

        if not self.libs:
            ttk.Label(self, text="No texture.lib found under %s" % GAME_DIR
                      ).pack(anchor="w")
            return

        self._build_top(self)
        self._build_body(self)
        self._build_actions(self)

        self.lib_box.current(0)
        self.on_lib_change()
        self.after(100, self._pump)

    # ---------------------------------------------------------------- layout
    def _build_top(self, parent):
        f = ttk.Frame(parent)
        f.pack(fill="x", pady=(0, 8))
        ttk.Label(f, text="Library").pack(side="left")
        self.lib_box = ttk.Combobox(f, state="readonly", width=44,
                                    values=[l[0] for l in self.libs])
        self.lib_box.pack(side="left", padx=(6, 10))
        self.lib_box.bind("<<ComboboxSelected>>", lambda e: self.on_lib_change())
        self.extract_btn = ttk.Button(f, text="Extract textures", command=self.do_extract)
        self.extract_btn.pack(side="left")
        self.folder_btn = ttk.Button(f, text="Open edit folder",
                                     command=lambda: self._open(self.edits_dir()))
        self.folder_btn.pack(side="left", padx=6)

        self.hd_lbl = ttk.Label(f, text="", foreground="#b00000")
        self.hd_btn = ttk.Button(f, text="", width=16, command=self.toggle_hd)
        if self.show_hd_toggle:
            self.hd_lbl.pack(side="right")
            self.hd_btn.pack(side="right", padx=6)

    def _build_body(self, parent):
        body = ttk.Frame(parent)
        body.pack(fill="both", expand=True)

        left = ttk.LabelFrame(body, text="Textures", padding=6)
        left.pack(side="left", fill="y")
        self.listbox = tk.Listbox(left, width=26, height=22, exportselection=False,
                                  font=("Consolas", 9), activestyle="none")
        self.listbox.pack(side="left", fill="y")
        sb = ttk.Scrollbar(left, orient="vertical", command=self.listbox.yview)
        sb.pack(side="left", fill="y")
        self.listbox.config(yscrollcommand=sb.set)
        self.listbox.bind("<<ListboxSelect>>", lambda e: self.on_select())
        self.listbox.bind("<Double-Button-1>", lambda e: self.do_edit())

        right = ttk.Frame(body, padding=(10, 0, 0, 0))
        right.pack(side="left", fill="both", expand=True)

        prev = ttk.Frame(right)
        prev.pack(fill="x")
        self.pv_orig = self._preview(prev, "Original in the game")
        self.pv_edit = self._preview(prev, "Your edit")

        info = ttk.Frame(right)
        info.pack(fill="x", pady=(8, 0))
        self.info = ttk.Label(info, text="", font=("Consolas", 9), justify="left")
        self.info.pack(side="left")

        btns = ttk.Frame(right)
        btns.pack(fill="x", pady=8)
        self.edit_btn = ttk.Button(btns, text="Copy to edits + open in editor",
                                   command=self.do_edit)
        self.edit_btn.pack(side="left")
        self.revert_btn = ttk.Button(btns, text="Discard this edit", command=self.do_revert)
        self.revert_btn.pack(side="left", padx=6)

        self.log = scrolledtext.ScrolledText(right, height=8, state="disabled",
                                             font=("Consolas", 9), wrap="none")
        self.log.pack(fill="both", expand=True)

    def _preview(self, parent, caption):
        f = ttk.LabelFrame(parent, text=caption, padding=4)
        f.pack(side="left", padx=(0, 8))
        lbl = ttk.Label(f, width=THUMB // 8)
        lbl.pack()
        return lbl

    def _build_actions(self, parent):
        f = ttk.LabelFrame(parent, text="Install", padding=8)
        f.pack(fill="x", pady=(8, 0))

        ttk.Label(f, text="Quality").grid(row=0, column=0, sticky="w")
        self.quality = tk.IntVar(value=93)
        self.quality_scale = ttk.Scale(
            f, from_=60, to=100, variable=self.quality, length=220,
            command=lambda v: self.q_lbl.config(text="%d" % self.quality.get()))
        self.quality_scale.grid(row=0, column=1, sticky="w", padx=6)
        self.q_lbl = ttk.Label(f, text="93", width=4, font=("Consolas", 9))
        self.q_lbl.grid(row=0, column=2, sticky="w")
        ttk.Label(f, text="93 is what Blue Byte used — above that the file grows with no "
                          "visible gain (the format's colour stage is the limit).",
                  foreground="#555").grid(row=0, column=3, sticky="w", padx=(10, 0))

        bar = ttk.Frame(f)
        bar.grid(row=1, column=0, columnspan=4, sticky="w", pady=(10, 0))
        self.install_btn = ttk.Button(bar, text="Install into game", command=self.do_install)
        self.install_btn.pack(side="left")
        self.restore_btn = ttk.Button(bar, text="Restore originals", command=self.do_restore)
        self.restore_btn.pack(side="left", padx=6)
        self.state_lbl = ttk.Label(bar, text="", font=("Consolas", 9))
        self.state_lbl.pack(side="left", padx=12)

    # ---------------------------------------------------------------- paths
    def lib_path(self):
        return self.libs[self.lib_box.current()][1]

    def slug(self):
        return self.libs[self.lib_box.current()][2]

    def source_dir(self):
        return os.path.join(WORK, self.slug(), "source")

    def edits_dir(self):
        return os.path.join(WORK, self.slug(), "edits")

    def backup_dir(self):
        return os.path.join(BACKUP, self.slug() + "_TEXTURES.orig")

    def pristine_lib(self):
        """The library to encode from — the untouched backup once one exists."""
        b = os.path.join(self.backup_dir(), os.path.basename(self.lib_path()))
        return b if os.path.exists(b) else self.lib_path()

    # ---------------------------------------------------------------- state
    def on_lib_change(self):
        os.makedirs(self.edits_dir(), exist_ok=True)
        self.refresh_list()
        self.refresh_state()

    def refresh_list(self):
        self.listbox.delete(0, "end")
        src = self.source_dir()
        self.names = []
        if os.path.isdir(src):
            self.names = sorted(os.path.splitext(f)[0] for f in os.listdir(src)
                                if f.lower().endswith(".png"))
        for n in self.names:
            edited = os.path.exists(os.path.join(self.edits_dir(), n + ".png"))
            self.listbox.insert("end", ("* " if edited else "  ") + n)
        if not self.names:
            self._set_status("No textures extracted yet — press \"Extract textures\".")
        self.on_select()

    def refresh_state(self):
        if self.show_hd_toggle:
            on = hd_pack_enabled()
            self.hd_lbl.config(text="HD pack is ON — it will hide your edit" if on else "")
            self.hd_btn.config(text="Turn HD pack off" if on else "HD pack is off")
            self.hd_btn.state(["!disabled"] if (self.enabled and
                              (on or os.path.isdir(PACK_OFF))) else ["disabled"])

        bak = os.path.join(self.backup_dir(), os.path.basename(self.lib_path()))
        if not os.path.exists(bak):
            self.state_lbl.config(text="game files are pristine")
            self.restore_btn.state(["disabled"])
        else:
            same = os.path.getsize(bak) == os.path.getsize(self.lib_path())
            self.state_lbl.config(text="original backed up — modified library installed"
                                  if not same else "original backed up — game lib matches it")
            self.restore_btn.state(["!disabled"] if self.enabled else ["disabled"])

    def set_enabled(self, flag):
        """Grey the whole workflow out — the launcher's Play switch owns this."""
        self.enabled = flag
        st = ["!disabled"] if flag else ["disabled"]
        for w in (self.lib_box, self.extract_btn, self.folder_btn,
                  self.edit_btn, self.revert_btn, self.quality_scale,
                  self.install_btn, self.restore_btn):
            try:
                w.state(["readonly"] + st if w is self.lib_box else st)
            except tk.TclError:
                pass
        try:
            self.listbox.config(state="normal" if flag else "disabled")
        except tk.TclError:
            pass
        if flag:
            self.on_select()          # restores per-selection button states
            self.refresh_state()

    def on_select(self):
        sel = self.listbox.curselection()
        if not sel:
            self.pv_orig.config(image="")
            self.pv_edit.config(image="")
            self.info.config(text="")
            self.edit_btn.state(["disabled"])
            self.revert_btn.state(["disabled"])
            return
        name = self.names[sel[0]]
        src = os.path.join(self.source_dir(), name + ".png")
        edit = os.path.join(self.edits_dir(), name + ".png")
        self.thumbs["o"] = self._thumb(src)
        self.thumbs["e"] = self._thumb(edit)
        self.pv_orig.config(image=self.thumbs["o"] or "")
        self.pv_edit.config(image=self.thumbs["e"] or "")
        txt = "%s\n%s" % (name, "edited — will be re-encoded on install"
                          if os.path.exists(edit) else "not edited — will be copied verbatim")
        self.info.config(text=txt)
        self.edit_btn.state(["!disabled"] if self.enabled else ["disabled"])
        self.revert_btn.state(["!disabled"] if self.enabled and os.path.exists(edit)
                              else ["disabled"])

    def _thumb(self, path):
        if not os.path.exists(path):
            return None
        try:
            from PIL import Image, ImageTk
            im = Image.open(path).convert("RGB")
            im.thumbnail((THUMB, THUMB))
            return ImageTk.PhotoImage(im)
        except Exception as e:
            self._log("preview failed for %s: %s\n" % (path, e))
            return None

    # ---------------------------------------------------------------- actions
    def do_extract(self):
        self.run(["decode", self.pristine_lib(), "-o", self.source_dir()],
                 "extracting textures", after=self.refresh_list)

    def do_edit(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        name = self.names[sel[0]]
        src = os.path.join(self.source_dir(), name + ".png")
        dst = os.path.join(self.edits_dir(), name + ".png")
        if not os.path.exists(dst):
            import shutil
            os.makedirs(self.edits_dir(), exist_ok=True)
            shutil.copy2(src, dst)
            self._log("copied %s into the edit folder\n" % name)
        self._open(dst)
        self.refresh_list()

    def do_revert(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        name = self.names[sel[0]]
        dst = os.path.join(self.edits_dir(), name + ".png")
        if os.path.exists(dst) and messagebox.askyesno(
                "Discard edit", "Delete your edited %s.png?\nThe original is untouched." % name):
            os.remove(dst)
            self._log("discarded edit for %s\n" % name)
            self.refresh_list()

    def do_install(self):
        edits = [f for f in os.listdir(self.edits_dir())] if os.path.isdir(self.edits_dir()) else []
        edits = [f for f in edits if f.lower().endswith(".png")]
        if not edits:
            messagebox.showinfo("Nothing to install",
                                "No edited PNGs yet.\n\nPick a texture, press "
                                "\"Copy to edits + open in editor\", paint on it and save.")
            return
        if hd_pack_enabled() and not messagebox.askyesno(
                "HD pack is on",
                "The HD pack is enabled, so the renderer will substitute its own HD texture "
                "and you will NOT see this edit in game.\n\nInstall anyway?"):
            return

        lib = self.lib_path()
        bdir = self.backup_dir()
        try:
            if not os.path.exists(os.path.join(bdir, os.path.basename(lib))):
                import shutil
                os.makedirs(bdir, exist_ok=True)
                stem = os.path.splitext(lib)[0]
                for ext in (".lib", ".dir", ".din"):
                    for cand in (stem + ext, stem + ext.upper()):
                        if os.path.exists(cand):
                            shutil.copy2(cand, bdir)
                            break
                self._log("backed up the originals to %s\n" % bdir)
        except OSError as e:
            messagebox.showerror("Backup failed", str(e))
            return

        out = os.path.join(WORK, self.slug(), "texture.lib")
        self.run(["repack", self.pristine_lib(), self.edits_dir(),
                  "-o", out, "-q", str(self.quality.get())],
                 "re-encoding %d texture(s)" % len(edits),
                 after=lambda: self._install_files(out))

    def _install_files(self, out):
        import shutil
        lib = self.lib_path()
        stem_src = os.path.splitext(out)[0]
        stem_dst = os.path.splitext(lib)[0]
        try:
            for ext in (".lib", ".dir", ".din"):
                if os.path.exists(stem_src + ext):
                    shutil.copy2(stem_src + ext, stem_dst + ext)
            self._log("installed into %s\n" % os.path.dirname(lib))
            self._set_status("Installed. Turn the HD pack off, then launch the game.")
        except OSError as e:
            messagebox.showerror("Install failed", str(e))
        self.refresh_state()

    def do_restore(self):
        import shutil
        bdir = self.backup_dir()
        lib = self.lib_path()
        base = os.path.basename(lib)
        if not os.path.exists(os.path.join(bdir, base)):
            return
        stem_dst = os.path.splitext(lib)[0]
        try:
            for f in os.listdir(bdir):
                shutil.copy2(os.path.join(bdir, f),
                             stem_dst + os.path.splitext(f)[1])
            self._log("restored the original library from %s\n" % bdir)
            self._set_status("Originals restored.")
        except OSError as e:
            messagebox.showerror("Restore failed", str(e))
        self.refresh_state()

    def toggle_hd(self):
        try:
            if hd_pack_enabled():
                os.rename(PACK_DIR, PACK_OFF)
                self._log("HD pack disabled (hd_pack_hd -> hd_pack_hd.off)\n")
            elif os.path.isdir(PACK_OFF):
                os.rename(PACK_OFF, PACK_DIR)
                self._log("HD pack enabled\n")
        except OSError as e:
            messagebox.showerror("HD pack", "Could not rename the pack folder:\n%s" % e)
        self.refresh_state()

    # ---------------------------------------------------------------- plumbing
    def _open(self, path):
        try:
            os.makedirs(path, exist_ok=True) if os.path.splitext(path)[1] == "" else None
            os.startfile(path)
        except OSError as e:
            messagebox.showerror("Open", str(e))

    def _set_status(self, msg):
        if self.status_cb:
            self.status_cb(msg)

    def _log(self, line):
        self.log.config(state="normal")
        self.log.insert("end", line)
        self.log.see("end")
        self.log.config(state="disabled")

    def run(self, args, what, after=None):
        if self.busy:
            return
        self.busy = True
        for b in (self.install_btn, self.restore_btn, self.edit_btn):
            b.state(["disabled"])
        self._set_status(what + " ...")
        self._log("\n$ visn.py %s\n" % " ".join(os.path.basename(a) for a in args))

        def work():
            try:
                # -u so progress streams in live instead of arriving at exit
                p = subprocess.Popen([PY, "-u", VISN_PY] + args, cwd=GAME_DIR,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, bufsize=1,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
                for line in p.stdout:
                    self.q.put(("log", line))
                p.wait()
                self.q.put(("status", "%s — %s" % (
                    what, "done" if p.returncode == 0 else "FAILED (exit %d)" % p.returncode)))
                self.q.put(("done", after if p.returncode == 0 else None))
            except Exception as e:
                self.q.put(("log", "ERROR: %s\n" % e))
                self.q.put(("status", "failed"))
                self.q.put(("done", None))

        threading.Thread(target=work, daemon=True).start()

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
                    if self.enabled:
                        for b in (self.install_btn, self.restore_btn, self.edit_btn):
                            b.state(["!disabled"])
                    if payload:
                        payload()
                    self.refresh_state()
        except queue.Empty:
            pass
        except tk.TclError:
            return
        self.after(100, self._pump)


class App(tk.Tk):
    """Standalone window around VisnFrame (what `Texture Mod.bat` opens)."""

    def __init__(self):
        super().__init__()
        self.title("Incubation — Texture Mod (vanilla)")
        self.minsize(980, 700)
        self.status = ttk.Label(self, text="", anchor="w", relief="sunken", padding=(6, 2))
        frame = VisnFrame(self, status_cb=lambda m: self.status.config(text=m))
        frame.pack(fill="both", expand=True)
        self.status.pack(fill="x", padx=10, pady=(0, 10))


if __name__ == "__main__":
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        sys.exit("Pillow is required:  %s -m pip install pillow" % sys.executable)
    App().mainloop()
