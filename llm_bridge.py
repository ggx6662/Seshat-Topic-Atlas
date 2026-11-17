"""大模型接入：可选的检索增强与方向改写。

设计原则（很重要）：
    ① **完全可选**。没配 key 时所有功能照常工作，只是走本地的词表/语义检索。
       不能因为没配大模型就让用户用不了——这是本地优先工具的底线。
    ② **key 只存本机**。写在 llm_config.json（同目录），不上传任何地方。
       界面里默认打码显示，复制时提醒。
    ③ **失败要能降级**。网络不通 / key 错 / 额度用完 → 返回 None，
       调用方回退到本地逻辑，不让整个界面卡死或报错。
    ④ **不假装**。模型给出的东西一律标注"由大模型生成，需要你判断"。

为什么是 OpenAI 兼容协议而不是各家 SDK：
    市面上的国产模型（DeepSeek、通义、智谱、月之暗面、硅基流动）、
    OpenAI 官方、本机 Ollama / vLLM / LM Studio，**都支持
    /chat/completions 这个接口**。写一套就够，用户换服务商只改 base_url。
    不引入 openai 这个 SDK 依赖（它还会拖进 httpx/anyio 一堆包），
    直接用标准库 urllib 发 POST，减少安装负担。
"""
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(HERE, "llm_config.json")

_lock = threading.Lock()
_last_call = [0.0]
MIN_GAP = 1.0          # 两次调用之间至少隔 1 秒，避免把自己限流

# 常见服务商的默认配置。用户点一下就能填好 base_url 和默认模型名，
# 不用去翻文档。—— base_url 都是"到 /v1 为止"，代码里再拼 /chat/completions
PROVIDERS = {
    "deepseek": {
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "key_url": "https://platform.deepseek.com/api_keys",
        "note": "便宜、中文好，适合改检索式与写创新点理由",
    },
    "qwen": {
        "label": "通义千问（阿里云百炼）",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
        "key_url": "https://bailian.console.aliyun.com/",
        "note": "国内直连稳定",
    },
    "zhipu": {
        "label": "智谱 GLM",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4-flash",
        "key_url": "https://open.bigmodel.cn/usercenter/apikeys",
        "note": "glm-4-flash 有免费额度",
    },
    "moonshot": {
        "label": "月之暗面 Kimi",
        "base_url": "https://api.moonshot.cn/v1",
        "model": "moonshot-v1-8k",
        "key_url": "https://platform.moonshot.cn/console/api-keys",
        "note": "长文本强",
    },
    "siliconflow": {
        "label": "硅基流动",
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "Qwen/Qwen2.5-7B-Instruct",
        "key_url": "https://cloud.siliconflow.cn/account/ak",
        "note": "聚合多种开源模型",
    },
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "key_url": "https://platform.openai.com/api-keys",
        "note": "需要能访问 api.openai.com",
    },
    "ollama": {
        "label": "本机 Ollama（完全离线）",
        "base_url": "http://127.0.0.1:11434/v1",
        "model": "qwen2.5:7b",
        "key_url": "https://ollama.com/download",
        "note": "不需要 key，本机跑模型，数据不出电脑",
    },
    "custom": {
        "label": "自定义（OpenAI 兼容）",
        "base_url": "",
        "model": "",
        "key_url": "",
        "note": "任何兼容 /chat/completions 的服务",
    },
}


def load_config():
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            d = json.load(f)
        if not isinstance(d, dict):
            return _default()
        out = _default()
        out.update(d)
        return out
    except Exception:
        return _default()


def _default():
    return {"provider": "", "base_url": "", "model": "", "api_key": "",
            "enabled": False, "temperature": 0.3, "timeout": 60,
            "last_ok": "", "last_error": ""}


def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def mask(key):
    """界面上显示用：只露前 4 后 4。"""
    k = (key or "").strip()
    if not k:
        return ""
    if len(k) <= 10:
        return "·" * len(k)
    return k[:4] + "…" + k[-4:]


def is_ready(cfg=None):
    cfg = cfg or load_config()
    return bool(cfg.get("enabled") and cfg.get("base_url")
                and cfg.get("model")
                and (cfg.get("api_key") or "127.0.0.1" in cfg.get("base_url", "")
                     or "localhost" in cfg.get("base_url", "")))


class LLMError(Exception):
    pass


def chat(messages, cfg=None, max_tokens=900, json_mode=False):
    """发一次对话请求。失败抛 LLMError（调用方要 catch 并降级）。

    messages: [{"role": "system"/"user", "content": "..."}]
    """
    cfg = cfg or load_config()
    if not is_ready(cfg):
        raise LLMError("没有配置大模型")
    base = (cfg.get("base_url") or "").rstrip("/")
    url = base + "/chat/completions"
    body = {
        "model": cfg.get("model"),
        "messages": messages,
        "temperature": float(cfg.get("temperature", 0.3)),
        "max_tokens": max_tokens,
        "stream": False,
    }
    if json_mode:
        # 不是所有服务商都支持 response_format，只在明确要 JSON 时加，
        # 并且失败时要能降级到"从文本里抠 JSON"
        body["response_format"] = {"type": "json_object"}

    with _lock:
        wait = MIN_GAP - (time.time() - _last_call[0])
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.time()

    headers = {"Content-Type": "application/json"}
    key = (cfg.get("api_key") or "").strip()
    if key:
        headers["Authorization"] = "Bearer " + key
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers=headers, method="POST")
    timeout = int(cfg.get("timeout", 60))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "ignore")[:300]
        except Exception:
            pass
        raise LLMError("HTTP %s：%s" % (e.code, detail or e.reason))
    except urllib.error.URLError as e:
        raise LLMError("连不上 %s（%s）" % (base, e.reason))
    except Exception as e:
        raise LLMError("%s: %s" % (type(e).__name__, e))

    try:
        d = json.loads(raw)
        return d["choices"][0]["message"]["content"]
    except Exception:
        raise LLMError("返回格式看不懂：%s" % raw[:200])


def test_connection(cfg=None):
    """设置页的"测试连接"按钮。返回 (ok, message)，不抛异常。"""
    cfg = cfg or load_config()
    t0 = time.time()
    try:
        out = chat([{"role": "user", "content": "回复两个字：可用"}],
                   cfg, max_tokens=20)
        ms = int((time.time() - t0) * 1000)
        c = load_config()
        c["last_ok"] = time.strftime("%Y-%m-%d %H:%M")
        c["last_error"] = ""
        save_config(c)
        return True, "连接成功（%d ms）：%s" % (ms, (out or "").strip()[:60])
    except Exception as e:
        c = load_config()
        c["last_error"] = str(e)[:200] + "  " + time.strftime("%m-%d %H:%M")
        save_config(c)
        return False, str(e)[:200]


# ── 三个实际用途 ──────────────────────────────────────────

def _profile_block():
    """把个人画像拼成提示词里的一段「这是谁」。

    画像完全可选：没建画像 / 读失败都返回空串，提示词与以前逐字一致。
    只读不写，也绝不把导师、学校这类信息写进日志或请求之外的任何地方。
    """
    try:
        import profile_memory as PM
        brief = (PM.profile_brief() or "").strip()
    except Exception:
        return ""
    if not brief:
        return ""
    return ("\n\n【提问的人是谁】（据此调整你的判断口径，不要复述这段）\n"
            + brief + "\n")


_PROFILE_RULE = (
    "\n回答时请贴合这个人的处境："
    "如果 ta 时间紧/在焦虑，优先给能落地的建议，少开新战场；"
    "如果 ta 时间宽裕或兴趣高，可以给更激进的方向。"
    "不要复述上面的个人信息。"
)


_REWRITE_SYS = (
    "你是学术检索助手。把中文研究方向改写成 1 条 arXiv 检索式。"
    "要求：只输出检索式本身，不要解释；用英文；"
    "把核心的方法/任务写成带引号的短语（如 abs:\"object detection\"）；"
    "多个条件用 AND 连接；最多 4 个条件；"
    "如果方向涉及计算机视觉之外的领域（如天文红外），"
    "在最后加上 (cat:cs.CV OR cat:cs.LG OR cat:cs.AI OR cat:cs.RO OR cat:eess.IV) 限定。"
)


def rewrite_query(direction, cfg=None, use_profile=False):
    """把中文方向名改成更好的 arXiv 检索式。

    为什么要用模型：本地词表只有 220 条，遇到「事件相机语义分割」
    这类组合只能逐词拼。模型知道这个领域在 arXiv 上通常怎么表述。
    返回 None 表示不可用（调用方用本地 build_query 兜底）。

    use_profile: 检索式本身不该被个人状态改写（那是客观映射），默认关闭；
    保留开关是为了以后「想让检索偏向自己的偏好方向」时有地方接。
    """
    sys_msg = _REWRITE_SYS
    if use_profile:
        sys_msg = _REWRITE_SYS + _profile_block()
    try:
        out = chat([{"role": "system", "content": sys_msg},
                    {"role": "user", "content": "方向：" + (direction or "")}],
                   cfg, max_tokens=200)
    except Exception:
        return None
    q = (out or "").strip()
    q = q.strip("`").strip()
    if q.lower().startswith("abs:") or "(" in q or " AND " in q:
        return q[:400] or None
    return None


_EXPLAIN_SYS = (
    "你是计算机方向的博士生导师。用户给你一个研究方向，和一批最近发表的相关论文标题。"
    "请用中文写出：\n"
    "1) 这些论文整体在做的 3 个技术走向（每条一句话，必须指向具体做法，不要空话）；\n"
    "2) 其中至少 1 条指出「还没被充分解决的」问题；\n"
    "3) 不要编造论文里没有的方法。\n"
    "输出纯文本，不要 markdown 标题符号。"
)


def explain_direction(direction, papers, cfg=None, use_profile=True):
    """让模型总结这批论文的技术走向，并针对提问者本人的处境给一句建议。

    use_profile=True 时会把画像摘要塞进 system 提示；没建画像时
    提示词与以前完全一致（_profile_block 返回空串）。
    失败返回 None。
    """
    titles = "\n".join("· " + (p.get("title") or "")[:120] +
                       ("  (" + p["venue"] + ")" if p.get("venue") else "")
                       for p in (papers or [])[:20])
    if not titles.strip():
        return None
    sys_msg = _EXPLAIN_SYS
    if use_profile:
        extra = _profile_block()
        if extra:
            sys_msg = _EXPLAIN_SYS + extra + _PROFILE_RULE
    try:
        return (chat([{"role": "system", "content": sys_msg},
                      {"role": "user",
                       "content": "方向：%s\n\n最近论文：\n%s"
                                  % (direction, titles)}],
                     cfg, max_tokens=700) or "").strip() or None
    except Exception:
        return None


_IDEA_SYS = (
    "你是计算机方向的审稿人。用户给你一个研究方向和一些候选选题，"
    "请指出哪几个最可能有真实贡献，并说明理由与最大风险。"
    "要求：只说你能从候选里看出来的东西；"
    "如果某个候选听起来像模板套话，直说。"
    "输出中文，控制在 300 字内。"
)


def critique_ideas(direction, candidates, cfg=None, use_profile=True):
    """让模型挑刺。

    use_profile=True 时会把提问者的时间/状态/已有偏好一起给它，
    这样「哪几个最值得做」才会考虑「这个人现在能不能做」。
    失败返回 None。
    """
    lines = []
    for i, c in enumerate((candidates or [])[:8], 1):
        t = c.get("title") or c.get("angle") or ""
        tag = ""
        if c.get("feasibility") is not None:
            tag = "（可行 %s / 新颖 %s）" % (c.get("feasibility"), c.get("novelty", "—"))
        lines.append("%d. %s%s" % (i, str(t)[:100], tag))
    if not lines:
        return None
    sys_msg = _IDEA_SYS
    if use_profile:
        extra = _profile_block()
        if extra:
            sys_msg = _IDEA_SYS + extra + _PROFILE_RULE
    try:
        return (chat([{"role": "system", "content": sys_msg},
                      {"role": "user",
                       "content": "方向：%s\n\n候选：\n%s"
                                  % (direction, "\n".join(lines))}],
                     cfg, max_tokens=700) or "").strip() or None
    except Exception:
        return None


def _extract_json(text):
    """模型有时会在 JSON 外面包 ```json ```，这里兜底抠出来。"""
    if not text:
        return None
    t = text.strip()
    m = re.search(r"\{.*\}", t, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def status():
    cfg = load_config()
    return {"ready": is_ready(cfg),
            "provider": cfg.get("provider", ""),
            "model": cfg.get("model", ""),
            "base_url": cfg.get("base_url", ""),
            "key": mask(cfg.get("api_key", "")),
            "last_ok": cfg.get("last_ok", ""),
            "last_error": cfg.get("last_error", "")}