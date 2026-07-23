# Incubation — reverse-engineered file formats (a modder's reference)

Everything here was reverse-engineered from the retail game. It's enough to read the game's
textures, UI graphics, and — importantly — its **plain-text game logic**. This is the reference
for deeper mods and for anyone considering a remake.

All offsets are little-endian. Paths are relative to the game install folder.

---

## 1. Textures — `.lib` / VISN  (world & video, 256×256, RGB565)

- A `texture.lib` is a concatenation of **`VISN`** picture records. The record table (offset,
  size, name) lives in a sibling **`.dir`** (plain text) or **`.din`** (binary) file.
- VISN is a custom JPEG-like **DCT codec** → 16-bit **RGB565**, always **256×256**. We do not
  decode the DCT ourselves; we call the game's own decoder in **`Eng3d.dll`**:
  `_E3D_init_vision(0x565)` then `_E3D_decode_picture(src, dst, width)`.
  Because `Eng3d.dll` is a 32-bit PE, **decoding must run under 32-bit Python.**
- The 256×256 size is enforced at three levels (assets, engine page, and the Glide API's
  `GR_LOD_256`), so you can never make a `.lib` texture bigger. **HD is done in the renderer**
  (our OpenGlide fork substitutes a larger image at upload; the game's normalised UVs do the
  rest). There is **no VISN encoder** — you don't need one for HD.
- Tools: `tools/incu_lib.py` (list/extract/preview), `tools/hd_tool.py extract` (all textures →
  PNG, named by the FNV-1a hash of the 256×256 RGB565 the game uploads — that hash is the
  runtime substitution key).

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

## 5. Still binary / not cracked

| File | Notes |
|------|-------|
| `Missions/*.lev` (~213 KB) | the actual **maps** — tiles, heights, unit placement. The biggest remaining data target. |
| `CHData/*.cho`, `*.cha` | 3D **models & animations**. `SetUnitInfo` references `.3DI` model names. |
| `DATA/Misc/Rec_0.dat` (82 KB) | binary record table, purpose unknown. |

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
