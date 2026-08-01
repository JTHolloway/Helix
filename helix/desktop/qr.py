"""A QR code, written by hand, for one job: getting a URL onto a phone.

WHY THIS EXISTS AT ALL. Helix folds down to 380 pixels and a phone can only
reach it once the server is listening on the network — and then somebody has
to type `http://192.168.1.47:8731/` into a browser on a device whose keyboard
covers half the screen. A square to point the camera at is the difference
between a feature that works and one that is technically available.

WHY IT IS NOT A DEPENDENCY. The program writes its own SVG, PDF, DXF and EPS
so that it runs on a machine with nothing installed, and adding a library to
draw twenty-one rows of black squares would be the first crack in that. What
is here is deliberately the SMALLEST USEFUL QR CODE and nothing more:

    version 2, 25x25 modules, error correction L, byte mode

which holds 32 bytes — enough for `http://192.168.100.100:65535/` with room
to spare, and not enough for anything else. There is no version negotiation,
no Kanji mode, no structured append. A URL longer than 32 bytes returns "" and
the interface shows the address as text instead, which is the honest failure.

The arithmetic is Reed-Solomon over GF(256) and the mask is fixed at pattern
0, chosen because it is the cheapest to compute and every reader handles it.
"""
from __future__ import annotations

# ── GF(256) with the QR generator polynomial x^8 + x^4 + x^3 + x^2 + 1 ──
_EXP = [0] * 512
_LOG = [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def _mul(a: int, b: int) -> int:
    return 0 if a == 0 or b == 0 else _EXP[_LOG[a] + _LOG[b]]


def _rs(data: bytes, n: int) -> bytes:
    """`n` error-correction codewords for `data`."""
    gen = [1]
    for i in range(n):
        gen = [gen[j] ^ _mul(gen[j + 1] if j + 1 < len(gen) else 0, _EXP[i])
               for j in range(len(gen))] + [_mul(gen[-1], _EXP[i])]
    rem = list(data) + [0] * n
    for i in range(len(data)):
        f = rem[i]
        if f:
            for j in range(1, len(gen)):
                rem[i + j] ^= _mul(gen[j], f)
    return bytes(rem[len(data):])


# Version 2-L: 25x25, 44 data codewords total, 34 data + 10 EC.
SIZE = 25
DATA_CW = 34
EC_CW = 10
CAP_BYTES = 32          # 34 codewords, less the mode nibble and length byte

# The two alignment-pattern centres for version 2, and the format bits for
# EC level L with mask 0 — both fixed, because the version and mask are.
_ALIGN = (18, 18)
_FORMAT = 0b111011111000100


def _blank():
    return [[None] * SIZE for _ in range(SIZE)]


def _finder(m, r0: int, c0: int) -> None:
    for dr in range(-1, 8):
        for dc in range(-1, 8):
            r, c = r0 + dr, c0 + dc
            if not (0 <= r < SIZE and 0 <= c < SIZE):
                continue
            edge = dr in (0, 6) or dc in (0, 6)
            core = 2 <= dr <= 4 and 2 <= dc <= 4
            m[r][c] = 1 if (edge or core) else 0


def _skeleton():
    """Everything a reader looks for before it looks at the data."""
    m = _blank()
    _finder(m, 0, 0)
    _finder(m, 0, SIZE - 7)
    _finder(m, SIZE - 7, 0)
    for i in range(8, SIZE - 8):            # the two timing lines
        m[6][i] = m[i][6] = 1 - (i % 2)
    ar, ac = _ALIGN                          # the one alignment square
    for dr in range(-2, 3):
        for dc in range(-2, 3):
            m[ar + dr][ac + dc] = 1 if max(abs(dr), abs(dc)) != 1 else 0
    m[SIZE - 8][8] = 1                       # the always-dark module
    for i in range(15):                      # format information, twice
        bit = (_FORMAT >> i) & 1
        if i < 6:
            m[8][i] = bit
        elif i == 6:
            m[8][7] = bit
        elif i == 7:
            m[8][8] = bit
        elif i == 8:
            m[7][8] = bit
        else:
            m[14 - i][8] = bit
        if i < 8:
            m[SIZE - 1 - i][8] = bit
        else:
            m[8][SIZE - 15 + i] = bit
    return m


def matrix(text: str):
    """The modules as a list of rows of 0/1, or None if it will not fit."""
    raw = text.encode("utf-8")
    if len(raw) > CAP_BYTES:
        return None

    # Byte mode (0100), an 8-bit length, the bytes, a terminator, then the
    # pad bytes QR specifies — 0xEC and 0x11 alternating, forever.
    bits = "0100" + f"{len(raw):08b}" + "".join(f"{b:08b}" for b in raw)
    bits += "0" * min(4, DATA_CW * 8 - len(bits))
    bits += "0" * (-len(bits) % 8)
    data = bytearray(int(bits[i:i + 8], 2) for i in range(0, len(bits), 8))
    for i in range(DATA_CW - len(data)):
        data.append(0xEC if i % 2 == 0 else 0x11)
    code = bytes(data) + _rs(bytes(data), EC_CW)

    m = _skeleton()
    stream = "".join(f"{b:08b}" for b in code)
    # Up the right-hand column pair, then down the next, skipping column 6
    # (the vertical timing line) and every module already spoken for.
    k, up, col = 0, True, SIZE - 1
    while col > 0:
        if col == 6:
            col -= 1
        rows = range(SIZE - 1, -1, -1) if up else range(SIZE)
        for r in rows:
            for c in (col, col - 1):
                if m[r][c] is not None:
                    continue
                bit = int(stream[k]) if k < len(stream) else 0
                k += 1
                # Mask 0: invert where (row + column) is even. Cheapest to
                # compute and universally supported.
                m[r][c] = bit ^ (1 if (r + c) % 2 == 0 else 0)
        up = not up
        col -= 2
    return [[v or 0 for v in row] for row in m]


def svg(text: str, *, quiet: int = 3, scale: int = 8) -> str:
    """A QR code as an SVG string, or "" if the text will not fit.

    Drawn as one path of small squares rather than one rect per module: a
    625-module code is 625 elements otherwise, and this is going into a
    dialogue that has to stay quick.
    """
    m = matrix(text)
    if m is None:
        return ""
    n = SIZE + quiet * 2
    d = []
    for r, row in enumerate(m):
        for c, v in enumerate(row):
            if v:
                d.append(f"M{c + quiet},{r + quiet}h1v1h-1z")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" '
            f'width="{n * scale}" height="{n * scale}" '
            f'shape-rendering="crispEdges" role="img" '
            f'aria-label="QR code for {text}">'
            f'<rect width="{n}" height="{n}" fill="#fff"/>'
            f'<path d="{"".join(d)}" fill="#26241F"/></svg>')
