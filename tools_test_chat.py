# -*- coding: utf-8 -*-
"""大模型接入与对话的离线自检（不需要真 Key、不联网）。

测什么
------
真正接上 API 之后最容易坏的不是"能不能连"，而是这几件事：
  1. 提示词里到底有没有把「我的情况」发出去（画像注入）
  2. 多轮对话的历史有没有带上（不带就退化成单轮）
  3. 没配模型时界面能不能降级（不能降级就是一整块死 UI）
  4. 密钥会不会被写进日志/导出/记忆（泄漏）
  5. 上下文过长时怎么截断（截尾还是截头，关系到模型还记不记得结论）

做法
----
把 `llm_bridge.chat` 换成一个假的，它只记录收到的 messages，
这样上面五件事全部可以离线断言。最后再用一个本地起的假 OpenAI 兼容
服务跑一次真实的 HTTP 往返，验证 chat() 的解析与错误处理。
"""
import io
import json
import os
import shutil
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import tools_isolate

_HERE = Path(__file__).resolve().parent

tools_isolate.isolate()          # 先隔离，避免写坏用户真实数据

import app_theme as T            # noqa: E402
import chat_panel as CP          # noqa: E402
import dialog as D               # noqa: E402
import llm_bridge as L           # noqa: E402
import prompt_context as PC      # noqa: E402

PASS, FAIL = [], []
SENT = []                        # 假 chat 收到的 messages


def ok(name):
    PASS.append(name)
    print("  [ok]   " + name)


def bad(name, why):
    FAIL.append((name, why))
    print("  [FAIL] %s —— %s" % (name, why))


def check(name, cond, why=""):
    ok(name) if cond else bad(name, why)


# ------------------------------------------------------------------ 假模型
def fake_chat(messages, cfg=None, max_tokens=900, json_mode=False):
    SENT.append(messages)
    return "好的，这是第 %d 轮的回答。" % len(SENT)


def _cfg():
    return {"provider": "custom", "base_url": "http://127.0.0.1:9/v1",
            "model": "fake", "api_key": "sk-test-1234567890",
            "enabled": True, "temperature": 0.3, "timeout": 5}


# ================================================================ 1 对话构造
def t_build():
    msgs = D.build_messages([], "红外小目标检测怎么做")
    check("没有历史时只有 system + 本轮",
          len(msgs) == 2 and msgs[0]["role"] == "system"
          and msgs[1]["content"] == "红外小目标检测怎么做",
          str([m["role"] for m in msgs]))

    hist = [{"role": "user", "content": "问1"},
            {"role": "assistant", "content": "答1"},
            {"role": "user", "content": "问2"},
            {"role": "assistant", "content": "答2"}]
    msgs = D.build_messages(hist, "问3")
    check("历史按原顺序带上",
          [m["content"] for m in msgs[1:]] == ["问1", "答1", "问2", "答2", "问3"],
          str([m["content"] for m in msgs[1:]]))

    many = [{"role": "user" if i % 2 == 0 else "assistant", "content": "第%d条" % i}
            for i in range(40)]
    msgs = D.build_messages(many, "最新一句")
    check("历史只保留最近 %d 条" % D.MAX_HISTORY,
          len(msgs) - 2 == D.MAX_HISTORY, "得到 %d 条" % (len(msgs) - 2))
    check("截断保留的是最近几条",
          msgs[1]["content"] == "第%d条" % (40 - D.MAX_HISTORY),
          msgs[1]["content"])

    long_msg = "结论在第一句。" + "废话" * 2000
    msgs = D.build_messages([{"role": "assistant", "content": long_msg}], "继续")
    body = msgs[1]["content"]
    check("超长消息被截断且保留开头",
          len(body) <= D.MAX_CHARS + 1 and body.startswith("结论在第一句。"),
          "长度 %d" % len(body))

    msgs = D.build_messages([{"role": "weird", "content": "x"}], "y")
    check("非法角色一律当成 user", msgs[1]["role"] == "user", msgs[1]["role"])

    msgs = D.build_messages([{"role": "user", "content": "   "}], "y")
    check("空白历史被丢掉", len(msgs) == 2, str(len(msgs)))


# ================================================================ 2 画像注入
def t_ctx():
    empty = D.build_messages([], "hi")[0]["content"]
    check("画像为空时 system 与通用模板逐字一致", empty == D._SYS)

    ctx = PC.block({"identity": {"school": "某大学", "stage": "硕士二年级"},
                    "state": {"urgency": 88, "mood": "焦虑"},
                    "prefs": {"fields": {"红外小目标检测": 5.0}}},
                   {"compute": "单卡 RTX 3090", "avoid": ["三维重建"]},
                   [{"text": "组会要报进度"}], want="task")
    check("画像段包含身份", "某大学" in ctx and "硕士二年级" in ctx)
    check("画像段包含紧迫度", "离截止很近" in ctx, ctx[:80])
    check("画像段包含硬约束", "单卡 RTX 3090" in ctx and "三维重建" in ctx)
    check("画像段包含关注方向", "红外小目标检测" in ctx)
    check("画像段包含最近记录", "组会要报进度" in ctx)

    sysmsg = D.build_messages([], "hi", ctx)[0]["content"]
    check("system 里真的带上了画像", "单卡 RTX 3090" in sysmsg and D._SYS in sysmsg)
    check("画像要求不复述个人信息", "不要复述" in sysmsg or "不复述" in ctx)

    low = PC.block({"prefs": {"fields": {"只看过一次": 1.0}}})
    check("权重不足的方向不算偏好", "只看过一次" not in low, low)


# ================================================================ 3 多轮往返
def t_rounds():
    global SENT
    SENT = []
    real = L.chat
    L.chat = fake_chat
    try:
        turns = []
        oks = []
        for i, q in enumerate(["第一句", "第二句", "第三句"]):
            good, txt = D.reply(turns, q, cfg=_cfg())
            oks.append(good)
            turns.append({"role": "user", "content": q})
            turns.append({"role": "assistant", "content": txt})
        check("三轮都成功", all(oks), str(oks))
        check("每轮都把完整历史带上",
              [len(m) for m in SENT] == [2, 4, 6],
              str([len(m) for m in SENT]))
        check("第二轮能看到第一轮的话",
              any(m["content"] == "第一句" for m in SENT[1]),
              str(SENT[1]))
        check("模型回复被原样收进历史", turns[1]["content"].startswith("好的"),
              turns[1]["content"])
    finally:
        L.chat = real


# ================================================================ 4 失败路径
def t_fail():
    real = L.chat

    def boom(messages, cfg=None, max_tokens=900, json_mode=False):
        raise L.LLMError("HTTP 401：invalid api key")

    L.chat = boom
    try:
        good, txt = D.reply([], "x", cfg=_cfg())
        check("接口报错时返回 (False, 错误原文) 而不抛异常",
              (good is False) and "401" in txt, txt)
    finally:
        L.chat = real

    real_r = L.is_ready
    L.is_ready = lambda cfg=None: False
    try:
        good, txt = D.reply([], "x")
        check("没配模型时也返回失败而不是抛异常", good is False and txt, txt)
    finally:
        L.is_ready = real_r

    good, txt = D.reply([], "   ", cfg=_cfg())
    check("空输入直接被挡下", good is False)

    real_c = L.chat
    L.chat = lambda *a, **k: ""
    try:
        good, txt = D.reply([], "x", cfg=_cfg())
        check("模型返回空串算失败", good is False and "空" in txt, txt)
    finally:
        L.chat = real_c


# ================================================================ 5 密钥不泄漏
def t_secret():
    secret = _cfg()["api_key"]
    sysmsg = D.build_messages([], "我的密钥是 sk-abc", D.build_messages([], "x")[0]["content"])[0]["content"]
    check("system 提示里不含密钥", secret not in sysmsg)

    md = D.export_markdown([{"role": "user", "content": "问"},
                            {"role": "assistant", "content": "答"}], "测试")
    check("导出 Markdown 不含密钥", secret not in md and "**我**" in md and "**助手**" in md,
          md[:80])

    # 这一组要验证「配置里确实有密钥 / status() 打码 / ready 判定」。
    # **必须在隔离后的临时配置上做**：llm_config.json 装的是用户真实密钥，
    # 早先版本在 finally 里 `os.remove(L.CONFIG_FILE)`，一旦隔离没生效
    # （比如 llm_bridge 在 isolate() 之前就被导入），跑一次测试就把用户的
    # 密钥文件删掉了 —— 真发生过。这里改成先备份内容、只在临时配置上操作，
    # 最后恢复原样，并且无论如何都不删真实文件。
    real_cfg = Path(getattr(L, "CONFIG_FILE", ""))
    is_real = str(real_cfg).startswith(str(_HERE))
    had = os.path.exists(L.CONFIG_FILE)
    backup = None
    if had:
        with io.open(L.CONFIG_FILE, encoding="utf-8") as f:
            backup = f.read()
    try:
        L.save_config(_cfg())
        st = L.status()
        dump = json.dumps(st, ensure_ascii=False)
        check("配置里确实有密钥（否则这条测试什么都没测到）",
              secret in json.dumps(L.load_config(), ensure_ascii=False))
        check("status() 里的密钥是打码的", secret not in dump and "…" in (st.get("key") or ""),
              dump[:120])
        check("status() 认得出这是可用配置", st.get("ready") is True, dump[:80])
    finally:
        if had and backup is not None:
            with io.open(L.CONFIG_FILE, "w", encoding="utf-8") as f:
                f.write(backup)
        elif not had:
            # 原来这里无条件 os.remove(L.CONFIG_FILE)。只要隔离没生效，
            # 跑一次测试就把用户的真实密钥文件删了 —— 真发生过一次。
            # 现在：只有确认是临时目录里的配置才删，真实目录一律不碰。
            if not is_real:
                try:
                    os.remove(L.CONFIG_FILE)
                except OSError:
                    pass
    check("测试后没有留下假的 llm_config.json", os.path.exists(L.CONFIG_FILE) == had)

    check("mask 只露前4后4", L.mask(secret) == secret[:4] + "…" + secret[-4:],
          L.mask(secret))
    check("短密钥全打点", set(L.mask("sk-123")) == {"·"}, L.mask("sk-123"))


# ================================================================ 6 会话存储
def t_store():
    tmp = tempfile.mkdtemp(prefix="kb_dlg_")
    old = D.CONV_DIR
    D.CONV_DIR = tmp
    try:
        turns = [{"role": "user", "content": "问"}, {"role": "assistant", "content": "答"}]
        p = D.save(turns, title="红外/小目标: 检测", direction="红外小目标检测")
        check("会话能存盘", bool(p) and os.path.exists(p), str(p))
        name = os.path.basename(p or "")
        check("标题里的非法字符被清掉",
              not any(c in name for c in '\\/:*?"<>|'), name)
        with io.open(p, encoding="utf-8") as f:
            d = json.load(f)
        check("存盘内容与对话一致", d["turns"] == turns and d["direction"] == "红外小目标检测",
              str(d)[:100])
        check("能列出来", D.list_saved() and D.list_saved()[0] == name, str(D.list_saved()))
        check("空对话不落盘", D.save([], "空") is None)
    finally:
        D.CONV_DIR = old
        shutil.rmtree(tmp, ignore_errors=True)


# ================================================================ 7 真 HTTP 往返
class _Handler(BaseHTTPRequestHandler):
    calls = []

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n).decode("utf-8"))
        type(self).calls.append(body)
        auth = self.headers.get("Authorization", "")
        if "bad-key" in auth:
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'{"error":"invalid api key"}')
            return
        out = {"choices": [{"message": {"content": "收到 %d 条消息"
                                        % len(body.get("messages") or [])}}]}
        raw = json.dumps(out).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *a):
        pass


def t_http():
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    port = srv.server_address[1]
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    cfg = {"base_url": "http://127.0.0.1:%d/v1" % port, "model": "fake",
           "api_key": "sk-good-1234567890", "enabled": True,
           "temperature": 0.2, "timeout": 8}
    try:
        good, txt = D.reply([], "hi", cfg=cfg, use_profile=False)
        check("真 HTTP 往返成功", good and "收到 2 条" in txt, txt)
        sent = _Handler.calls[-1]
        check("请求体带 model 与 temperature",
              sent.get("model") == "fake" and abs(sent.get("temperature", 0) - 0.2) < 1e-6,
              str(sent.get("model")))
        check("请求体是 system+user 两条", len(sent["messages"]) == 2,
              str(len(sent["messages"])))

        bad_cfg = dict(cfg, api_key="bad-key-0000000000")
        good2, txt2 = D.reply([], "hi", cfg=bad_cfg, use_profile=False)
        check("401 被翻译成可读错误", good2 is False and "401" in txt2, txt2)
        check("401 时错误体也带出来了", "invalid api key" in txt2, txt2)

        down = dict(cfg, base_url="http://127.0.0.1:%d/v1" % 9, timeout=3)
        good3, txt3 = D.reply([], "hi", cfg=down, use_profile=False)
        check("端口不通时给出连不上而不是崩", good3 is False and "连不上" in txt3, txt3)
    finally:
        srv.shutdown()
        try:
            srv.socket.close()
        except Exception:
            pass


# ================================================================ 8 面板降级
def t_panel():
    root = T.Tk() if hasattr(T, "Tk") else __import__("tkinter").Tk()
    root.geometry("640x420+60+60")
    # FakeApp.post 在真实 App 里是"丢进队列、主线程下一拍再执行"。
    # 这里如果直接同步调用，就会在「正在思考…」那条占位还没被清掉时就断言 ——
    # 而且 Tk 自己并不满足"等后台线程"这个条件（非线程安全），
    # 所以显式用 join 等线程结束，而不是靠 root.update() 转圈。
    waiters = []
    try:
        fr = T.tk.Frame(root)
        fr.pack(fill="both", expand=True)

        class FakeApp:
            def __init__(self):
                self.toasts = []

            def toast(self, msg, color=None):
                self.toasts.append(msg)

            def post(self, fn):
                # 收集而不是立刻执行（真实 App 用的是 after(50) 轮询队列）
                waiters.append(fn)

        def drain(timeout=8.0):
            """等后台线程结束，再把队列里的回调执行一遍。"""
            import time as _t
            t0 = _t.time()
            while not waiters and _t.time() - t0 < timeout:
                _t.sleep(0.02)
            import threading as _th
            for th in _th.enumerate():
                if th is not _th.current_thread() and th.daemon:
                    th.join(timeout=timeout)
            while waiters:
                waiters.pop(0)()
            root.update()

        app = FakeApp()
        real_ready = L.is_ready
        L.is_ready = lambda cfg=None: False
        try:
            p = CP.ChatPanel(fr, app, anchor="选题：测试",
                             context_fn=lambda: "", suggestions=["问题A"])
            p.pack(fill="both", expand=True)
            root.update()
            p.ask("没配模型时会怎样")
            drain()
            root.update()
            last = p.last_reply()
            check("没配模型时给出明确指引而不是空白",
                  "设置与数据" in last and "提示词" in last, last[:80])
            check("没配模型时也把用户这句显示出来",
                  any(t.get("role") == "user" for t in p.turns))
            check("没配模型时发 Toast 提示", app.toasts, str(app.toasts))
            p.clear()
            check("清空能清干净", p.turns == [])
        finally:
            L.is_ready = real_ready

        real_chat = L.chat
        real_ready = L.is_ready
        L.chat = fake_chat
        L.is_ready = lambda cfg=None: True    # 面板走的是 is_ready 这一关
        try:
            p2 = CP.ChatPanel(fr, app, anchor="选题：测试",
                              context_fn=lambda: "【这次要聊的对象】\n选题：测试")
            p2.pack(fill="both", expand=True)
            # 打开面板 ≠ 第一次对话。锚点上下文只在用户真的问第一句时才发出去，
            # 所以要在 ask 之后取 SENT[-1]，不能提前读（否则读到的是上一段面板的请求）。
            root.update()
            p2.ask("第一问")
            drain()
            root.update()
            first_sent = SENT[-1]
            first = p2.last_reply()
            p2.ask("第二问")
            drain()
            root.update()
            check("面板能连续两轮", p2.last_reply() != first and "第" in p2.last_reply(),
                  "%s / %s" % (first[:20], p2.last_reply()[:20]))
            sysmsg = first_sent[0]["content"]
            check("面板把锚点上下文发给了模型", "这次要聊的对象" in sysmsg, sysmsg[:60])
            last_sent = SENT[-1]
            hist_text = " ".join(m["content"] for m in last_sent[1:-1])
            check("第二轮把第一轮的历史也带上",
                  "第一问" in hist_text, hist_text[:80])
            check("面板成功后写入画像记忆",
                  __import__("profile_hooks").stats()["ok"] > 0,
                  str(__import__("profile_hooks").stats()))
            ex = p2.export()
            check("面板能导出 Markdown", "第一问" in ex and "**助手**" in ex, ex[:60])
        finally:
            L.chat = real_chat
            L.is_ready = real_ready
    finally:
        root.destroy()


# ================================================================ main
def main():
    print("== 1 对话消息构造 ==")
    t_build()
    print("== 2 画像注入 ==")
    t_ctx()
    print("== 3 多轮往返 ==")
    t_rounds()
    print("== 4 失败路径 ==")
    t_fail()
    print("== 5 密钥不泄漏 ==")
    t_secret()
    print("== 6 会话存储 ==")
    t_store()
    print("== 7 真 HTTP 往返 ==")
    t_http()
    print("== 8 面板降级 ==")
    t_panel()

    print("\n" + "=" * 56)
    print("通过 %d / %d   失败 %d" % (len(PASS), len(PASS) + len(FAIL), len(FAIL)))
    for name, why in FAIL:
        print("  FAIL:", name, "——", why)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())