#!/usr/bin/env python3
"""visn.py — a standalone decoder for Blue Byte's VISN image codec (Incubation, 1997).

Pure Python. Needs NO game DLL and runs on any Python (32- or 64-bit) — unlike the
`Eng3d.dll` route in incu_lib.py, which requires 32-bit Python.

VISN is JPEG with a different bitstream syntax: standard JPEG Annex K quantisation
tables, standard zigzag, IJG quality scaling, AAN fast IDCT. Only the entropy layer and
the container are custom. Full format write-up: re-visn/VISN-FORMAT.md.

    import visn
    w, h, rgb565 = visn.decode(record_bytes)      # bytes, little-endian RGB565
    img = visn.decode_to_image(record_bytes)      # PIL Image (needs Pillow)

CLI:
    python visn.py info    <file.lib|file.visn>
    python visn.py decode  <file.lib> -o out/     # every record -> PNG
    python visn.py verify  <file.lib>             # compare against the game's own decoder
                                                  # (32-bit Python + Eng3d.dll required)
"""
import os
import struct
import sys

# --------------------------------------------------------------------------- constants
# Standard JPEG zigzag: NATURAL_ORDER[scan_position] = raster index.
NATURAL_ORDER = (
     0,  1,  8, 16,  9,  2,  3, 10, 17, 24, 32, 25, 18, 11,  4,  5,
    12, 19, 26, 33, 40, 48, 41, 34, 27, 20, 13,  6,  7, 14, 21, 28,
    35, 42, 49, 56, 57, 50, 43, 36, 29, 22, 15, 23, 30, 37, 44, 51,
    58, 59, 52, 45, 38, 31, 39, 46, 53, 60, 61, 54, 47, 55, 62, 63)

# Standard JPEG Annex K base quantisation tables (verified byte-identical to the ones in
# Eng3d.dll at 0x41aa30 / 0x41aa70).
QUANT_LUMA = (
    16, 11, 10, 16, 24, 40, 51, 61,  12, 12, 14, 19, 26, 58, 60, 55,
    14, 13, 16, 24, 40, 57, 69, 56,  14, 17, 22, 29, 51, 87, 80, 62,
    18, 22, 37, 56, 68,109,103, 77,  24, 35, 55, 64, 81,104,113, 92,
    49, 64, 78, 87,103,121,120,101,  72, 92, 95, 98,112,100,103, 99)
QUANT_CHROMA = (
    17, 18, 24, 47, 99, 99, 99, 99,  18, 21, 26, 66, 99, 99, 99, 99,
    24, 26, 56, 99, 99, 99, 99, 99,  47, 66, 99, 99, 99, 99, 99, 99,
    99, 99, 99, 99, 99, 99, 99, 99,  99, 99, 99, 99, 99, 99, 99, 99,
    99, 99, 99, 99, 99, 99, 99, 99,  99, 99, 99, 99, 99, 99, 99, 99)

# IJG AAN prescale factors. NOTE: the last entry is 124 in the game's table where IJG has
# 1247 — a dropped digit in Blue Byte's copy. It must be reproduced verbatim, otherwise the
# highest-frequency coefficient decodes ~10x too small.
AAN_SCALE = (
    16384, 22725, 21407, 19266, 16384, 12873,  8867,  4520,
    22725, 31521, 29692, 26722, 22725, 17855, 12299,  6270,
    21407, 29692, 27969, 25172, 21407, 16819, 11585,  5906,
    19266, 26722, 25172, 22654, 19266, 15137, 10426,  5315,
    16384, 22725, 21407, 19266, 16384, 12873,  8867,  4520,
    12873, 17855, 16819, 15137, 12873, 10114,  6967,  3552,
     8867, 12299, 11585, 10426,  8867,  6967,  4799,  2446,
     4520,  6270,  5906,  5315,  4520,  3552,  2446,   124)

# Code lengths of the fixed 17-symbol meta-alphabet used to transmit the code-length
# tables (Eng3d.dll 0x41a998).
META_LENGTHS = (2, 2, 3, 4, 8, 8, 9, 9, 8, 8, 8, 8, 8, 5, 4, 3, 4)

N_SYMBOLS_META = 17
LUT_BITS = 8

MODE_420 = 0   # 16x16 macroblocks, 6 blocks: Cb Cr Y0 Y1 Y2 Y3
MODE_444 = 2   #  8x8  macroblocks, 3 blocks: Cb Cr Y   <- what the game's textures use


class VisnError(Exception):
    pass


# --------------------------------------------------------------------------- bit reader
class BitReader:
    """MSB-first over a stream of 16-bit little-endian words, exactly as the decoder does."""

    __slots__ = ("d", "p", "buf", "n")

    def __init__(self, data, pos):
        v = int.from_bytes(data[pos:pos + 4], "little")
        self.buf = ((v << 16) | (v >> 16)) & 0xFFFFFFFF
        self.n = 32
        self.d = data
        self.p = pos + 4

    def _fill(self, k):
        while self.n < k:
            p = self.p
            w = self.d[p] | (self.d[p + 1] << 8) if p + 1 < len(self.d) else 0
            self.p = p + 2
            self.buf |= ((w << 16) & 0xFFFFFFFF) >> self.n
            self.n += 16

    def read(self, k):
        if self.n < k:
            self._fill(k)
        v = self.buf >> (32 - k)
        self.buf = (self.buf << k) & 0xFFFFFFFF
        self.n -= k
        return v

    def read_signed(self, k):
        v = self.read(k)
        return v - (1 << k) if v >> (k - 1) else v

    def peek8(self):
        if self.n < 8:
            self._fill(8)
        return self.buf >> 24

    def skip(self, k):
        if self.n < k:
            self._fill(k)
        self.buf = (self.buf << k) & 0xFFFFFFFF
        self.n -= k

    def read_bit(self):
        if self.n < 1:
            self._fill(1)
        v = self.buf >> 31
        self.buf = (self.buf << 1) & 0xFFFFFFFF
        self.n -= 1
        return v


# --------------------------------------------------------------------------- huffman
class Huffman:
    """Canonical Huffman, decoded through an 8-bit LUT with a bit-tree for longer codes.

    Mirrors the table builder at Eng3d.dll 0x412df7: codes of <= 8 bits are expanded into
    a 256-entry LUT; longer codes store a node id in the LUT and then walk two child
    arrays one bit at a time.
    """

    __slots__ = ("lut", "lengths", "tree0", "tree1", "nsym")

    def __init__(self, lengths):
        self.lengths = lengths
        self.nsym = nsym = len(lengths)
        self.lut = [0] * 256
        self.tree0 = []
        self.tree1 = []

        count = [0] * 17
        for L in lengths:
            if L > 15:
                raise VisnError("code length %d > 15" % L)
            if L:
                count[L] += 1

        nextcode = [0] * 17
        code = 0
        for L in range(1, 16):
            code = (code + count[L - 1]) << 1
            nextcode[L] = code

        next_node = nsym
        nodes = {}          # node id -> [child0, child1]

        for sym, L in enumerate(lengths):
            if L == 0:
                continue
            code = nextcode[L]
            nextcode[L] += 1
            if L <= LUT_BITS:
                top = code << (LUT_BITS - L)
                for k in range(1 << (LUT_BITS - L)):
                    self.lut[top + k] = sym
            else:
                rest = L - LUT_BITS
                idx = code >> rest                      # first 8 bits index the LUT
                node = self.lut[idx]
                if node < nsym:
                    node = next_node
                    next_node += 1
                    nodes[node] = [0, 0]
                    self.lut[idx] = node
                for i in range(rest):
                    bit = (code >> (rest - 1 - i)) & 1
                    child = nodes[node][bit]
                    if i == rest - 1:
                        nodes[node][bit] = sym
                    else:
                        if child < nsym:
                            child = next_node
                            next_node += 1
                            nodes[child] = [0, 0]
                            nodes[node][bit] = child
                        node = child

        self.tree0 = [0] * next_node
        self.tree1 = [0] * next_node
        for node, (c0, c1) in nodes.items():
            self.tree0[node] = c0
            self.tree1[node] = c1

    def decode(self, br):
        sym = self.lut[br.peek8()]
        if sym < self.nsym:
            br.skip(self.lengths[sym])
            return sym
        br.skip(LUT_BITS)
        while sym >= self.nsym:
            sym = self.tree1[sym] if br.read_bit() else self.tree0[sym]
        return sym


_META = Huffman(META_LENGTHS)


def read_length_table(br):
    """Read one code-length table (Eng3d.dll 0x412d16). Lengths are delta-coded mod 16;
    meta-symbol 0x10 introduces a 5-bit run of unused (length 0) symbols."""
    n = br.read(12)
    lengths = []
    running = 0
    while len(lengths) < n:
        sym = _META.decode(br)
        if sym == 0x10:
            k = br.read(5)
            lengths.extend([0] * k)
        else:
            running = (running + sym) & 0xF
            lengths.append(running)
    if len(lengths) != n:
        raise VisnError("length table overran: %d != %d" % (len(lengths), n))
    return lengths


# --------------------------------------------------------------------------- quant
def build_quant(quality, base):
    """IJG quality scaling, then fold in the AAN prescale. Returns 64 multipliers in
    SCAN order (Eng3d.dll 0x412fb7)."""
    q = max(1, quality)
    scale = (100 - q) * 2 if q > 50 else 5000 // q
    out = [0] * 64
    for scan_pos, raster in enumerate(NATURAL_ORDER):
        v = (base[raster] * scale + 50) // 100
        v = 1 if v < 1 else (255 if v > 255 else v)
        out[scan_pos] = v * AAN_SCALE[raster]
    return out


# --------------------------------------------------------------------------- block
def decode_block(br, huff, qtab, block):
    """One 8x8 block into `block` (64 ints, raster order).

    6 bits nAC | 12 bits (DC + 0x800) | nAC coefficient symbols in zigzag order.
    Symbols 0x00..0x74 carry the value directly (sym - 0x3A); 0x75..0x80 are escapes with
    (sym - 0x74) extra signed bits. Zeros are explicit; there is no run-length or EOB.
    """
    for i in range(64):
        block[i] = 0
    nac = br.read(6)
    block[0] = br.read(12) - 0x800          # DC: raw, unquantised, not predicted
    for k in range(1, nac + 1):
        sym = huff.decode(br)
        if sym <= 0x74:
            v = sym - 0x3A
        else:
            v = br.read_signed(sym - 0x74)
        if v:
            block[NATURAL_ORDER[k]] = (v * qtab[k]) >> 14


# --------------------------------------------------------------------------- idct
def idct(b):
    """AAN fast IDCT, integer, in place on a 64-element list (Eng3d.dll 0x41301f).

    Constants are the IJG ifast ones in 8-bit fixed point: 362=sqrt2, 473=1.8477,
    277=1.0824, -669=-2.6131. Pass 1 (columns) does not descale; pass 2 (rows) shifts
    right by 3. There is no level shift and no clamping here — the +128 rides in the DC
    coefficient, and clamping happens in the colour tables.
    """
    for c in range(8):
        if not (b[c + 8] or b[c + 16] or b[c + 24] or b[c + 32]
                or b[c + 40] or b[c + 48] or b[c + 56]):
            dc = b[c]
            for r in range(8, 64, 8):
                b[c + r] = dc
            continue
        t0 = b[c] + b[c + 32]
        t1 = b[c] - b[c + 32]
        t2 = b[c + 16] + b[c + 48]
        t3 = (((b[c + 16] - b[c + 48]) * 362) >> 8) - t2
        tmp10 = t0 + t2
        tmp13 = t0 - t2
        tmp11 = t1 + t3
        tmp12 = t1 - t3

        z13 = b[c + 40] + b[c + 24]
        z10 = b[c + 40] - b[c + 24]
        z11 = b[c + 8] + b[c + 56]
        z12 = b[c + 8] - b[c + 56]
        tmp7 = z11 + z13
        tmp11o = ((z11 - z13) * 362) >> 8
        z5 = ((z10 + z12) * 473) >> 8
        tmp10o = ((z12 * 277) >> 8) - z5
        tmp12o = ((z10 * -669) >> 8) + z5
        tmp6 = tmp12o - tmp7
        tmp5 = tmp11o - tmp6
        tmp4 = tmp10o + tmp5

        b[c] = tmp10 + tmp7
        b[c + 56] = tmp10 - tmp7
        b[c + 8] = tmp11 + tmp6
        b[c + 48] = tmp11 - tmp6
        b[c + 16] = tmp12 + tmp5
        b[c + 40] = tmp12 - tmp5
        b[c + 32] = tmp13 + tmp4
        b[c + 24] = tmp13 - tmp4

    for r in range(0, 64, 8):
        t0 = b[r] + b[r + 4]
        t1 = b[r] - b[r + 4]
        t2 = b[r + 2] + b[r + 6]
        t3 = (((b[r + 2] - b[r + 6]) * 362) >> 8) - t2
        tmp10 = t0 + t2
        tmp13 = t0 - t2
        tmp11 = t1 + t3
        tmp12 = t1 - t3

        z13 = b[r + 5] + b[r + 3]
        z10 = b[r + 5] - b[r + 3]
        z11 = b[r + 1] + b[r + 7]
        z12 = b[r + 1] - b[r + 7]
        tmp7 = z11 + z13
        tmp11o = ((z11 - z13) * 362) >> 8
        z5 = ((z10 + z12) * 473) >> 8
        tmp10o = ((z12 * 277) >> 8) - z5
        tmp12o = ((z10 * -669) >> 8) + z5
        tmp6 = tmp12o - tmp7
        tmp5 = tmp11o - tmp6
        tmp4 = tmp10o + tmp5

        b[r] = (tmp10 + tmp7) >> 3
        b[r + 7] = (tmp10 - tmp7) >> 3
        b[r + 1] = (tmp11 + tmp6) >> 3
        b[r + 6] = (tmp11 - tmp6) >> 3
        b[r + 2] = (tmp12 + tmp5) >> 3
        b[r + 5] = (tmp12 - tmp5) >> 3
        b[r + 4] = (tmp13 + tmp4) >> 3
        b[r + 3] = (tmp13 - tmp4) >> 3


# --------------------------------------------------------------------------- colour
def _fix(x):
    return int(x * 65536 + 0.5)


def _fixt(x):
    """The B coefficient is truncated rather than rounded in the shipped tables — with the
    rounded 116130 the delta at Cb=253 comes out 222 instead of the correct 221."""
    return int(x * 65536)


def _build_colour():
    """Rebuild what _E3D_init_vision(0x565) builds.

    Per pixel the decoder computes three independent channel lookups:
        R = Rtab[ clamp(Y,0,256) + dR (Cr) ]
        G = Gtab[ clamp(Y,0,256) + dGcb(Cb) + dGcr(Cr) ]
        B = Btab[ clamp(Y,0,256) + dB (Cb) ]
        pixel = R | G | B          (each table already holds its shifted RGB565 field)
    The chroma deltas are IJG's integer YCbCr coefficients, and the chroma index is clamped
    to 0..256 — the tables carry a 257th step, so a saturated chroma plane reaches one step
    further than 255 would. The channel tables are full-range scaled ((v*31)//255,
    (v*63)//255) — not bit shifts — zero below 0, saturated from 255 through 383, and zero
    above that (verified entry-by-entry against the tables the DLL builds).
    """
    dR = [(_fix(1.40200) * (i - 128) + 32768) >> 16 for i in range(257)]
    dB = [(_fixt(1.77200) * (i - 128) + 32768) >> 16 for i in range(257)]
    dGcb = [(-_fix(0.34414) * (i - 128) + 32768) >> 16 for i in range(257)]
    dGcr = [(-_fix(0.71414) * (i - 128) + 32768) >> 16 for i in range(257)]

    # reachable index: clamp(y,0,256) + delta  ->  -227 .. +435
    lo, hi = -256, 513
    def table(bits, shift):
        maxv = (1 << bits) - 1
        out = []
        for i in range(lo, hi):
            if i < 0 or i > 383:
                out.append(0)
            elif i > 255:
                out.append(maxv << shift)
            else:
                out.append(((i * maxv) // 255) << shift)
        return out

    return dR, dGcb, dGcr, dB, table(5, 11), table(6, 5), table(5, 0), -lo


_dR, _dGcb, _dGcr, _dB, _RTAB, _GTAB, _BTAB, _BIAS = _build_colour()


# --------------------------------------------------------------------------- picture
def parse_header(rec):
    if rec[:4] != b"VISN":
        raise VisnError("not a VISN record (magic=%r)" % rec[:4])
    w, h = struct.unpack_from("<HH", rec, 4)
    return w, h, rec[8], rec[9]


def decode(rec, stride=None):
    """Decode one VISN record. Returns (width, height, rgb565_bytes little-endian)."""
    w, h, quality, mode = parse_header(rec)
    if mode not in (MODE_420, MODE_444):
        raise VisnError("unsupported mode %d" % mode)
    stride = w if stride is None else stride

    qc = build_quant(quality, QUANT_CHROMA)
    ql = build_quant(quality, QUANT_LUMA)

    br = BitReader(rec, 10)
    huff_chroma = Huffman(read_length_table(br))
    huff_luma = Huffman(read_length_table(br))

    mbx, mby = w >> 4, h >> 4
    if mode == MODE_444:
        mbx, mby, mbsize, nluma = mbx * 2, mby * 2, 8, 1
    else:
        mbsize, nluma = 16, 4

    out = bytearray(stride * h * 2)
    cb = [0] * 64
    cr = [0] * 64
    ys = [[0] * 64 for _ in range(nluma)]

    for my in range(mby):
        for mx in range(mbx):
            decode_block(br, huff_chroma, qc, cb)
            decode_block(br, huff_chroma, qc, cr)
            for i in range(nluma):
                decode_block(br, huff_luma, ql, ys[i])
            idct(cb)
            idct(cr)
            for i in range(nluma):
                idct(ys[i])
            _emit(out, stride, mx * mbsize, my * mbsize, cb, cr, ys, mode)

    return w, h, bytes(out)


def _emit(out, stride, px, py, cb, cr, ys, mode):
    """Colour-convert one macroblock and write RGB565 into the destination."""
    rtab, gtab, btab, bias = _RTAB, _GTAB, _BTAB, _BIAS
    dR, dGcb, dGcr, dB = _dR, _dGcb, _dGcr, _dB
    for sub in range(len(ys)):
        # 4:2:0 arranges the four luma blocks as a 2x2 grid inside the macroblock
        ox = px + (sub & 1) * 8 if mode == MODE_420 else px
        oy = py + (sub >> 1) * 8 if mode == MODE_420 else py
        y = ys[sub]
        for row in range(8):
            base = ((oy + row) * stride + ox) * 2
            for col in range(8):
                if mode == MODE_420:
                    ci = ((row >> 1) + (sub >> 1) * 4) * 8 + (col >> 1) + (sub & 1) * 4
                else:
                    ci = row * 8 + col
                yv = y[row * 8 + col]
                yv = 0 if yv < 0 else (256 if yv > 256 else yv)
                c_b = cb[ci]
                c_b = 0 if c_b < 0 else (256 if c_b > 256 else c_b)
                c_r = cr[ci]
                c_r = 0 if c_r < 0 else (256 if c_r > 256 else c_r)
                pix = (rtab[yv + dR[c_r] + bias]
                       | gtab[yv + dGcb[c_b] + dGcr[c_r] + bias]
                       | btab[yv + dB[c_b] + bias])
                o = base + col * 2
                out[o] = pix & 0xFF
                out[o + 1] = pix >> 8


# --------------------------------------------------------------------------- encoder
#
# Why the maths is simple: the decoder reconstructs a coefficient as
#     coef = (sym * quant[k] * aan[k]) >> 14
# and the AAN inverse transform expects its input prescaled as  X = F * aan/16384,
# where F is the plain DCT-II with the usual (1/4)c(u)c(v) normalisation. The aan factor
# cancels, leaving  sym = F / quant  — textbook JPEG quantisation. The DC is transmitted
# raw and unquantised, and since a flat block of value P decodes to DC>>3, the DC is
# simply 8*mean — which is also where the +128 level shift lives (we never subtract it).

import math

_C = [[0.0] * 8 for _ in range(8)]
for _u in range(8):
    _cu = (0.5 / math.sqrt(2.0)) if _u == 0 else 0.5
    for _x in range(8):
        _C[_u][_x] = _cu * math.cos((2 * _x + 1) * _u * math.pi / 16.0)


class BitWriter:
    """MSB-first into 16-bit little-endian words — the exact inverse of BitReader."""

    __slots__ = ("out", "acc", "n")

    def __init__(self):
        self.out = bytearray()
        self.acc = 0
        self.n = 0

    def write(self, v, k):
        self.acc = (self.acc << k) | (v & ((1 << k) - 1))
        self.n += k
        while self.n >= 16:
            self.n -= 16
            w = (self.acc >> self.n) & 0xFFFF
            self.out.append(w & 0xFF)
            self.out.append(w >> 8)
        self.acc &= (1 << self.n) - 1

    def finish(self, pad_words=4):
        if self.n:
            w = (self.acc << (16 - self.n)) & 0xFFFF
            self.out.append(w & 0xFF)
            self.out.append(w >> 8)
            self.acc = self.n = 0
        self.out += b"\0" * (2 * pad_words)      # the decoder pre-reads up to 32 bits
        return bytes(self.out)


def canonical_codes(lengths):
    """Same canonical assignment the decoder's table builder uses."""
    count = [0] * 17
    for L in lengths:
        if L:
            count[L] += 1
    nextcode = [0] * 17
    code = 0
    for L in range(1, 16):
        code = (code + count[L - 1]) << 1
        nextcode[L] = code
    codes = [0] * len(lengths)
    for s, L in enumerate(lengths):
        if L:
            codes[s] = nextcode[L]
            nextcode[L] += 1
    return codes


def huffman_lengths(hist, maxlen=15):
    """Code lengths from a symbol histogram, limited to `maxlen` bits by halving counts
    until the tree is shallow enough. Unused symbols get length 0."""
    import heapq
    n = len(hist)
    used = [s for s in range(n) if hist[s]]
    if not used:
        out = [0] * n
        out[0] = 1
        return out
    if len(used) == 1:
        out = [0] * n
        out[used[0]] = 1
        return out
    counts = list(hist)
    while True:
        heap = [(counts[s], 1, [s]) for s in used]
        heapq.heapify(heap)
        depth = dict.fromkeys(used, 0)
        while len(heap) > 1:
            c0, _, g0 = heapq.heappop(heap)
            c1, _, g1 = heapq.heappop(heap)
            for s in g0:
                depth[s] += 1
            for s in g1:
                depth[s] += 1
            heapq.heappush(heap, (c0 + c1, len(g0) + len(g1), g0 + g1))
        if max(depth.values()) <= maxlen:
            out = [0] * n
            for s, d in depth.items():
                out[s] = d
            return out
        counts = [((c + 1) >> 1) if c else 0 for c in counts]


def write_length_table(bw, lengths):
    """Inverse of read_length_table: 12-bit symbol count, then lengths delta-coded mod 16
    under the fixed meta-code. The zero-run escape is never needed — a length of 0 is just
    another delta."""
    meta = canonical_codes(META_LENGTHS)
    bw.write(len(lengths), 12)
    running = 0
    for L in lengths:
        d = (L - running) & 0xF
        bw.write(meta[d], META_LENGTHS[d])
        running = L


def build_quant_plain(quality, base):
    """The bare IJG-scaled quantisation values (1..255) in SCAN order — i.e. build_quant()
    without the AAN prescale folded in. This is what the encoder divides by."""
    q = max(1, quality)
    scale = (100 - q) * 2 if q > 50 else 5000 // q
    out = [0] * 64
    for scan_pos, raster in enumerate(NATURAL_ORDER):
        v = (base[raster] * scale + 50) // 100
        out[scan_pos] = 1 if v < 1 else (255 if v > 255 else v)
    return out


def _iround(x):
    return int(x + 0.5) if x >= 0 else -int(0.5 - x)


def _fdct(f, out):
    """Plain separable DCT-II, (1/4)c(u)c(v) normalised, raster order in and out."""
    tmp = [0.0] * 64
    for u in range(8):
        cu = _C[u]
        for x in range(8):
            s = 0.0
            for y in range(8):
                s += cu[y] * f[y * 8 + x]
            tmp[u * 8 + x] = s
    for u in range(8):
        row = u * 8
        for v in range(8):
            cv = _C[v]
            s = 0.0
            for x in range(8):
                s += cv[x] * tmp[row + x]
            out[row + v] = s


def _symbols_for_block(f, quant, dc_only, block_out):
    """One 8x8 plane block -> (dc, [symbol values in scan order 1..nAC]).

    Returns raw coefficient *values*; mapping them onto the 129-symbol alphabet happens at
    write time so the histogram can be gathered first.
    """
    F = block_out
    _fdct(f, F)
    dc = _iround(F[0])
    if dc < -2048:
        dc = -2048
    elif dc > 2047:
        dc = 2047
    if dc_only:
        return dc, []
    vals = []
    last = 0
    for k in range(1, 64):
        v = _iround(F[NATURAL_ORDER[k]] / quant[k])
        if v < -2048:
            v = -2048
        elif v > 2047:
            v = 2047
        vals.append(v)
        if v:
            last = k
    return dc, vals[:last]


def _sym_of(v):
    """Map a coefficient value onto the alphabet: direct symbol, or an escape plus a
    signed literal. Returns (symbol, extra_bits_count, extra_value)."""
    if -58 <= v <= 58:
        return v + 0x3A, 0, 0
    n = 1
    while not (-(1 << (n - 1)) <= v < (1 << (n - 1))):
        n += 1
    return 0x74 + n, n, v


def encode(rgb, w, h, quality=93, dc_only=False):
    """Encode 8-bit RGB (bytes, w*h*3) into a VISN record. Mode 2 (4:4:4, 8x8 macroblocks).

    `dc_only` emits one flat colour per 8x8 block — useful as a first-light test of the
    container, the tables and the block walk.
    """
    if w % 16 or h % 16:
        raise VisnError("dimensions must be multiples of 16 (got %dx%d)" % (w, h))

    # --- colour transform, standard JPEG YCbCr with the +128 chroma bias and NO level shift
    npx = w * h
    Y = [0] * npx
    CB = [0] * npx
    CR = [0] * npx
    for i in range(npx):
        r = rgb[3 * i]
        g = rgb[3 * i + 1]
        b = rgb[3 * i + 2]
        y = 0.299 * r + 0.587 * g + 0.114 * b
        cb = 128.0 - 0.168736 * r - 0.331264 * g + 0.5 * b
        cr = 128.0 + 0.5 * r - 0.418688 * g - 0.081312 * b
        Y[i] = 0 if y < 0 else (255 if y > 255 else _iround(y))
        CB[i] = 0 if cb < 0 else (255 if cb > 255 else _iround(cb))
        CR[i] = 0 if cr < 0 else (255 if cr > 255 else _iround(cr))

    ql = build_quant_plain(quality, QUANT_LUMA)
    qc = build_quant_plain(quality, QUANT_CHROMA)

    # --- pass 1: transform everything, gather the two symbol histograms
    blocks = []
    hist_c = [0] * 129
    hist_l = [0] * 129
    tile = [0] * 64
    F = [0.0] * 64
    for my in range(h // 8):
        for mx in range(w // 8):
            base = my * 8 * w + mx * 8
            for plane, quant, hist in ((CB, qc, hist_c), (CR, qc, hist_c), (Y, ql, hist_l)):
                for row in range(8):
                    src = base + row * w
                    tile[row * 8:row * 8 + 8] = plane[src:src + 8]
                dc, vals = _symbols_for_block(tile, quant, dc_only, F)
                for v in vals:
                    hist[_sym_of(v)[0]] += 1
                blocks.append((dc, vals))

    # a symbol we never emit still needs a code if the table is to round-trip cleanly;
    # nothing forces that, so leave unused symbols at length 0 (the decoder skips them).
    len_c = huffman_lengths(hist_c)
    len_l = huffman_lengths(hist_l)
    code_c = canonical_codes(len_c)
    code_l = canonical_codes(len_l)

    # --- pass 2: emit
    bw = BitWriter()
    write_length_table(bw, len_c)          # chroma table first, then luma
    write_length_table(bw, len_l)
    for i, (dc, vals) in enumerate(blocks):
        codes, lens = (code_l, len_l) if i % 3 == 2 else (code_c, len_c)
        bw.write(len(vals), 6)
        bw.write((dc + 0x800) & 0xFFF, 12)
        for v in vals:
            sym, nbits, extra = _sym_of(v)
            bw.write(codes[sym], lens[sym])
            if nbits:
                bw.write(extra & ((1 << nbits) - 1), nbits)

    return b"VISN" + struct.pack("<HH", w, h) + bytes((quality, MODE_444)) + bw.finish()


def encode_image(img, quality=93, dc_only=False):
    """Encode a PIL Image."""
    img = img.convert("RGB")
    return encode(img.tobytes(), img.width, img.height, quality, dc_only)


def psnr(a, b):
    """Peak signal-to-noise ratio between two equal-length 8-bit buffers, in dB."""
    n = len(a)
    se = 0
    for i in range(n):
        d = a[i] - b[i]
        se += d * d
    if se == 0:
        return float("inf")
    return 10.0 * math.log10(255.0 * 255.0 * n / se)


# --------------------------------------------------------------------------- helpers
def rgb565_to_rgb(buf):
    out = bytearray(len(buf) // 2 * 3)
    for i in range(len(buf) // 2):
        v = buf[2 * i] | (buf[2 * i + 1] << 8)
        r = (v >> 11) & 0x1F
        g = (v >> 5) & 0x3F
        b = v & 0x1F
        out[3 * i] = (r << 3) | (r >> 2)
        out[3 * i + 1] = (g << 2) | (g >> 4)
        out[3 * i + 2] = (b << 3) | (b >> 2)
    return bytes(out)


def decode_to_image(rec):
    from PIL import Image
    w, h, raw = decode(rec)
    return Image.frombytes("RGB", (w, h), rgb565_to_rgb(raw))


def split_lib(path):
    """Yield (name, record_bytes) for every VISN record in a .lib, using its .dir/.din TOC
    when present and falling back to scanning for the magic."""
    data = open(path, "rb").read()
    stem = os.path.splitext(path)[0]
    for ext in (".dir", ".DIR"):
        if os.path.exists(stem + ext):
            text = open(stem + ext, "rb").read().decode("latin-1")
            for line in text.splitlines():
                parts = line.split("\t")
                if len(parts) < 2:
                    continue
                rest = parts[-1].split()
                if len(rest) == 5 and all(p.lstrip("-").isdigit() for p in rest):
                    _, _, off, size, _ = map(int, rest)
                    yield parts[0].strip(), data[off:off + size]
            return
    pos, idx = data.find(b"VISN"), 0
    while pos >= 0:
        nxt = data.find(b"VISN", pos + 4)
        yield "rec%04d" % idx, data[pos:nxt if nxt > 0 else len(data)]
        pos, idx = nxt, idx + 1


# --------------------------------------------------------------------------- cli
def _cmd_info(args):
    for name, rec in split_lib(args.path):
        try:
            w, h, q, m = parse_header(rec)
            print("%-14s %4dx%-4d quality=%-3d mode=%d  %7d bytes (%.1f%% of raw)"
                  % (name, w, h, q, m, len(rec), 100.0 * len(rec) / (w * h * 2)))
        except VisnError as e:
            print("%-14s !! %s" % (name, e))


def _cmd_decode(args):
    os.makedirs(args.out, exist_ok=True)
    n = 0
    for name, rec in split_lib(args.path):
        try:
            decode_to_image(rec).save(os.path.join(args.out, name + ".png"))
            n += 1
        except Exception as e:
            print("  ! %s: %s" % (name, e))
    print("decoded %d record(s) -> %s" % (n, args.out))


def _cmd_verify(args):
    """Bit-exactness check against the game's own decoder. 32-bit Python only."""
    import ctypes
    game = os.environ.get("INCU_GAME_DIR", os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    if struct.calcsize("P") != 4:
        sys.exit("verify needs 32-bit Python (Eng3d.dll is PE32)")
    os.add_dll_directory(game)
    cwd = os.getcwd()
    os.chdir(game)
    dll = ctypes.CDLL(os.path.join(game, "Eng3d.dll"))
    dll._E3D_init_vision.argtypes = [ctypes.c_int]
    dll._E3D_init_vision(0x565)
    dll._E3D_decode_picture.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
    dll._E3D_decode_picture.restype = None
    os.chdir(cwd)

    total = same = 0
    for name, rec in split_lib(args.path):
        try:
            w, h, ours = decode(rec)
        except Exception as e:
            print("  ! %-12s ours failed: %s" % (name, e))
            total += 1
            continue
        src = (ctypes.c_char * len(rec)).from_buffer_copy(rec)
        dst = (ctypes.c_char * (w * h * 2))()
        dll._E3D_decode_picture(src, dst, w)
        theirs = bytes(dst)
        total += 1
        if ours == theirs:
            same += 1
        else:
            diff = sum(1 for a, b in zip(ours, theirs) if a != b)
            first = next(i for i in range(len(ours)) if ours[i] != theirs[i])
            print("  ! %-12s %d/%d bytes differ, first at %d (px %d,%d): ours=%02x theirs=%02x"
                  % (name, diff, len(ours), first, (first // 2) % w, (first // 2) // w,
                     ours[first], theirs[first]))
    print("%d/%d records bit-identical to the game's decoder" % (same, total))
    return 0 if same == total else 1


def _cmd_encode(args):
    from PIL import Image
    rec = encode_image(Image.open(args.image), quality=args.quality)
    open(args.out, "wb").write(rec)
    print("%s -> %s (%d bytes)" % (args.image, args.out, len(rec)))


def _load_toc(lib_path):
    stem = os.path.splitext(lib_path)[0]
    for ext in (".dir", ".DIR"):
        if os.path.exists(stem + ext):
            entries = []
            for line in open(stem + ext, "rb").read().decode("latin-1").splitlines():
                parts = line.split("\t")
                if len(parts) < 2:
                    continue
                rest = parts[-1].split()
                if len(rest) == 5 and all(p.lstrip("-").isdigit() for p in rest):
                    typ, idx, off, size, mtime = map(int, rest)
                    entries.append([parts[0].strip(), typ, idx, off, size, mtime])
            return entries
    raise VisnError("no .dir TOC next to " + lib_path)


def _cmd_repack(args):
    """Rebuild a texture.lib, re-encoding any record for which <dir>/<name>.png exists and
    copying the original bytes for the rest."""
    from PIL import Image
    entries = _load_toc(args.lib)
    data = open(args.lib, "rb").read()
    out = open(args.out, "wb")
    off = 0
    new = []
    changed = 0
    for name, typ, idx, o, size, mtime in entries:
        png = os.path.join(args.pngs, name + ".png")
        if os.path.exists(png):
            rec = encode_image(Image.open(png), quality=args.quality)
            changed += 1
            print("  re-encoded %-14s %6d -> %6d bytes" % (name, size, len(rec)))
        else:
            rec = data[o:o + size]
        out.write(rec)
        new.append([name, typ, idx, off, len(rec), mtime])
        off += len(rec)
    out.close()

    stem = os.path.splitext(args.out)[0]
    with open(stem + ".dir", "w", newline="") as f:
        f.write("3DI\r\n[DIRECTORY]\r\n")
        for name, typ, idx, o, size, mtime in new:
            f.write("%s\t\t%d %d %d %d %d\r\n" % (name, typ, idx, o, size, mtime))
        f.write("ENDDIR\r\n[END3DI]\r\n")
    with open(stem + ".din", "wb") as f:
        f.write(b"DBIN" + struct.pack("<I", len(new)))
        for name, typ, idx, o, size, mtime in new:
            f.write(struct.pack("<I", idx) + name.encode("latin-1")[:13].ljust(13, b"\0")
                    + struct.pack("<II", o, size))
    print("repacked %d records (%d re-encoded) -> %s (%d bytes) + .dir/.din"
          % (len(new), changed, args.out, off))


def main():
    import argparse
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    pi = sub.add_parser("info"); pi.add_argument("path"); pi.set_defaults(f=_cmd_info)
    pd = sub.add_parser("decode"); pd.add_argument("path")
    pd.add_argument("-o", "--out", default="out"); pd.set_defaults(f=_cmd_decode)
    pv = sub.add_parser("verify"); pv.add_argument("path"); pv.set_defaults(f=_cmd_verify)
    pe = sub.add_parser("encode"); pe.add_argument("image")
    pe.add_argument("-o", "--out", default="out.visn")
    pe.add_argument("-q", "--quality", type=int, default=93); pe.set_defaults(f=_cmd_encode)
    pr = sub.add_parser("repack"); pr.add_argument("lib"); pr.add_argument("pngs")
    pr.add_argument("-o", "--out", required=True)
    pr.add_argument("-q", "--quality", type=int, default=93); pr.set_defaults(f=_cmd_repack)
    args = p.parse_args()
    sys.exit(args.f(args) or 0)


if __name__ == "__main__":
    main()
