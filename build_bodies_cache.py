"""预生成标题+摘要的压缩缓存，把 load_bodies 的 6.7 秒降到 1 秒内。

load_bodies() 每次新进程都要把 157 个 jsonl（825MB）读一遍、逐行 json.loads，
实测 6.68 秒。新颖性核查、AND 检索都要用它 —— 用户点一次候选就卡 7 秒，
这是「按视口惰性核」落地后的最后一处硬伤。

做法：把所有正文按行拼成一个 bytes（\\n 分隔，行内不含 \\n），zlib 压缩后落盘。
读的时候一次解压再 split，比 157 次小文件读 + 54 万次 json.loads 快得多。
文件签名用 157 个 jsonl 的 (名字, 大小, mtime) 拼 hash，源数据变了自动重建。

用法：
    python build_bodies_cache.py            # 有缓存且签名未变就跳过
    python build_bodies_cache.py --force
"""
import glob
import hashlib
import json
import os
import sys
import time
import zlib
from pathlib import Path

SRC, OUT = _base()


def _base():
    """目录从 kb_vector 统一取（支持 KB_VECTOR_DIR / config.json 的 kb_vector_path）。"""
    try:
        import kb_vector
        return kb_vector.SRC, kb_vector.OUT / "bodies.z"
    except Exception:
        return Path(r"G:\kb-vector\arxiv_cs"), Path(r"G:\kb-vector\index\bodies.z")


def source_sig(files=None):
    files = files or sorted(glob.glob(str(SRC / "*.jsonl")))
    h = hashlib.md5()
    for f in files:
        st = os.stat(f)
        h.update(("%s|%d|%d;" % (os.path.basename(f), st.st_size,
                                 int(st.st_mtime))).encode())
    return h.hexdigest()


def build(force=False, log=print):
    t0 = time.time()
    files = sorted(glob.glob(str(SRC / "*.jsonl")))
    if not files:
        raise SystemExit("没有找到 %s/*.jsonl" % SRC)
    sig = source_sig(files)
    if not force and OUT.exists():
        try:
            with open(OUT, "rb") as fh:
                head = json.loads(fh.readline().decode("utf-8"))
            if head.get("sig") == sig:
                log("缓存已是最新（%s）" % sig[:8])
                return
        except Exception:
            pass

    # 顺序必须和 load() 里的 ids 一致，否则正文和向量对不上号。
    # 这里按 jsonl 文件名排序读入，kb_vector.load_bodies 也走同一顺序。
    lines = []
    for f in files:
        with open(f, encoding="utf-8") as fh:
            for ln in fh:
                try:
                    r = json.loads(ln)
                except Exception:
                    continue
                txt = ((r.get("title") or "") + " "
                       + (r.get("abstract") or "")).lower()
                lines.append(str(r.get("id") or "") + "\t" + txt.replace("\n", " "))
    log("读入 %d 条，%.1fs" % (len(lines), time.time() - t0))

    raw = "\n".join(lines).encode("utf-8")
    t1 = time.time()
    comp = zlib.compress(raw, 6)
    log("压缩 %.1fs：%.1f MB → %.1f MB" % (time.time() - t1,
                                         len(raw) / 1048576.0,
                                         len(comp) / 1048576.0))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    with open(tmp, "wb") as fh:
        fh.write((json.dumps({"sig": sig, "n": len(lines),
                              "block": len(comp)}) + "\n").encode("utf-8"))
        fh.write(comp)
    os.replace(tmp, OUT)
    log("已写出 %s（总耗时 %.1fs）" % (OUT, time.time() - t0))


if __name__ == "__main__":
    build(force="--force" in sys.argv)