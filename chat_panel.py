"""对话面板：贴着某个具体对象和模型来回改。

为什么不做成独立的一整页聊天窗
------------------------------
用户要的「对话」不是通用闲聊，是「我把这个选题 / 这个方向给模型看，
它来回帮我改」。所以这个面板以一个**锚点对象**为中心：

    ChatPanel(host, app, anchor="选题：xxx", context_fn=..., suggestions=[...])

锚点对象决定了每轮对话里附带的本地事实（方向、候选理由、诊断结论），
模型不用你复述背景，也不会答非所问成「通用科研建议」。

界面（2026-11-15 按用户给的聊天界面参考重做）
  · 用户消息靠右、深色气泡；模型消息靠左、浅色气泡 + 角色圆点
  · 气泡圆角用 Canvas 画（Tk 的 Frame 只能直角），整行最大宽度 78%
  · 日期/时间居中的淡色分隔线
  · 输入区是一个大圆角容器：多行输入 + 右下角圆形发送按钮，
    Enter 发送、Shift+Enter 换行（参考图的交互习惯）
  · 发送期间输入区禁用并显示「正在思考…」，**后台线程 + app.post()**，
    主线程阻塞会让窗口假死
  · 没配模型时**不发禁**：输入框可用，发送时给出可执行的退路
"""
import threading
import time
import tkinter as tk

import app_theme as T

MAX_TURNS_SHOWN = 40

# 气泡最大宽度占可视区的比例。参考图里用户气泡约占 55%，模型气泡更宽
# （因为回答长），但两者都不该铺满整行 —— 贴边会失去「谁在说话」的边界感。
_W_USER = 0.62
_W_BOT = 0.80


def _stamp():
    return time.strftime("%H:%M")


def _day_of(ts):
    return time.strftime("%Y-%m-%d", time.localtime(ts or time.time()))


class _Bubble(tk.Frame):
    """一条消息：圆角气泡 + 可选的角色/时间小字。

    圆角画在一个固定高度的 Canvas 上，文字 Label 叠在 Canvas 里
    （`create_window`），这样气泡能跟着文字高度自动长高。
    """

    def __init__(self, parent, text, mine, bg, max_px, stamp="", tone="normal"):
        super().__init__(parent, bg=bg)
        # 气泡配色：
        #   我 = 主色系浅底（spark 感，一眼分出「我说的」）
        #   模型 = 比面板底色亮一档的中性底（CARD_HI），保证正文有足够对比
        # 早先用 mine ? CARD_HI : BG —— 深色下 BG 近乎纯黑，正文直接看不见。
        if mine:
            fill = T.tint(T.ACCENT, 0.16, bg)
            fg = T.TXT
        else:
            # 模型气泡要和面板底色拉开：CARD_HI 在深色下只比 CARD 亮一档，
            # 整片看上去像同一块灰。用 CARD_HI 再往文字色里掺 6%。
            fill = T.mix(T.TXT, T.CARD_HI, 0.06)
            fg = T.TXT
        if tone == "error":
            fill, fg = T.tint(T.ERR, 0.14, bg), T.ERR

        pad_x, pad_y = 12, 8
        wrap_px = max(160, max_px - pad_x * 2)
        cv = tk.Canvas(self, bg=bg, width=120, height=44,
                       highlightthickness=0, bd=0)
        cv.pack(side="right" if mine else "left")
        # 文字 Label 必须是 Canvas 的子控件：create_window 放一个「兄弟」
        # 控件（这里是 self 的子）时 Tk 不报错，但那个控件永远不会被画
        # 出来 —— 实测 body mapped=1 w=306 h=36 fg=#e6e8eb，放大截图里
        # 一个文字像素都没有，只有底下的圆角。
        body = tk.Label(cv, text=text, bg=fill, fg=fg, font=T.T_BODY_SM(),
                        anchor="w", justify="left", wraplength=wrap_px)
        # 量「自然宽度」时必须把 wraplength 设成很大，否则 Label 直接按
        # wraplength 报宽度，量出来永远是满宽 —— 短消息也会变成一条长条。
        try:
            body.configure(wraplength=4000)
            body.update_idletasks()
            need = body.winfo_reqwidth() + pad_x * 2
        except Exception:
            need = max_px
        w = int(min(max_px, max(120, need)))
        inner = max(120, w - pad_x * 2)
        # 别再设 width=：tk.Label 的 width 单位是**字符数**（传 441 就成了
        # 441 个字符宽，实测 reqwidth 3598），而且 wraplength 只管折行、
        # 不保证折出来的行不超过窗口宽度，超出的部分被 canvas 边缘切掉，
        # 看起来就是「文字压边」。做法：折行宽度比窗口窄 4px 留余量。
        body.configure(wraplength=max(96, inner - 4))
        # 换行宽度变了以后高度要重算，而且 Tk 要**两次** idle 才把新的
        # 行数反映到 reqheight 上：只算一次会少一行，文字压在气泡下边框。
        try:
            for _ in range(2):
                body.update_idletasks()
            h = body.winfo_reqheight() + pad_y * 2
            # 再兜一层：按真实 reqheight 反校准，防止字体度量差 1–2 px
            real = body.winfo_reqheight()
            if real > 0:
                h = real + pad_y * 2
        except Exception:
            h = 44

        cv.configure(width=w, height=h)
        T._round_rect(cv, 0, 0, w - 1, h - 1, min(14, h // 2), fill=fill)
        cv.create_window(pad_x, pad_y, window=body, anchor="nw")
        self.canvas = cv
        self.body = body
        self.mine = mine
        if stamp:
            tk.Label(self, text=stamp, bg=bg, fg=T.TXT4,
                     font=T.T_CAPTION()).pack(
                         side="right" if mine else "left",
                         padx=(8, 0) if mine else (0, 8))


class ChatPanel(tk.Frame):
    def __init__(self, parent, app, anchor="", context_fn=None,
                 suggestions=None, fallback_cmd=None, bg=None, height=300):
        self._bg = bg or T.CARD
        super().__init__(parent, bg=self._bg)
        self.app = app
        self.anchor = anchor or ""
        self._ctx_fn = context_fn
        self._fallback = fallback_cmd
        self.turns = []            # [{"role","content","ts"}]
        self._busy = False
        self._last_ok = False
        self._bubbles = []

        self._build(suggestions or [], height)

    # ------------------------------------------------------------ 界面
    def _build(self, suggestions, height):
        bg = self._bg

        # ---- 标题行：左侧角色点 + 会话名，右侧「清空」「导出」
        head = tk.Frame(self, bg=bg)
        head.pack(fill="x", pady=(0, 8))
        dot = tk.Canvas(head, width=10, height=10, bg=bg,
                        highlightthickness=0, bd=0)
        dot.pack(side="left", pady=(3, 0))
        dot.create_oval(1, 1, 9, 9, fill=T.ACCENT, outline=T.ACCENT)
        tk.Label(head, text="和模型继续聊", bg=bg, fg=T.TXT,
                 font=T.T_LABEL(), anchor="w").pack(side="left", padx=(7, 0))
        if self.anchor:
            tk.Label(head, text="·", bg=bg, fg=T.TXT4,
                     font=T.T_CAPTION()).pack(side="left", padx=6)
            tk.Label(head, text=self.anchor, bg=bg, fg=T.TXT3,
                     font=T.T_CAPTION(), anchor="w").pack(side="left")
        for txt, cmd in (("清空", self.clear), ("导出", self.export)):
            b = tk.Label(head, text=txt, bg=bg, fg=T.TXT3,
                         font=T.T_CAPTION(), cursor="hand2", padx=6)
            b.pack(side="right")
            b.bind("<Button-1>", lambda e, c=cmd: c())
            b.bind("<Enter>", lambda e, w=b: w.config(fg=T.TXT))
            b.bind("<Leave>", lambda e, w=b: w.config(fg=T.TXT3))

        # ---- 消息流
        self.stream = T.ScrollArea(self, bg=bg)
        self.stream.pack(fill="both", expand=True)
        try:
            self.stream.canvas.configure(height=height)
        except Exception:
            pass
        self.stream.canvas.bind("<Configure>", self._on_stream_resize, add="+")
        self._render_stream()

        # ---- 快捷问题（只在没聊过时出现，聊起来之后就不占地方了）
        self._sugg_row = tk.Frame(self, bg=bg)
        self._suggestions = list(suggestions[:3])
        if self._suggestions:
            self._sugg_row.pack(fill="x", pady=(8, 0), before=None)
            for s in self._suggestions:
                b = tk.Label(self._sugg_row, text=s, bg=T.CARD_HI, fg=T.TXT2,
                             font=T.T_CAPTION(), padx=10, pady=4, cursor="hand2")
                b.pack(side="left", padx=(0, 6))
                b.bind("<Button-1>", lambda e, t=s: self.ask(t))
                b.bind("<Enter>", lambda e, w=b: w.config(bg=T.CARD))
                b.bind("<Leave>", lambda e, w=b: w.config(bg=T.CARD_HI))

        # ---- 输入区：一个大圆角容器
        self._input_wrap = tk.Frame(self, bg=bg)
        self._input_wrap.pack(fill="x", pady=(10, 0))
        self._input_cv = tk.Canvas(self._input_wrap, bg=bg, height=92,
                                   highlightthickness=0, bd=0)
        self._input_cv.pack(fill="x")
        self._input_cv.bind("<Configure>", self._paint_input)

        self.entry = tk.Text(self._input_cv, height=2, wrap="word",
                             bg=T.CARD_HI, fg=T.TXT, insertbackground=T.TXT,
                             relief="flat", font=T.T_BODY_SM(),
                             padx=12, pady=10, highlightthickness=0, bd=0)
        self._entry_win = self._input_cv.create_window(
            8, 8, window=self.entry, anchor="nw")
        # Enter 发送、Shift+Enter 换行：参考图的习惯，比 Ctrl+Enter 顺手
        self.entry.bind("<Return>", self._on_return)
        self.entry.bind("<Shift-Return>", lambda e: None)

        self.send_btn = tk.Canvas(self._input_cv, width=34, height=34, bg=bg,
                                  highlightthickness=0, bd=0, cursor="hand2")
        self._send_id = self.send_btn.create_oval(1, 1, 33, 33,
                                                  fill=T.ACCENT, outline=T.ACCENT)
        # 发送键的箭头用线段画，不用「↑」字形：不同字体/DPI 下这个符号
        # 会落到别处（实测截图里显示成「t」），矢量笔画不会有这个问题。
        self._send_arrow = self.send_btn.create_line(
            17, 24, 17, 10, fill="#ffffff", width=2,
            capstyle="round", joinstyle="round")
        self._send_head = self.send_btn.create_line(
            11, 16, 17, 10, 23, 16, fill="#ffffff", width=2,
            capstyle="round", joinstyle="round")
        self.send_btn.bind("<Button-1>", lambda e: self.send())
        self.send_btn.bind("<Enter>", lambda e: self._paint_send(True))
        self.send_btn.bind("<Leave>", lambda e: self._paint_send(False))

        self.hint = tk.Label(self, text="Enter 发送 · Shift+Enter 换行 · "
                                        "模型会看到你画像里的方向、约束与状态",
                             bg=bg, fg=T.TXT4, font=T.T_CAPTION(), anchor="w")
        self.hint.pack(fill="x", pady=(6, 0))

    def _paint_input(self, ev=None):
        """画输入区圆角框，并把输入框/发送键放到框里。"""
        cv = self._input_cv
        try:
            w = ev.width if ev else cv.winfo_width()
            h = ev.height if ev else int(cv.cget("height"))
        except Exception:
            return
        if w <= 2:
            return
        for i in cv.find_all():
            if i in (self._entry_win,):
                continue
            cv.delete(i)
        edge = T.card_outline(T.LINE, self._bg)
        # 输入区要比气泡更「凹陷」一点：气泡用 CARD_HI，输入框用 CARD
        # 并带描边，参考图里也是这种「浅底输入框 + 描边」的读法。
        ids = T._round_rect(cv, 1, 1, w - 2, h - 2, 13,
                            fill=T.CARD, outline=edge or T.LINE)
        for i in ids:
            cv.tag_lower(i)
        cv.coords(self._entry_win, 8, 6)
        cv.itemconfigure(self._entry_win, width=max(80, w - 16 - 44),
                         height=max(40, h - 12))
        self._place_send(w, h)

    def _place_send(self, w, h):
        try:
            self.send_btn.place(in_=self._input_cv, x=w - 42, y=h - 42)
        except Exception:
            pass

    def _paint_send(self, on):
        try:
            self.send_btn.itemconfig(self._send_id,
                                     fill=(T.ACCENT_HI if on else T.ACCENT),
                                     outline=(T.ACCENT_HI if on else T.ACCENT))
        except Exception:
            pass

    # ------------------------------------------------------------ 渲染
    def _on_stream_resize(self, ev=None):
        # 可视宽度变了要按新宽度重排气泡（wraplength 是像素值）
        if ev is not None and getattr(self, "_last_w", None) == ev.width:
            return
        self._last_w = getattr(ev, "width", None)
        self._render_stream()

    def _max_px(self, ratio):
        try:
            w = self.stream.canvas.winfo_width()
        except Exception:
            w = 0
        if w <= 2:
            w = 720
        return int(max(240, (w - 24) * ratio))

    def _render_stream(self):
        self.stream.clear()
        self._bubbles = []
        inner = self.stream.inner
        if not self.turns:
            tk.Label(inner, text="还没有对话。用下面的快捷问题起个头，"
                                 "或者直接把你的问题打进去。",
                     bg=self._bg, fg=T.TXT3, font=T.T_BODY_SM(), anchor="w",
                     justify="left", wraplength=T.wrap(560)).pack(
                         fill="x", padx=6, pady=(10, 6))
        day = None
        for m in self.turns[-MAX_TURNS_SHOWN:]:
            d = _day_of(m.get("ts"))
            if d != day:
                day = d
                self._render_day(d)
            self._render_turn(m)
        self.stream.refresh()

    def _render_day(self, day):
        row = tk.Frame(self.stream.inner, bg=self._bg)
        row.pack(fill="x", pady=(10, 8))
        try:
            real = time.strftime("%Y年%m月%d日", time.strptime(day, "%Y-%m-%d"))
        except Exception:
            real = day
        tk.Label(row, text=real, bg=self._bg, fg=T.TXT4,
                 font=T.T_CAPTION()).place(relx=0.5, rely=0.5, anchor="center")

    def _render_turn(self, m):
        mine = m.get("role") != "assistant"
        text = str(m.get("content") or "")
        tone = "error" if text.startswith("没成功：") else "normal"
        wrap = tk.Frame(self.stream.inner, bg=self._bg)
        wrap.pack(fill="x", pady=3, padx=6)
        b = _Bubble(wrap, text, mine, self._bg,
                    self._max_px(_W_USER if mine else _W_BOT),
                    stamp="", tone=tone)
        b.pack(fill="x", anchor="e" if mine else "w")
        self._bubbles.append(b)

    # ------------------------------------------------------------ 动作
    def _sync_suggestions(self):
        """聊过之后把快捷问题收起来 —— 它们只在空白态有用。"""
        try:
            if self.turns and self._sugg_row.winfo_manager():
                self._sugg_row.pack_forget()
            elif not self.turns and self._suggestions \
                    and not self._sugg_row.winfo_manager():
                self._sugg_row.pack(fill="x", pady=(8, 0))
        except Exception:
            pass

    def _set_busy(self, on):
        self._busy = on
        try:
            self.entry.configure(state="disabled" if on else "normal")
        except Exception:
            pass
        try:
            self.send_btn.itemconfig(
                self._send_id,
                fill=(T.LINE if on else T.ACCENT),
                outline=(T.LINE if on else T.ACCENT))
        except Exception:
            pass
        try:
            self.hint.config(text="正在思考…" if on else
                             "Enter 发送 · Shift+Enter 换行 · "
                             "模型会看到你画像里的方向、约束与状态",
                             fg=(T.TXT3 if on else T.TXT4))
        except Exception:
            pass
        if on:
            self.turns.append({"role": "assistant", "content": "正在思考…",
                               "ts": time.time(), "_pending": True})
            self._render_stream()
            self._scroll_bottom()

    def _scroll_bottom(self):
        try:
            self.stream.canvas.yview_moveto(1.0)
        except Exception:
            pass

    def _on_return(self, ev=None):
        # Shift+Enter 由 <Shift-Return> 绑定吃掉（返回 None 即换行）
        if ev is not None and (ev.state & 0x0001):
            return None
        self.send()
        return "break"

    def send(self):
        text = self.entry.get("1.0", "end").strip()
        if not text:
            return
        self.ask(text)

    def ask(self, text):
        """界面上的入口都走这里：快捷问题点进来也走同一条路。"""
        if self._busy:
            return
        text = str(text or "").strip()
        if not text:
            return
        try:
            import llm_bridge as L
            ready = L.is_ready()
        except Exception as exc:
            ready = False
            err = str(exc)
        else:
            err = ("还没有配置大模型。去「设置与数据」填接口地址、模型名和密钥；"
                   "不想配的话也可以用「生成提示词」把这一段带出去问别的 AI。")
        if not ready:
            try:
                self.app.toast("未配置大模型", T.WARN)
            except Exception:
                pass
            self.turns.append({"role": "user", "content": text,
                               "ts": time.time()})
            self.turns.append({"role": "assistant", "content": err,
                               "ts": time.time()})
            self._render_stream()
            self._sync_suggestions()
            self._scroll_bottom()
            return

        self.entry.delete("1.0", "end")
        history = [t for t in self.turns if not t.get("_pending")]
        self.turns.append({"role": "user", "content": text, "ts": time.time()})
        self._last_ok = False
        self._sync_suggestions()
        self._set_busy(True)

        ctx = ""
        lines = []
        if self._ctx_fn:
            try:
                lines.append(str(self._ctx_fn() or "").strip())
            except Exception:
                pass
        # 对话不等于任务，不套用任务口径的收尾语（"以上是我的实际情况…"），
        # 那段用在提示词里合适，用在聊天里像在给自己下指令。
        try:
            import prompt_context as PC
            got = PC.gather()
            body = PC.block(got.get("profile"), got.get("constraints"),
                            got.get("memories"), want="plan")
        except Exception:
            body = ""
        if body.strip():
            lines.append(body.strip())
        ctx = "\n\n".join(x for x in lines if x)

        def work():
            import dialog as D
            ok, out = D.reply(history, text, ctx=ctx)
            self.app.post(lambda: self._done(ok, out, ctx))

        threading.Thread(target=work, daemon=True).start()

    def _done(self, ok, out, ctx=""):
        self._busy = False
        try:
            self.entry.configure(state="normal")
        except Exception:
            pass
        try:
            self.send_btn.itemconfig(self._send_id, fill=T.ACCENT,
                                     outline=T.ACCENT)
        except Exception:
            pass
        try:
            self.hint.config(text="Enter 发送 · Shift+Enter 换行 · "
                                  "模型会看到你画像里的方向、约束与状态",
                             fg=T.TXT4)
        except Exception:
            pass
        # 去掉占位气泡（按标记而不是按文本，回答里真出现「正在思考…」也不误删）
        self.turns = [t for t in self.turns if not t.get("_pending")]
        if ok:
            self.turns.append({"role": "assistant", "content": out,
                               "ts": time.time()})
            self._last_ok = True
            try:
                import profile_hooks as PH
                PH.note("AI 对话：%s" % str(out)[:60],
                        tags=["对话", self.anchor[:20]], kind="daily",
                        source="对话面板", ref=self.anchor[:40])
            except Exception:
                pass
        else:
            self.turns.append({"role": "assistant",
                               "content": "没成功：%s\n\n检查设置页的「测试连接」。"
                                          % out,
                               "ts": time.time()})
        self._render_stream()
        self._scroll_bottom()
        try:
            import ui_parts as U
            U._resync(self)
        except Exception:
            pass

    def clear(self):
        self.turns = []
        self._last_ok = False
        self._render_stream()
        self._sync_suggestions()
        try:
            self.entry.delete("1.0", "end")
        except Exception:
            pass

    def last_reply(self):
        """最后一条模型回复的正文（测试与「复制」用）。"""
        for m in reversed(self.turns):
            if m.get("role") == "assistant" and not m.get("_pending"):
                return m.get("content") or ""
        return ""

    def export(self):
        import dialog as D
        return D.export_markdown(self.turns, title=self.anchor or "对话")