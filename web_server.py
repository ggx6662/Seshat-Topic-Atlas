# -*- coding: utf-8 -*-
"""网页版体验端：只读、受限、零依赖。

## 为什么用标准库 http.server

装 FastAPI 要拖 uvicorn/starlette/pydantic，装 Flask 要拖 werkzeug。这个项目
主打「绿色便携、担心依赖」，多一个第三方包就多一处版本冲突。体验端只需要
十几个 GET 接口，`http.server.ThreadingHTTPServer` 完全够用，而且它是标准库，
打包进 exe 不会让体积变大。

## 受限策略（用户明确要求）

    ✓ 选题候选生成      ✓ 文献空白分析      ✓ 导师与院校查询
    ✓ 方向图谱浏览      ✓ 科研方法论        ✓ 期刊会议推荐

    ✗ 下载到知识库      —— 会写用户磁盘
    ✗ 大模型设置        —— 密钥属于本机
    ✗ 个人画像          —— 含学校/导师/目标
    ✗ 文献库全文检索    —— 会暴露本地文件路径
    ✗ 抓取最新论文      —— 外部请求，体验端限流

限制不是「前端藏起来」，而是**后端根本不注册这些路由**。前端就算手改 URL
也只会拿到 404。这条写在 `ALLOWED` 表里，加接口必须显式登记。

## 启动

    python web_server.py                 # http://127.0.0.1:8765
    python web_server.py --port 9000 --host 0.0.0.0

`--host 0.0.0.0` 才能被手机访问（④移动端），默认只绑本机。
"""
import argparse
import json
import os
import re
import socket
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

try:
    import app_paths as P
    _RES = P.res
except Exception:
    _RES = lambda n: HERE / n

STATIC_DIR = Path(str(_RES("web_static")))


def _token_style():
    """把 design_tokens 里的色彩 / 字号 / 圆角渲染成一段 <style>。

    桌面端 app_theme.py 从同一个文件取色，所以改 design_tokens.COLORS
    一处，客户端与网页端同时生效 —— 这是「三端像同一个产品」的物理保证，
    而不是靠两处手工对齐。
    """
    try:
        import design_tokens as DT
        body = DT.css_block()
    except Exception:
        return ""
    return "<style>\n/* 由 design_tokens.py 注入，勿手改 */\n%s\n</style>" % body

# ---- 懒加载：网页版不启动 Tk，只用到纯数据层 -------------------------------
_LOCK = threading.Lock()
_MODS = {}


def _mod(name):
    with _LOCK:
        if name not in _MODS:
            _MODS[name] = __import__(name)
        return _MODS[name]


def _import_all():
    import topic_gen        # noqa: F401
    import research_gap     # noqa: F401
    import advisor_index    # noqa: F401
    import kb_widget        # noqa: F401
    import research_skills  # noqa: F401


# ---- 受限白名单 -------------------------------------------------------------
# key -> (方法, 说明)。加接口必须在这里登记，否则路由不生效。
ALLOWED = {
    "/api/ping":          ("GET", "健康检查"),
    "/api/overview":      ("GET", "总览数字"),
    "/api/taxonomy":      ("GET", "方向图谱"),
    "/api/topics":        ("GET", "选题候选生成"),
    "/api/gap":           ("GET", "文献空白分析"),
    "/api/advisors":      ("GET", "导师与院校查询"),
    "/api/skills":        ("GET", "科研方法论"),
}

# 明确禁止的路径，返回 403 并说明原因（比 404 更有教育意义，用户知道是「故意不开」）
BLOCKED = {
    "/api/download":  "下载到知识库会写你的磁盘，体验端不开放。请在桌面客户端里做。",
    "/api/llm":       "大模型密钥属于本机配置，体验端不开放。",
    "/api/profile":   "个人画像含学校/导师/目标，体验端不开放。",
    "/api/library":   "文献库全文检索会暴露本地文件路径，体验端不开放。",
    "/api/latest":    "抓取最新论文要走外部请求，体验端限流不开放。",
}

# ---- 简单限流：同一 IP 每分钟 N 次 -----------------------------------------
RATE_LIMIT = 120
_RATE = {}
_RATE_LOCK = threading.Lock()


def _rate_ok(ip):
    now = time.time()
    with _RATE_LOCK:
        win = _RATE.setdefault(ip, [])
        win[:] = [t for t in win if now - t < 60]
        if len(win) >= RATE_LIMIT:
            return False
        win.append(now)
        return True


# ---- 绑端口 ----------------------------------------------------------------
class _Server(ThreadingHTTPServer):
    """禁止 SO_REUSEADDR。

    Windows 的 SO_REUSEADDR 语义与 Linux 不同：它允许绑到**已被占用**的端口
    （甚至能把别的进程挤掉），于是「端口被占就往后找」的判断永远不成立，
    最后两个服务抢同一个端口，请求随机落到其中一个上。
    ThreadingHTTPServer 默认带 allow_reuse_address = 1，这里必须关掉。
    """

    allow_reuse_address = False
    daemon_threads = True


# ---- 业务处理 ---------------------------------------------------------------
_CACHE = {}


def _cached(key, ttl, fn):
    now = time.time()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    val = fn()
    _CACHE[key] = (now, val)
    return val


def api_overview(q):
    kb = _mod("kb_widget")
    st = kb.kb_stats()

    def build():
        try:
            ai = _mod("advisor_index").stats()
        except Exception:
            ai = {}
        try:
            ss = _mod("semantic_search").stats()
        except Exception:
            ss = {}
        try:
            mi = _mod("meta_index").stats()
        except Exception:
            mi = {}
        # 2026-11-20：原来这里把 kb_stats() 的 total_txt（本地 PDF 转出的
        # **文本文件**个数，16）当成「方向大类」抛给前端，页面上写着
        # 「16 个方向大类」，而桌面端方向图谱是 25 个大类 / 536 个方向。
        # 两个字段同名不同义，是同一个坑的一部分。改成直接数方向库。
        try:
            dir_total = len(kb.load_direction_library() or {})
        except Exception:
            dir_total = 0
        try:
            venues = len((json.loads(Path(str(_RES("venue_meta.json")))
                                     .read_text(encoding="utf-8"))
                          .get("venues") or {}))
        except Exception:
            venues = 0
        return {"papers": st.get("total_pdf", 0),
                "cats": dir_total,
                "text_files": st.get("total_txt", 0),
                "venues": venues,
                "advisors": ai.get("advisors", 0),
                "complete_advisors": ai.get("complete_advisors", 0),
                "institutions": ai.get("institutions", 0),
                "indexed": ss.get("indexed", 0),
                "titled": mi.get("title", 0)}
    return _cached("overview", 300, build)


def api_taxonomy(q):
    def build():
        # 2026-11-20：这里原来直接读 directions_library.json（12 个大类 / 64 个
        # 小类），而桌面端方向图谱用的是 kb.load_direction_library() 合并后的
        # 25 大类 / 536 个方向 —— 同一份数据两套口径，网页版方向图谱凭空少一半。
        # 改成走桌面端同一个函数，两边就只有一个真相。
        # 返回结构保持 {category, count, fields:[{name, keywords}]} 不变。
        lib = _mod("kb_widget").load_direction_library()
        out = []
        for cat, body in (lib or {}).items():
            if not isinstance(body, dict):
                continue
            subs = []
            for s in body.get("subs", []):
                if isinstance(s, dict):
                    subs.append({"name": s.get("name", ""),
                                 "keywords": s.get("keywords", [])[:6]})
            out.append({"category": cat, "count": len(subs), "fields": subs})
        return {"categories": out, "total": sum(c["count"] for c in out)}
    return _cached("taxonomy", 3600, build)


def api_topics(q):
    dirn = (q.get("direction") or [""])[0].strip()
    if not dirn:
        return {"error": "缺少 direction 参数"}
    limit = min(24, max(1, int((q.get("limit") or ["18"])[0] or 18)))
    tg = _mod("topic_gen")
    cands = tg.build(dirn, "自动混合", limit)
    keep = ("title", "strategy", "angle", "reason", "questions",
            "min_experiment", "relevance", "novelty", "feasibility", "score")
    return {"direction": dirn,
            "generic_questions": list(getattr(tg, "GENERIC_QUESTIONS", [])),
            "candidates": [{k: c.get(k) for k in keep} for c in cands]}


def api_gap(q):
    dirn = (q.get("direction") or [""])[0].strip()
    if not dirn:
        return {"error": "缺少 direction 参数"}
    g = _mod("research_gap")
    d = g.analyze(dirn)
    return {"direction": dirn,
            "total": d.get("total", 0),
            "methods": [list(x) for x in d.get("methods", [])][:12],
            "tasks": [list(x) for x in d.get("tasks", [])][:12],
            "modals": [list(x) for x in d.get("modals", [])][:10],
            "issues": [list(x) for x in d.get("issues", [])][:10],
            "combos": [{k: c.get(k) for k in ("method", "task", "count", "examples")}
                       for c in d.get("combos", [])][:20],
            "gaps": [{k: x.get(k) for k in ("method", "task", "reason")}
                     for x in d.get("gaps", [])][:8],
            "issue_gaps": [{k: x.get(k) for k in ("issue", "reason")}
                           for x in d.get("issue_gaps", [])][:8]}


def api_advisors(q):
    kw = (q.get("q") or [""])[0].strip()
    if not kw:
        return {"error": "缺少 q 参数"}
    kb = _mod("kb_widget")
    A = _mod("advisor_index")
    cat, field, conf = kb.infer_category_field(kw)
    top = min(60, max(5, int((q.get("top") or ["30"])[0] or 30)))
    # 体验端一律只给画像完整的，跟客户端口径一致
    rows = A.recommend(cat, field, "", [], [], [], top=top, complete_only=True)
    try:
        real, real_all = A.field_count(field) if field else (0, 0)
    except Exception:
        real, real_all = 0, 0
    items = []
    for r in rows:
        a = r.get("advisor") or {}
        items.append({
            "name": a.get("name"), "institution": a.get("institution"),
            "province": a.get("province"), "fields": a.get("fields", [])[:4],
            "cited": a.get("cited_by_count", 0), "works": a.get("works_count", 0),
            "orcid": a.get("orcid") or "",
            "score": r.get("score"), "reasons": r.get("reasons", [])[:3],
        })
    return {"query": kw, "category": cat, "field": field,
            "confidence": conf, "field_total": real, "field_total_all": real_all,
            "returned": len(items), "advisors": items}


def api_skills(q):
    rs = _mod("research_skills")
    out = []
    # SKILLS 是 list，每项 {id, name, en, when, goal, steps, output, pitfall}
    for sk in getattr(rs, "SKILLS", []):
        out.append({"id": sk.get("id"), "name": sk.get("name"),
                    "en": sk.get("en"), "when": sk.get("when"),
                    "goal": sk.get("goal"), "steps": sk.get("steps", [])[:8],
                    "output": sk.get("output"), "pitfall": sk.get("pitfall")})
    return {"skills": out}


ROUTES = {
    "/api/ping": lambda q: {"ok": True, "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                            "edition": "web-demo"},
    "/api/overview": api_overview,
    "/api/taxonomy": api_taxonomy,
    "/api/topics": api_topics,
    "/api/gap": api_gap,
    "/api/advisors": api_advisors,
    "/api/skills": api_skills,
}


# ---- HTTP 处理 --------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "KBHelper/1.0"

    def log_message(self, fmt, *args):
        # 默认实现往 stderr 打，GUI 启动时会弹黑窗。这里静默。
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _text(self, s, code=200, ctype="text/plain; charset=utf-8", extra=None):
        body = s.encode("utf-8") if isinstance(s, str) else s
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        ip = self.client_address[0]
        u = urlparse(self.path)
        path = u.path
        if not _rate_ok(ip):
            return self._json({"error": "请求太频繁，歇一分钟再来"}, 429)
        if path in BLOCKED:
            return self._json({"error": BLOCKED[path], "blocked": True}, 403)
        if path in ROUTES:
            try:
                q = parse_qs(u.query)
                return self._json(ROUTES[path](q))
            except Exception as exc:
                traceback.print_exc()
                return self._json({"error": "服务端出错：%s" % exc}, 500)
        if path.startswith("/api/"):
            return self._json({"error": "没有这个接口（体验端只开了 %d 个）"
                                        % len(ROUTES),
                               "available": sorted(ROUTES)}, 404)
        return self._static(path)

    def _static(self, path):
        if path in ("/", ""):
            path = "/index.html"
        name = os.path.normpath(path.lstrip("/")).replace("\\", "/")
        if name.startswith("..") or os.path.isabs(name):
            return self._text("bad path", 400)
        f = STATIC_DIR / name
        if not f.exists() or not f.is_file():
            return self._text("not found", 404)

        # 设计令牌注入：色彩 / 字号 / 圆角来自 design_tokens.py 这一个文件，
        # 桌面端 app_theme.py 也从那里取色。改一处，三端一起变。
        # 把 :root 变量直接写进 <head>，CSS 文件里的兜底值只在注入失败时才生效。
        if name.endswith('.html') or name == 'index.html':
            try:
                raw = f.read_text(encoding="utf-8")
                raw = raw.replace("<!-- DESIGN_TOKENS -->", _token_style())
            except Exception:
                raw = f.read_text(encoding="utf-8")
            return self._text(raw, 200, 'text/html; charset=utf-8',
                              {"Cache-Control": "no-cache"})

        ctype = {".html": "text/html; charset=utf-8",
                 ".js": "application/javascript; charset=utf-8",
                 ".css": "text/css; charset=utf-8",
                 ".svg": "image/svg+xml",
                 ".png": "image/png",
                 ".webp": "image/webp",
                 ".ico": "image/x-icon",
                 # PWA：manifest 必须是 application/manifest+json，
                 # 用 application/json 时部分浏览器会拒绝安装
                 ".webmanifest": "application/manifest+json; charset=utf-8",
                 }.get(f.suffix, "application/octet-stream")
        # Service Worker 必须始终拿最新版本，否则改了 sw.js 浏览器还跑旧的
        extra = {}
        if name.endswith(".js") or name.endswith(".webmanifest"):
            extra["Cache-Control"] = "no-cache"
        self._text(f.read_bytes(), 200, ctype, extra)


def _lan_ip():
    """拿本机在内网里的地址，方便手机扫。拿不到就返回 127.0.0.1。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def serve(host="127.0.0.1", port=8765, quiet=False):
    _import_all()
    httpd = _Server((host, port), Handler)
    httpd.daemon_threads = True
    local = "http://127.0.0.1:%d" % port
    lan = "http://%s:%d" % (_lan_ip(), port)
    if not quiet:
        print("知识库助手 · 网页体验端")
        print("  本机   %s" % local)
        if host == "0.0.0.0":
            print("  手机   %s   （同一 Wi-Fi 下打开）" % lan)
        print("  只读受限：选题 / 文献空白 / 导师 / 图谱 / 方法论；下载与密钥不开放")
        print("  Ctrl+C 停止")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        httpd.server_close()
    return httpd


# ---- 进程内起停（给桌面端的设置页用） ---------------------------------------
_SRV = {"httpd": None, "thread": None, "port": 0, "host": ""}


def start(host="127.0.0.1", port=8765):
    """在当前进程里起一个后台服务线程。返回 (ok, message)。

    桌面上点「启动网页版」走这里，而不是另起一个进程 —— 另起进程要处理
    解释器路径、窗口隐藏、退出时清理，在打包成 exe 之后全都会出问题
    （打包后 sys.executable 是 exe 自己，不是 python）。

    端口被占用时自动往后找一个空端口，而不是直接报错 —— 8765 太容易被
    别的程序占了。
    """
    if _SRV["httpd"] is not None:
        return True, "已经在运行：%s" % _cur_url()
    _import_all()
    last = None
    for p in range(port, port + 20):
        try:
            httpd = _Server((host, p), Handler)
        except OSError as exc:
            last = exc
            continue
        httpd.daemon_threads = True
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        _SRV.update(httpd=httpd, thread=t, port=p, host=host)
        return True, "已启动：%s" % _cur_url()
    return False, "端口 %d–%d 全被占用，换个端口再试（%s）" % (port, port + 19, last)


def stop():
    httpd = _SRV.get("httpd")
    if httpd is None:
        return
    try:
        httpd.shutdown()
        httpd.server_close()
        # server_close() 之后监听 socket 理论上已经关了，但 Windows 上实测
        # 还会有连接留在队列里挂到超时（TimeoutError 而不是连接被拒）。
        # 显式再关一次，代价为零。
        httpd.socket.close()
    except Exception:
        pass
    _SRV.update(httpd=None, thread=None, port=0, host="")


def _cur_url():
    p = _SRV.get("port") or 8765
    return "http://127.0.0.1:%d" % p


def status():
    running = _SRV.get("httpd") is not None
    p = _SRV.get("port") or 0
    return {"running": running,
            "port": p,
            "url": ("http://127.0.0.1:%d" % p) if running else "",
            "lan_url": ("http://%s:%d" % (_lan_ip(), p)) if running else "",
            "routes": len(ROUTES)}


# ---- 命令行入口 -------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="知识库助手 网页体验端")
    ap.add_argument("--host", default="127.0.0.1",
                    help="绑定的地址；想用手机访问填 0.0.0.0")
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    serve(a.host, a.port)


if __name__ == "__main__":
    main()