# -*- coding: utf-8 -*-
"""验证 PWA 资源与二维码入口。

不靠肉眼看：起真服务，用 urllib 拿每个资源，检查状态码 / Content-Type /
关键内容，再调 web_server.start 从设置页的角度跑一遍。
"""
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

import tools_isolate  # noqa: E402

ISO = tools_isolate.isolate()

import web_server as W  # noqa: E402

OK = []
BAD = []


def check(name, fn):
    try:
        fn()
        OK.append(name)
        print("  PASS  " + name)
    except Exception as e:
        BAD.append((name, str(e)))
        print("  FAIL  %s  -> %s" % (name, e))


BASE = [""]


def get(path):
    with urllib.request.urlopen(BASE[0].rstrip("/") + path, timeout=20) as r:
        return r.status, r.headers.get("Content-Type", ""), r.read()


def t_manifest():
    st, ct, body = get("/manifest.webmanifest")
    assert st == 200, "状态码 %s" % st
    assert "manifest+json" in ct, "Content-Type 错误：%s" % ct
    d = json.loads(body.decode("utf-8"))
    assert d["name"] and d["short_name"], "缺 name"
    assert d["display"] == "standalone", "display 应为 standalone"
    assert d["theme_color"] == "#061220", "theme_color 应与设计令牌一致"
    assert len(d["icons"]) >= 2, "图标至少两个尺寸"
    assert any(i.get("purpose") == "maskable" for i in d["icons"]), "缺 maskable 图标"


def t_icons():
    for name in ("icon-192.png", "icon-512.png", "icon-maskable.png"):
        st, ct, body = get("/" + name)
        assert st == 200, "%s 状态 %s" % (name, st)
        assert ct.startswith("image/png"), "%s 类型 %s" % (name, ct)
        assert body[:8] == b"\x89PNG\r\n\x1a\n", "%s 不是 PNG" % name


def t_sw():
    st, ct, body = get("/sw.js")
    assert st == 200, "状态码 %s" % st
    src = body.decode("utf-8")
    assert "javascript" in ct, "类型 %s" % ct
    assert "/api/" in src and "startsWith" in src, "SW 必须跳过 /api/"
    assert "cache" in src.lower(), "应使用 Cache API"


def t_index():
    st, ct, body = get("/")
    html = body.decode("utf-8")
    assert st == 200 and "text/html" in ct
    assert 'rel="manifest"' in html, "index 未声明 manifest"
    assert "apple-touch-icon" in html, "iOS 需要 apple-touch-icon"
    assert "serviceWorker" in html, "未注册 service worker"


H = {}

try:
    ok, msg = W.start(port=8899)
    assert ok, "启动失败：" + msg
    BASE[0] = W.status()["url"]
    print("服务：", BASE[0])

    print("\n== PWA ==")
    check("manifest 内容与类型正确", t_manifest)
    check("三个图标都是真 PNG", t_icons)
    check("service worker 可下载且不缓存接口", t_sw)
    check("index 声明了 manifest / 图标 / SW", t_index)

    print("\n== 二维码 ==")

    def t_qr_roundtrip():
        import tools_test_qr
        import qrtool
        url = W.status()["lan_url"]
        assert url.startswith("http://"), "局域网地址异常：" + url
        m, size = qrtool.build(url)
        assert tools_test_qr.decode(m) == url, "二维码解出来的不是原地址"

    check("局域网地址能编成可解码的二维码", t_qr_roundtrip)

    def t_qr_svg():
        import qrtool
        svg = qrtool.to_svg("http://192.168.1.2:8765/")
        assert svg.startswith("<svg"), "SVG 头不对"
        assert "</svg>" in svg and "path" in svg

    check("SVG 输出结构正确", t_qr_svg)

    def t_qr_many():
        import qrtool
        import tools_test_qr
        for n in (12, 20, 40, 80, 150):
            txt = "http://192.168.88.230:8765/" + "x" * n
            m, size = qrtool.build(txt)
            got = tools_test_qr.decode(m)
            assert got == txt, "长度 %d 往返失败" % n

    check("不同长度的地址都能往返", t_qr_many)

    def t_qr_capacity():
        import qrtool
        try:
            qrtool.build("x" * 4000)
            raise AssertionError("超长内容应当报错而不是静默截断")
        except ValueError:
            pass

    check("超长内容明确报错", t_qr_capacity)

    print("\n== 设置页 ==")

    def t_settings_qr():
        import tkinter as tk
        from app_main import App
        root = App()
        root.geometry("1320x860+20+20")
        for _ in range(20):
            root.update()
        root.goto("settings")
        for _ in range(20):
            root.update()
        pg = root.pages["settings"]
        assert hasattr(pg, "_toggle_qr"), "设置页没有二维码入口"
        pg._qr_show()
        for _ in range(10):
            root.update()
        n = len(pg._qr_canvas.find_all())
        assert n > 40, "二维码图形太少（%d），可能没画出来" % n
        assert pg._qr_open is True
        pg._qr_hide()
        for _ in range(6):
            root.update()
        assert pg._qr_open is False
        assert not pg._qr_box.winfo_ismapped(), "收起后仍占位"
        root.destroy()

    check("设置页能显示/收起二维码", t_settings_qr)

    print("\n== 二级窗口 ==")

    def t_child_windows():
        import tkinter as tk
        from app_main import App
        root = App()
        root.geometry("1320x860+20+20")
        for _ in range(20):
            root.update()

        def find_tops():
            found = []
            seen = set()

            def walk(w):
                if id(w) in seen:
                    return
                seen.add(id(w))
                for c in w.winfo_children():
                    if isinstance(c, tk.Toplevel):
                        found.append(c)
                    walk(c)
            for w in root.winfo_children():
                if isinstance(w, tk.Toplevel):
                    found.append(w)
                walk(w)
            return found

        tp = root.page("topic")
        tp.show_help()
        for _ in range(8):
            root.update()
        wins = [w for w in find_tops() if w.title() == "选题方法论"]
        assert wins, "没弹出窗口"
        w = wins[-1]
        assert w.transient(), "二级窗口必须 transient，否则主窗口最小化后它不跟着走"
        assert w.bind("<Escape>"), "二级窗口要能用 Esc 关"
        # 切页后自动收掉
        root.goto("mentor")
        for _ in range(8):
            root.update()
        left = [x for x in find_tops() if x.title() == "选题方法论"]
        assert not left, "离开页面后二级窗口还在（%d 个）" % len(left)
        root.destroy()

    check("二级窗口 transient + Esc + 切页自动关闭", t_child_windows)

finally:
    W.stop()
    tools_isolate.cleanup(ISO.get("__tmp__"))

print("\n通过 %d / 失败 %d" % (len(OK), len(BAD)))
sys.exit(0 if not BAD else 1)