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
- **Format tools** for the community: the texture format (VISN), the UI sprite archives
  (`Libs/*.LIB`), and the game's scripting language (LCL) are all decoded — see **MODDING.md**.

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
- **No VISN encoder.** You can't write edited pixels back into a `texture.lib`. You don't need
  to — HD substitution happens live in the renderer; the `.lib` is never modified.
- **It does not ship textures.** You make your own (that's the point).

---

## Requirements

1. **A legally-owned copy of Incubation**, installed (GOG "Battle Isle Platinum" includes it, or
   the standalone CD release). This mod contains **none** of the game's files.
2. **32-bit Python 3.10+** with **Pillow** and **numpy**:
   - Install the 32-bit build from python.org (the pipeline decodes textures by calling the
     game's own 32-bit `Eng3d.dll`, so 64-bit Python **cannot** be used for extraction).
   - `py -3-32 -m pip install Pillow numpy`  (or `pip install Pillow numpy` from that install).
3. **An AI image upscaler** of your choice — Real-ESRGAN, Upscayl, chaiNNer, Topaz, etc.
4. A GPU with OpenGL 3+ (anything from the last ~15 years). Anti-aliasing/filtering use standard
   OpenGL; no special hardware needed.
5. *(Only if you want to rebuild the renderer yourself)* a 32-bit MinGW-w64 GCC/G++. Not needed
   just to play — a prebuilt `glide2x.dll` is included.

## Downloads — official sources only

Download each component **only** from the links below (its author's own site/repo). Beware
look-alike sites and "free download" mirrors — they're not official.

| Component | Needed for | Official source |
|-----------|-----------|-----------------|
| **Incubation** (Battle Isle Platinum) | the game itself (you must own it) | https://www.gog.com/en/game/battle_isle_platinum |
| **Python for Windows (32-bit)** | the texture pipeline | https://www.python.org/downloads/windows/ |
| **Pillow** | pipeline (image I/O) | https://pypi.org/project/pillow/ · `pip install Pillow` |
| **NumPy** | pipeline (normal maps) | https://pypi.org/project/numpy/ · `pip install numpy` |
| **Real-ESRGAN** | AI upscaler (option A) | https://github.com/xinntao/Real-ESRGAN |
| **Upscayl** | AI upscaler (option B, GUI) | https://upscayl.org · https://github.com/upscayl/upscayl |
| **chaiNNer** | AI upscaler (option C, node-based) | https://github.com/chaiNNer-org/chaiNNer |
| **MinGW-w64** | *only* to rebuild the renderer | https://www.mingw-w64.org/ |

**Bundled in this package (no separate download needed):** our renderer `glide2x.dll` (built from
**OpenGlide** — original https://openglide.sourceforge.net/, fork https://github.com/fcbarros/openglide),
and **DDrawCompat** by narzoul (`ddraw_impl.dll`, from https://github.com/narzoul/DDrawCompat).

**Optional fallback renderer — NOT bundled:** **dgVoodoo 2** by Dege, only if you want the
no-HD fallback in the launcher's Advanced tab. Official: https://dege.freeweb.hu/ or
https://github.com/dege-diosg/dgVoodoo2/releases — put its 32-bit `glide2x.dll` at
`backup/glide2x.dll.dgvoodoo`.

---

## Install

1. Back up your Incubation folder (or at least `glide2x.dll` if one exists, and `DDraw.dll`).
2. Copy **everything from `game_files/`** into your Incubation install folder (the one with
   `Incubation.exe`). That's `glide2x.dll`, `DDraw.dll`, `ddraw_impl.dll`, `OpenGLid.ini`,
   `dgVoodoo.conf`, `setres.exe`, `Incubation HD.bat`, and the `tools/` subfolder.
3. Edit the paths at the top of `Incubation HD.bat` if your 32-bit Python isn't at the default
   `%LOCALAPPDATA%\Programs\Python\Python312-32\`.

## Use

Run **`Incubation HD.bat`** — the launcher opens.

**First time (make your HD pack):**
1. **Textures tab → “1. Extract textures.”** Decodes the 306 unique textures to
   `hd_work/source/*.png`. The filename is a hash the renderer uses to match them — **keep it**
   (a suffix like `_out` is fine; `025f4383_out.png` still matches).
2. **Upscale** everything in `hd_work/source/` with your AI upscaler and save the results into
   `hd_work/upscaled/` (create it, or use the “Open upscaled” button). Keep the filenames.
3. **Textures tab → “2. Pack upscaled.”** Writes `hd_pack_hd/<hash>.rgba` — the live HD pack.
4. **Play tab → ▶ Launch game.** Pick a resolution, leave **HD textures** on, hit launch.

**Every time after:** just launch. Edited a texture? Re-run “Pack upscaled” and play — that's the
whole loop.

**Sliders (Play tab):**
- **2D sharpen** (0–0.6) — menu/briefing sharpness. ~0.15 is gentle.
- **Bump strength** (0–2.0) — only affects textures that have a normal map. Make normal maps
  with **“Generate normal maps”** (Textures tab) first. Off by default in effect if no map.
- **Bump diagnostic** — renders the raw normal map, to confirm bump is active.

**A/B compare:** toggle **HD textures** off to see the original 256×256 art instantly.

---

## Troubleshooting

- **Game starts in a small window / software mode.** You launched `Incubation.exe` directly or via
  the GOG launcher (that runs SOFTWARE mode). Always use `Incubation HD.bat` (it passes `-3dfx`).
- **Weird colours or "restart with dx5".** The game didn't accept the 3Dfx renderer — make sure
  `glide2x.dll` from `game_files/` is in place and you're on the 3Dfx path.
- **Two cursors / a frozen cursor after lots of resolution switching.** This is a transient
  Windows display-state glitch, **not** the mod. **Reboot** and it's gone. (We chased this for an
  hour once; a reboot was the fix.)
- **Extraction fails with a Python/DLL error.** You're on 64-bit Python. Use 32-bit — the decoder
  is a 32-bit DLL.
- **NVIDIA overlay flickers.** Cosmetic; disable the NVIDIA in-game overlay.
- **Fallback:** the launcher's **Advanced** tab can swap in dgVoodoo (`no HD`, but a safe renderer)
  if OpenGlide misbehaves on your system.

---

## For modders

The reverse-engineered formats — textures (VISN), UI sprites (`Libs/*.LIB`), palettes, and the
**LCL scripting language** (which holds all unit/weapon/equipment/terrain stats in plain text) —
are documented in **MODDING.md**. That's also the starting point if you're thinking about a
full remake on a modern engine.

## Building the renderer

The renderer is an OpenGlide fork; its full source (plus our added files) is in `source/`. See
`source/BUILD.md`. Shipping the source keeps us compliant with OpenGlide's license.

## Credits & licenses

See **CREDITS.md**. In short: built on **OpenGlide** (Fabio Barros et al.) and **DDrawCompat**
(narzoul); this project's own code and tools are provided freely for the community. *Incubation*
is © Blue Byte / Ubisoft — this mod ships none of it.
