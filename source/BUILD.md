# Building the renderer (and the ddraw proxy)

You do **not** need this to play — `game_files/glide2x.dll` is prebuilt. This is for the license
(OpenGlide source is included) and for anyone who wants to change the renderer.

## Toolchain
- **32-bit MinGW-w64** GCC/G++ (i686). The game is a 32-bit process, so the DLL must be 32-bit.
- Nothing else — the build is self-contained and statically links the C/C++ runtimes.

## The OpenGlide fork (`source/openglide-src/`)

Our added / modified files on top of the fcbarros/openglide base:

| File | What we added |
|------|---------------|
| `hd_inject.cpp` | HD texture substitution (the core) + anisotropic/mipmaps on HD textures + `bump3d_register` call |
| `bump3d.cpp` | experimental screen-space fake bump / normal mapping (per-texture via `<fnv>_n.rgba`) |
| `sharp2d.cpp` | GLSL unsharp-mask pass on the composited 2D layer |
| `input_remap.cpp` | fullscreen mouse remap (IAT-hooks the game's ClipCursor/Get/SetCursorPos) + focus-based gamma |
| `platform/windows/window.cpp` | window adopt + pillarbox, MSAA pixel-format probe, gamma apply/restore |
| `GlOgl.h` | fractional pillarbox scaling macros (`G_SCALE`, `VX_SCALE`, …) |
| `Glide.cpp`, `grguSstGlide.cpp`, `grguMisc.cpp`, `grguDepth.cpp` | viewport uses `G_XOFF + VSZ(...)` |
| `grguLfb.cpp` | 2D LFB texture LINEAR filter + the `sharp2d` hook + color-key alpha fix |
| `GLRender.cpp` | `bump3d_begin/end` around the 3D draw; `g_FrameDrawnTriangles` |
| `stubs20.c` | 20 stub exports (`pci*`, `guMP*`, `grSstConfigPipeline`, `grSstVidMode`) the game imports |
| `Glide2x.def` | +20 exports for the stubs |

### Build command (from `source/openglide-src/`, MinGW on PATH)
```sh
# 1) compile the C stubs to an object first (g++ would name-mangle a .c)
gcc -c -O2 stubs20.c -o stubs20.o

# 2) compile the version resource. Without it the DLL has no resource directory
#    at all - no product, company or version - which is one of the things
#    Defender's ML heuristic holds against an unsigned binary.
windres incu_version.rc -O coff -o incu_version.o

# 3) link everything into a 32-bit glide2x.dll. -s strips debug symbols, which
#    also removes the MinGW /NN debug sections (652 KB -> 350 KB).
SRC=$(ls *.cpp | grep -vE "gbanner.cpp|gsplash.cpp")
g++ -shared -O2 -s -DWIN32 -D_WINDOWS -DHAVE_CONFIG_H -DOGL_DONE -include compat.h -I. -Iplatform/windows \
  $SRC stubs20.o incu_version.o platform/windows/{clock,error,library,openglext,window}.cpp Glide2x.def \
  -static -static-libgcc -static-libstdc++ -lopengl32 -lglu32 -lgdi32 -luser32 -lwinmm \
  -o glide2x_ogl.dll

# 4) deploy
cp glide2x_ogl.dll "<game>/glide2x.dll"
```

Notes:
- **`-static -static-libgcc -static-libstdc++` is required** — otherwise the game can't load the
  DLL (no libstdc++/libgcc runtime DLLs alongside it).
- `-DOGL_DONE` enables logging to `OpenGLid.log` (handy for debugging).
- Verify the DLL still satisfies all 144 imports of `ENG3DFX.DLL` (diff its imports vs the DLL's
  exports) if you touch the exports.
- ⚠️ `OpenGLid.ini` overrides compiled defaults (e.g. `InitFullScreen`) — keep `InitFullScreen=0`.

Runtime env vars the renderer reads: `INCU_SHARP` (2D sharpen 0–~0.6), `INCU_BUMP` (bump strength
0–~2, or >10 = show the normal map), `INCU_STRETCH` (0 = keep 4:3 pillarboxed, 1 = stretch to
fill). The launcher sets these for you.

### Verifying the shipped DLL against your own build

Everything needed to rebuild `game_files/glide2x.dll` is in this folder — that is the point of
shipping the source, especially given the Defender false positive (see the README). A rebuild here
produces the same size and the same 147 exports as the shipped binary.

It will **not** be byte-identical, and that is expected: the build is not reproducible. MinGW
stamps the PE header with the build time and the linker's layout varies slightly between runs, so
roughly 3–4 % of bytes differ between two builds of the same source. Compare what actually
matters instead:

```sh
# same exports, same count?
objdump -p rebuilt.dll   | grep -A2000 "Export Address Table" | wc -l
# the switches are present?
strings rebuilt.dll | grep INCU_
# the symbol the game imports is exported?
strings rebuilt.dll | grep _ConvertAndDownloadRle@64
```

## The ddraw proxy (`source/ddraw-wrapper/`)

A thin C++ COM pass-through in front of DDrawCompat (`ddraw_proxy.cpp` → `DDraw.dll`, which loads
`ddraw_impl.dll`). Build with MinGW:
```sh
g++ -shared -O2 -DWIN32 -D_WINDOWS ddraw_proxy.cpp ddraw.def \
  -static -static-libgcc -static-libstdc++ -luuid -lole32 -lgdi32 -luser32 -o ddraw.dll
```

## `setres.exe` (display-mode helper, optional)
`gcc -O2 game_files/tools/setres.c -o setres.exe -luser32` (the launcher changes modes itself via
ctypes; `setres` is only used by the legacy `.bat` launchers).
