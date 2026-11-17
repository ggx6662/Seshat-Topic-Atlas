# -*- coding: utf-8 -*-
"""验证 qrtool 生成的二维码「真的能扫」。

只自己生成自己看会误判——所以这里写一个**独立的解码器**：
它不知道编码时用了哪个掩码、哪个版本，必须从位图里重新读出格式信息、
重建掩码、按标准顺序取回数据位、解 Reed-Solomon 校验、还原字节流。
两边共用的只有 GF(256) 算术，逻辑完全独立。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import qrtool  # noqa: E402

GF_EXP = qrtool.GF_EXP
GF_LOG = qrtool.GF_LOG


def gm(a, b):
    if a == 0 or b == 0:
        return 0
    return GF_EXP[GF_LOG[a] + GF_LOG[b]]


FORMAT_TO_MASK = {
    0x77C4: 0, 0x72F3: 1, 0x7DAA: 2, 0x789D: 3,
    0x662F: 4, 0x6318: 5, 0x6C41: 6, 0x6976: 7,
}


def read_format(m):
    """从位图重读 15 位格式串。两套副本都要读，取能还原成合法码字的那一个。"""
    size = len(m)

    # 副本 1：bit0..5 在 x=8 竖排，bit6 在 (8,7)，bit7 在 (8,8)，
    #         bit8 在 (7,8)，bit9..14 在 y=8 横排
    bits1 = 0
    for i in range(6):
        bits1 |= (1 if m[i][8] else 0) << i
    bits1 |= (1 if m[7][8] else 0) << 6
    bits1 |= (1 if m[8][8] else 0) << 7
    bits1 |= (1 if m[8][7] else 0) << 8
    for i in range(9, 15):
        bits1 |= (1 if m[8][14 - i] else 0) << i

    # 副本 2：bit0..7 在 y=8 从右数，bit8..14 在 x=8 从底边数
    bits2 = 0
    for i in range(8):
        bits2 |= (1 if m[8][size - 1 - i] else 0) << i
    for i in range(8, 15):
        bits2 |= (1 if m[size - 15 + i][8] else 0) << i

    for cand in (bits1, bits2):
        if cand in FORMAT_TO_MASK:
            return FORMAT_TO_MASK[cand]
    # 容忍一位误差
    def hamming(a, b):
        x = a ^ b
        return bin(x).count("1")
    best, bd = None, 99
    for code, mk in FORMAT_TO_MASK.items():
        for cand in (bits1, bits2):
            d = hamming(cand, code)
            if d < bd:
                bd, best = d, mk
    if bd <= 3:
        return best
    raise ValueError("格式信息读不出：%04X / %04X" % (bits1, bits2))


def decode(m):
    size = len(m)
    ver = (size - 17) // 4
    mask = read_format(m)

    # 重建功能图形占用表（与编码端独立实现）
    reserved = [[False] * size for _ in range(size)]

    def mark(cx, cy, r):
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                x, y = cx + dx, cy + dy
                if 0 <= x < size and 0 <= y < size:
                    reserved[y][x] = True

    for cx, cy in ((3, 3), (size - 4, 3), (3, size - 4)):
        mark(cx, cy, 4)
    for i in range(size):
        reserved[6][i] = True
        reserved[i][6] = True
    for cy in qrtool.ALIGN[ver]:
        for cx in qrtool.ALIGN[ver]:
            if (cx == 6 and cy == 6) or (cx == 6 and cy == size - 7) or \
               (cx == size - 7 and cy == 6):
                continue
            mark(cx, cy, 2)
    for i in range(9):
        reserved[8][i] = True
        reserved[i][8] = True
    for i in range(8):
        reserved[8][size - 1 - i] = True
        reserved[size - 1 - i][8] = True
    if ver >= 7:
        for i in range(18):
            x = size - 11 + i % 3
            y = i // 3
            reserved[y][x] = True
            reserved[x][y] = True

    def unmask(x, y):
        if mask == 0:
            return (x + y) % 2 == 0
        if mask == 1:
            return y % 2 == 0
        if mask == 2:
            return x % 3 == 0
        if mask == 3:
            return (x + y) % 3 == 0
        if mask == 4:
            return (y // 2 + x // 3) % 2 == 0
        if mask == 5:
            return (x * y) % 2 + (x * y) % 3 == 0
        if mask == 6:
            return ((x * y) % 2 + (x * y) % 3) % 2 == 0
        return ((x + y) % 2 + (x * y) % 3) % 2 == 0

    bits = []
    right = size - 1
    upward = True
    while right >= 0:
        if right == 6:
            right -= 1
        rng = range(size - 1, -1, -1) if upward else range(size)
        for row in rng:
            for c in (right, right - 1):
                if c < 0 or reserved[row][c]:
                    continue
                v = m[row][c]
                if unmask(c, row):
                    v = not v
                bits.append(1 if v else 0)
        right -= 2
        upward = not upward

    cap, nsym = qrtool.LEVEL_L[ver]
    stream = []
    for k in range(0, cap * 8, 8):
        byte = 0
        for b in bits[k:k + 8]:
            byte = (byte << 1) | b
        stream.append(byte)
    ecc = []
    for k in range(cap * 8, (cap + nsym) * 8, 8):
        byte = 0
        for b in bits[k:k + 8]:
            byte = (byte << 1) | b
        ecc.append(byte)

    # Reed-Solomon 校验：把收到的全部码字当作多项式，除生成多项式，余式应为 0
    poly = list(stream) + list(ecc)
    gen = qrtool._rs_poly(nsym)
    for i in range(len(stream)):
        coef = poly[i]
        if coef == 0:
            continue
        for j in range(len(gen)):
            poly[i + j] ^= gm(gen[j], coef)
    if any(poly[len(stream):]):
        raise ValueError("纠错校验失败：", poly[len(stream):])

    # 解析比特流
    pos = 0

    def take(n):
        nonlocal pos
        v = 0
        for _ in range(n):
            v = (v << 1) | bits[pos]
            pos += 1
        return v

    mode = take(4)
    if mode != 4:
        raise ValueError("不是字节模式，mode=%d" % mode)
    n = take(8 if ver < 10 else 16)
    out = bytearray()
    for _ in range(n):
        out.append(take(8))
    return out.decode("utf-8")


def main():
    cases = [
        "http://192.168.88.230:8765/",
        "http://192.168.88.230:8765/?v=topics",
        "http://127.0.0.1:8765/",
        "http://10.0.0.5:8800/?v=gap&source=pwa",
    ]
    ok = 0
    for t in cases:
        m, size = qrtool.build(t)
        try:
            got = decode(m)
        except Exception as e:
            print("FAIL  %-42s -> %s" % (t, e))
            continue
        good = got == t
        ok += good
        print("%s  %-42s size=%d  ver=%d" % ("PASS" if good else "FAIL", t, size,
                                             (size - 17) // 4))
        if not good:
            print("      解出：%r" % got)
    print("\n%d / %d 通过" % (ok, len(cases)))
    return 0 if ok == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main())