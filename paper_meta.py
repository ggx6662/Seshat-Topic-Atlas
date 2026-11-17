"""从 PDF 全文里提取论文元数据：标题 / 作者 / 摘要 / 年份 / 体裁。

背景：文献库原本只有 name(文件名) / cat(目录) / path 三个字段，
371 条记录 title 全空。但 pdf_text_index.json 已缓存每篇前 6 页全文，
标题、作者、摘要就在里面，白白浪费了。

设计原则：
- 只用本地文本，不联网、不调 API —— 离线可算
- 提取不到就返回 None，绝不编造
- 摘要取 Abstract 后第一段，判"像不像摘要"而不是硬截 N 字
"""
import re
import os

# ── 摘要起始标记（多语言 / 多体裁） ─────────────────────────
_ABS_START = re.compile(
    r"\b(?:Abstract|ABSTRACT|A\s?B\s?S\s?T\s?R\s?A\s?C\s?T)\s*[—\-–:.\s]{0,6}",
)

# 摘要结束标记：后面出现这些词说明摘要完了
_ABS_END = re.compile(
    r"\n\s*(?:I{1,3}\s*\.\s*INTRODUCTION|1\s*\.?\s*INTRODUCTION|"
    r"Index Terms|Keywords|Key words|CCS Concepts|"
    r"I\.\s+INTRO|INTRODUCTION)\b",
    re.IGNORECASE,
)

# 摘要里不该出现的排版噪声
_NOISE = re.compile(r"arXiv:\S+|Preprint\.|Under review|©|Copyright|\d{4}\.\d{4,5}v\d")

# 标题常见的后续行标记（标题到这些词就结束）
_TITLE_END = re.compile(
    r"(Abstract\s*[—\-–:]|arXiv:\S+|\n\s*[∗†‡§¶]|\bUniversity\b|\bInstitute\b|"
    r"\bSchool of\b|\bDepartment of\b|@|Corresponding)",
    re.IGNORECASE,
)

# 年份候选
_YEARS = re.compile(r"\b(19[89]\d|20[0-4]\d)\b")

# 会议 / 期刊缩写
_VENUE_HINTS = [
    ("CVPR", "CVPR"), ("ICCV", "ICCV"), ("ECCV", "ECCV"), ("NeurIPS", "NeurIPS"),
    ("NIPS", "NeurIPS"), ("ICML", "ICML"), ("ICLR", "ICLR"), ("AAAI", "AAAI"),
    ("IJCAI", "IJCAI"), ("ACM MM", "ACM MM"), ("MM '", "ACM MM"),
    ("TPAMI", "TPAMI"), ("TIP", "TIP"), ("TMM", "TMM"), ("TGRS", "TGRS"),
    ("TNNLS", "TNNLS"), ("TCSVT", "TCSVT"), ("TITS", "TITS"),
    ("ICRA", "ICRA"), ("IROS", "IROS"), ("MICCAI", "MICCAI"),
    ("ACL", "ACL"), ("EMNLP", "EMNLP"), ("NAACL", "NAACL"),
    ("KDD", "KDD"), ("SIGIR", "SIGIR"), ("WWW", "WWW"),
    ("Remote Sensing", "Remote Sensing"), ("Sensors", "Sensors"),
    ("Applied Sciences", "Applied Sciences"),
]


def _clean(s):
    """压掉多余空白，把连字符换行接回单词。"""
    if not s:
        return ""
    s = s.replace("\r", "\n")
    # 行尾连字符 + 换行 = 单词被拆断，接回去
    s = re.sub(r"(\w)-\n(\w)", r"\1\2", s)
    # 双栏 PDF 抽成一行后没有换行，"connec- tions" 这种断词就留在了句中。
    # 只在两侧都是小写字母时拼接（避免把 "YOLO- SORT" / "GPT- 4" 拼坏）。
    s = re.sub(r"([a-z]{2,})-\s+([a-z]{2,})", r"\1\2", s)
    s = re.sub(r"[ \t\u00a0]+", " ", s)
    return s.strip()


def _looks_like_title(line):
    """判断一行像不像论文标题。"""
    if not line:
        return False
    s = line.strip()
    if len(s) < 8 or len(s) > 220:
        return False
    # 纯数字 / 纯符号
    if not re.search(r"[A-Za-z\u4e00-\u9fff]{3,}", s):
        return False
    # 邮箱 / URL / 编号行
    if "@" in s or "http" in s.lower():
        return False
    if re.fullmatch(r"[\d\W_]+", s):
        return False
    return True


def _split_title_authors(head):
    """在「Abstract 之前」的文本里，找出标题与作者的分界点。

    双栏 PDF 抽成一行后形如：
        MMA-Diffusion: MultiModal Attack on Diffusion Models Yijun Yang1, Ruiyuan Gao1, ...
        ^________________________ 标题 ______________________^ ^________ 作者 ________^

    分界点特征：第一次出现「名 姓 + 上标数字」或「名 姓 + ∗」且其后紧跟逗号/更多人名。
    返回 (标题结尾位置, 作者起始位置)；找不到返回 (None, 0)。
    """
    best = None
    for rx in (_ONE_AUTHOR, _ONE_AUTHOR_SYM):
        for m in rx.finditer(head):
            # 姓不能是标题里的学术常用词
            surname = m.group(2) if len(m.groups()) >= 2 else ""
            if surname in _NOT_A_NAME:
                continue
            if best is None or m.start() < best:
                best = m.start()
            break
    if best is None:
        return None, 0
    # 名字前面那个空格不算标题
    return best, best


def extract_title(text):
    """从全文开头提取标题。

    学术 PDF 开头：标题（可能折行，也可能与作者压在同一行）→ 作者 → 机构 → Abstract。

    难点：双栏 PDF 抽成一行后，标题、作者、机构全挤在一起，没有可靠分隔符。
    稳妥做法是「由后往前剪」：
        1. 取 Abstract 之前的全部文本
        2. 在文本中找**第一个作者标记**（名 姓 + 数字/星号），它之后都不是标题
        3. 若找不到，按长度上限截断
    """
    if not text:
        return None
    head = _clean(text[:3000])
    m = _ABS_START.search(head)
    before = head[:m.start()] if m else head[:1200]

    # 去掉开头的水印行（arXiv / Preprint / DOI …）
    before = re.sub(
        r"^(?:(?:arXiv|Preprint|Under Review|Published as|Accepted|DOI)[:.\s][^\n]{0,120}\n?){1,4}",
        "", before, flags=re.I).strip()
    if not before:
        return None

    # ── ① 找作者区起点：从最后一个作者标记往前推，取"密集相连"的那一段 ──
    hits = []
    for rx in (_ONE_AUTHOR, _ONE_AUTHOR_SYM):
        for mm in rx.finditer(before):
            hits.append((mm.start(), mm.end()))
    hits.sort()
    hits = [h for h in hits if h[1] > h[0]]

    cut = None
    if hits:
        # 从最后的命中开始，向前合并间隔 <= 40 字符的相邻命中
        seg_start = hits[-1][0]
        for s, e in reversed(hits[:-1]):
            if seg_start - e <= 40:
                seg_start = s
            else:
                break
        # 作者区起点前的那个空格不属于标题
        cut = seg_start
        # 名字前缀可能被粘上标题词：形如 "Capabilities Moritz Nottebaum1"
        # 「名 姓」里姓后面紧跟数字，名最多 2 词。若前缀名是小写普通词
        # （标题里的实词）而不是人名，就还回标题。
        head_seg = before[cut:cut + 80]
        hm = re.match(r"([A-Z][a-z'’\-]+)\s+([A-Z][a-z'’\-]+)\s+([A-Z][a-z'’\-]+)\d", head_seg)
        if hm:
            first = hm.group(1)
            # 标题实词特征：在 _NOT_A_NAME 里，或是个长而普通的英文词
            if first in _NOT_A_NAME or len(first) >= 8:
                cut += len(first) + 1

    # ①-b 兜底：名+姓+星号(无数字) 也算作者标记
    if cut is None:
        m2 = re.search(r"[A-Z][a-z'’\-]+(?:\s+[A-Z][a-z'’\-]+)?\s+([A-Z][a-z'’\-]+)\s*[*∗†‡§⋆]",
                       before)
        if m2 and m2.group(1) not in _NOT_A_NAME:
            cut = m2.start()
    # ①-c 兜底：出现 "名 姓 名 姓" 两个相邻人名（无上标）
    if cut is None:
        m3 = re.search(
            r"([A-Z][a-z'’\-]{2,})\s+([A-Z][a-z'’\-]{2,})\s+"   # 名 姓
            r"([A-Z][a-z'’\-]{2,})\s+([A-Z][a-z'’\-]{2,})(?:\s*(?:,|and|$))",
            before)
        if m3 and m3.group(2) not in _NOT_A_NAME and m3.group(3) not in _NOT_A_NAME:
            # 这一串从第一个名字开始，往前找到词边界
            seg_start = m3.start()
            if seg_start > 30:
                cut = seg_start

    t = before[:cut] if cut else before
    t = t.strip()

    # ── ② 还太长就按词边界截断 ──
    if len(t) > 300:
        t = t[:300]
        p = t.rfind(" ")
        if p > 150:
            t = t[:p]

    # ── ③ 削掉尾部悬空的人名 / 机构名 ──
    # 形如 "... Object Detection Jincheng Li* Chunyu Xie* Ji Ao Dawei Du"
    #   或 "... Detection Yu-Hsi Chen The University of Mel"
    t = re.sub(
        r"\s+(?:[A-Z][a-z'’\-]+(?:\s+[A-Z][a-z'’\-]+)?\s*[*∗†‡§⋆]?\s*){1,8}$",
        "", t) if re.search(r"[*∗†‡§⋆]", t) else t
    t = re.sub(r"\s+(?:The\s+)?(?:University|Institute|School|Department|College|"
               r"Laboratory|Lab\b|Faculty|Center|Centre|Academy).*$", "", t)
    # 尾部 "Yunze Xiao & Nan Di" / "Xiaotan Wei, Zhens..." 这类纯人名列表
    m_tail = re.search(
        r"\s+((?:[A-Z][a-z'’\-]{1,12}\s+){1,3}[A-Z][a-z'’\-]{1,14})(?:\s*[&,]\s*[A-Z][a-z'’\-]+)*\s*$",
        t)
    if m_tail and m_tail.start() > 30:
        # 被切掉的必须是**像人名**的词：不在 _NOT_A_NAME 里，
        # 否则 "Radar Object Detection" 这类正常结尾会被误伤。
        tail_words = m_tail.group(1).split()
        if all(w not in _NOT_A_NAME for w in tail_words):
            t = t[:m_tail.start()]
    # 尾部 "Currently, lightweight..." —— 摘要正文混进来了
    t = re.split(r"\s+(?:Currently|Recently|In this|Deep learning|Existing)\b", t)[0]

    # 尾部以 and / 逗号 结尾 → 明显被截断在人名中间，整条不可信
    if re.search(r"(?:\band|,|\*|†|‡|&)\s*$", t):
        return None

    # 尾部悬空介词：标题被剪掉了最后一两个词，只剩 "…Computing System on"。
    # 这种残缺标题会连累质量分，导致退回文件名变成 "ICCV2025-36"。
    # 只删掉悬空介词本身是够的 —— 前面的 "Mixture of Experts Computing System"
    # 已经是完整语义。注意不能整条丢弃。
    t = re.sub(r"\s+(?:on|of|for|in|at|to|with|by|via|from|and|the|a|an)\s*$",
               "", t, flags=re.I).strip(" .,;:-")

    t = re.sub(r"\s+", " ", t).strip(" .,;:-")
    t = _strip_banner(t)
    # 削掉尾部期刊信息：". Sensors 2024, 24, 4639." / "2024, 24(5): 1234"
    t = re.sub(r"\.?\s*[A-Z][A-Za-z &]{2,40}\s+\d{4},\s*\d+(\s*\(\d+\))?\s*,\s*\d+\.?$", "", t)
    t = re.sub(r"\s+", " ", t).strip(" .,;:-")
    if len(t) < 10:
        return None
    if _is_garbage_title(t):
        return None
    return t


# 明显不是标题的文本（许可证 / 会议横幅 / 版权 / 图书馆编号 / 投稿信息）
_GARBAGE_TITLE = re.compile(
    r"(licensed under|creative commons|all rights reserved|copyright|"
    r"permission to make|proceedings of the|ieee international conference|"
    r"manuscript received|authorized licensed use|downloaded (?:from|on)|"
    r"see discussions|publication in this|isbn|issn|doi:|\bfigure\s*\d|"
    r"^\s*this work\s|^\s*the\d{3}|"
    r"received\s+\d{1,2}\s+\w+\s+\d{4}|accepted\s+\d{1,2}\s+\w+\s+\d{4}|"
    r"date of publication|date of current version|"
    r"ieee (?:journal|transactions|geoscience)|society section|"
    r"^\d{3,5}\s+ieee|"
    # 摘要句被当成标题：这些开头一定是正文，不是标题。
    # 注意整段是「A|B|C」式交替而**没有外层分组** ——
    # 每组 (?:...) 必须自己闭合，多一层就会报 unterminated subpattern。
    r"^\s*(?:we\s+(?:present|propose|introduce|show|argue|study))\b|"
    r"^\s*(?:in this (?:paper|work))|^\s*(?:this (?:paper|work|article|letter))\b|"
    r"^\s*recently\s*,|^\s*in recent years|^\s*over the past|"
    r"^\s*as (?:a|an) (?:result|consequence)|"
    r"^\s*deep learning has|^\s*the (?:rapid|recent) (?:development|advance))",
    re.IGNORECASE,
)


def _strip_banner(t):
    """削掉标题前面的期刊横幅 / 引用格式 / 页眉。"""
    if not t:
        return t
    # IEEE TRANSACTIONS ON XXXX, VOL. 63, 2025 3001515 <真标题>
    t = re.sub(
        r"^IEEE\s+TRANSACTIONS\s+ON\s+[A-Z ,&-]{4,80},\s*VOL\.?\s*\d+[^A-Z]{0,20}\d{3,7}\s*",
        "", t, flags=re.I)
    # Citation: Zhang, R.; Xu, L.; ... <真标题>  或  Citation: <真标题>
    if re.match(r"^citation\s*:", t, re.I):
        t = re.sub(r"^citation\s*:\s*", "", t, flags=re.I)
        # 如果后面紧跟 "张三, 李四;" 样式的作者串，跳过它
        t2 = re.sub(r"^(?:[A-Z][a-z']+,\s*[A-Z]\.\s*(?:;\s*)?){1,12}", "", t)
        if len(t2) > 20:
            t = t2
    # Research Article / Original Paper 之类
    t = re.sub(r"^(?:research|original|regular)\s+(?:article|paper|contribution)\s*[:.]?\s*",
               "", t, flags=re.I)
    # 地名+日期的会议横幅：2024 IEEE International Conference...
    t = re.sub(r"^\d{4}\s+IEEE\s+(?:International\s+)?(?:Conference|Workshop|Symposium)\s+on\s+",
               "", t, flags=re.I)
    return t.strip(" .,;:-")


def _is_garbage_title(t):
    """判断提取结果是否其实是许可证 / 会议横幅 / 版权行。"""
    if not t:
        return True
    if _GARBAGE_TITLE.search(t):
        return True
    # 数字占比过高（页码、编号、ISBN）
    digits = sum(c.isdigit() for c in t)
    if digits > len(t) * 0.35:
        return True
    # 没有足够的字母
    if len(re.findall(r"[A-Za-z]{3,}", t)) < 2:
        return True
    return False


def extract_abstract(text):
    """提取摘要正文。"""
    if not text:
        return None
    # 从 8000 字符内找 Abstract（通常在首页）
    zone = _clean(text[:9000])
    m = _ABS_START.search(zone)
    if not m:
        return None
    body = zone[m.end():]
    # 找到摘要结束处
    e = _ABS_END.search(body)
    if e:
        body = body[:e.start()]
    if not body:
        return None

    body = _NOISE.sub(" ", body)
    body = re.sub(r"\s+", " ", body).strip()

    # 摘要一般 300~2500 字符。太短说明截错了，太长说明没截断
    if len(body) < 120:
        return None
    if len(body) > 2600:
        # 在句子边界处截断
        cut = body[:2600]
        p = cut.rfind(". ")
        body = cut[:p + 1] if p > 600 else cut

    return body.strip()


# 标题里常见、但绝不会是"姓"的词——防止把标题尾巴误判成作者
# 注：这些词只能用于"不要在这里切"，不能用于"标题不能以它结尾"，
#     否则 "Object Detection" / "Multi-modal Learning" 这类正常结尾会被误杀。
_NOT_A_NAME = {
    "Models", "Model", "Modeling", "Modelling", "Methods", "Method", "Learning", "Deep",
    "Networks", "Network", "Detection", "Recognition", "Segmentation", "Tracking",
    "Attention", "Vision", "Visual", "Language", "Multimodal", "Multi", "Image", "Images",
    "Video", "Object", "Objects", "Prompt", "Prompts", "Prompting", "Generative", "Generation",
    "Diffusion", "Transformer", "Transformers", "Fusion", "Feature", "Features", "Robust",
    "Robustness", "Efficient", "Towards", "Rethinking", "Survey", "Review", "Task", "Tasks",
    "Knowledge", "Graph", "Graphs", "Data", "Training", "Inference", "Estimating", "Estimation",
    "System", "Systems", "Approach", "Approaches", "Framework", "Framework", "Benchmark",
    "Evaluation", "Analysis", "Understanding", "Towards", "Learning", "Adaptive", "Dynamic",
    "Semantic", "Structural", "Structure", "Alignment", "Retrieval", "Reasoning", "Planning",
    "Control", "Policy", "Spatial", "Temporal", "Global", "Local", "Cross", "Self", "Super",
    "Semi", "Weakly", "Zero", "Few", "Open", "Large", "Small", "Object", "Instance", "Scene",
    "Depth", "Pose", "Motion", "Action", "Event", "Point", "Cloud", "Closure", "Scale",
    "Anomaly", "Adversarial", "Attack", "Privacy", "Safety", "Explainable", "Interpretable",
    "Calibration", "Distillation", "Pruning", "Quantization", "Compression", "Acceleration",
}

# 单个作者：名(最多2词) 姓 上标数字(可多个)
#   例: Yijun Yang1 / Tsung-Yi Ho1 / Nan Xu3,4 / Xiaosen Wang2
# 注意：名部分必须限长。写成 * 会贪婪地把 "Diffusion Models Yijun Yang1"
# 整体吃成「名=Diffusion Models Yijun，姓=Yang」，标题尾巴就被当成作者了。
_ONE_AUTHOR = re.compile(
    r"([A-Z][a-z'’\-]+(?:\s+[A-Z][a-z'’\-]+)?)\s+([A-Z][a-z'’\-]+)\s*"
    r"(\d{1,2}(?:\s*,\s*\d{1,2})*)"
)

# 也可能是纯符号上标: Yijun Yang∗ / Ruiyuan Gao†
_ONE_AUTHOR_SYM = re.compile(
    r"([A-Z][a-z'’\-]+(?:\s+[A-Z][a-z'’\-]+)?)\s+([A-Z][a-z'’\-]+)\s*([∗†‡§⋆¶])"
)

# 机构 / 地名 起始词（作者串到这里必须结束）
_STOP_WORDS = re.compile(
    r"\b(?:The|Chinese|University|Universities|Institut[eo]|School|Department|College|"
    r"Laboratory|Lab|Faculty|Center|Centre|Academy|Inc|Ltd|Corporation|Company|"
    r"Huawei|Microsoft|Google|Meta|NVIDIA|Alibaba|Tencent|Baidu|ByteDance|"
    r"Beijing|Shanghai|Hong\s+Kong|Taipei|Taiwan|China|Singapore|Japan|Korea|"
    r"Abstract|Keywords?|Preprint|arXiv)\b"
)


def extract_authors(text, title=None):
    """提取作者名串。

    双栏 PDF 抽出来常压成一整行（实测某篇前 2000 字符 0 个换行），
    所以按"人名+上标数字"模式找。

    关键：作者串必须**紧跟在标题之后**。若不先定位标题结尾，
    会把标题尾巴（如 "Diffusion Models"）当成作者的第一个名字。
    """
    if not text:
        return None
    head = _clean(text[:3500])
    m = _ABS_START.search(head)
    if m:
        head = head[:m.start()]
    else:
        head = head[:1800]

    # ① 先确定作者区起点：标题在 head 中的结束位置
    start_at = 0
    if title:
        # 标题到 head 中可能被换行/空格改写，用前 20 字符做锚
        t_norm = re.sub(r"\s+", " ", title)
        anchor = t_norm[:20]
        pos = head.find(anchor)
        if pos >= 0:
            start_at = pos + len(t_norm)
            # 2026-11-15 修：传进来的 title 有可能**尾部被截断**
            # （extract_title 收在 "Infrared Small Object"，正文里实际是
            #  "...Infrared Small Object Detection"）。上面那行只把游标推到
            #  title 尾部，剩下的 "Detection" 就被当成作者名的一部分，
            #  产出 "Detection Zihan Liu, ..." 这种脏数据（343 篇里 3 篇）。
            # 这里再往后看一小段：若紧跟的词与 title 末尾的词同源（大小写不敏感），
            # 说明标题还没走完，继续把游标推到该词之后。
            tail_word = t_norm.split()[-1] if t_norm.split() else ""
            if tail_word:
                guard = 0
                while guard < 6:
                    guard += 1
                    mm = re.match(r"[\s\-–—:]+([A-Za-z][A-Za-z\-]*)", head[start_at:])
                    if not mm:
                        break
                    nxt = mm.group(1)
                    # 只在「下一个词和标题尾词相同/互为前缀」时才吞掉，
                    # 否则会把作者名（如 "Detection" 后的 "Zihan"）也吃掉
                    if (nxt.lower() == tail_word.lower()
                            or nxt.lower().startswith(tail_word.lower())
                            or tail_word.lower().startswith(nxt.lower())):
                        start_at += mm.end()
                        tail_word = nxt
                        continue
                    break
    if start_at == 0:
        # 没传标题时退化为：从 Abstract 前 40% 处开始找
        start_at = int(len(head) * 0.25)

    zone = head[start_at:start_at + 700]

    hits = []
    for rx in (_ONE_AUTHOR, _ONE_AUTHOR_SYM):
        for am in rx.finditer(zone):
            full = " ".join(x for x in am.groups()[:2] if x)
            hits.append((am.start(), am.end(), full))
    if not hits:
        return None
    hits.sort()

    # ② 合并相邻命中：中间只隔逗号/空格/and 才连成一串
    runs = []
    cur_s, cur_e, cur_names = hits[0][0], hits[0][1], [hits[0][2]]
    for s, e, name in hits[1:]:
        gap = zone[cur_e:s]
        if len(gap) <= 12 and re.fullmatch(r"[\s,;]*|[\s,;]+and[\s,]+", gap):
            cur_e = e
            cur_names.append(name)
        else:
            runs.append((cur_s, cur_e, cur_names))
            cur_s, cur_e, cur_names = s, e, [name]
    runs.append((cur_s, cur_e, cur_names))

    # ③ 取作者数最多的那串
    runs.sort(key=lambda r: (len(r[2]), r[1] - r[0]), reverse=True)
    for s, e, names in runs:
        good = [n for n in names if not _STOP_WORDS.search(n)]
        if not good:
            continue
        # 2026-11-15 修：首段若以标题的尾词开头（"Models Prabhavathy Pachaiyappan"
        # 里的 Models），说明切分点落在标题内部，剥掉这个词。
        # 这类 PDF（MDPI/Elsevier 模板）标题不是首行，extract_title 返回 None，
        # 走兜底的 25% 偏移正好切在标题中间。
        if title:
            tw = [w for w in re.split(r"\s+", title.strip()) if w]
            if tw:
                last = tw[-1]
                head_words = good[0].split()
                if len(head_words) >= 3 and head_words[0].lower() == last.lower():
                    good[0] = " ".join(head_words[1:])
        if len(good) < 2 and len(good[0]) < 12:
            continue
        out = ", ".join(good)
        if len(out) >= 4:
            return out[:300]
    return None


def guess_year(text, path=""):
    """猜年份：优先看路径（ICCV2025-3.pdf），再看正文里的 arXiv 编号。"""
    if path:
        m = _YEARS.search(os.path.basename(path))
        if m:
            return int(m.group(1))
    if text:
        # arXiv 编号 2512.12345v1 → 2025 年 12 月
        m = re.search(r"arXiv:\s*(2\d)(\d{2})\.\d{4,5}", text[:2000])
        if m:
            yy = int(m.group(1))
            return 2000 + yy
    return None


def guess_venue(text, path=""):
    """猜会议/期刊：优先路径，再看正文首页。"""
    blob = (os.path.basename(path) if path else "") + " " + (text or "")[:3000]
    for key, name in _VENUE_HINTS:
        if key in blob:
            return name
    return None


def is_survey(text, title=""):
    """判断是否综述。"""
    blob = ((title or "") + " " + (text or "")[:1500]).lower()
    for kw in ("review", "survey", "综述", "overview", "state of the art"):
        if kw in blob:
            return True
    return False


def extract(path, text):
    """主入口：给路径和全文，返回元数据字典。"""
    title = extract_title(text)
    authors = extract_authors(text, title)   # 依赖标题定位作者起点
    return {
        "title": title,
        "authors": authors,
        "abstract": extract_abstract(text),
        "year": guess_year(text, path),
        "venue": guess_venue(text, path),
        "is_survey": is_survey(text, title),
        "has_text": bool(text and len(text) > 500),
    }