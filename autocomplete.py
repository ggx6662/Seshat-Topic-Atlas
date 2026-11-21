#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""输入框联想词引擎 —— 打「红外」就弹出「红外小目标检测」「红外与低光视觉」…

为什么要有
----------
这个应用里所有「研究方向」都得用户手打。但方向词的写法极其不统一：
    红外小目标检测 / 红外小目标 / infrared small target / 热红外弱小目标
用户既不知道我们词表里收的是哪种写法，也不知道哪些词是我们**认得**的
（不认得的词会翻译失败，检索结果直接是 0 篇）。

联想词同时解决两件事：
  1. 少打字 —— 前缀 / 包含 / 拼音首字母都能命中
  2. **只推荐我们查得到的写法** —— 候选全部来自真实词表（方向库、CN2EN、
     _SYN_GROUP、方法/任务/模态/问题词表），点中就去查，不会空手而归

词来源（按可信度排序）
----------------------
  field   方向库 536 个细分领域（含 25 个类目）—— 最推荐
  alias   方向别名表 152 组
  method  方法词（对比学习/Mamba/扩散模型…）
  task    任务词（检测/分割/跟踪…）
  modal   模态词（红外/医学/点云…）
  issue   失效场景（小目标/遮挡/低光照…）
  en      英文学术写法（infrared small target…）

匹配规则（命中分数从高到低）
--------------------------
  完全相等 > 前缀 > 拼音首字母 > 包含 > 子序列
只按前缀排的话，输「红外」看不到「热红外」；只按包含排，「检测」会把
「小目标检测」排到「检测」前面。所以要分层。

这个模块**不 import tkinter**，可单独跑自测：
    python autocomplete.py 红外
"""
import re
import sys

# ---------------------------------------------------------------- 拼音首字母
# 不引入 pypinyin（项目零新增依赖）。只覆盖方向词里常见字的声母，
# 覆盖不到就退回前缀/包含匹配，不会崩。
_INITIALS = {
    "红": "h", "外": "w", "与": "y", "低": "d", "光": "g", "视": "s", "觉": "j",
    "小": "x", "目": "m", "标": "b", "检": "j", "测": "c", "图": "t", "像": "x",
    "分": "f", "割": "g", "跟": "g", "踪": "z", "识": "s", "别": "b", "分": "f",
    "类": "l", "融": "r", "合": "h", "超": "c", "级": "j", "辨": "b", "率": "l",
    "增": "z", "强": "q", "去": "q", "雾": "w", "噪": "z", "模": "m", "型": "x",
    "扩": "k", "散": "s", "生": "s", "成": "c", "变": "b", "换": "h", "三": "s",
    "维": "w", "重": "c", "建": "j", "深": "s", "度": "d", "估": "g", "计": "j",
    "点": "d", "云": "y", "医": "y", "学": "x", "遥": "y", "感": "g", "无": "w",
    "人": "r", "机": "j", "事": "s", "件": "j", "相": "x", "热": "r", "成": "c",
    "多": "d", "谱": "p", "高": "g", "语": "y", "义": "y", "大": "d", "语言": "y",
    "对": "d", "比": "b", "习": "x", "自": "z", "监": "j", "督": "d", "半": "b",
    "知": "z", "蒸": "z", "馏": "l", "轻": "q", "量": "l", "化": "h", "剪": "j",
    "枝": "z", "注": "z", "意": "y", "力": "l", "网": "w", "络": "l", "神": "s",
    "经": "j", "强": "q", "元": "y", "开": "k", "放": "f", "词": "c", "汇": "h",
    "零": "l", "样": "y", "本": "b", "少": "s", "小": "x", "提": "t", "示": "s",
    "遮": "z", "挡": "d", "夜": "y", "间": "j", "照": "z", "实": "s", "时": "s",
    "跨": "k", "域": "y", "域": "y", "缺": "q", "陷": "x", "异": "y", "常": "c",
    "医": "y", "疗": "l", "手": "s", "术": "s", "工": "g", "业": "y", "卫": "w",
    "星": "x", "航": "h", "空": "k", "水": "s", "下": "x", "内": "n", "窥": "k",
    "镜": "j", "车": "c", "驾": "j", "驶": "s", "交": "j", "通": "t", "规": "g",
    "划": "h", "控": "k", "制": "z", "机": "j", "器": "q", "人": "r", "智": "z",
    "能": "n", "体": "t", "推": "t", "理": "l", "学": "x", "忆": "y", "储": "c",
    "存": "c", "性": "x", "频": "p", "时": "s", "序": "x", "列": "l", "预": "y",
    "警": "j", "入": "r", "侵": "q", "对": "d", "抗": "k", "攻": "g", "击": "j",
    "鲁": "l", "棒": "b", "泛": "f", "迁": "q", "移": "y", "联": "l", "邦": "b",
    "隐": "y", "私": "s", "公": "g", "平": "p", "可": "k", "解": "j", "释": "s",
    "评": "p", "价": "j", "基": "j", "准": "z", "数": "s", "据": "j", "集": "j",
    "标": "b", "注": "z", "合": "h", "成": "c", "检": "j", "索": "s", "文": "w",
    "档": "d", "问": "w", "答": "d", "对": "d", "话": "h", "智": "z", "代": "d",
    "码": "m", "程": "c", "编": "b", "译": "y", "器": "q", "软": "r", "件": "j",
    "工": "g", "系": "x", "统": "t", "网": "w", "络": "l", "安": "a", "全": "q",
    "数": "s", "库": "k", "云": "y", "计": "j", "算": "s", "分": "f", "布": "b",
    "式": "s", "并": "b", "行": "x", "高": "g", "性": "x", "能": "n", "图": "t",
    "计": "j", "算": "s", "金": "j", "融": "r", "时": "s", "空": "k", "据": "j",
}
_PUNCT = re.compile(r"[\s\-_/·、，,（）()]+")


def _is_pinyin_initial(ch):
    return "\u4e00" <= ch <= "\u9fff"


def initials(text):
    """中文串 → 拼音首字母串（覆盖不到的字原样保留，仍可被前缀命中）。

    字段名不能叫 s 再在循环里被 str 覆盖 —— 这里显式保留原始字，
    汉字取声母、非汉字取自身，最后拼起来。
    """
    chars = []
    for ch in _PUNCT.sub("", str(text or "").lower()):
        if _is_pinyin_initial(ch):
            got = _INITIALS.get(ch)
            chars.append(got if got else ch)
        else:
            chars.append(ch)
    return "".join(chars)





def _norm(s):
    return _PUNCT.sub("", str(s or "").lower())


# ---------------------------------------------------------------- 词表构建
_CACHE = {"key": None, "items": []}

# 高频组合：方向库是「类目→细分领域」，词表是散装单词，
# 两者之间缺一层「红外 → 红外小目标检测」这种组合。
# 这些是用户最常打的十二个方向词，手写进去，比让用户自己拼强。
# 加的方式很简单：后面写它的英文检索式，和 search_and 同口径。
_COMBOS = {
    "红外小目标检测": "infrared small object detection",
    "红外图像去雾": "infrared image dehazing",
    "红外可见光融合": "infrared visible image fusion",
    "医学图像分割": "medical image segmentation",
    "医学影像小目标": "medical small object",
    "点云语义分割": "point cloud semantic segmentation",
    "事件相机视觉": "event camera vision",
    "扩散模型生成": "diffusion model generation",
    "小样本目标检测": "few-shot object detection",
    "自监督预训练": "self-supervised pretraining",
    "轻量化目标检测": "lightweight object detection",
    "长尾分布识别": "long-tailed recognition",
    "多模态大模型": "multimodal large language model",
    "单目深度估计": "monocular depth estimation",
    "视频目标跟踪": "video object tracking",
    "遥感小目标检测": "remote sensing small object detection",
    "低光图像增强": "low-light image enhancement",
    "无监督域适应": "unsupervised domain adaptation",
    "知识蒸馏检测": "knowledge distillation object detection",
    "异常检测工业": "industrial anomaly detection",
}


def _add(items, seen, text, kind, weight, hint=""):
    text = str(text or "").strip()
    if not text or len(text) < 2:
        return
    key = text.lower()
    if key in seen:
        # 同一个词出现多次时保留权重最高的来源，但合并 hint
        old = seen[key]
        if weight > old["weight"]:
            old["weight"] = weight
            old["kind"] = kind
        if hint and hint not in old["hint"]:
            old["hint"] = (old["hint"] + " · " + hint).strip(" ·")
        return
    it = {"text": text, "kind": kind, "weight": weight, "hint": hint,
          "n": _norm(text), "ini": initials(text)}
    seen[key] = it
    items.append(it)


def build_items(force=False):
    """汇总所有词源。带进程内缓存 —— 方向库读盘约 0.1 秒，每次按键都读会卡。"""
    if _CACHE["items"] and not force:
        return _CACHE["items"]

    items = []
    seen = {}

    # 0) 高频组合排最前 —— 这是用户最可能想要的那几个词
    for cn, en in _COMBOS.items():
        _add(items, seen, cn, "combo", 120, "常用组合 · 检索式 " + en)

    # 1) 方向库（536 个细分领域 + 25 类目）
    try:
        import kb_widget as kb
        lib = kb.load_direction_library() or {}
        for cat, conf in lib.items():
            subs = conf.get("subs") if isinstance(conf, dict) else None
            _add(items, seen, cat, "field", 70, "方向类目")
            for sub in subs or []:
                name = sub.get("name") if isinstance(sub, dict) else str(sub)
                kws = (sub.get("keywords") or []) if isinstance(sub, dict) else []
                hint = "方向 · %s" % cat
                if kws:
                    hint += " · 含 " + "、".join(kws[:3])
                _add(items, seen, name, "field", 100, hint)
                for kw in kws[:6]:
                    _add(items, seen, kw, "en", 40, "英文学术写法")
    except Exception as exc:
        print("autocomplete: 方向库读取失败 %s" % exc, file=sys.stderr)

    # 2) 方向别名（同义说法 → 都能映射到同一个方向）
    try:
        import json
        from pathlib import Path
        fp = Path(__file__).resolve().parent / "direction_aliases.json"
        if fp.exists():
            data = json.loads(fp.read_text(encoding="utf-8"))
            # 实际结构：{"aliases": [{"category":..,"field":..,"terms":[..]}]}
            rows = (data.get("aliases") if isinstance(data, dict) else data) or []
            for g in rows:
                if not isinstance(g, dict):
                    continue
                field = g.get("field") or ""
                cat = g.get("category") or ""
                terms = g.get("terms") or []
                if len(terms) <= 1:
                    continue
                # 别名本身就常是「同一个方向的其他说法」，例如
                # 「轻量化模型 / 模型压缩 / 网络剪枝 / 推理加速」
                hint = "同义 · %s" % field
                if cat:
                    hint += " · %s" % cat
                for a in terms:
                    if a == field:
                        continue
                    _add(items, seen, a, "alias", 88, hint)
    except Exception as exc:
        print("autocomplete: 别名词表读取失败 %s" % exc, file=sys.stderr)

    # 3) 检索词表：方法 / 任务 / 模态 / 问题
    try:
        import arxiv_latest
        for cn in arxiv_latest.CN2EN:
            if any("\u4e00" <= ch <= "\u9fff" for ch in cn):
                _add(items, seen, cn, "keyword", 60, "检索词表")
    except Exception:
        pass
    try:
        import kb_vector
        for name, kind in (("_METHOD_CN", "method"), ("_HEAD_CN", "task"),
                           ("_MOD_CN", "modal"), ("_TASK_CN", "task")):
            for word in getattr(kb_vector, name, ()) or ():
                _add(items, seen, word, kind, 65, "检索词表")
    except Exception:
        pass

    items.sort(key=lambda it: (-it["weight"], len(it["text"])))
    _CACHE["items"] = items
    _CACHE["key"] = "v1"
    return items


def stats():
    items = build_items()
    by = {}
    for it in items:
        by[it["kind"]] = by.get(it["kind"], 0) + 1
    return {"total": len(items), "by_kind": by}


# ---------------------------------------------------------------- 打分
def _score(it, q, qn, qi):
    if not qn:
        return 0
    n = it["n"]
    w = it["weight"]
    if n == qn:
        return 1000 + w
    if n.startswith(qn):
        return 800 + w
    # 拼音首字母：打 hwx 能出「红外小目标检测」
    if qi and len(qi) >= 2 and it["ini"].startswith(qi):
        return 600 + w
    pos = n.find(qn)
    if pos >= 0:
        # 越靠前越相关；在词首附近额外加分
        base = 400 + w - min(pos, 30) * 2
        # 「只在词尾出现、前面挂着一大串」的重罚：
        # 输「去雾」不该先给「医学场景去雾的检测方法」，
        # 该先给「去雾」本身和「去雾霾」。
        if pos > 0 and pos + len(qn) >= len(n) - 1:
            base -= 120
        return base
    if qn in it["ini"]:
        return 200 + w
    return 0


def _last_token(q):
    """已经打了多个词时，只拿最后一个词去联想 —— 前面的词是已确定的检索条件。"""
    parts = [p for p in re.split(r"[,，;；\s]+", str(q or "")) if p]
    return parts[-1] if parts else ""


def suggest(query, limit=8, kinds=None):
    """返回候选列表 [{text, kind, hint, score}]，已按相关度排好、去重。

    query 为空时给「热门方向」（权重最高的若干个），让用户一聚焦就看到能点什么。
    """
    items = build_items()
    if kinds:
        items = [it for it in items if it["kind"] in kinds]
    q0 = str(query or "").strip()
    # 「去雾 图像」应当按最后一个词「图像」联想，而不是整串拿去匹配（整串必然 0 条）
    q = _last_token(q0) if q0 else ""
    if not q:
        hot = [it for it in items if it["kind"] in ("combo", "field", "method")]
        hot.sort(key=lambda it: -it["weight"])
        return [dict(it, score=0) for it in hot[:limit]]
    qn = _norm(q)
    # 拼音：把输入的每个字母也按声母处理，这样拼音和中文混打（hwx外）都能命中。
    # 但 capital/Term 这类纯拉丁输入不能当拼音去 match 中文串 —— 只在输入含中文
    # 或全小写时才生成声母串。
    qi = initials(q)
    has_cjk = any("\u4e00" <= ch <= "\u9fff" for ch in q)
    look_pinyin = has_cjk or q.islower()
    scored = []
    for it in items:
        s = _score(it, q, qn, qi if look_pinyin else "")
        if s > 0:
            scored.append((s, it))
    scored.sort(key=lambda p: -p[0])
    out = []
    seen_low = set()
    for s, it in scored:
        low = it["text"].lower()
        if low in seen_low:
            continue
        seen_low.add(low)
        out.append(dict(it, score=s))
        if len(out) >= limit:
            break
    return out


def apply_choice(entry_text, choice):
    """把选中的候选词拼进已输入的内容。

    规则：已经含有逗号/空格分隔的多个词时，追加成一个新的词；
    只有一个半截词时，用候选词替换它。
    这样「红外 去雾」里删掉去雾再选「医学」→ 「红外 医学」，而不是把整行吞掉。
    """
    raw = str(entry_text or "")
    parts = [p for p in re.split(r"[,，;；\s]+", raw) if p]
    if len(parts) >= 2:
        # 最后一个词是半截的，换成候选，别把前面已定的条件吞掉
        return " ".join(parts[:-1] + [str(choice)])
    return choice


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or ""
    print(stats())
    for it in suggest(q, limit=12):
        print("  %-28s %-8s %s" % (it["text"], it["kind"], it["hint"]))