# -*- coding: utf-8 -*-
"""网页体验端端到端测试：真起一个 HTTP 服务，真发请求。

不用 requests（不想加依赖），直接 urllib。测的是**网络层**，不是函数层——
上一轮 `web_server` 的函数单独调没问题，但路由、编码、静态文件全没验证过。

    python tools_test_web.py
"""
import json
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import web_server as W  # noqa: E402

PASS = []
FAIL = []


def check(name, fn):
    try:
        fn()
        PASS.append(name)
        print("  ok   %s" % name)
    except Exception as exc:
        FAIL.append((name, exc))
        print("  FAIL %s -> %s" % (name, exc))


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


PORT = free_port()
BASE = "http://127.0.0.1:%d" % PORT
_server = None


def start():
    global _server
    W._import_all()
    from http.server import ThreadingHTTPServer
    _server = ThreadingHTTPServer(("127.0.0.1", PORT), W.Handler)
    _server.daemon_threads = True
    t = threading.Thread(target=_server.serve_forever, daemon=True)
    t.start()
    for _ in range(100):
        try:
            urllib.request.urlopen(BASE + "/api/ping", timeout=1).read()
            return
        except Exception:
            time.sleep(0.05)
    raise RuntimeError("服务没起来")


def stop():
    """停掉自建的测试服务器。

    2026-11-14 实测：只调 server_close() 不够——连接在 listen 队列里排着时不会被拒，
    请求会一直挂白直到超时（表现为 urllib 超时而不是 URLError）。
    必须把实体已经建立的 socket 也关掉。
    """
    global _server
    if _server:
        srv, _server = _server, None
        srv.shutdown()
        srv.server_close()
        try:
            srv.socket.close()
        except Exception:
            pass


def get(path, expect=200):
    try:
        r = urllib.request.urlopen(BASE + path, timeout=30)
        return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def jget(path, expect=200):
    code, body = get(path)
    assert code == expect, "期望 %d 得到 %d：%s" % (expect, code, body[:200])
    return json.loads(body)


# ---------------------------------------------------------------- 用例
def t_ping():
    d = jget("/api/ping")
    assert d["ok"] is True
    assert d["edition"] == "web-demo"


def t_static_index():
    code, body = get("/")
    assert code == 200
    assert "知识库助手" in body
    assert 'id="out"' in body


def t_static_css():
    code, body = get("/style.css")
    assert code == 200
    assert "--accent" in body
    assert "@media (max-width: 860px)" in body, "移动端断点丢了"


def t_theme_injected():
    """设计令牌必须真的注入到 HTML 里。

    :root 变量写进 <head> 后，CSS 文件里的兜底值才不会被用到。
    注入一旦静默失败（比如模板占位符改了名字），页面照样能打开、
    只是颜色悄悄退回兜底值 —— 这种退化没有任何报错，只能靠断言拦。
    """
    import design_tokens as DT
    code, body = get("/")
    assert code == 200
    # 品牌色必须来自 design_tokens，而不是 CSS 文件里写死的旧值
    assert DT.COLORS["primary"] in body, "主色没有注入"
    assert DT.COLORS["canvas"] in body, "底色没有注入"
    # 注入块必须排在样式表之前，否则会被 style.css 的 :root 覆盖
    i_style = body.find("<style>")
    i_link = body.find("rel=\"stylesheet\"")
    assert i_style >= 0, "没有注入 <style> 块"
    assert i_link < 0 or i_style < i_link, "令牌必须注入在样式表之前"
    # 2026-11-14 换成灰阶双调色板后，品牌色本身就是 GitHub 蓝（#2f81f7/浅色 #0969da），
    # 不能再把它们当“旧配色”排除。真正要拦的是原来那套深空蓝的壳子色。
    for old in ("#0d1117", "#161b22", "#6be7ff"):
        assert old not in body.lower(), "旧配色 %s 还在" % old


def t_static_js():
    code, body = get("/app.js")
    assert code == 200
    assert "renderTopics" in body
    # 安全：不允许用 innerHTML 拼数据。
    # 先剥掉注释再查——注释里解释「为什么不用 innerHTML」不算违规。
    import re
    code_only = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
    code_only = re.sub(r"(?m)^\s*//.*$", "", code_only)
    assert ".innerHTML" not in code_only, "app.js 的可执行代码里用了 innerHTML，有注入风险"


def t_static_404():
    code, _ = get("/nope.html")
    assert code == 404


def t_path_traversal():
    """`/../kb_widget.py` 必须被挡住，不能读到源码。"""
    code, _ = get("/../kb_widget.py")
    assert code in (400, 404), "路径穿越没被挡住：%d" % code


def t_overview():
    d = jget("/api/overview")
    assert d["papers"] > 0, "论文数为 0"
    assert d["advisors"] >= 1000, "学者数太少：%s" % d["advisors"]
    assert d["institutions"] > 0


def t_taxonomy():
    d = jget("/api/taxonomy")
    assert d["total"] > 0
    assert len(d["categories"]) >= 5
    c0 = d["categories"][0]
    assert "category" in c0 and isinstance(c0["fields"], list)
    assert "name" in c0["fields"][0], "方向结构不对"


def t_topics():
    d = jget("/api/topics?direction=%s&limit=5" % urllib.request.quote("红外小目标检测"))
    assert d["candidates"], "没生成候选"
    c = d["candidates"][0]
    for k in ("title", "reason", "score"):
        assert k in c, "候选缺字段 %s" % k
    assert c["score"] > 0


def t_topics_reason_diverse():
    """18 个候选的理由不能全是同一句模板 —— 这是 v2 生成器的核心卖点。"""
    d = jget("/api/topics?direction=%s&limit=18" % urllib.request.quote("目标检测"))
    reasons = {c.get("reason") for c in d["candidates"]}
    assert len(reasons) >= 8, "理由只有 %d 种，疑似退回模板" % len(reasons)


def t_topics_missing_param():
    d = jget("/api/topics", expect=200)
    assert "error" in d


def t_gap():
    d = jget("/api/gap?direction=%s" % urllib.request.quote("红外小目标检测"))
    assert d["total"] > 0, "库里没匹配到论文"
    assert d["methods"], "方法分布为空"
    assert d["tasks"], "任务分布为空"
    assert len(d["combos"]) > 0


def t_gap_unknown_direction():
    d = jget("/api/gap?direction=%s" % urllib.request.quote("完全不存在的方向xyz"))
    assert d["total"] == 0
    assert d["methods"] == []


def t_advisors():
    d = jget("/api/advisors?q=%s&top=10" % urllib.request.quote("单目深度估计"))
    assert d["returned"] > 0
    a = d["advisors"][0]
    for k in ("name", "institution", "score"):
        assert k in a, "导师缺字段 %s" % k
    assert d["field_total"] >= 1


def t_advisors_has_orcid_somewhere():
    d = jget("/api/advisors?q=%s&top=40" % urllib.request.quote("目标检测"))
    assert any(x.get("orcid") for x in d["advisors"]), "40 位里没有一个有 ORCID，画像口径可能被改坏"


def t_skills():
    d = jget("/api/skills")
    assert len(d["skills"]) == 7, "方法步骤数变了：%d" % len(d["skills"])
    s = d["skills"][0]
    for k in ("id", "name", "steps", "pitfall"):
        assert k in s, "技能缺字段 %s" % k


def t_blocked_download():
    code, body = get("/api/download")
    assert code == 403, "下载接口没被挡住：%d" % code
    d = json.loads(body)
    assert d.get("blocked") is True
    assert "磁盘" in d["error"]


def t_blocked_llm():
    code, body = get("/api/llm")
    assert code == 403
    assert json.loads(body).get("blocked") is True


def t_blocked_profile():
    code, body = get("/api/profile")
    assert code == 403
    assert json.loads(body).get("blocked") is True


def t_blocked_library():
    code, body = get("/api/library?q=test")
    assert code == 403


def t_unknown_api():
    code, body = get("/api/whatever")
    assert code == 404
    d = json.loads(body)
    assert "available" in d, "404 没告诉用户有哪些接口"


def t_allowed_table_matches_routes():
    """ALLOWED 表里登记了但 ROUTES 里没有（或反之），说明接口表被改乱了。"""
    declared = set(W.ALLOWED)
    actual = set(W.ROUTES)
    assert declared == actual, "登记不一致：只在ALLOWED %s / 只在ROUTES %s" % (
        declared - actual, actual - declared)


def t_no_secret_leak():
    """任何接口的响应里都不能出现 sk- 开头的密钥。"""
    for path in ("/api/overview", "/api/taxonomy", "/api/skills"):
        code, body = get(path)
        assert "sk-" not in body, "%s 泄露了疑似密钥" % path


def t_concurrent():
    """8 个并发请求不能把服务搞崩（ThreadingHTTPServer + 共享缓存）。"""
    results = []
    lock = threading.Lock()

    def one(i):
        try:
            d = jget("/api/topics?direction=%s&limit=3" % urllib.request.quote("目标检测"))
            ok = bool(d.get("candidates"))
        except Exception:
            ok = False
        with lock:
            results.append(ok)

    ts = [threading.Thread(target=one, args=(i,)) for i in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(60)
    assert all(results), "并发下失败 %d/8" % results.count(False)


def t_inprocess_start_stop():
    """设置页里点「启动网页版」走的是 web_server.start()，不是另起进程。
    这条路径必须能起来、能停、能重复调用不炸。"""
    W.stop()
    ok, msg = W.start(port=8801)
    assert ok, "启动失败：%s" % msg
    try:
        time.sleep(0.3)
        d = json.loads(urllib.request.urlopen(
            "http://127.0.0.1:8801/api/ping", timeout=5).read().decode("utf-8"))
        assert d["ok"] is True
        ok2, msg2 = W.start(port=8801)
        assert ok2 and "已经在运行" in msg2, "重复启动没被识别：%s" % msg2
    finally:
        W.stop()
    time.sleep(0.3)
    assert W.status()["running"] is False
    # 停下来之后，连接应该被直接拒绝。
    # 2026-11-14 实测：只关 serve_forever + socket，Windows 上已建立的 keep-alive 连接
    # 不会被切断，下一个请求会一直挂着直到超时（TimeoutError）而不是 URLError。
    # 但“停了还能访问”和“停了但连接挂着”在用户看来是一回事，两种都不允许请求成功。
    # 为了不让测试挂 2 秒，超时取 1 秒。
    try:
        urllib.request.urlopen("http://127.0.0.1:8801/api/ping", timeout=1)
        raise AssertionError("stop() 之后服务还在响应")
    except urllib.error.URLError:
        pass
    except TimeoutError:
        pass


def t_port_fallback():
    """8765 被别的程序占用时，要自动往后找空端口而不是直接失败。

    在 Windows 上这条测试真正防的是 SO_REUSEADDR：它允许绑到已被占用的端口，
    于是「回退」永远不触发，两个服务抢同一端口、请求随机落到其中一个。
    """
    W.stop()
    blocker = socket.socket()
    blocker.bind(("127.0.0.1", 8802))
    blocker.listen(1)
    try:
        ok, msg = W.start(port=8802)
        assert ok, "端口被占时没有回退：%s" % msg
        assert W.status()["port"] != 8802, "居然绑上了被占用的端口"
    finally:
        W.stop()
        blocker.close()


def t_btn_disabled_not_clickable():
    """Btn 是 Label 子类，state='disabled' 默认只锁文字、不锁点击。
    构造时 disabled 的按钮必须点不动，否则「变灰但还能点」。"""
    import tkinter as tk
    import app_theme as T
    root = tk.Tk()
    root.withdraw()
    try:
        hit = []
        b = T.Btn(root, "test", lambda: hit.append(1), "ghost", state="disabled")
        b.invoke()
        assert not hit, "disabled 按钮被 invoke 触发了"
        assert b._cmd is None, "disabled 按钮还留着回调"
        b2 = T.Btn(root, "test2", lambda: hit.append(2), "ghost")
        b2.invoke()
        assert hit == [2], "普通按钮 invoke 失效"
        fg_before = b2.cget("fg")
        b2.enable(False)
        b2.enable(True)
        assert b2.cget("fg") == fg_before, "enable 之后前景色没还原"
        b2.invoke()
    finally:
        root.destroy()


def main():
    print("启动测试服务 %s" % BASE)
    start()
    try:
        print("\n[接口]")
        for fn in (t_ping, t_overview, t_taxonomy, t_topics, t_topics_reason_diverse,
                   t_topics_missing_param, t_gap, t_gap_unknown_direction,
                   t_advisors, t_advisors_has_orcid_somewhere, t_skills):
            check(fn.__name__, fn)
        print("\n[静态文件]")
        for fn in (t_static_index, t_static_css, t_static_js,
                   t_static_404, t_path_traversal, t_theme_injected):
            check(fn.__name__, fn)
        print("\n[受限白名单]")
        for fn in (t_blocked_download, t_blocked_llm, t_blocked_profile,
                   t_blocked_library, t_unknown_api, t_allowed_table_matches_routes):
            check(fn.__name__, fn)
        print("\n[健壮性]")
        for fn in (t_no_secret_leak, t_concurrent):
            check(fn.__name__, fn)
        print("\n[设置页集成]")
        for fn in (t_inprocess_start_stop, t_port_fallback,
                   t_btn_disabled_not_clickable):
            check(fn.__name__, fn)
    finally:
        stop()

    print("\n通过 %d / 失败 %d" % (len(PASS), len(FAIL)))
    if FAIL:
        for n, e in FAIL:
            print("  FAIL %s: %s" % (n, e))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())