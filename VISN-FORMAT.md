# VISN — the Incubation texture codec, fully specified

*Blue Byte's custom image codec, used for the 3D/model textures in `WorldSet/*/TEXTURES/texture.lib`.
Community-reported to be the same codec in **Extreme Assault** (unverified here).*

The container splits easily — the `VISN` magic is right there at the start of every record — but
the compressed payload behind it had no public description, and no tool could read it. This
document is that description.

**VISN is JPEG with a different bitstream syntax.** Standard JPEG Annex K quantisation tables,
standard zigzag, standard IJG quality scaling, AAN fast IDCT. Only the entropy layer and the
container are custom — and they are *simpler* than JPEG's.

Recovered by disassembling the decoder. Everything below is read off the machine code, not
inferred from sample data.

## Where the decoder is

In **`Eng3d.dll`**, not in `Incubation.exe` — the codec lives in the 3D engine DLL, and it is
**exported by name**:

| Export | RVA | Purpose |
|--------|-----|---------|
| `_E3D_init_vision` | 0x23d8 | builds the colour tables; call with `0x565` for RGB565 (`0x555` = RGB555) |
| `_E3D_decode_picture` | 0x23e8 | `(src, dst, stride_in_pixels)` — decodes one VISN record |
| `_E3D_decode_picture_halve_size` | 0x24f8 | same, decodes to half resolution |
| `_E3D_convert_picblock_from_64kcolor_to_32kcolor` | 0x24d0 | RGB565 → RGB555 |

Those are thunks; the real code starts at `0x412648` (imagebase 0x400000). The original source
module name survives in the binary: `SRC\devision.asm` — the whole codec is hand-written 32-bit
assembly, which is why decompilers produce nonsense for it. Reference binary used here:
`Eng3d.dll`, 666 507 bytes, MD5 `2BB3BC9FB8B766837779DD1FAF09FE8D` (GOG release).

**You do not have to use it, though.** `tools/visn.py` in this kit is a from-scratch decoder in
pure Python — no game DLL, any Python, 32- or 64-bit, ~0.07 s per 256×256 texture:

```
python visn.py info   WorldSet/World_A00/TEXTURES/texture.lib
python visn.py decode WorldSet/World_A00/TEXTURES/texture.lib -o out/
```

Calling the game's own decoder is still the shortest path if you are working in another language
(32-bit process required): `_E3D_init_vision(0x565)` once, then
`_E3D_decode_picture(record, out, stride)` into a `stride*height*2` RGB565 buffer —
`tools/incu_lib.py` does that. The spec below is what you need for your own decoder, or an
**encoder**.

## Container

`texture.lib` is a plain concatenation of VISN records. The table of contents is a sibling file:
`<name>.dir` (plain text) or `<name>.din` (binary).

```
3DI
[DIRECTORY]
<name>\t\t<type> <index> <offset> <size> <mtime>
...
ENDDIR
[END3DI]
```

Binary `.din`: `"DBIN"`, `u32 count`, then per entry `u32 index`, `char name[13]` (NUL-padded),
`u32 offset`, `u32 size`.

## Record header

```
off  size  meaning
0    4     "VISN"
4    2     u16  width  in pixels
6    2     u16  height in pixels
8    1     quality 1..100  (IJG scale; retail textures use 0x5D = 93)
9    1     mode: 0 = 4:2:0, 16×16 macroblocks, 6 blocks each
                 2 = 4:4:4,  8×8  macroblocks, 3 blocks each   <-- what the game's textures use
10   ..    bitstream
```

Only modes 0 and 2 exist (the dispatch table's middle slot is `0xFFFFFFFF`). Macroblock counts are
`width >> 4` by `height >> 4`, and mode 2 then doubles both — giving 8-pixel macroblocks.

The third argument to `_E3D_decode_picture` is the **destination stride in pixels**, not the
picture width; you can decode into a larger buffer.

## Bitstream mechanics

A sequence of **16-bit little-endian words**, bits consumed **MSB-first**.

- Initial fill: read the dword at offset 10 and rotate it left by 16 (i.e. word 0 occupies the
  high half, word 1 the low half). 32 bits available.
- Refill (when fewer than *n* bits are buffered): take the next 16-bit LE word `w`, then
  `buffer |= (w << 16) >> bitcount`, `bitcount += 16`.
- Read *n* bits: `v = buffer >> (32 − n)`, `buffer <<= n`, `bitcount −= n`.

An encoder packs bits MSB-first into 16-bit LE words. **Pad the end with 2–4 spare words** — the
decoder pre-reads up to 32 bits and will run past the last block.

## Picture prologue — two Huffman tables

Right after the initial fill, two code-length tables are read, in this order:

1. table **A** — used by the **chroma** blocks,
2. table **B** — used by the **luma** blocks.

Each is encoded as:

```
12 bits : N = number of symbols (the game writes 0x81 = 129)
then N code lengths, delta-coded mod 16, using a FIXED built-in meta-code over 17 meta-symbols:
    meta 0x00..0x0F : running = (running + meta) & 0xF ; emit running as the next length
    meta 0x10       : followed by 5 bits = k ; emit k entries of length 0 (unused symbol)
running starts at 0
```

The meta-alphabet's own code lengths are hard-coded in the DLL:
`[2, 2, 3, 4, 8, 8, 9, 9, 8, 8, 8, 8, 8, 5, 4, 3, 4]`, assigned canonically (below).

### Canonical assignment

Textbook, identical to the JPEG/DEFLATE convention:

```
count[len] for len = 1..15          (0 = symbol unused, >15 = error)
next[1] = 0 ;  next[len+1] = (next[len] + count[len]) << 1
symbols take codes in increasing symbol order within each length
```

Codes of length ≤ 8 are expanded into a 256-entry lookup table; longer codes walk a bit-tree.
**Keep every code ≤ 8 bits and the tree is never used.**

## Block syntax

Blocks per macroblock, in stream order:

- mode 0 (16×16): **Cb, Cr, Y0, Y1, Y2, Y3**
- mode 2 (8×8): **Cb, Cr, Y**

Each block:

```
6 bits  : nAC — how many AC coefficients follow (0..63)
12 bits : DC + 0x800   (decoder subtracts 0x800 → signed, −2048..2047)
nAC symbols, one coefficient each, in zigzag scan order
```

- **The DC is raw** — not quantised, not dequantised, not predicted from the previous block.
- Coefficient symbols (alphabet of 129):

  | symbol | meaning |
  |--------|---------|
  | `0x00..0x74` | value = `symbol − 0x3A` (−58..+58), no extra bits |
  | `0x75..0x80` | escape: `n = symbol − 0x74` (1..12) extra bits follow, read as a **signed** n-bit value |

  then `coefficient = (value * qtab[scan_position]) >> 14`.
- **Zeros are explicit** (symbol `0x3A`). There is no run-length coding and no EOB marker — `nAC`
  alone ends the block.
- Coefficients past `nAC` are not cleared per block: the decoder keeps a per-plane high-water mark
  and only zeroes the tail left over from the *previous* block of that plane. Irrelevant to an
  encoder, but a reimplemented decoder must match it.

## Quantisation

The base tables are the **standard JPEG Annex K** ones — luma begins `16 11 10 16 24 40 51 61`,
chroma begins `17 18 24 47 99 99 99 99`. Scaling is plain IJG:

```
q     = header byte 8, clamped to >= 1
scale = (q > 50) ? (100 − q) * 2 : 5000 / q
value = clamp((base[i] * scale + 50) / 100, 1, 255)      # i in raster order
qtab[ zigzag[i] ] = value * aanscale[i]                  # stored in SCAN order
```

`aanscale` is the classic IJG AAN table: the outer product of
`{16384, 22725, 21407, 19266, 16384, 12873, 8867, 4520}` divided by 16384. One caveat — the last
entry in the shipped table is **124** where the formula gives 1246, an apparent typo in Blue Byte's
data. It only affects the highest-frequency coefficient. **Reproduce it as-is; do not "fix" it.**

## Transform

AAN fast IDCT (the `jpeg_idct_ifast` family), int32, with the usual "all AC in this column are
zero → replicate the DC" shortcut. Coefficients arrive already multiplied by
`quant * aanscale >> 14`, i.e. in the prescaled convention — so an encoder needs the matching AAN
forward DCT with the inverse prescale.

Fixed-point constants, 8-bit: `362` (√2), `473` (1.8477), `277` (1.0824), `−669` (−2.6131) — the
IJG ifast set. Pass 1 runs down the **columns** and does **not** descale; pass 2 runs along the
**rows** and shifts right by 3. Shifts are arithmetic (floor), which matters for negatives.

There is **no level shift and no clamping in the IDCT**. The `+128` rides in the DC coefficient —
the encoder simply never subtracts it, so a mid-grey block carries a DC of about `128 * 8` and the
IDCT output lands in 0..255 on its own. Clamping happens in the colour tables.

## Colour

Fully table-driven. Per pixel, with the three planes in stream order **Cb, Cr, Y**:

```
yi  = clamp(Y,  0, 256)                     # note the upper bound is 256, not 255
cbi = clamp(Cb, 0, 256)
cri = clamp(Cr, 0, 256)
pixel =  Rtab[ yi + dR  (cri) ]
       | Gtab[ yi + dGcb(cbi) + dGcr(cri) ]
       | Btab[ yi + dB  (cbi) ]
```

The chroma deltas are IJG's integer YCbCr coefficients, `delta(i) = (FIX * (i − 128) + 32768) >> 16`
with an arithmetic (floor) shift:

| delta | FIX | note |
|-------|-----|------|
| `dR`   (Cr) | `+91881`  | `int(1.40200 * 65536 + 0.5)` |
| `dB`   (Cb) | `+116129` | `int(1.77200 * 65536)` — **truncated, not rounded**; the rounded 116130 gives 222 instead of 221 at Cb = 253 |
| `dGcb` (Cb) | `−22554`  | `int(0.34414 * 65536 + 0.5)`, negated |
| `dGcr` (Cr) | `−46802`  | `int(0.71414 * 65536 + 0.5)`, negated |

Each channel table already holds its **shifted RGB565 field**, so the three lookups are simply
OR'd together. For an index `i`:

```
i < 0            -> 0
0 <= i <= 255    -> ((i * 31) // 255) << 11   (R)     full-range scaling,
                    ((i * 63) // 255) <<  5   (G)     NOT a bit shift
                    ((i * 31) // 255)         (B)
256 <= i <= 383  -> the saturated value (31 / 63 / 31, shifted)
i > 383          -> 0
```

## Verification status

Every statement above has been checked by an independent implementation: a from-scratch decoder
written only from this document reproduces the game decoder's output **byte-for-byte on all 723
VISN records in the retail game** — 384 across the nine `WorldSet/*/TEXTURES/texture.lib`
libraries and 339 across the `Video/*/Textures/Texture.lib` cutscene libraries. The quantisation
tables it computes also match the ones `Eng3d.dll` builds in memory, all 64 entries, for both
luma and chroma. That decoder is `tools/visn.py` in this kit.

## Encoding

**`tools/visn.py` in this kit encodes as well as decodes**, so you can edit a texture and put it
back into `texture.lib` for the **vanilla game**:

```
python visn.py decode WorldSet/World_A00/TEXTURES/texture.lib -o out/
#   ... edit out/al040000.png in any image editor ...
python visn.py repack WorldSet/World_A00/TEXTURES/texture.lib out/ -o new/texture.lib
```

`repack` re-encodes only the records for which a matching `<name>.png` exists and copies the rest
byte-for-byte, then rewrites the `.dir` and `.din` tables with the new offsets. With no PNGs
present it reproduces the input library byte-identically.

### The one piece of maths you need

The decoder reconstructs a coefficient as `coef = (sym * quant[k] * aan[k]) >> 14`, and the AAN
inverse transform wants its input prescaled as `X = F * aan / 16384`, where `F` is the plain DCT-II
with the usual `(1/4)c(u)c(v)` normalisation. **The AAN factor cancels**, so

```
sym = round(F / quant)          # textbook JPEG quantisation, prescale not involved
DC  = F[0]  = 8 * mean(block)   # transmitted raw, unquantised, carries the +128 level shift
```

Set `nAC` to the scan index of the last non-zero coefficient and emit every symbol from 1 to `nAC`
(zeros included — symbol `0x3A`).

### Why the entropy layer is easy

- **The Huffman tables are transmitted per picture, so you choose them.** Give all 129 symbols
  8-bit codes and canonical assignment makes `code(symbol s) == byte s` — emitting a symbol is
  emitting its byte. (129 of 256 slots used; an incomplete code is fine, the decoder never checks.)
  `visn.py` instead builds a real per-image Huffman code from the symbol histogram, limited to 15
  bits; that is what keeps its output the same size as Blue Byte's.
- Coefficients are independent symbols — no run/size pairs to construct, no EOB.
- Pad the bitstream with a few spare words; the decoder pre-reads up to 32 bits.

### Measured results

Re-encoding all 61 records of `World_A00` at the game's own quality setting (93), compared against
the original decoded image:

| | |
|---|---|
| PSNR | 32.2 – 40.3 dB, average **35.0 dB** |
| Size | **104 %** of Blue Byte's own encoder |
| Accepted by the game's decoder | **61 / 61**, output identical to our decoder |

That is essentially the format's ceiling, not the encoder's: the colour stage alone —
RGB → YCbCr → the decoder's tables → RGB565, **with no DCT at all** — already costs 36.6 dB on the
same image, and our full encode of it scores 36.3 dB. Raising the quality byte above ~93 therefore
buys almost no fidelity and costs a lot of size (q=99 doubles the file for +0 dB).

## Hard limit worth knowing

Textures are **256×256** and cannot be made larger, no matter how you repack: the size is enforced
by the asset, by the engine's texture page, and by the Glide API's `GR_LOD_256`. A bigger record
renders as stride-mismatched garbage. Real HD requires substituting the image **in the renderer**
(what the OpenGlide fork in this kit does); a VISN encoder is for **editing texture content for the
vanilla game**, not for resolution.
