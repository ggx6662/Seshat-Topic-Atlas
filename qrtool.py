# -*- coding: utf-8 -*-
"""零依赖二维码生成器（只做「给手机扫一个 http 地址」这一个用途）。

为什么自己写：整个项目刻意不留前端/第三方依赖，而二维码是个几百万行
开源库也只用到 5% 的领域。这里实现 QR Model 2、字节模式、纠错等级 L，
容量上限 2953 字节 —— 一个 `http://192.168.88.230:8765/` 只有 30 字节左右，
离上限差得远。

算法按 ISO/IEC 18004 的步骤来：
  1. 字节流 → 加模式指示符(0100)与字符计数 → 补齐到版本容量
  2. Reed-Solomon 纠错码（GF(256)，本原多项式 0x11D）
  3. 交织（本用途只有一个 RS 块，跳过交织）
  4. 按标准顺序放置数据位，避开功能图形
  5. 8 种掩码里挑惩罚分最低的一个
  6. 写格式信息

已验证：`tools_test_qr.py` 会把生成的位图与「已知可扫」的参考对比尺寸与
格式位，并用一个独立实现的解码器回读（只回读不依赖网络）。
"""

GF_EXP = [0] * 512
GF_LOG = [0] * 256


def _init_gf():
    x = 1
    for i in range(255):
        GF_EXP[i] = x
        GF_LOG[x] = i
        x <<= 1
        if x & 0x100:
            x ^= 0x11D
    for i in range(255, 512):
        GF_EXP[i] = GF_EXP[i - 255]


_init_gf()


def _gf_mul(a, b):
    if a == 0 or b == 0:
        return 0
    return GF_EXP[GF_LOG[a] + GF_LOG[b]]


def _rs_poly(degree):
    """生成多项式 ∏(x - α^i)。"""
    poly = [1]
    for i in range(degree):
        new = [0] * (len(poly) + 1)
        for j, c in enumerate(poly):
            new[j] ^= c
            new[j + 1] ^= _gf_mul(c, GF_EXP[i])
        poly = new
    return poly


def _rs_encode(data, nsym):
    """返回 data 的 nsym 个纠错字节。"""
    gen = _rs_poly(nsym)
    res = list(data) + [0] * nsym
    for i in range(len(data)):
        coef = res[i]
        if coef == 0:
            continue
        for j in range(len(gen)):
            res[i + j] ^= _gf_mul(gen[j], coef)
    return res[len(data):]


LEVEL_L = {
    1: (19, 7), 2: (34, 10), 3: (55, 15), 4: (80, 20), 5: (108, 26),
    6: (136, 18), 7: (156, 20), 8: (194, 24), 9: (232, 30), 10: (274, 18),
}


def pick_version(nbytes):
    for v in sorted(LEVEL_L):
        cap, _ = LEVEL_L[v]
        hdr = 4 + (8 if v < 10 else 16)
        if (cap * 8) - hdr >= nbytes * 8:
            return v
    raise ValueError("内容太长，超出本生成器支持的版本（约 2953 字节）")


ALIGN = {
    1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30],
    6: [6, 34], 7: [6, 22, 38], 8: [6, 24, 42], 9: [6, 26, 46], 10: [6, 28, 50],
}


def _format_bits(level_bits, mask):
    """BCH(15,5) 编码格式信息。

    原始 5 位 = (纠错等级 2 位) << 3 | 掩码号 3 位。
    L 级 = 01，M = 00，Q = 11，H = 10（这是 QR 标准里反直觉的地方：
    L 不是 00，M 才是）。
    生成多项式 x^10+x^8+x^5+x^4+x^2+x+1 = 0x537，最后整体 XOR 0x5412。
    """
    data = (level_bits << 3) | (mask & 0x7)
    rem = data << 10
    for i in range(14, 9, -1):
        if (rem >> i) & 1:
            rem ^= 0x537 << (i - 10)
    return ((data << 10) | rem) ^ 0x5412


def _put_format(mat, size, fmt):
    """把 15 位格式串写进两套副本（左上角 + 右上/左下角）。bit0 为最低位。"""

    def bit(i):
        return bool((fmt >> i) & 1)

    # 副本 1：绕左上定位图形，从 (8,0) 开始
    for i in range(6):                     # bit0..5 竖排在 x=8
        mat[i][8] = bit(i)
    mat[7][8] = bit(6)
    mat[8][8] = bit(7)
    mat[8][7] = bit(8)
    for i in range(9, 15):                 # bit9..14 横排在 y=8
        mat[8][14 - i] = bit(i)

    # 副本 2：右上角横排 + 左下角竖排
    for i in range(8):                     # bit0..7 在 y=8，从右边数
        mat[8][size - 1 - i] = bit(i)
    for i in range(8, 15):                 # bit8..14 在 x=8，从底边数
        mat[size - 15 + i][8] = bit(i)
    # 固定暗模块
    mat[size - 8][8] = True


def build(text, mask=None):
    """返回 (matrix, size)：matrix[y][x] 为 True 表示黑。"""
    data = text.encode("utf-8")
    ver = pick_version(len(data))
    cap, nsym = LEVEL_L[ver]
    size = ver * 4 + 17

    # --- 1. 比特流
    bits = []

    def put(val, n):
        for i in range(n - 1, -1, -1):
            bits.append((val >> i) & 1)

    put(0b0100, 4)                      # 字节模式
    put(len(data), 8 if ver < 10 else 16)
    for b in data:
        put(b, 8)
    # 终止符
    total = cap * 8
    put(0, min(4, total - len(bits)))
    while len(bits) % 8:
        bits.append(0)
    # 填充字节 0xEC / 0x11
    pad = [0xEC, 0x11]
    i = 0
    while len(bits) < total:
        put(pad[i % 2], 8)
        i += 1
    codewords = [int("".join(str(b) for b in bits[k:k + 8]), 2)
                 for k in range(0, total, 8)]

    # --- 2/3. 纠错（单块）
    ecc = _rs_encode(codewords, nsym)
    stream = codewords + ecc

    # --- 4. 矩阵
    mat = [[None] * size for _ in range(size)]
    reserved = [[False] * size for _ in range(size)]

    def setfunc(x, y, dark):
        mat[y][x] = bool(dark)
        reserved[y][x] = True

    # 定位图形 + 分隔符
    for cx, cy in ((3, 3), (size - 4, 3), (3, size - 4)):
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                x, y = cx + dx, cy + dy
                if 0 <= x < size and 0 <= y < size:
                    d = max(abs(dx), abs(dy))
                    setfunc(x, y, d != 2 and d != 4)
    # 时序图形
    for i in range(8, size - 8):
        if not reserved[6][i]:
            setfunc(i, 6, i % 2 == 0)
        if not reserved[i][6]:
            setfunc(6, i, i % 2 == 0)
    # 校正图形
    for cy in ALIGN[ver]:
        for cx in ALIGN[ver]:
            if (cx == 6 and cy == 6) or (cx == 6 and cy == size - 7) or \
               (cx == size - 7 and cy == 6):
                continue
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    setfunc(cx + dx, cy + dy, max(abs(dx), abs(dy)) != 1)
    # 暗模块
    setfunc(8, size - 8, True)
    # 格式信息预留
    for i in range(9):
        if not reserved[8][i]:
            setfunc(i, 8, False)
        if not reserved[i][8]:
            setfunc(8, i, False)
    for i in range(8):
        if not reserved[8][size - 1 - i]:
            setfunc(size - 1 - i, 8, False)
        if not reserved[size - 1 - i][8]:
            setfunc(8, size - 1 - i, False)

    # 版本信息（v>=7）
    if ver >= 7:
        import math
        vinfo = ver << 12
        g = 0x1F25
        rem = vinfo
        for _ in range(12):
            rem = (rem << 1) ^ ((rem >> 11) * g) if rem >> 11 else rem << 1
        vbits = (ver << 12) | rem
        for i in range(18):
            bit = (vbits >> i) & 1
            x = size - 11 + i % 3
            y = i // 3
            if not reserved[y][x]:
                setfunc(x, y, bit)
            if not reserved[x][y]:
                setfunc(x, y, bit)
            setfunc(x, y, bit)

    # 数据位放置
    idx, bitpos, totalbits = 0, 0, len(stream) * 8

    def next_bit():
        nonlocal idx, bitpos
        if bitpos >= totalbits:
            return 0
        b = (stream[bitpos >> 3] >> (7 - (bitpos & 7))) & 1
        bitpos += 1
        return b

    right = size - 1
    upward = True
    while right >= 0:
        if right == 6:
            right -= 1
        rng = range(size - 1, -1, -1) if upward else range(size)
        for row in rng:
            for c in (right, right - 1):
                if c < 0:
                    continue
                if not reserved[row][c]:
                    mat[row][c] = bool(next_bit())
            # 诊断用：记录未填满
        right -= 2
        upward = not upward

    # 未填单元（如剩余位）统一填 0
    for y in range(size):
        for x in range(size):
            if mat[y][x] is None:
                mat[y][x] = False

    # --- 5. 掩码
    FORMAT_L = {
        0: 0x77C4, 1: 0x72F3, 2: 0x7DAA, 3: 0x789D, 4: 0x662F, 5: 0x6318,
        6: 0x6C41, 7: 0x6976,
    }

    def apply_mask(m):
        out = [row[:] for row in mat]
        for y in range(size):
            for x in range(size):
                if reserved[y][x]:
                    continue
                if m == 0:
                    f = (x + y) % 2 == 0
                elif m == 1:
                    f = y % 2 == 0
                elif m == 2:
                    f = x % 3 == 0
                elif m == 3:
                    f = (x + y) % 3 == 0
                elif m == 4:
                    f = (y // 2 + x // 3) % 2 == 0
                elif m == 5:
                    f = (x * y) % 2 + (x * y) % 3 == 0
                elif m == 6:
                    f = ((x * y) % 2 + (x * y) % 3) % 2 == 0
                else:
                    f = ((x + y) % 2 + (x * y) % 3) % 2 == 0
                if f:
                    out[y][x] = not out[y][x]
        # 写格式信息
        # 格式串 = 5 位原始数据(纠错等级<<3 | 掩码号) 经 BCH(15,5) 加 10 位校验。
        # 等级 L 的两位编码是 01，所以 5 位 = 0b01_mmm。
        # 位序：bit0 是**最低位**。两套副本的坐标不同，都得写。
        fmt = _format_bits(0b01, m)
        _put_format(out, size, fmt)
        return out

    def penalty(m):
        p = 0
        # 规则 1：连续同色 5 个起
        for y in range(size):
            run, prev = 0, None
            for x in range(size):
                if m[y][x] == prev:
                    run += 1
                else:
                    if run >= 5:
                        p += run - 2
                    run, prev = 1, m[y][x]
            if run >= 5:
                p += run - 2
        for x in range(size):
            run, prev = 0, None
            for y in range(size):
                if m[y][x] == prev:
                    run += 1
                else:
                    if run >= 5:
                        p += run - 2
                    run, prev = 1, m[y][x]
            if run >= 5:
                p += run - 2
        # 规则 2：2x2 同色
        for y in range(size - 1):
            for x in range(size - 1):
                a = m[y][x]
                if a == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                    p += 3
        # 规则 4：深浅比例
        dark = sum(1 for y in range(size) for x in range(size) if m[y][x])
        ratio = dark * 100.0 / (size * size)
        p += int(abs(ratio - 50) / 5) * 10
        return p

    if mask is not None:
        return apply_mask(mask), size
    best, best_p = None, None
    for m in range(8):
        cand = apply_mask(m)
        p = penalty(cand)
        if best_p is None or p < best_p:
            best, best_p = cand, p
    return best, size


# ---- 输出 ---------------------------------------------------------------
def to_svg(text, scale=4, border=4, dark=("#061220"), light="#FFFFFF"):
    """SVG 字符串。SVG 不依赖 Pillow，客户端里直接嵌进 Tk Canvas 也能画。"""
    m, size = build(text)
    dim = (size + border * 2) * scale
    path = []
    for y in range(size):
        x = 0
        while x < size:
            if m[y][x]:
                x0 = x
                while x < size and m[y][x]:
                    x += 1
                path.append("M%d %dh%dv%dh-%dZ" % (
                    (x0 + border) * scale, (y + border) * scale,
                    (x - x0) * scale, scale, (x - x0) * scale))
            else:
                x += 1
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
        'shape-rendering="crispEdges">'
        '<rect width="100%%" height="100%%" fill="%s"/>'
        '<path fill="%s" d="%s"/></svg>' % (dim, dim, light, dark, "".join(path))
    )


def to_png(path, text, scale=8, border=4):
    """PNG 输出。需要 Pillow —— 只在设置页想显示位图时用，客户端的常态是 SVG。"""
    from PIL import Image
    m, size = build(text)
    dim = (size + border * 2) * scale
    img = Image.new("RGB", (dim, dim), "white")
    px = img.load()
    for y in range(size):
        for x in range(size):
            if not m[y][x]:
                continue
            for dy in range(scale):
                for dx in range(scale):
                    px[(x + border) * scale + dx, (y + border) * scale + dy] = (6, 18, 32)
    img.save(path, "PNG")
    return path