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

## Part A — Get it running (fullscreen + anti-aliasing) · ~10 minutes

This part alone gives you **fullscreen at your monitor's resolution, anti-aliasing, and sharper
texture filtering** — a real upgrade even before you touch the textures. No image skills needed.

**You need:** the game, and Python (the launcher runs on it).

1. **Own & install Incubation** — from GOG ("Battle Isle Platinum") or your CD. This mod ships
   none of the game; you provide it.
2. **Install Python for Windows** from https://www.python.org/downloads/windows/ — choose the
   **32-bit ("Windows installer (32-bit)")** build, and on the first setup screen tick
   **"Add python.exe to PATH."** *(32-bit matters: the HD pipeline calls the game's `Eng3d.dll`
   to decode textures, and that is a 32-bit DLL a 64-bit Python cannot load. The vanilla texture
   tools in Part C are pure Python and run on either.)*
3. **Copy the files.** Open the `game_files/` folder from this download and copy **everything
   inside it** into your Incubation folder (the one containing `Incubation.exe`). Overwrite if asked.
4. **Play.** Double-click **`Incubation HD.bat`** → the launcher opens → on the **Play** tab pick a
   resolution → click **▶ Launch game**.

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
- **Two Python add-ons.** Open **Command Prompt** and run:
  `py -3-32 -m pip install Pillow numpy`
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

| Component | For | Official source |
|-----------|-----|-----------------|
| **Incubation** (Battle Isle Platinum) | the game — **Part A** | https://www.gog.com/en/game/battle_isle_platinum |
| **Python for Windows (32-bit)** | launcher + tools — **Part A** | https://www.python.org/downloads/windows/ |
| **Pillow** + **NumPy** | the texture tools — **Part B** | `py -3-32 -m pip install Pillow numpy` · https://pypi.org/project/pillow/ · https://pypi.org/project/numpy/ |
| **Upscayl** (easiest, GUI) | AI upscaler — **Part B** | https://upscayl.org · https://github.com/upscayl/upscayl |
| **Real-ESRGAN** / **chaiNNer** | other AI upscalers — **Part B** | https://github.com/xinntao/Real-ESRGAN · https://github.com/chaiNNer-org/chaiNNer |
| **MinGW-w64** | *only* to rebuild the renderer | https://www.mingw-w64.org/ |

**Already bundled — don't download:** the renderer `glide2x.dll` (built from **OpenGlide** —
https://openglide.sourceforge.net/ · fork https://github.com/fcbarros/openglide) and **DDrawCompat**
(`ddraw_impl.dll`, by narzoul — https://github.com/narzoul/DDrawCompat).
**Optional, not bundled:** **dgVoodoo 2** (Dege) — the stock wrapper used by the launcher's
Vanilla mode, and a no-HD fallback on the Debug tab —
https://dege.freeweb.hu/ ; put its 32-bit `glide2x.dll` at `backup/glide2x.dll.dgvoodoo`.

> **Tip:** always back up your Incubation folder before copying files in (or at least any existing
> `glide2x.dll` / `DDraw.dll`).

---

## Troubleshooting

- **Game starts in a small window / software mode.** You launched `Incubation.exe` directly or via
  the GOG launcher (that runs SOFTWARE mode). Always use `Incubation HD.bat` (it passes `-3dfx`).
- **Weird colours or "restart with dx5".** The game didn't accept the 3Dfx renderer — make sure
  `glide2x.dll` from `game_files/` is in place and you're on the 3Dfx path.
- **Two cursors / a frozen cursor after lots of resolution switching.** This is a transient
  Windows display-state glitch, **not** the mod. **Reboot** and it's gone. (We chased this for an
  hour once; a reboot was the fix.)
- **“1. Extract textures” fails with a Python/DLL error.** You're on 64-bit Python. The HD
  pipeline loads the game's `Eng3d.dll`, which is 32-bit — use a 32-bit Python. (The *Vanilla
  textures* tab is unaffected: its codec is pure Python.)
- **NVIDIA overlay flickers.** Cosmetic; disable the NVIDIA in-game overlay.
- **Fallback:** the launcher's **Debug** tab can swap in dgVoodoo (`no HD`, but a safe renderer)
  if OpenGlide misbehaves on your system.

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

See **CREDITS.md**. In short: built on **OpenGlide** (Fabio Barros et al.) and **DDrawCompat**
(narzoul); this project's own code and tools are provided freely for the community. *Incubation*
is © Blue Byte / Ubisoft — this mod ships none of it.
