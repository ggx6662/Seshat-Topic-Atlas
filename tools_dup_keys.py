"""CN2EN 重复键检测：同一个中文键写了两次、值还不一样，是隐藏的错误源。

Python 字典字面量里后出现的键会静默覆盖前面的，写成
    "去噪": "denoising", ... "去噪": "denoise",
不会有任何报错，但改前一处的人会以为改生效了。
"""
import io
import re
import sys


def main(path="arxiv_latest.py"):
    src = io.open(path, encoding="utf-8").read()
    m = re.search(r"CN2EN\s*=\s*\{(.*?)\n\}", src, re.S)
    if not m:
        print("没找到 CN2EN 定义")
        return 1
    seen = {}
    dups = []
    for ln_no, ln in enumerate(m.group(1).splitlines()):
        for k, v in re.findall(r'"([^"]+)"\s*:\s*"([^"]*)"', ln):
            if k in seen:
                dups.append((k, seen[k], v))
            else:
                seen[k] = v
    if not dups:
        print("CN2EN 无重复键（%d 个键）" % len(seen))
        return 0
    bad = 0
    for k, a, b in dups:
        if a == b:
            print("重复（值相同，无害）：%s = %s" % (k, a))
        else:
            bad += 1
            print("冲突：%s 先写 %s，后写 %s —— 生效的是后者" % (k, a, b))
    print("\n共 %d 个重复键，其中 %d 个值冲突" % (len(dups), bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))