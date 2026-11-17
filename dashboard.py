#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""知识库助手：本地可视化面板（纯标准库，无依赖）。

用法:
  python dashboard.py            # 启动并自动打开浏览器
  python dashboard.py --no-open  # 只启动服务器（测试用）
  port: 127.0.0.1:8765
"""
import argparse
import datetime
import html
import json
import os
import re
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG_FILE = HERE / "config.json"
KBSCAN = HERE / "kbscan.py"
TASK_NAME = "KB-Monitor-Update"
HOST, PORT = "127.0.0.1", 8765

SCAN_STATE = {"running": False, "last_start": "", "last_end": "", "message": ""}
SCAN_LOCK = threading.Lock()


def _hidden_kwargs():
    if os.name != "nt":
        return {}
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0
    except Exception:
        return {"creationflags": 0x08000000}
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
            "startupinfo": si}


def _decode_output(raw):
    if not raw:
        return ""
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def load_config():
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def kb_root():
    cfg = load_config()
    return Path(cfg.get("kb_path", r"G:\相关内容\AuthorKit27\知识库"))


def inbox_dir():
    return kb_root() / load_config().get("inbox_dir", "新论文")


def task_status():
    try:
        proc = subprocess.run(
            ["schtasks", "/Query", "/FO", "LIST", "/V", "/TN", TASK_NAME],
            capture_output=True, timeout=20, **_hidden_kwargs(),
        )
        raw = proc.stdout
    except Exception:
        return {"name": TASK_NAME, "status": "查询失败", "next_run": "未知"}
    text = ""
    for enc in ("utf-16", "utf-8", "gbk"):
        try:
            candidate = raw.decode(enc)
            if "Status" in candidate or "状态" in candidate or "TaskName" in candidate:
                text = candidate
                break
        except Exception:
            continue
    if not text:
        text = raw.decode("utf-8", "replace")
    text = text.replace("\x00", "").replace("：", ":")
    info = {"name": TASK_NAME, "status": "未注册", "next_run": "未设置"}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key, val = key.strip(), val.strip()
        if key in ("Status", "状态", "计划任务状态"):
            info["status"] = val
        elif key in ("Next Run Time", "下次运行时间"):
            info["next_run"] = val
    return info


def list_digests():
    d = inbox_dir()
    if not d.exists():
        return []
    files = sorted(d.glob("新论文速览-*.md"),
                   key=lambda f: f.stat().st_mtime, reverse=True)
    return [{"name": f.name, "path": str(f), "date": f.stem.split("速览-")[-1]} for f in files]


def changelog_tail(n=30):
    log = inbox_dir() / "更新日志.md"
    if not log.exists():
        return []
    lines = [ln for ln in log.read_text(encoding="utf-8-sig").splitlines() if ln.strip()]
    return lines[-n:]


def kb_stats():
    kb = kb_root()
    total_pdf = sum(1 for p in kb.rglob("*.pdf")) if kb.exists() else 0
    total_txt = sum(1 for p in kb.rglob("*.txt")) if kb.exists() else 0
    return {"total_pdf": total_pdf, "total_txt": total_txt}


def seen_count():
    f = HERE / "seen_ids.json"
    if not f.exists():
        return 0
    try:
        return len(json.loads(f.read_text(encoding="utf-8")))
    except Exception:
        return 0


def md_to_html(text):
    out = []
    in_list = False

    def close_list():
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    for raw in text.splitlines():
        line = html.escape(raw.rstrip())
        if not line.strip():
            close_list()
            continue
        if line.startswith("## "):
            close_list()
            out.append("<h3>" + line[3:] + "</h3>")
        elif line.startswith("# "):
            close_list()
            out.append("<h2>" + line[2:] + "</h2>")
        elif line.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append("<li>" + line[2:] + "</li>")
        elif re.match(r"^\d+\.\s", line):
            close_list()
            out.append("<p class=num>" + re.sub(r"^\d+\.\s", "◆ ", line) + "</p>")
        else:
            close_list()
            out.append("<p>" + line + "</p>")
    close_list()
    return "\n".join(out)


def run_scan(days):
    cmd = [sys.executable, "-X", "utf8", "-u", str(KBSCAN), "--days", str(days)]
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=60 * 30,
                              env=env, **_hidden_kwargs())
        tail = _decode_output(proc.stdout) + _decode_output(proc.stderr)
        lines = [ln for ln in tail.splitlines() if ln.strip()]
        msg = "\n".join(lines[-25:])
    except subprocess.TimeoutExpired:
        msg = "抓取超时（30 分钟），请缩小 days 或手动重试"
    except Exception as exc:
        msg = "抓取失败: " + str(exc)
    with SCAN_LOCK:
        SCAN_STATE.update(running=False, last_end=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), message=msg)


class Handler(BaseHTTPRequestHandler):
    server_version = "KnowledgeHub/0.1"

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False, indent=2), "application/json")

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/?"):
            self._send(200, PAGE_HTML, "text/html")
        elif self.path == "/api/status":
            self._json(status_payload())
        elif self.path.startswith("/api/digest"):
            name = self.path.split("name=", 1)[-1] if "name=" in self.path else ""
            d = inbox_dir() / name if name else (inbox_dir() / (list_digests() or [{"name": ""}])[0]["name"])
            if d.exists() and d.is_file():
                self._json({"name": d.name, "html": md_to_html(d.read_text(encoding="utf-8-sig"))})
            else:
                self._json({"html": "<p>暂无速览。点击「立即抓取」或等待周日任务。</p>"})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8", "replace") if length else "{}"
        try:
            payload = json.loads(body) if body else {}
        except Exception:
            payload = {}
        if self.path == "/api/scan":
            with SCAN_LOCK:
                if SCAN_STATE["running"]:
                    self._json({"ok": False, "msg": "已有一个抓取任务在运行"})
                    return
                SCAN_STATE.update(running=True, last_start=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                                  last_end="", message="正在抓取…")
            days = int(payload.get("days", load_config().get("days_back", 7)))
            threading.Thread(target=run_scan, args=(days,), daemon=True).start()
            self._json({"ok": True, "msg": "抓取已在后台启动"})
        elif self.path == "/api/open":
            key = payload.get("target", "")
            targets = {
                "inbox": inbox_dir(),
                "kb": kb_root(),
                "monitor": HERE,
            }
            p = targets.get(key)
            if p and p.exists():
                os.startfile(str(p))
                self._json({"ok": True})
            else:
                self._json({"ok": False, "msg": "目录不存在"})
        else:
            self._json({"ok": False, "error": "not found"}, 404)


def status_payload():
    cfg = load_config()
    digests = list_digests()
    with SCAN_LOCK:
        scan = dict(SCAN_STATE)
    return {
        "now": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "task": task_status(),
        "kb": kb_stats(),
        "seen": seen_count(),
        "queries": len(cfg.get("queries", [])),
        "days_back": cfg.get("days_back", 7),
        "digests": digests[:8],
        "latest_digest": digests[0]["name"] if digests else "",
        "changelog": changelog_tail(),
        "scan": scan,
        "dirs": {"inbox": str(inbox_dir()), "kb": str(kb_root())},
    }


PAGE_HTML = r"""<!doctype html>
<html lang=zh>
<head>
<meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>知识库助手</title>
<style>
:root{--bg:#0f1420;--card:#171e2e;--line:#263049;--txt:#e6ebf5;--mut:#8b96ad;--acc:#4f8cff;--ok:#3ddc97;--warn:#ffb454}
*{box-sizing:border-box}body{margin:0;font-family:"Microsoft YaHei",system-ui,sans-serif;background:var(--bg);color:var(--txt)}
.wrap{max-width:1080px;margin:0 auto;padding:22px 18px 80px}
h1{font-size:22px;margin:0 0 4px}h1 small{color:var(--mut);font-weight:400;font-size:13px;margin-left:10px}
.sub{color:var(--mut);font-size:13px;margin-bottom:18px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.card .k{font-size:12px;color:var(--mut)}.card .v{font-size:20px;font-weight:700;margin-top:4px;word-break:break-all}
.card .v.s{font-size:14px}
.row{display:flex;gap:10px;flex-wrap:wrap;margin:18px 0}
button{background:var(--acc);color:#fff;border:0;border-radius:9px;padding:9px 16px;font-size:14px;cursor:pointer}
button.ghost{background:transparent;border:1px solid var(--line);color:var(--txt)}
button:disabled{opacity:.55;cursor:not-allowed}
.panel{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin-top:14px}
.panel h2{font-size:15px;margin:0 0 10px;color:var(--acc)}
.panel h3{font-size:14px;margin:16px 0 6px}.panel h2:first-child{margin-top:0}
.panel ul{margin:6px 0;padding-left:20px;line-height:1.7}
.panel p{line-height:1.7;margin:6px 0;font-size:13.5px}
.panel p.num{color:var(--warn)}
pre{background:#0b1018;border:1px solid var(--line);border-radius:10px;padding:12px;overflow:auto;font-size:12px;color:var(--mut);line-height:1.5;white-space:pre-wrap}
.muted{color:var(--mut)}
.pills{display:flex;gap:6px;flex-wrap:wrap}.pill{border:1px solid var(--line);border-radius:999px;padding:2px 10px;font-size:12px;color:var(--mut)}
dialog{background:var(--card);color:var(--txt);border:1px solid var(--line);border-radius:12px;padding:18px;max-width:520px}
</style>
</head>
<body>
<div class=wrap>
<h1>知识库助手 <small>RGB-T / 多模态检测 · 文献情报</small></h1>
<div class=sub id=now></div>
<div class=grid id=cards></div>
<div class=row>
<button id=scan onclick=scan()>立即抓取新论文</button>
<button class=ghost onclick=fetchDigest()>刷新</button>
<button class=ghost onclick=openDir("inbox")>打开新论文目录</button>
<button class=ghost onclick=openDir("kb")>打开知识库</button>
<button class=ghost onclick=openDir("monitor")>打开监控目录</button>
</div>
<div id=scanmsg class=card style="display:none"></div>
<div class=panel><h2>最新一期《新论文速览》</h2><p class=muted id=digestmeta></p><div id=digest></div></div>
<div class=panel><h2>最近更新日志</h2><pre id=log></pre></div>
</div>
<dialog id=dlg><h2>抓取结果</h2><pre id=dlgbody></pre><div style=margin-top:12px><button onclick=document.getElementById("dlg").close()>关闭</button></div></dialog>
<script>
async function api(u,opt){const r=await fetch(u,opt);return r.json()}
function el(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e}
function pad(s){return String(s).padStart(2,"0")}
async function load(){
  const s=await api("/api/status");
  document.getElementById("now").textContent="更新于 "+s.now+" · 下次计划任务: "+(s.task.next_run||"未设置")+" · 任务状态: "+s.task.status;
  const cards=[["知识库 PDF",s.kb.total_pdf],["已跟踪 arXiv 论文",s.seen],["本周速览","<span class=pills>"+s.digests.length+" 期</span>"],["检索关键词组",s.queries],["抓取窗口","近 "+s.days_back+" 天"],["最近速览",s.latest_digest||"—"]];
  const g=document.getElementById("cards");g.innerHTML="";
  cards.forEach(c=>{const d=el("div","card");d.appendChild(el("div","k",c[0]));const v=el("div","v "+(String(c[1]).length>18?"s":""));v.innerHTML=c[1];d.appendChild(v);g.appendChild(d)});
  document.getElementById("log").textContent=(s.changelog&&s.changelog.length?s.changelog.join("\n"):"暂无日志");
  const sm=document.getElementById("scanmsg");
  if(s.scan.running){sm.style.display="block";sm.textContent="⏳ "+s.scan.message;document.getElementById("scan").disabled=true}
  else{document.getElementById("scan").disabled=false;if(s.scan.message){sm.style.display="block";sm.textContent=s.scan.message}else{sm.style.display="none"}}
  await fetchDigest();
}
async function fetchDigest(){
  const s=await api("/api/status");
  const name=s.latest_digest||"";
  const r=await api("/api/digest"+(name?"?name="+encodeURIComponent(name):""));
  document.getElementById("digestmeta").textContent=name?("文件: "+name):"暂无";
  document.getElementById("digest").innerHTML=r.html||"<p class=muted>暂无速览，点击「立即抓取」生成。</p>";
}
async function scan(){
  const r=await api("/api/scan",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});
  const d=document.getElementById("dlg");d.querySelector("pre").textContent=r.msg;d.showModal();await load();
}
async function openDir(k){await api("/api/open",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({target:k})})}
load();setInterval(load,30000);
</script>
</body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--port", type=int, default=PORT)
    args = ap.parse_args()
    try:
        server = ThreadingHTTPServer((HOST, args.port), Handler)
    except OSError:
        webbrowser.open("http://%s:%d" % (HOST, args.port))
        print("端口被占用，已打开已有实例")
        return 0
    url = "http://%s:%d" % (HOST, args.port)
    print("知识库助手已启动: " + url)
    if not args.no_open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
