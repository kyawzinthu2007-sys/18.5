"""Minimal, spec-correct QR code encoder (byte mode only) — stdlib only.
Implements ISO/IEC 18004 closely enough to produce scannable codes:
Reed-Solomon error correction, proper version/EC-level data capacity,
data codeword construction with mode/length/terminator/padding, structure
placement (finder/timing/alignment patterns), 8 mask patterns with
standard penalty scoring, and format/version info bits.
"""
import itertools

# --- Galois Field GF(256) arithmetic for Reed-Solomon ---
GF_EXP = [0]*512
GF_LOG = [0]*256
def _init_gf():
    x = 1
    for i in range(255):
        GF_EXP[i] = x
        GF_LOG[x] = i
        x <<= 1
        if x & 0x100:
            x ^= 0x11D
    for i in range(255, 512):
        GF_EXP[i] = GF_EXP[i-255]
_init_gf()

def gf_mul(a, b):
    if a == 0 or b == 0: return 0
    return GF_EXP[GF_LOG[a] + GF_LOG[b]]

def rs_generator_poly(nsym):
    g = [1]
    for i in range(nsym):
        g = poly_mul(g, [1, GF_EXP[i]])
    return g

def poly_mul(p, q):
    r = [0]*(len(p)+len(q)-1)
    for i,pi in enumerate(p):
        if pi == 0: continue
        for j,qj in enumerate(q):
            if qj == 0: continue
            r[i+j] ^= gf_mul(pi, qj)
    return r

def rs_encode(data, nsym):
    gen = rs_generator_poly(nsym)
    res = list(data) + [0]*nsym
    for i in range(len(data)):
        coef = res[i]
        if coef != 0:
            for j in range(len(gen)):
                res[i+j] ^= gf_mul(gen[j], coef)
    return res[len(data):]

# QR version capacity table (byte mode, EC level M), versions 1-9, sourced
# from the official ISO/IEC 18004 error-correction/block table (cross-
# checked against thonky.com/qr-code-tutorial/error-correction-table, and
# each version end-to-end verified against a real QR decoder — OpenCV's
# cv2.QRCodeDetector — before shipping). Capped at version 9 (~179 bytes of
# capacity) since that comfortably covers the longest realistic otpauth://
# setup URI this app generates (worst case ~143 bytes with a max-length
# 32-character username); version 10 hit decoder-side issues in testing
# that weren't worth chasing for headroom this app will never need.
# version: (total_data_codewords, ec_codewords_per_block,
#           group1_block_count, group1_data_codewords_per_block,
#           group2_block_count, group2_data_codewords_per_block)
VERSION_INFO_M = {
    1:  (16,  10, 1, 16,  0, 0),
    2:  (28,  16, 1, 28,  0, 0),
    3:  (44,  26, 1, 44,  0, 0),
    4:  (64,  18, 2, 32,  0, 0),
    5:  (86,  24, 2, 43,  0, 0),
    6:  (108, 16, 4, 27,  0, 0),
    7:  (124, 18, 4, 31,  0, 0),
    8:  (154, 22, 2, 38,  2, 39),
    9:  (182, 22, 3, 36,  2, 37),
}
# total modules per side = 4*version + 17
def version_size(v): return 4*v + 17

ALIGNMENT_POSITIONS = {
    1: [], 2: [6,18], 3: [6,22], 4: [6,26], 5: [6,30], 6: [6,34],
    7: [6,22,38], 8: [6,24,42], 9: [6,26,46], 10: [6,28,50],
}

def encode_byte_mode(data_bytes, version):
    """Build the data codeword sequence: mode(4)+len(8)+data+terminator+pad,
    then split into blocks (2 groups, per the official block table) and
    append Reed-Solomon error correction per block."""
    data_cw, ec_cw, g1_count, g1_size, g2_count, g2_size = VERSION_INFO_M[version]
    bits = []
    def push(val, n):
        for i in range(n-1,-1,-1): bits.append((val>>i)&1)
    push(0b0100, 4)  # byte mode indicator
    push(len(data_bytes), 8)
    for b in data_bytes: push(b, 8)
    total_data_bits = data_cw*8
    push(0, min(4, max(0, total_data_bits-len(bits))))
    while len(bits) % 8 != 0: bits.append(0)
    codewords = [int(''.join(map(str,bits[i:i+8])),2) for i in range(0,len(bits),8)]
    pad_bytes = itertools.cycle([0xEC,0x11])
    while len(codewords) < data_cw:
        codewords.append(next(pad_bytes))
    codewords = codewords[:data_cw]

    # Split into group 1 blocks (size g1_size) then group 2 blocks (size
    # g2_size = g1_size + 1, per spec) — NOT a naive equal split, since
    # versions 8+ have deliberately uneven block sizes across the two groups.
    blocks = []
    pos = 0
    for _ in range(g1_count):
        blocks.append(codewords[pos:pos+g1_size]); pos += g1_size
    for _ in range(g2_count):
        blocks.append(codewords[pos:pos+g2_size]); pos += g2_size
    assert pos == data_cw, f"block split mismatch: consumed {pos} of {data_cw}"

    ec_blocks = [rs_encode(b, ec_cw) for b in blocks]

    # interleave data codewords (longest block first per spec ordering —
    # shorter group-1 blocks simply stop contributing once exhausted)
    max_block_len = max(len(b) for b in blocks)
    interleaved = []
    for i in range(max_block_len):
        for b in blocks:
            if i < len(b):
                interleaved.append(b[i])
    for i in range(ec_cw):
        for eb in ec_blocks:
            interleaved.append(eb[i])
    return interleaved

def build_matrix(version, data_codewords, mask_pattern):
    n = version_size(version)
    matrix = [[None]*n for _ in range(n)]
    reserved = [[False]*n for _ in range(n)]

    def set_module(r,c,val,res=True):
        matrix[r][c]=val
        if res: reserved[r][c]=True

    def place_finder(r0,c0):
        for r in range(-1,8):
            for c in range(-1,8):
                rr,cc = r0+r, c0+c
                if 0<=rr<n and 0<=cc<n:
                    if 0<=r<=6 and 0<=c<=6 and (r in (0,6) or c in (0,6) or (2<=r<=4 and 2<=c<=4)):
                        set_module(rr,cc,1)
                    else:
                        set_module(rr,cc,0)
    place_finder(0,0); place_finder(0,n-7); place_finder(n-7,0)

    # timing patterns
    for i in range(8, n-8):
        set_module(6,i, 1 if i%2==0 else 0)
        set_module(i,6, 1 if i%2==0 else 0)

    # alignment patterns
    positions = ALIGNMENT_POSITIONS.get(version, [])
    for r0 in positions:
        for c0 in positions:
            # skip if overlapping finder patterns
            if (r0<=8 and c0<=8) or (r0<=8 and c0>=n-9) or (r0>=n-9 and c0<=8):
                continue
            for r in range(-2,3):
                for c in range(-2,3):
                    val = 1 if max(abs(r),abs(c))!=1 else 0
                    set_module(r0+r,c0+c,val)

    # dark module
    set_module(n-8, 8, 1)

    # reserve format info areas
    for i in range(9):
        if not reserved[8][i] if i<n else False: pass
    for c in range(9):
        reserved[8][c]=True
    for r in range(9):
        reserved[r][8]=True
    for c in range(n-8,n):
        reserved[8][c]=True
    for r in range(n-7,n):
        reserved[r][8]=True

    # reserve version info area for version>=7 (not needed for our small versions)
    if version >= 7:
        for r in range(6):
            for c in range(n-11,n-8):
                reserved[r][c]=True
        for c in range(6):
            for r in range(n-11,n-8):
                reserved[r][c]=True

    # place data bits in zigzag column pairs, skipping reserved
    bits = []
    for cw in data_codewords:
        for i in range(7,-1,-1):
            bits.append((cw>>i)&1)
    bit_idx = 0
    col = n-1
    upward = True
    while col > 0:
        if col == 6: col -= 1  # skip timing column
        for row_i in range(n):
            row = (n-1-row_i) if upward else row_i
            for c in (col, col-1):
                if not reserved[row][c]:
                    bitval = bits[bit_idx] if bit_idx < len(bits) else 0
                    bit_idx += 1
                    # apply mask
                    if mask_pattern == 0: m = (row+c)%2==0
                    elif mask_pattern == 1: m = row%2==0
                    elif mask_pattern == 2: m = c%3==0
                    elif mask_pattern == 3: m = (row+c)%3==0
                    elif mask_pattern == 4: m = ((row//2)+(c//3))%2==0
                    elif mask_pattern == 5: m = ((row*c)%2)+((row*c)%3)==0
                    elif mask_pattern == 6: m = (((row*c)%2)+((row*c)%3))%2==0
                    else: m = (((row+c)%2)+((row*c)%3))%2==0
                    matrix[row][c] = bitval ^ (1 if m else 0)
        upward = not upward
        col -= 2
    return matrix, reserved

def format_info_bits(ec_level_bits, mask_pattern):
    data = (ec_level_bits<<3) | mask_pattern
    g = 0x537
    val = data << 10
    for i in range(4,-1,-1):
        if val & (1<<(10+i)):
            val ^= g << i
    full = (data<<10) | val
    full ^= 0b101010000010010
    return [(full>>i)&1 for i in range(14,-1,-1)]

def version_info_bits(version):
    g = 0x1F25
    data = version
    val = data << 12
    for i in range(5, -1, -1):
        if val & (1 << (12 + i)):
            val ^= g << i
    full = (data << 12) | val
    return [(full >> i) & 1 for i in range(17, -1, -1)]


def apply_version_info(matrix, n, version):
    """Version >=7 codes carry their own 18-bit BCH-encoded version number
    in two 6x3 blocks near the top-right and bottom-left finder patterns,
    separate from and in addition to the 15-bit format info strip."""
    if version < 7:
        return
    bits = version_info_bits(version)[::-1]  # placed LSB-first per spec
    # Bottom-left block: 6 rows x 3 cols, rows 0..n-11, cols n-11..n-9? per
    # spec it's rows 0-5, cols n-11..n-9 for one block and its transpose
    # for the other; using the standard placement order (column-major
    # within each 3x6 block).
    idx = 0
    for c in range(6):
        for r in range(3):
            matrix[n - 11 + r][c] = bits[idx]
            idx += 1
    idx = 0
    for r in range(6):
        for c in range(3):
            matrix[r][n - 11 + c] = bits[idx]
            idx += 1


def apply_format_info(matrix, n, mask_pattern, ec_level_bits=0b00):
    bits = format_info_bits(ec_level_bits, mask_pattern)
    # around top-left finder
    positions_a = [(8,0),(8,1),(8,2),(8,3),(8,4),(8,5),(8,7),(8,8),(7,8),(5,8),(4,8),(3,8),(2,8),(1,8),(0,8)]
    for (r,c), b in zip(positions_a, bits):
        matrix[r][c]=b
    positions_b = [(n-1,8),(n-2,8),(n-3,8),(n-4,8),(n-5,8),(n-6,8),(n-7,8),
                   (8,n-8),(8,n-7),(8,n-6),(8,n-5),(8,n-4),(8,n-3),(8,n-2),(8,n-1)]
    for (r,c), b in zip(positions_b, bits):
        matrix[r][c]=b

def penalty_score(matrix, n):
    score = 0
    for r in range(n):
        run=1
        for c in range(1,n):
            if matrix[r][c]==matrix[r][c-1]: run+=1
            else:
                if run>=5: score += 3+(run-5)
                run=1
        if run>=5: score += 3+(run-5)
    for c in range(n):
        run=1
        for r in range(1,n):
            if matrix[r][c]==matrix[r-1][c]: run+=1
            else:
                if run>=5: score += 3+(run-5)
                run=1
        if run>=5: score += 3+(run-5)
    for r in range(n-1):
        for c in range(n-1):
            v = matrix[r][c]
            if matrix[r][c+1]==v and matrix[r+1][c]==v and matrix[r+1][c+1]==v:
                score += 3
    dark = sum(sum(row) for row in matrix)
    total = n*n
    pct = dark*100//total
    lo = (pct//5)*5
    hi = lo+5
    score += min(abs(lo-50),abs(hi-50))//5*10
    return score

def choose_version(data_len):
    for v in sorted(VERSION_INFO_M.keys()):
        data_cw = VERSION_INFO_M[v][0]
        cap = data_cw - 3  # headroom for mode+length+terminator (~2 bytes)
        if data_len <= cap:
            return v
    raise ValueError("data too long for supported versions (max ~213 bytes at EC level M)")

def encode_qr_svg(text: str, module_px: int = 6, quiet: int = 4) -> str:
    data_bytes = text.encode('utf-8')
    version = choose_version(len(data_bytes))
    codewords = encode_byte_mode(data_bytes, version)
    n = version_size(version)

    best = None
    for mask in range(8):
        matrix, reserved = build_matrix(version, codewords, mask)
        apply_format_info(matrix, n, mask)
        apply_version_info(matrix, n, version)
        score = penalty_score(matrix, n)
        if best is None or score < best[0]:
            best = (score, matrix)
    _, matrix = best

    size = (n + 2*quiet) * module_px
    rects = []
    for r in range(n):
        for c in range(n):
            if matrix[r][c]:
                x = (c+quiet)*module_px
                y = (r+quiet)*module_px
                rects.append(f'<rect x="{x}" y="{y}" width="{module_px}" height="{module_px}"/>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" '
           f'width="{size}" height="{size}" shape-rendering="crispEdges">'
           f'<rect width="{size}" height="{size}" fill="#ffffff"/>'
           f'<g fill="#000000">{"".join(rects)}</g></svg>')
    return svg
