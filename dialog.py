"""和 "写提示词专用的模型" 连续对话。

和 `llm_bridge` 里那三个一次性调用的区别
----------------------------------------
`rewrite_query` / `explain_direction` / `critique_ideas` 都是「发一句、拿一段、结束」，
不保存任何东西，也不认人。学生真实的用法不是这样：他们会追问 ——
「第三条再具体点」「我不太懂什么叫开放词汇」「这个方向有没有人做过」。

所以这里单开一层，只管三件事：

1. **保留上下文**：每轮把历史消息原样带给模型，模型才记得上一轮说了什么。
2. **每轮都吃画像**：画像在第一轮拼一次就够了吗？不够。对话到第 5 轮时
   用户可能刚在别处更新了「快截止了」，所以每轮都重新取一次画像段
   （`prompt_context.block`）。画像为空时这一段是空字符串，不会污染提示词。
3. **能降级**：没配大模型时 `reply()` 返回 `None`，界面照常显示本地逻辑生成的
   内容，不会变成一个什么都做不了的输入框。

线程模型
--------
`reply()` 是**阻塞**的（最坏要等 timeout 秒）。界面必须在后台线程里调它，
再用 `App.post()` 把结果丢回主线程 —— 直接在主线程调会让窗口假死，
Tk 在等待期间连重绘都做不了。

存储
----
`CONV_DIR` 下一条会话一个 json。**只在用户显式保存时才写盘**，
否则每次试一下就留一个文件，几个月后目录里全是废稿。
"""
import json
import os
import re
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CONV_DIR = os.path.join(HERE, "dialogs")

# 一轮对话最多带多少条历史消息。太多会把 token 花在重复内容上，
# 太少模型会忘记 3 轮前说过的话。8 条 = 4 轮问答，正好是「再改改」的跨度。
MAX_HISTORY = 8
MAX_CHARS = 2400        # 单条历史消息的截断长度（超过这个基本是模型在复读）

_lock = threading.Lock()


# ---------------------------------------------------------------- 提示词
_SYS = (
    "你是一个帮计算机方向的学生打磨研究想法的助手。\n"
    "规矩：\n"
    "1. 对方问什么就答什么，不要每次都重新铺一遍背景。\n"
    "2. 具体、可执行；说「用更强的方法」这种话不如不给。\n"
    "3. 不知道就说不知道。不要编造论文标题、作者、数字、实验结果。\n"
    "4. 对方给的约束（算力、期限、不想碰的方向）是硬边界，"
    "你的建议不能越过它；确实做不到时直接说，不要绕。\n"
    "5. 不要复述下面【我的情况】里的任何原话，把它当成你已经知道的事。\n"
    "6. 中文回答，控制在 300 字内，不用 markdown 标题符号。"
)


def _sys_prompt(ctx=""):
    """系统提示 + 画像段。画像为空时返回的字符串与以前逐字一致。"""
    if not (ctx or "").strip():
        return _SYS
    return _SYS + "\n\n" + ctx.strip()


def _trim(msgs):
    """只保留最近若干条，并把超长的截断。

    截断要保留**开头**而不是结尾：模型回复的结论常在第一句，
    后 200 字多半是在复读。
    """
    msgs = [m for m in (msgs or []) if (m.get("content") or "").strip()]
    msgs = msgs[-MAX_HISTORY:]
    out = []
    for m in msgs:
        role = "assistant" if m.get("role") == "assistant" else "user"
        text = str(m.get("content") or "").strip()
        if len(text) > MAX_CHARS:
            text = text[:MAX_CHARS] + "…"
        out.append({"role": role, "content": text})
    return out


def build_messages(turns, user_msg, ctx=""):
    """把「历史 + 这一句」拼成传给模型的消息列表（纯函数，方便测试）。"""
    msgs = [{"role": "system", "content": _sys_prompt(ctx)}]
    msgs.extend(_trim(turns))
    msgs.append({"role": "user", "content": str(user_msg or "").strip()})
    return msgs


# ---------------------------------------------------------------- 调用
def reply(turns, user_msg, cfg=None, use_profile=True, ctx=""):
    """发一轮对话。返回 (ok, text_or_error)。

    绝不抛异常 —— 界面回调里一次未捕获的异常会让整个对话面板停在
    「正在思考…」上再也点不动。
    """
    try:
        import llm_bridge as L
    except Exception as exc:                       # pragma: no cover
        return False, "大模型模块加载失败：%s" % exc

    text = str(user_msg or "").strip()
    if not text:
        return False, "还没有输入内容"

    ctx = str(ctx or "").strip()
    if not ctx and use_profile:
        try:
            import prompt_context as PC
            got = PC.gather()
            # want="task"：对话是具体任务，用任务口径的收尾语
            ctx = PC.block(got.get("profile"), got.get("constraints"),
                           got.get("memories"), want="task")
        except Exception:
            # 画像坏了不阻止对话 —— 只是这轮没有个性化
            ctx = ""

    try:
        out = L.chat(build_messages(turns, text, ctx),
                     cfg=cfg, max_tokens=800)
    except Exception as exc:
        return False, str(exc)
    out = (out or "").strip()
    if not out:
        return False, "模型返回了空内容"
    return True, out


# ---------------------------------------------------------------- 存取
def _safe_name(title):
    """会话文件名。标题是中文，直接当文件名在 Windows 上也行，
    但要挡掉 \\ / : * ? " < > | 和开头的点。"""
    t = re.sub(r'[\\/:*?"<>|\r\n\t]', " ", str(title or "")).strip(" .")
    return (t or "对话")[:40]


def save(turns, title="", direction=""):
    """保存一条会话，返回文件路径；失败返回 None。"""
    if not turns:
        return None
    ts = time.strftime("%Y%m%d-%H%M%S")
    path = os.path.join(CONV_DIR, "%s-%s.json" % (ts, _safe_name(title)))
    data = {"title": title or "对话", "direction": direction,
            "saved": time.strftime("%Y-%m-%d %H:%M"), "turns": list(turns)}
    try:
        os.makedirs(CONV_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return path
    except Exception:
        return None


def list_saved(limit=20):
    """按时间倒序列出已保存的会话（只读文件名，不解析内容）。"""
    try:
        names = [n for n in os.listdir(CONV_DIR) if n.endswith(".json")]
    except Exception:
        return []
    names.sort(reverse=True)
    return names[:limit]


def export_markdown(turns, title=""):
    """把对话导成可粘贴进论文笔记的 Markdown。"""
    lines = ["# " + (title or "对话记录"),
             "", "_导出时间：" + time.strftime("%Y-%m-%d %H:%M") + "_", ""]
    for m in turns or []:
        who = "我" if m.get("role") != "assistant" else "助手"
        lines.append("**%s**" % who)
        lines.append("")
        lines.append(str(m.get("content") or "").strip())
        lines.append("")
    return "\n".join(lines)