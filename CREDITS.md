# Credits & licenses

## The game
**Incubation: The Wilderness Missions** is © **Blue Byte / Ubisoft** (1997). This mod contains
**none** of the game's files, art, audio, or code. You must own and install the game yourself.
All trademarks belong to their owners. This is an unofficial fan mod, not affiliated with or
endorsed by the rights holders.

## The renderer
Built on **OpenGlide** — a Glide→OpenGL wrapper originally by **Fabio Barros**, with later work
by **Paul (for Glidos)** and others. Original project: https://openglide.sourceforge.net/ ;
this project uses the **fcbarros/openglide** fork (https://github.com/fcbarros/openglide) as its
base. OpenGlide's license (as shipped in the fork) is in `source/openglide-src/LICENSE`; its
source files also carry LGPL headers. **Full source is included in `source/`** to comply with
those terms. Our modifications are the files listed in `source/BUILD.md`.

## The 2D / DirectDraw layer
This package contains no DirectDraw component. In `-3dfx` mode the game never calls
`DirectDrawCreate`: the 2D layer (menus, briefings) is written into the Glide buffer and drawn by
`glide2x.dll` like everything else. `source/ddraw-wrapper/` holds a logging DirectDraw proxy from
the reverse-engineering phase; it is kept as source for reference and is not part of the release.

## The alternative renderer (optional)
Vanilla mode can run through **dgVoodoo 2** by **Dege** if you put its 32-bit `Glide2x.dll` and
`ddraw.dll` in the `dgVoodoo\` folder. dgVoodoo is **not** included in this package — download it
only from the official source (https://dege.freeweb.hu/ or
https://github.com/dege-diosg/dgVoodoo2/releases). The included `dgVoodoo.conf` is only a
configuration file and carries no dgVoodoo code.

## This project
Created and directed by **Sonatix** — the vision, the design decisions, the testing at every
step, and the HD texture work. The implementation (reverse-engineering, renderer, and tools) was
done with AI assistance (**Claude**, by Anthropic) under that direction.

The HD texture/normal-map injection, the input remap, the MSAA/anisotropic/gamma/2D-sharpen and
bump code, the `hd_tool` pipeline, the GUI launcher, the VISN codec, `setres`, and the format
reverse-engineering (VISN, `Libs/*.LIB`, LCL) are provided **freely for the community** under the
**MIT licence in `LICENSE`** — use, modify, and redistribute them. That licence covers this
project's own code only: the OpenGlide fork in `source/openglide-src/` stays under OpenGlide's
terms (see above). If you build on the format research or tools, a credit/link back to Sonatix is
appreciated but not required.

## No warranty
Provided as-is, at your own risk. Back up your install first. What it touches:

- **Always:** `glide2x.dll` in the game folder, and the display mode while the game runs (both are
  restored — the renderer from `backup/`, the mode on exit).
- **Vanilla via DirectX:** `ddraw.dll` for that run, removed afterwards.
- **Only if you ask for it:** `texture.lib` of the library you install an edit into (originals
  copied to `backup/<World>_TEXTURES.orig/` first, and **Restore originals** puts them back), and
  the `_C_100` mission slot if you use the Debug tab's test-map swap (restored when the game
  exits).

Nothing else in the game's data is modified, and no game file is ever deleted.
