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
**DDrawCompat** by **narzoul** (`ddraw_impl.dll`) handles the game's DirectDraw layer on modern
Windows. It is redistributed here unmodified; see https://github.com/narzoul/DDrawCompat for its
source and license. `DDraw.dll` in this package is our own thin logging/pass-through proxy in
front of it (source in `source/ddraw-wrapper/`).

## The fallback renderer (optional)
The launcher can swap in **dgVoodoo 2** by **Dege** as a no-HD fallback. dgVoodoo is **not**
included in this package — download it only from the official source
(https://dege.freeweb.hu/ or https://github.com/dege-diosg/dgVoodoo2/releases) if you want that
fallback. The included `dgVoodoo.conf` is only a configuration file.

## This project
Created and directed by **Sonatix** — the vision, the design decisions, the testing at every
step, and the HD texture work. The implementation (reverse-engineering, renderer, and tools) was
done with AI assistance (**Claude**, by Anthropic) under that direction.

The HD texture/normal-map injection, the input remap, the MSAA/anisotropic/gamma/2D-sharpen and
bump code, the `hd_tool` pipeline, the GUI launcher, `setres`, and the format reverse-engineering
(VISN usage, `Libs/*.LIB`, LCL) are provided **freely for the community** — use, modify, and
redistribute them. If you build on the format research or tools, a credit/link back to Sonatix is
appreciated but not required.

## No warranty
Provided as-is. It modifies how a game renders on your machine and briefly changes the display
mode; it does not touch the game's data files, but back up your install anyway. You run it at
your own risk.
