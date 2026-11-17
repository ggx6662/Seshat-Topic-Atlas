#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""科研方法论 Skill —— 把「怎么想出一个能站住的选题」变成可调用的模块。

为什么需要它
------------
之前应用能告诉你「缺 baseline」「缺消融」，但这只是清单勾选，
并没有教你**怎么补**。真正决定选题成败的是方法：

  * 怎么从一个模糊兴趣收敛到一个可证伪的问题
  * 怎么找到近邻工作、证明自己不是重复
  * 怎么设计「如果机制不成立就一定会显现」的实验
  * 怎么用审稿人的眼光提前杀死自己的课题

本模块把这些方法写成结构化的 SKILL（目标 / 步骤 / 产出 / 常见错误），
既能直接显示在界面上当教程，也能生成高质量的提示词交给外部 AI。

设计原则：每个 skill 都必须能被「做完」并「产出可检查的物件」，
不提供「多想想」「多调研」这类无法验收的废话。
"""

SKILLS = [
    {
        "id": "converge",
        "name": "问题收敛",
        "en": "Problem Converging",
        "when": "只有一个模糊兴趣（如「我对红外检测感兴趣」）",
        "goal": "把大方向收敛成一个具体的、有失败现场的问题",
        "steps": [
            "写下 3 个你在真实数据/文献里看到的具体失败：哪个场景、哪类样本、差多少",
            "对每个失败问：现有方法为什么在这里失败？答案必须是机制层面的，不能是「不够强」",
            "从 3 个失败里挑 1 个，把它写成「在 __ 条件下，现有方法在 __ 上失效，误差达到 __」",
            "确认这个失败不能靠「换更大的模型/更多数据」直接解决",
        ],
        "output": "一句话问题陈述（含条件、失效点、量化差距）+ 3 条排除理由",
        "pitfall": "把「提升性能」当问题。性能不是问题，某种条件下的失效才是。",
    },
    {
        "id": "novelty",
        "name": "新颖性核查",
        "en": "Novelty Check",
        "when": "已经有一句话问题陈述",
        "goal": "在投入实验前，确认这不是别人已经做过的工作",
        "steps": [
            "用问题的核心名词+方法词检索近 2 年 arXiv / 顶会，至少找 5 篇最近邻工作",
            "对每篇写一行：它做了什么、和你的差异在哪、这个差异重要吗",
            "如果最近邻工作已经覆盖你的差异，就只有三条路：换失效场景、换机制、换评测",
            "找出至少 3 个「别人没做但值得做」的理由（数据缺失、评测缺失、假设不成立）",
        ],
        "output": "近邻工作表（≥5 行）+ 差异声明 + 3 条新颖性理由",
        "pitfall": "只找支持自己的文献。必须主动找「可能已经做过」的那篇。",
    },
    {
        "id": "hypothesis",
        "name": "可证伪假设",
        "en": "Falsifiable Hypothesis",
        "when": "确定了机制差异",
        "goal": "把「我要改进 X」变成「如果机制成立，就会看到 Y」",
        "steps": [
            "写出主假设：因为 __ 机制，所以在 __ 条件下，__ 指标会 __（方向+幅度）",
            "写出零假设：如果机制无效，会看到什么（必须和主假设可区分）",
            "写出至少两条替代解释（参数量变大、数据泄漏、更长的训练），并各设计一个排除方式",
            "设定判定阈值：提升超过多少才算成立，低于多少算失败",
        ],
        "output": "主假设 + 零假设 + ≥2 条替代解释 + 数值阈值",
        "pitfall": "假设写成「会有提升」。没有方向和幅度的假设无法被证伪。",
    },
    {
        "id": "experiment",
        "name": "最小实验设计",
        "en": "Minimal Experiment",
        "when": "有了可证伪假设，还没开始写代码",
        "goal": "用两周以内的成本得到「继续 / 停止」的判断",
        "steps": [
            "选 1 个数据集、1 个最强 baseline、1 个主指标，其他全部先不管",
            "先复现 baseline（不改进），确认你复现出的数字可信",
            "只改机制的那一个变量，其他超参和 baseline 完全一致",
            "预先写下停止条件：跑完如果 __ 没达到 __，就判定机制不成立",
            "记录失败结果。负结果同样是产出，而且能省下后面三个月",
        ],
        "output": "实验表（基线/改动/指标/结果/是否通过）+ 一行结论",
        "pitfall": "一上来就做完整消融和全数据集。最小实验只回答一个问题。",
    },
    {
        "id": "evidence",
        "name": "证据门槛",
        "en": "Evidence Bar",
        "when": "最小实验有效果，想推进成完整课题",
        "goal": "确定「什么才算证据」，避免用弱证据说服自己",
        "steps": [
            "按创新类型确定必需证据：结构创新要看消融，方法创新要看机制归因",
            "列出 3 个强度递增的证据：能跑通 → 比 baseline 好 → 在其他数据集/场景也成立",
            "确定哪些证据是「必须有」、哪些是「加分项」，只有前者决定课题成败",
            "准备至少一个失败切片分析：在什么情况下你的方法反而更差",
        ],
        "output": "证据清单（必须/加分）+ 失败切片分析计划",
        "pitfall": "只报平均指标。平均提升掩盖失败的切片，正是审稿人最常攻击的点。",
    },
    {
        "id": "reviewer",
        "name": "审稿人视角",
        "en": "Reviewer Simulation",
        "when": "课题基本成形，准备投稿或申请",
        "goal": "用最挑剔的眼光提前找出致命问题",
        "steps": [
            "把自己当成不认识你、只读摘要的审稿人，写下你的第一反应：「这有什么新意？」",
            "按 Reject 顺序检查：问题不重要 → 已有工作 → 实验不足 → 结论过度",
            "写出 3 条最可能的拒稿理由，并各给出一条可执行的补救",
            "检查结论是否超出实验覆盖范围（在 A 数据集成立，不要声称普遍成立）",
        ],
        "output": "3 条拒稿理由 + 3 条补救方案 + 结论边界声明",
        "pitfall": "只在心里过一遍。必须写下来，写下来的才是真检查。",
    },
    {
        "id": "writeup",
        "name": "开题/投稿结构",
        "en": "Proposal Structure",
        "when": "实验有结果，要写开题报告或论文",
        "goal": "把课题组织成评审者期待的叙事结构",
        "steps": [
            "问题 → 现有方法的失败 → 你的机制 → 为什么它应该有效 → 证据链",
            "每一段都要能回答「上一段的结论从哪来」",
            "把「我们的贡献」写成 3 条可验证的陈述，每条对应一组实验",
            "最后写局限性：主动说出你不覆盖的场景，比被审稿人指出更好",
        ],
        "output": "五段式叙事骨架 + 3 条贡献陈述 + 局限性段落",
        "pitfall": "先写方法和实验，最后才想问题。评审者是从问题开始读的。",
    },
]


def get(skill_id):
    for s in SKILLS:
        if s["id"] == skill_id:
            return s
    return None


def all_names():
    return [s["name"] for s in SKILLS]


def skill_prompt(skill_id, idea, profile=None, constraints=None, memories=None):
    """把某个 skill 变成可交给 AI 的具体任务提示词。

    `profile` / `constraints` / `memories` 三样给了就拼成「我的情况」段插在
    课题描述之后；不给则现场从 profile_memory 取。**画像为空时这一段整段不出现**
    （`prompt_context.block` 返回空字符串），而不是写「暂无偏好」。
    以前这里完全不吃画像，同样的课题对研一和博四生成的是同一份提示词。
    """
    s = get(skill_id)
    if not s:
        return ""
    title = (idea.get("title") or "").strip()
    desc = (idea.get("desc") or "").strip()
    try:
        import prompt_context as PC
        ctx = PC.block(profile, constraints, memories, want="task")
    except Exception:
        ctx = ""
    lines = [
        "【科研方法论任务 · %s】" % s["name"],
        "",
        "我的课题：",
        "  标题：" + (title or "（未填）"),
        "  描述：" + (desc or "（未填）"),
        "",
    ]
    if ctx:
        lines.append(ctx)
    lines += [
        "这个环节的目标：" + s["goal"],
        "",
        "请严格按以下步骤带我完成，每步都要我给出具体内容，不要替我编造：",
    ]
    for i, step in enumerate(s["steps"], 1):
        lines.append("  %d. %s" % (i, step))
    lines += [
        "",
        "最终产出：" + s["output"],
        "常见错误（请帮我检查是否踩了）：" + s["pitfall"],
        "",
        "要求：",
        "  1. 如果我的描述里某一步信息缺失，直接指出缺什么，不要用通用套话填补",
        "  2. 每条建议都要能落到具体动作（看什么文献、跑什么对比、记什么数）",
        "  3. 最后按「已完成 / 仍缺失 / 下一步」三栏总结",
    ]
    return "\n".join(lines)


def pipeline_prompt(idea, diagnosis=None, profile=None, constraints=None, memories=None):
    """按课题当前缺口，自动挑选并串起最该做的几个 skill。

    「我的情况」放在最前面 —— 改进计划是长期任务，时间/算力/身份决定了
    该挑哪几个 SKILL、每一步能做多大。没有画像时这一段整段不出现。
    """
    order = ["converge", "novelty", "hypothesis", "experiment", "evidence", "reviewer"]
    missing = {m["key"] for m in (diagnosis or {}).get("missing", [])}
    pick = []
    if {"problem"} & missing:
        pick.append("converge")
    if {"baseline", "data"} & missing:
        pick.append("novelty")
    if {"mechanism"} & missing:
        pick.append("hypothesis")
    if {"metric", "ablation", "budget"} & missing:
        pick.append("experiment")
    if {"stop"} & missing or not missing:
        pick.append("evidence")
    if not pick:
        pick = ["reviewer"]
    # 保持方法论顺序
    pick = [p for p in order if p in pick] or ["reviewer"]

    lines = ["【科研选题改进计划】", ""]
    try:
        import prompt_context as PC
        ctx = PC.block(profile, constraints, memories, want="plan")
    except Exception:
        ctx = ""
    if ctx:
        lines += [ctx]
    lines += [
             "课题：" + (idea.get("title") or ""),
             "描述：" + (idea.get("desc") or "（未填）"), ""]
    if diagnosis:
        lines.append("结构诊断：%s（已具备 %s/%s 项）" % (
            diagnosis.get("stage", ""), diagnosis.get("count", {}).get("passed", "-"),
            diagnosis.get("count", {}).get("total", "-")))
        if diagnosis.get("missing"):
            lines.append("尚未交代：" + "、".join(m["label"] for m in diagnosis["missing"]))
        lines.append("")
    lines.append("请按下面顺序完成（每一步的产出我都要看到）：")
    for i, sid in enumerate(pick, 1):
        s = get(sid)
        lines.append("")
        lines.append("第 %d 步 · %s —— %s" % (i, s["name"], s["goal"]))
        for st in s["steps"]:
            lines.append("    - " + st)
        lines.append("    产出：" + s["output"])
    lines += ["", "不要跳过前面的步骤直接给方案；每步完成后再进入下一步。"]
    return "\n".join(lines)