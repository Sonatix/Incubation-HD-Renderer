# Incubation HD — a renderer mod for *Incubation: The Wilderness Missions* (Blue Byte, 1997)

This project runs the original **Incubation** through a custom **OpenGlide** fork so you can
replace the game's 256×256 textures with your own AI-upscaled HD versions, play in **fullscreen
at any resolution** with proper **anti-aliasing** and **anisotropic filtering**, and tweak a few
image-quality options — all without touching the game's data files.

It is a **tool + renderer**, not an asset pack: you extract the textures, upscale them with
whatever AI upscaler you like, and pack them back. Nothing copyrighted is redistributed.

**By Sonatix** — creator and director of this project: its goals, the decisions on what to
pursue and what to drop, the hands-on testing at every step, and the HD textures themselves.
The reverse-engineering, renderer and tools were implemented with AI assistance (Claude, by
Anthropic) working under that direction.

> Українською: див. **README_UA.md**.

---

## See it in action

Demo videos by Sonatix — the same renderer, textures upscaled two different ways. The mod is
**upscaler-agnostic**, so use whatever gives you the look you want:

- ▶ **Textures upscaled with Upscayl + Google Gemini (“Nano Banana”)** — https://youtu.be/vm6WE56kJTo
- ▶ **Textures upscaled with Upscayl** — https://youtu.be/TSEZLvDdf0o

---

## What it does (done ✓)

- **True HD textures.** The game uploads every texture as a 256×256 image; our renderer
  intercepts that and substitutes an arbitrarily larger RGBA image at draw time. The game's
  geometry and UV mapping are untouched — you just get more texel detail.
- **Fullscreen at native resolution**, with a working mouse cursor and menus. Tested up to
  2560×1440; any mode your monitor supports is selectable in the launcher.
- **MSAA 8× anti-aliasing** — smooths the hard polygon edges that make old 3D look blocky.
- **Anisotropic 16× + trilinear mipmaps** — crisp textures on floors/walls seen at an angle,
  no shimmering in the distance.
- **2D sharpening** — a shader pass that makes the menus/briefings look less soft when scaled up.
- **Experimental fake bump/normal mapping** — adds surface relief to textures that have a
  generated normal map. Subtle (the HD textures already carry a lot of baked-in shading), but
  it's there if you want it.
- **A GUI launcher** that ties it all together: resolution, the HD toggle, sliders, and the
  whole extract → upscale → pack pipeline, with the display mode reliably restored on exit.
- **Format tools** for the community: the texture format (**VISN** — fully specified in
  **VISN-FORMAT.md**, with a standalone pure-Python decoder in `tools/visn.py` that needs no game
  DLL), the UI sprite archives (`Libs/*.LIB`), and the game's scripting language (LCL) are all
  decoded — see **MODDING.md**.

## What it does NOT do (limits — honest list ✗)

These are hard limits of a 1997 engine, not TODOs. We verified each one; please don't file them
as bugs.

- **It cannot raise the polygon count.** The models are low-poly and that is baked into the
  geometry the engine sends. At the renderer we only receive already-projected 2D triangles with
  no surface normals, so tessellation would add nothing and can't round a silhouette. Repacking
  higher-poly models breaks the animation. HD textures on low-poly models = "great texture on a
  cube", and that's the ceiling for the shape.
- **It cannot HD the interface per element.** The game composites its whole 2D UI itself and
  hands the renderer only the finished ~640×480 frame, so individual buttons/icons/cursor never
  arrive separately and can't be swapped for HD art. The 2D is *upscaled and sharpened*, not
  replaced. (The UI sprites are still extractable for reference / native-size edits.)
- **DLSS / frame-generation don't apply.** They need per-pixel motion vectors and engine
  integration this game can't provide, and they reconstruct detail this game doesn't have.
- **Editing a `texture.lib` can't give you HD.** It now works — `tools/visn.py` decodes *and*
  encodes VISN, so you can repaint a texture and repack it for the **vanilla** game with no DLLs
  at all. But the engine's texture page is fixed at 256×256, so that route stays at 256×256
  forever. HD needs the renderer substitution, which is what this kit's `glide2x.dll` does.
- **It does not ship textures.** You make your own (that's the point).

---

## TL;DR — for the very lazy

1. Install the game.
2. Copy the contents of `game_files` from this repo into the folder that has `launcher.exe` and
   `Incubation.exe` (by default `\GOG Games\Battle Isle Platinum\Incubation`).
3. Copy the 2 DLLs from the **Windows 10/11 patch** into that same folder.
4. Run **`Incubation HD.bat`** — it creates every folder it needs.
   - Also run the original `launcher.exe` **once**: after that the original campaign shows up in
     the menu. (Not yet known which setting decides between the original campaign and the add-on
     with the network game.)

To mod the game:

5. Install **32-bit Python**.
6. `py -3-32 -m pip install Pillow`
7. `py -3-32 -m pip install numpy` — optional, only for generating normal maps.

Everything should work now. If not, read the loooong part written by Claude below.

**(OPTIONAL)** You can copy `Glide2x.dll` and `ddraw.dll` from dgVoodoo into
`\Battle Isle Platinum\Incubation\dgVoodoo\` (the launcher creates that folder at step 4) — it
will use them in **Vanilla mode only**.

---

## Part A — Get it running (fullscreen + anti-aliasing) · ~10 minutes

This part alone gives you **fullscreen at your monitor's resolution, anti-aliasing, and sharper
texture filtering** — a real upgrade even before you touch the textures. No image skills needed.

**You need:** the game, and Python (the launcher runs on it).

1. **Own & install Incubation** — from GOG ("Battle Isle Platinum") or your CD. This mod ships
   none of the game; you provide it.
2. **Apply the Windows 10/11 patch — do this first.** Stock Incubation **hangs at startup on
   Windows 10/11**: the process sits in Task Manager with no window. The community patch (part of
   the 25th Anniversary Mod) fixes it by replacing `audio.dll` and `sound.dll`. Download it,
   unzip, and copy those two DLLs into your Incubation folder, overwriting.
   → https://www.moddb.com/mods/incubation-blue-byte-25-years-anniversary-mod/downloads/incubation-windows-10-patch
   *(The launcher checks for this and warns you if it looks missing — but without it nothing runs,
   so do it now.)*
3. **Install Python for Windows** from https://www.python.org/downloads/windows/ —
   **any version 3.8 or newer**, but it must be the **32-bit** build
   ("Windows installer (32-bit)"). On the first setup screen tick
   **"Add python.exe to PATH"**, and leave **"tcl/tk and IDLE"** ticked — that is the launcher's
   window toolkit; without it nothing can open.
   *(Why 32-bit: the HD pipeline calls the game's `Eng3d.dll` to decode textures, and a 64-bit
   process cannot load a 32-bit DLL. Why 3.8: the tools use `os.add_dll_directory`, added in 3.8.
   The vanilla texture tools in Part C are pure Python and run on any bitness.)*
4. **Copy the files.** Open the `game_files/` folder from this download and copy **everything
   inside it** into your Incubation folder (the one containing `Incubation.exe`). Overwrite if asked.
5. **Play.** Double-click **`Incubation HD.bat`** → the launcher opens → on the **Play** tab pick a
   resolution → click **▶ Launch HD game**.

You're now playing in fullscreen with anti-aliasing. The **HD textures** switch is on, but until
you do Part B there's no HD pack yet — so you'll see the original art, just full-screen and cleaner.

> `Incubation HD.bat` finds Python by itself: the default install folder first, then the `py`
> launcher (`py -3-32`), then whatever is on PATH. If it can't find a 32-bit Python 3 it tells you
> so instead of failing silently.

---

## Part B — Make your own HD textures · the upscaling pipeline

This is where the "HD" comes from: extract the game's textures, upscale them with an AI tool, pack
them back. Redo it anytime, texture by texture. Everything below is buttons in the launcher's
**HD textures** tab — no command line except one install step.

**You need (on top of Part A):**
- **Pillow**, the Python imaging library — it does every PNG read and write in the pipeline.
  Open **Command Prompt** and run:
  `py -3-32 -m pip install Pillow`
  Add `numpy` too *only* if you want the experimental bump effect (it is the maths behind
  "Generate normal maps"); everything else works without it:
  `py -3-32 -m pip install numpy`
- **An AI image upscaler.** Easiest to start with is **Upscayl** — free, a normal app window:
  https://upscayl.org . Any upscaler works (Real-ESRGAN, chaiNNer, Topaz, even an online one) —
  the mod doesn't care which.

**Steps:**
1. **“1. Extract textures.”** Writes 306 PNGs to `hd_work/source/` (button **“Open source”** opens it).
2. **Upscale them.** In Upscayl: set input folder = `hd_work/source`, output folder =
   `hd_work/upscaled`, pick a model and scale (×4 is a good start), run. **Keep the file names** —
   `025f4383_out.png` is fine; the `025f4383` part is what the renderer matches on.
3. **“2. Pack upscaled.”** Builds the live HD pack in `hd_pack_hd/`.
4. **Play** (Play tab → ▶ Launch). Your HD textures are now in the game.

**Next time you tweak a texture:** re-run **“2. Pack upscaled”** and launch — that's the whole loop.

**Also on the HD textures tab:**
- **2D sharpen** (0–0.6) — sharpness of menus/briefings; ~0.15 is gentle.
- **Bump strength** (0–2) — fake surface relief; only affects textures you first give a normal map
  via **“Generate normal maps”**. Optional / experimental.
- **HD textures** switch — turn it **off** any time to instantly compare against the original art.
- **Manual** button — every control on the tab explained, in English and Ukrainian.

---

## Part C — Edit the game's own textures (mods for the vanilla game) · optional

Part B makes the game *look* better through our renderer. Part C changes what the textures
actually **are**, inside the game's own `texture.lib` — so the edit shows up in the **plain,
unmodified game**, with no DLLs and no launcher of ours. That is how you make a texture mod other
people can just install.

Two limits, up front: it stays **256×256** forever (the engine's texture page is fixed), and the
codec is lossy, so a re-encoded texture is a touch softer than the original. Your painted content
stays crisp. This is about texture *content*, not resolution.

**Steps** — all on the launcher's **Vanilla textures** tab:
1. On the **Play** tab, switch the mode to **Vanilla**. (That single switch is the master control:
   in HD mode this tab is greyed out, because our renderer would substitute the HD pack and hide
   your edit.)
2. **Library** → pick one. `World_A00` is what the first campaign missions use.
3. **Extract textures** → every texture in that library becomes a PNG.
4. Select one → **Copy to edits + open in editor** → paint on it → save as a **256×256 PNG**.
5. **Install into game.** The pristine originals are backed up once to
   `backup/<World>_TEXTURES.orig/`; only the textures you edited are re-encoded, the rest are
   copied byte-for-byte.
6. **Play** tab → **▶ Launch vanilla game**.
7. **Restore originals** puts everything back whenever you want.

The **Manual** button on that tab has the full step-by-step and explains every control.
`tools/visn.py` does the same thing from the command line (`info` / `decode` / `encode` /
`repack` / `verify`).

---

## Downloads — official sources only

Get each component **only** from its author's own site/repo below. Avoid look-alike sites and
"free download" mirrors.

| Component | Needed for | Why exactly | Official source |
|-----------|-----------|-------------|-----------------|
| **Windows 10/11 patch** | **required, Part A** | stock Incubation hangs at startup on Win10/11; this replaces `audio.dll`+`sound.dll` and fixes it. From the 25th Anniversary Mod. | https://www.moddb.com/mods/incubation-blue-byte-25-years-anniversary-mod/downloads/incubation-windows-10-patch |
| **Incubation** (Battle Isle Platinum) | everything — **Part A** | this is a mod, not a game; you supply the game | https://www.gog.com/en/game/battle_isle_platinum |
| **Python for Windows** — **any 3.8+, 32-bit** | launcher + tools — **Part A** | the launcher is a Python program. 32-bit specifically because the HD pipeline loads the game's `Eng3d.dll` to decode textures, and a 64-bit process cannot load a 32-bit DLL. No particular version is required — the launcher probes for any suitable one. Keep "tcl/tk and IDLE" ticked during install (that is `tkinter`, the window toolkit). | https://www.python.org/downloads/windows/ |
| **Pillow** | textures — **Part B** and **Part C** | all the PNG reading and writing: extracting textures to PNG, loading your edited PNGs, thumbnails in the launcher. Nothing texture-related works without it. | `py -3-32 -m pip install Pillow` · https://pypi.org/project/pillow/ |
| **NumPy** *(optional)* | **only** normal maps — **Part B** | used by one feature: "Generate normal maps" for the experimental bump effect, which needs per-pixel gradient maths. Skip it and everything else still works — the tool just says so and moves on. | `py -3-32 -m pip install numpy` · https://pypi.org/project/numpy/ |
| **Upscayl** (easiest, GUI) | AI upscaler — **Part B** | makes the bigger textures. The mod only substitutes images; it does not generate art. Any upscaler works. | https://upscayl.org · https://github.com/upscayl/upscayl |
| **Real-ESRGAN** / **chaiNNer** | other AI upscalers — **Part B** | same job as Upscayl, more control | https://github.com/xinntao/Real-ESRGAN · https://github.com/chaiNNer-org/chaiNNer |
| **MinGW-w64**, **i686** | *only* to rebuild the renderer | compiles `glide2x.dll`. Must be the **i686 (32-bit)** toolchain — the game is 32-bit, an x86_64 build produces a DLL it cannot load. | https://winlibs.com · https://www.mingw-w64.org/ |

### What is in the package, and where its source is

Fair question when a download contains a `.dll`. The answer here is short: **the package contains
exactly one binary**, it is ours, and its full source is in this repository.

| File | What it is | Source |
|------|-----------|--------|
| `glide2x.dll` | the renderer: our fork of **OpenGlide**. Receives the game's 3dfx calls, substitutes your HD textures, adds fullscreen, MSAA and anisotropic filtering. 350 720 bytes, SHA-256 `222db7cd748fb2112ce9ffd29dfeef34302d9e19d774ecd13f6250b650239d85` | `source/openglide-src/`, with build and verification steps in `source/BUILD.md`. Upstream: https://openglide.sourceforge.net/ · fork https://github.com/fcbarros/openglide |
| `Incubation HD.bat` | starts the launcher | plain text, open it and read it |
| `tools/*.py` | the launcher and the texture tools | plain-text Python |
| `OpenGLid.ini` | renderer settings | plain text |
| `dgVoodoo.conf` | settings for dgVoodoo, if you decide to use it in Vanilla mode. A configuration file only; it contains no dgVoodoo code | plain text |
| `docs/*.md` | the manuals | plain text |

Verify the DLL you downloaded:

```
certutil -hashfile glide2x.dll SHA256
```

`source/` also carries code that is deliberately **not** shipped as a binary: `ddraw-wrapper/`
(a DirectDraw logging proxy from the reverse-engineering phase; in `-3dfx` mode the game never
calls DirectDraw, so it is not needed) and `setres.c` (a display-mode helper for the legacy `.bat`
launchers; the launcher changes modes itself).

**Optional, not bundled: dgVoodoo 2** (Dege) — the stock wrapper, with far more display settings
than we expose. Its licence forbids redistribution, so get it from https://dege.freeweb.hu/ and
drop **both** 32-bit DLLs from its `MS\x86` folder into the `dgVoodoo\` folder the launcher
creates. The file names do not matter; the launcher checks the contents.

The game takes its renderer from the command line, and the Play tab's **Vanilla via** switch
chooses which one Vanilla mode uses:

| | Renderer | With dgVoodoo you get |
|---|---|---|
| **DirectX** | `Incubation.exe -directx` → `ENG3D.DLL`, the game's own **software** rasterizer, presented through DirectDraw. This is the path the GOG launcher uses. | the **dgVoodoo** logo, and **the mouse works** |
| **Glide** | `Incubation.exe -3dfx` → `ENG3DFX.DLL`, the **3dfx** renderer the game was built around — the better-looking one, and the one our HD fork replaces. | the **3dfx** logo, but a misaligned cursor |

> **Why the mouse depends on this.** The game reads the cursor in screen coordinates while
> assuming a 640×480 screen. dgVoodoo's cursor handling lives in its DirectX path —
> `dgVoodoo.conf` documents `SystemHookFlags` as x86-DX only — so on the Glide path nothing
> converts those coordinates and the whole game screen maps into the top-left 640×480 pixels of
> your display. Prefer DirectX when you run dgVoodoo.

`ddraw.dll` is copied into the game folder only for the run and removed again afterwards; anything
that was there is kept in `backup/` and put back. A crashed run is repaired at the next start.

**Vanilla** mode works without dgVoodoo too: it then runs our renderer with the HD texture pack
paused for that session, which looks like the plain game and is what matters for A/B comparisons
and for seeing vanilla texture mods. The pack is switched back on when the game exits.

> **Tip:** always back up your Incubation folder before copying files in (or at least any existing
> `glide2x.dll`).

---

## Antivirus false positives — please read before panicking

Windows Defender may flag `glide2x.dll` as **`Trojan:Win32/Wacatac.B!ml`**. It is a false
positive. Here is the honest explanation rather than "just trust me":

- The **`!ml` suffix means it was flagged by a machine-learning guess**, not by matching any known
  malware. Wacatac.B!ml is Microsoft's generic bucket for "this looks unfamiliar".
- On VirusTotal the file is clean for every other engine — Microsoft's heuristic is the only one
  that objects.
- Why it trips the heuristic: the DLL is **unsigned** (a code-signing certificate costs money we
  are not spending on a 1997 game mod), it is **rarely downloaded** (prevalence counts heavily),
  and it legitimately **hooks input APIs** — `ClipCursor`, `GetCursorPos`, `SetCursorPos` — because
  the game hard-codes a 640×480 mouse area and fullscreen would otherwise trap your cursor in the
  top-left corner. That hooking is a real technique malware also uses; here it is the whole reason
  the mouse works in fullscreen, and you can read it in `source/openglide-src/input_remap.cpp`.

What we have done about it:

- The DLL now carries a **proper version resource** (product, company, description, version) and is
  built stripped, instead of being an anonymous binary — anonymity was part of what the heuristic
  disliked.
- **The complete source is in this repository** (`source/`), with the exact build command in
  `source/BUILD.md`. You can rebuild `glide2x.dll` yourself with MinGW and compare, which is the
  only guarantee that actually means anything.

What you can do:

- **Report it to Microsoft as a false positive** — https://www.microsoft.com/en-us/wdsi/filesubmission
  (choose "Software developer" if you rebuilt it, or "Home customer"). This is what actually gets
  the detection removed for everyone; the more reports, the faster.
- Or add an exclusion for the game folder in Windows Security → Virus & threat protection →
  Manage settings → Exclusions.
- Or simply build the DLL yourself from `source/`.

If you are not comfortable with any of that, that is a completely reasonable position — do not run
the mod. We would rather explain the situation than have you run something you distrust.

---

## Troubleshooting

- **Game starts in a small window / software mode.** That is the `-directx` path: the game's own
  software rasterizer, which is what bare `Incubation.exe` and the GOG launcher use. For HD and
  for the 3dfx renderer, start from `Incubation HD.bat` — the launcher passes `-3dfx`.
- **Weird colours or "restart with dx5".** The game didn't accept the 3Dfx renderer — make sure
  `glide2x.dll` from `game_files/` is in place and you're on the 3Dfx path.
- **Only the add-on campaign and network game appear in the menu.** Run the game's original
  `launcher.exe` **once**; after that the base campaign is there for good, including through our
  launcher. What that first run initialises is not yet known — if you find out, tell us.
- **The mouse does not line up in Vanilla mode with dgVoodoo.** Switch **Vanilla via** to
  **DirectX** on the Play tab and put dgVoodoo's `ddraw.dll` in the `dgVoodoo\` folder. See the
  dgVoodoo notes above for why.
- **Two cursors / a frozen cursor after lots of resolution switching.** This is a transient
  Windows display-state glitch, **not** the mod. **Reboot** and it's gone. (We chased this for an
  hour once; a reboot was the fix.)
- **“1. Extract textures” fails with a Python/DLL error.** You're on 64-bit Python. The HD
  pipeline loads the game's `Eng3d.dll`, which is 32-bit — use a 32-bit Python. (The *Vanilla
  textures* tab is unaffected: its codec is pure Python.)
- **Different libraries seem to extract the same textures.** They partly do: all nine `World_*`
  libraries carry the same 28 alien/unit textures byte for byte, and each world adds only 1 to 19
  of its own. The list marks the shared ones with `=` and the status line gives the counts.
- **`Incubation HD.bat` does nothing at all — no window, no error.** Older copies of this file
  handed straight over to `pythonw.exe`, which has no console and therefore dies silently on any
  startup problem. The current one runs a preflight first and tells you what is wrong. To see the
  raw error yourself, run from a terminal in the game folder:
  `py -3-32 tools\launcher.py`
  The usual causes: Python installed **without** "tcl/tk and IDLE" (so `tkinter` is missing —
  re-run the installer, choose Modify, tick it); the `tools\` folder not copied along with the
  loose files; or the files copied somewhere other than the folder holding `Incubation.exe`.
- **NVIDIA overlay flickers.** Cosmetic; disable the NVIDIA in-game overlay.
- **Fallback:** if our renderer misbehaves on your system, put dgVoodoo's DLLs in the `dgVoodoo\`
  folder (the **Debug** tab has a file picker for it) and play in **Vanilla** mode — no HD, but a
  different renderer entirely.

---

## For modders

The reverse-engineered formats — textures (VISN), UI sprites (`Libs/*.LIB`), palettes, and the
**LCL scripting language** (which holds all unit/weapon/equipment/terrain stats in plain text) —
are documented in **MODDING.md**. The texture codec has its own complete write-up in
**VISN-FORMAT.md** — enough to build a decoder or an encoder from scratch. That's also the
starting point if you're thinking about a full remake on a modern engine.

## Building the renderer

The renderer is an OpenGlide fork; its full source (plus our added files) is in `source/`. See
`source/BUILD.md`. Shipping the source keeps us compliant with OpenGlide's license.

## Credits & licenses

See **CREDITS.md**. In short: built on **OpenGlide** (Fabio Barros et al.); this project's own
code and tools are provided freely for the community. *Incubation* is © Blue Byte / Ubisoft —
this mod ships none of it.
