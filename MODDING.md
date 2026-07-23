# Incubation — reverse-engineered file formats (a modder's reference)

Everything here was reverse-engineered from the retail game. It's enough to read the game's
textures, UI graphics, and — importantly — its **plain-text game logic**. This is the reference
for deeper mods and for anyone considering a remake.

All offsets are little-endian. Paths are relative to the game install folder.

## What you can change today — at a glance

| Asset | Format | Read | Write back | Tool |
|-------|--------|:----:|:----------:|------|
| 3D/world textures — `WorldSet/*/TEXTURES/texture.lib` | VISN (§1) | ✅ | ✅ | `tools/visn.py` |
| Cutscene textures — `Video/*/Textures/Texture.lib` | VISN (§1) | ✅ | ✅ | `tools/visn.py` |
| UI sprites — `Libs/*.LIB` | palettised (§2) | ✅ | ⚠️ | `hd_tool.py extract2d`; write-back only via the game's own `LibTool` (§9) |
| Fullscreen art — `Graphics/*.bmp` | plain BMP (§3) | ✅ | ✅ | any image editor |
| Unit / weapon / terrain stats — `DATA/Info.lcl` | XOR 0xFF text (§4) | ✅ | ✅ | 3 lines of Python |
| Mission scripts — `Missions/*.lcl` | XOR 0xFF text (§4) | ✅ | ✅ | 3 lines of Python |
| GUI layout — `DATA/GUI/*.lcl` | XOR 0xFF text (§4) | ✅ | ✅ | 3 lines of Python |
| Sound — `Waves/*.wav` | plain WAV (§5) | ✅ | ✅ | any audio editor |
| Scene / object placement — `WorldSet/*/Worlds/*.3DW` | plain text (§6) | ✅ | ✅ | any text editor |
| Models & animations — `CHData/*.cho`, `*.cha` | chunked, tagged (§7) | 🟡 | ❌ | structure known, contents not |
| Maps — `Missions/*.lev` | binary (§8) | ❌ | ❌ | — |

✅ done and proven · ⚠️ possible but awkward · 🟡 structure known, payload not · ❌ open

The short version: **everything except the maps and the model interiors is already reachable**, and
three whole categories (stats/scripts, sound, scene layout) are plain text or plain WAV — no tool
required at all.

---

## 1. Textures — `.lib` / VISN  (world & video, 256×256, RGB565)  ★ fully specified

- A `texture.lib` is a concatenation of **`VISN`** picture records. The record table (offset,
  size, name) lives in a sibling **`.dir`** (plain text) or **`.din`** (binary) file.
- **VISN is JPEG with a different bitstream syntax** — standard JPEG Annex K quantisation tables,
  standard zigzag, standard IJG quality scaling, AAN fast IDCT; only the entropy layer and the
  container are custom, and they're *simpler* than JPEG's. Output is 16-bit **RGB565**, 256×256.
  **→ Full specification: [VISN-FORMAT.md](VISN-FORMAT.md)** — header, bit packing, Huffman
  layer, block syntax, quantisation, and how to write an encoder.
- **`tools/visn.py` decodes VISN on its own** — pure Python, no game DLL, any Python (32- or
  64-bit), ~0.07 s per 256×256 texture. Verified **byte-for-byte against the game's own decoder on
  all 723 VISN records** in the retail game (384 world + 339 cutscene).
  `python visn.py decode <texture.lib> -o out/`
- The game's decoder lives in **`Eng3d.dll`**, not in `Incubation.exe`, and it is
  **exported by name**: `_E3D_init_vision(0x565)` then
  `_E3D_decode_picture(src, dst, stride_in_pixels)`. Calling it is still the shortest path from
  another language — but since `Eng3d.dll` is a 32-bit PE, that route needs a 32-bit process.
- **`visn.py` also encodes**, so edited textures can go back into a `texture.lib` and be rendered
  by the **vanilla game** — no renderer swap, no DLLs:
  `python visn.py repack <texture.lib> <png_dir> -o new/texture.lib` (re-encodes only the records
  with a matching `<name>.png`, copies the rest byte-for-byte, rewrites `.dir`/`.din`).
  Re-encoding a whole library averages **35 dB PSNR at 104 % of Blue Byte's size**, and all 61
  records were accepted by the game's own decoder. That is the format's ceiling, not the
  encoder's — its colour stage alone costs 36.6 dB with no DCT involved.
- The game files themselves contain **no encoder** (all 89 `Eng3d.dll` exports plus
  `ENGWLIB.DLL` / `NewToolsR.dll` / the `-debugx` editor tools were checked) — Blue Byte's was an
  internal build tool. Ours was written from the spec in **VISN-FORMAT.md**.
- The 256×256 size is enforced at three levels (assets, engine page, and the Glide API's
  `GR_LOD_256`), so you can never make a `.lib` texture bigger. **HD is done in the renderer**
  (our OpenGlide fork substitutes a larger image at upload; the game's normalised UVs do the
  rest). An encoder is for **changing texture content in the vanilla game**, not for resolution.
- Tools: `tools/incu_lib.py` (list/extract/preview/pack), `tools/hd_tool.py extract` (all textures →
  PNG, named by the FNV-1a hash of the 256×256 RGB565 the game uploads — that hash is the
  runtime substitution key). `pack` currently repackages raw VISN records byte-losslessly
  (rearrange/swap textures); it does not re-encode.

## 2. UI sprites — `Libs/*.LIB`  (buttons, cursor, icons, medals, fonts, weapons)

A separate, **uncompressed palettized** format (NOT VISN). 58 files, all share it. Cracked
2026; `tools/hd_tool.py extract2d` dumps every sprite to PNG.

```
Header (20 bytes):  u32 magic = 0x000000FF
                    u32 count            (number of sprites)
                    u32 filesize
                    u32 20               (header size)
                    u32 data_offset      (where pixel data begins)
TOC:  count × 36-byte entries, each 9×u32:
      [ type(=2), width, height, 0, 0, 0, width*height, f7, f8 ]   (f7,f8 ≈ hotspot/bbox, unused)
Pixels: at data_offset, concatenated, per entry = width*height bytes of 8-bit palette indices.
        sum(width*height) == filesize - data_offset  (exact; mouse.LIB has +2 padding)
```

- **Palette** = `Graphics/<name>.pal`, which is itself a **BMP**; its 256-colour table (BGRA,
  4 bytes/entry) sits at BMP file **offset 54**. Match by name (`buttons.LIB` → `buttons.pal`;
  `item_w2.LIB` → `items_w.pal`; `uicons2.LIB` → `UIcons.pal`). A few (`font_0..3`, `addons*`)
  have no direct palette and come out grayscale.
- **These cannot be HD-injected at the renderer** — the game composites the whole UI into one
  ~640×480 frame before it reaches the renderer. Useful for reference or native-size repaints.

## 3. Fullscreen 2D art — `Graphics/*.bmp`

Plain 8-bit **BMP** files, 640×480: `Title.bmp`, `Bluebyte.bmp`, `Credits.bmp`, `MsgScr.bmp`,
`Ship.bmp`, `Graphics/GUI/plate_1..7.bmp` (menu panels), and ~96 `Graphics/Briefing/*.bmp`.
Editable in any image editor. (Same renderer caveat as §2 for making them *bigger*.)

## 4. Game logic & balance — `.lcl` / `.gcl`  (LCL scripting language)  ★ the big one

The game's scripting language, **LCL** (Blue Byte, credited to Andreas Nitsche, 1996–97). Every
`.lcl`/`.gcl` file is obfuscated with a **single-byte XOR 0xFF** (bitwise NOT) and decodes to
readable plain-text source. (`WorldDesc/*.lcl` are already plain.)

```python
text = bytes(b ^ 0xFF for b in open(path, "rb").read()).decode("latin-1")
```

| File | Contains |
|------|----------|
| **`DATA/Info.lcl`** | **the master balance file** — `SetWeaponInfo(id, name, …≈18 numbers…)`, `SetUnitInfo(id, name, "<model>.3DI", …)` (links each unit to its model), `SetEquipInfo(…)`, `SetCtrlMapInfo(id, …, cover%, name)` (terrain + cover). Literal numbers → edit balance directly. |
| `Missions/*.lcl` (307) | per-mission triggers, objectives, dialogs, camera paths, doors/elevators/barriers, `InsertUnit` spawns, `GetUnitsInArea`, action points (`SetActPt`/`GetActPt`), `HeroKilled` |
| `DATA/GUI/*.lcl` | GUI layout (`GUI_SetText/Button/Icon/Window/Listbox`) |
| `WorldDesc/*.lcl` | world descriptions (already plain text) |

**Engine event model (free bonus):** mission scripts dispatch on `_A_Calltype` with branches for
`NEXT PLAYER`, `MOVE UNIT`, `ATTACK`, `USE`, `NEXT TURN`, `INIT MAP`, `DIALOG` — a ready map of
where the engine calls into game logic.

> ⚠️ **The numbers are data; the formulas are code.** LCL gives you the stat tables and mission
> flow, but the actual combat maths (hit chance, damage roll, line-of-sight, how cover applies,
> AP costs, reaction fire) and the **tactical AI** are compiled x86 inside `Incubation.exe`
> (1 MB, stripped). LCL has no AI-decision commands. To recover the formulas you'd disassemble
> the exe (Ghidra — and LCL hands you the stat names/order to anchor the search) and/or observe
> the running game with an injected logging DLL.

## 5. Sound — `Waves/*.wav`

100 **plain RIFF/WAV** files. No container, no compression, no tool needed: replace them with
same-named WAVs and the game plays yours. The easiest mod in the whole game.

## 6. World / scene layout — `WorldSet/*/Worlds/*.3DW`  ★ plain text

Each world folder holds a handful of `.3DW` scene files (`LEVEL01A.3DW`, `CITY.3DW`, …) and they
are **readable, editable text**:

```
3DW
[COORD_SYSTEM] X_RIGHT_Z_INFRONT_Y_DOWN

[GRP] OBJECTE:\BI4\BACKUPS\HICOL\WORLD1\OBJECTS\LEVEL01A.3DW
 LEVEL01A.000
 ...
ENDGRP

[CLO] LEVEL01A.000
PROTOTYP LEVEL01A.000
ROTATION ...
```

So object placement, grouping and orientation for a scene are directly hand-editable. (The build
paths left in the files also confirm the internal project name: **BI4** — Battle Isle 4.)

**This is also how you find which world a mission uses.** A mission's `.lev` names its scene in the
first bytes, and that scene lives in exactly one `WorldSet/World_*/Worlds/` folder. Worked example:
`_C_100.lev` → `Level01e` → `WorldSet/World_A00/Worlds/LEVEL01E.3DW`, so **the first campaign
missions use `World_A00`** — which is the library to edit if you want your texture mod visible
right away.

## 7. Models & animations — `CHData/`, `Video/*/*.cha`

Not cracked, but **not opaque either** — they are chunked, self-describing files:

```
u32 version(=1) | u32 length | <length bytes>   ... repeating
```

and the very first chunk is an ASCII type tag:

| File | First tag | Count |
|------|-----------|-------|
| `CHData/Objects/*.cho` | `V100ModelDesc` | 114 |
| `CHData/Animations/*.cha` | `KeyFramedAnimationDesc` | 114 |
| `Video/*/Animation_*.cha` | `KeyFramedAnimationDesc` | cutscene animation |

The tag names ("model description", "key-framed animation description") plus the length-prefixed
chunk walk are a solid starting point for anyone who wants to attack the model format.
`SetUnitInfo` in `DATA/Info.lcl` (§4) tells you which `.3DI` model belongs to which unit.

## 8. Still binary / not cracked

| File | Notes |
|------|-------|
| `Missions/*.lev` (~213 KB) | the actual **maps** — tiles, heights, unit placement. The biggest remaining data target. The first bytes are ASCII: the **next** map's stem, then this map's own stem, then its `.3DW` scene name. |
| `WorldSet/*/Objects/prototyp.bin` + `.dir`/`.din` | Same `3DI`/`[DIRECTORY]` catalogue convention as §1, but a **different field set** — `name type idx N size` (four numbers, no mtime) and it is *not* a plain offset table: the sizes do not sum to the `.bin`, and the third field is a small enum (0–10, apparently a type code). 2179 entries against a 1.3 MB blob, so most entries must point elsewhere. The `.din` here is **not** the `DBIN` layout used by `texture.din`. Open. |
| `WorldSet/*/IMG/*.IMG` | `ATN.IMG`, `TRIG.IMG` — 2050 bytes, looks like a small `u16` lookup table. |
| `DATA/Misc/Rec_0.dat` (82 KB) | binary record table, purpose unknown. |

## 9. The developers' own tools are still in the exe

`Incubation.exe -debugx` opens Blue Byte's internal **TestVersion** menu: the usual
3DFX / DirectX / Window entries plus **Debug A**, **Librarytool**, **Systeminfos** and
**MapDesigner**. `LibTool` opens the palettised `Libs/*.LIB` archives (§2) and can save them back —
copy the matching `.pal` next to the `.LIB` first or it fails. It does **not** open the VISN
`texture.lib` files. `Editor.exe` and `iDesigner.exe` ship in the game folder too.

Launcher trivia worth knowing before you script anything: `Incubation.exe` with **no arguments**
runs the 1997 CD check, while `Incubation.exe -3dfx` skips it. GOG's `launcher.exe` is CD-free but
Windows demands UAC elevation for it (its name matches the installer-detection heuristic and it
carries no manifest), so `-3dfx` is the friction-free way to start the game from a script.

---

## Where the HD substitution hooks in (for renderer hackers)

`Incubation.exe -3dfx` → `ENG3DFX.DLL` → `glide2x.dll` (our OpenGlide fork) → OpenGL. On each
new texture, `PGTexture::MakeReady` computes a hash and (in `hd_inject.cpp`) checks for
`hd_pack_hd/<fnv8>.rgba`; if present it `glTexImage2D`s the larger image instead of the 256×256
one. The FNV-1a in `tools/hd_tool.py` must match the C implementation in `hd_inject.cpp`.
Normal maps for bump use the same key with an `_n` suffix (`hd_pack_hd/<fnv8>_n.rgba`).

## Thinking about a remake?

The clean-room pattern (OpenXcom, Devilution, OpenRCT2, OpenTTD, Corsix-TH): reuse the original
data files, reimplement the rules. LCL (§4) gives you units/weapons/equipment/terrain/missions
for free; you'd still need to crack `.lev` (§5) and recover the combat/AI formulas from the exe.
The ship-no-assets model (read the player's installed copy at runtime) keeps it legal.
