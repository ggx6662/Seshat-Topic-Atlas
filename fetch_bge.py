"""下载 bge-small-zh-v1.5 权重（绕开 huggingface_hub 的 httpx bug）。

背景：huggingface_hub 2.4.0 + httpx2 在解压响应时抛
`TypeError: process() takes no keyword arguments`，自动下载走不通。
hf-mirror 的小文件能下，model.safetensors（95MB）会挂住。
改用 OpenBMB 官方直链（bge 的作者团队，模型就叫 bge-small-zh-v1.5）。

用法：
    python fetch_bge.py            # 依次尝试多个源
    python fetch_bge.py --probe    # 只测连通性不打文件
"""
import sys
import time
import urllib.request
from pathlib import Path

MODEL_ZIP_URLS = [
    # OpenBMB 官方发布（zip 内含完整目录）
    "https://model.ks3-cn-beijing.ksyuncs.com/model/BAAI/bge-small-zh-v1.5.zip",
    "https://hf-mirror.com/BAAI/bge-small-zh-v1.5/resolve/main/model.safetensors",
    "https://huggingface.co/BAAI/bge-small-zh-v1.5/resolve/main/model.safetensors",
]
SMALL = {
    "config.json": "https://hf-mirror.com/BAAI/bge-small-zh-v1.5/resolve/main/config.json",
    "modules.json": "https://hf-mirror.com/BAAI/bge-small-zh-v1.5/resolve/main/modules.json",
    "sentence_bert_config.json":
        "https://hf-mirror.com/BAAI/bge-small-zh-v1.5/resolve/main/sentence_bert_config.json",
    "1_Pooling/config.json":
        "https://hf-mirror.com/BAAI/bge-small-zh-v1.5/resolve/main/1_Pooling/config.json",
    "tokenizer.json": "https://hf-mirror.com/BAAI/bge-small-zh-v1.5/resolve/main/tokenizer.json",
    "tokenizer_config.json":
        "https://hf-mirror.com/BAAI/bge-small-zh-v1.5/resolve/main/tokenizer_config.json",
    "vocab.txt": "https://hf-mirror.com/BAAI/bge-small-zh-v1.5/resolve/main/vocab.txt",
}
try:  # 目录从 kb_vector 统一取（支持 KB_VECTOR_DIR / config.json 的 kb_vector_path）
    import kb_vector as _KV
    DEST = _KV.BASE / "models" / "bge-small-zh-v1.5"
except Exception:
    DEST = Path(r"G:\kb-vector\models\bge-small-zh-v1.5")


def probe(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "kb-vector/1.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            n = 0
            t0 = time.time()
            while n < (2 << 20):
                b = r.read(65536)
                if not b:
                    break
                n += len(b)
            return "OK 读到 %d KB / %.1fs  总大小 %s" % (
                n // 1024, time.time() - t0, r.headers.get("Content-Length"))
    except Exception as exc:
        return "FAIL %s: %s" % (type(exc).__name__, exc)


def main(argv):
    if "--probe" in argv:
        for u in MODEL_ZIP_URLS:
            print("%-72s %s" % (u[:72], probe(u)), flush=True)
        return 0
    DEST.mkdir(parents=True, exist_ok=True)
    for name, url in SMALL.items():
        dst = DEST / name
        if dst.exists() and dst.stat().st_size > 100:
            print("  跳过 %s" % name, flush=True)
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "kb-vector/1.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            dst.write_bytes(data)
            print("  ✓ %-26s %6d B" % (name, len(data)), flush=True)
        except Exception as exc:
            print("  ✗ %-26s %s" % (name, exc), flush=True)
    print("小文件完成", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))