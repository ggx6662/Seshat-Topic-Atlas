"""自检：画像是否真的在积累，提示词是否真的吃了画像。

跑法：
    D:\\miniconda3\\python.exe -X utf8 tools_test_personalize.py

这一层以前没有任何自动检查，所以出现了两个真实问题却没人发现：
  1. `profile_memory.learn_from_ideas()` 写好了但**从来没有被调用**
  2. 12 个页面只有 4 个在记，`tilt_inputs()` 一直返回 None，
     整套个性化逻辑一次都没生效过

所以这里测的不是「函数能跑」，而是：
  · 记一次之后，画像文件真的多了一条（不是被 except 吞掉）
  · 画像为空时提示词里**不出现**「我的情况」段（不能有空洞占位）
  · 画像有内容时，身份/约束/记忆都出现在提示词的正确位置
  · `recall()` 返回 dict 而不是列表时，记忆不会被渲染成 "items；total；shown"
"""
import json
import os
import sys
import tempfile
import traceback

import app_theme as T

FAILED = []
PASSED = []


def check(name, fn):
    try:
        fn()
        PASSED.append(name)
        print("  [OK]   " + name)
    except Exception as exc:
        FAILED.append((name, exc))
        print("  [FAIL] " + name + " — " + str(exc))
        traceback.print_exc()


def _isolate():
    """把画像指到临时文件，绝不碰用户真实的 researcher_profile.json。"""
    import profile_memory as PM
    d = tempfile.mkdtemp(prefix="kbprof_")
    PM.PROFILE_FILE = type(PM.PROFILE_FILE)(d) / "researcher_profile.json"
    PM.LOCK_FILE = type(PM.LOCK_FILE)(d) / ".lock"
    PM._cache = {"mtime": None, "data": None}
    import profile_hooks as PH
    PH.reset_stats()
    return PM, d


def main():
    print("\n==== 个性化自检 ====\n")

    # ---------------------------------------------------------- 1
    def t_empty_block():
        import prompt_context as PC
        assert PC.block() == "", "空画像不该生成任何文字，实际：" + repr(PC.block()[:80])
        assert PC.block({}, {}, []) == "", "空 dict 也应返回空"

    check("空画像不产生占位文字", t_empty_block)

    # ---------------------------------------------------------- 2
    def t_empty_gather():
        PM, d = _isolate()
        import prompt_context as PC
        g = PC.gather()
        assert g["ok"], "gather 不该报错：" + str(g["errors"])
        assert PC.block(g["profile"], g["constraints"], g["memories"]) == "", \
            "真实空画像下也不该产出段落"
        assert "我的情况" not in PC.block(g["profile"], g["constraints"], g["memories"])

    check("gather 在空画像下返回空段", t_empty_gather)

    # ---------------------------------------------------------- 3
    def t_record_persists():
        PM, d = _isolate()
        import profile_hooks as PH
        ok = PH.see_field("红外小目标检测", source="自检")
        assert ok, "see_field 返回 False，说明写盘失败：" + str(PH.stats())
        assert PM.PROFILE_FILE.exists(), "画像文件没被创建"
        p = PM.load()
        assert len(p.get("anchors") or []) == 1, \
            "应写入 1 条记忆，实际 %d" % len(p.get("anchors") or [])
        prefs = (p.get("preferences") or {}).get("fields") or {}
        assert prefs.get("红外小目标检测", 0) >= 1, "方向偏好没记上：" + str(prefs)
        h = PH.health()
        assert h["active"], "health 应判定为在积累：" + str(h)
        assert h["record_fail"] == 0, "不该有失败记录"

    check("记录一次后画像真的落盘", t_record_persists)

    # ---------------------------------------------------------- 4
    def t_search_only_zero():
        PM, d = _isolate()
        import profile_hooks as PH
        assert PH.search("mamba", "file", 42) is False, "有命中的检索不该写记忆"
        assert PH.search("冷门词xyz", "file", 0) is True, "零结果的检索应写记忆"
        texts = [a.get("text", "") for a in (PM.load().get("anchors") or [])]
        assert len(texts) == 1 and "冷门词xyz" in texts[0], \
            "只该留下零结果那一条：" + str(texts)

    check("只记零结果的检索", t_search_only_zero)

    # ---------------------------------------------------------- 5
    def t_recall_dict_shape():
        """recall() 返回 dict，直接喂给 _clean_memories 会把键名当内容。"""
        PM, d = _isolate()
        import profile_hooks as PH
        import prompt_context as PC
        PH.note("卡在 ROI 对齐的复现", tags=["复现"])
        g = PC.gather()
        mems = g["memories"]
        assert isinstance(mems, list), "gather 应把 recall 结果转成列表"
        block = PC.block(g["profile"], g["constraints"], mems)
        for bad in ("items", "total", "shown"):
            assert bad not in block, "记忆段里混进了 dict 键名 %r：%s" % (bad, block)
        assert "ROI" in block, "真实记忆没进提示词：" + block

    check("记忆不会被渲染成 dict 键名", t_recall_dict_shape)

    # ---------------------------------------------------------- 6
    def t_block_has_all_parts():
        import prompt_context as PC
        prof = {"identity": {"school": "某大学", "stage": "博士在读", "goal": "投 CVPR"},
                "state": {"urgency": 90, "mood": "焦虑"},
                "prefs": {"fields": {"红外": 5}, "angle": {"轻量化": 4}}}
        cons = {"compute": "单卡消费级", "months": "3 个月内", "avoid": ["纯理论"]}
        mem = [{"text": "ROI 对齐卡住"}]
        b = PC.block(prof, cons, mem, want="task")
        for need in ("某大学", "博士在读", "投 CVPR", "离截止很近", "焦虑",
                     "单卡消费级", "3 个月内", "纯理论", "轻量化", "ROI 对齐"):
            assert need in b, "缺字段 %r：\n%s" % (need, b)
        assert "的的" not in b, "文案有重复字"

    check("情况段包含身份/状态/约束/偏好/记忆", t_block_has_all_parts)

    # ---------------------------------------------------------- 6b
    def t_flat_tilt_shape():
        """tilt_inputs() 是**扁平**结构（urgency/mood 在顶层）。

        早期版本只读 profile["state"]["urgency"]，而真实调用方传的是扁平字典，
        于是一个人把紧迫度拉到 85、心境改成「焦虑」，提示词里一个字都没有 ——
        测试当时用的是自己编的嵌套结构，所以一直"通过"。这里两种都钉住。
        """
        import prompt_context as PC
        flat = {"urgency": 90, "interest": 40, "mood": "焦虑",
                "prefs": {"fields": {"红外小目标检测": 4.0}}, "has_profile": True}
        b = PC.block(flat, None, None)
        assert "离截止很近" in b, "扁平结构的紧急度没进提示词：\n" + b
        assert "焦虑" in b, "扁平结构的心境没进提示词：\n" + b
        nest = {"state": {"urgency": 90, "mood": "焦虑"}}
        b2 = PC.block(nest, None, None)
        assert "离截止很近" in b2 and "焦虑" in b2, "嵌套结构反而坏了：\n" + b2
        assert "身份" not in PC.block({"identity": {"stage": "硕士在读"}}, None, None), \
            "默认身份「硕士在读」不是用户填的，不该出现在提示词里"

    check("扁平与嵌套两种画像结构都能进提示词", t_flat_tilt_shape)

    # ---------------------------------------------------------- 7
    def t_weak_pref_ignored():
        """只存过 1 次的方向不该当成偏好 —— 否则第一次点一下就锁死了。"""
        import prompt_context as PC
        prof = {"prefs": {"fields": {"偶尔看看": 1}, "angle": {"试了一次": 1}}}
        b = PC.block(prof, {}, [])
        assert "偶尔看看" not in b, "权重 1 的方向不该进提示词"
        assert "试了一次" not in b, "权重 1 的角度不该进提示词"

    check("权重不足的偏好不算偏好", t_weak_pref_ignored)

    # ---------------------------------------------------------- 8
    def t_skill_prompt_injection():
        PM, d = _isolate()
        import profile_hooks as PH
        import research_skills as SK
        idea = {"title": "红外小目标", "desc": "跨域泛化"}
        bare = SK.skill_prompt("converge", idea)
        assert "我的情况" not in bare, "空画像下不该出现情况段"
        PH.constraints(compute="单卡消费级", months="3 个月内")
        prof, cons, mem = (lambda g: (g["profile"], g["constraints"], g["memories"]))(
            __import__("prompt_context").gather())
        rich = SK.skill_prompt("converge", idea, profile=prof, constraints=cons, memories=mem)
        assert "我的情况" in rich, "有约束时该出现情况段：\n" + rich[:400]
        assert "单卡消费级" in rich, "约束没进提示词"
        assert len(rich) > len(bare), "带画像的提示词应更长"

    check("方法论提示词吃画像", t_skill_prompt_injection)

    # ---------------------------------------------------------- 9
    def t_plan_prompt_injection():
        import research_skills as SK
        idea = {"title": "T", "desc": "d"}
        bare = SK.pipeline_prompt(idea)
        prof = {"identity": {"stage": "硕士在读"}, "state": {"urgency": 85}}
        rich = SK.pipeline_prompt(idea, None, profile=prof, constraints={}, memories=[])
        assert "背景：这个人是谁" in rich, "改进计划里该有背景段"
        assert "背景：这个人是谁" not in bare, "空画像不该有背景段"

    check("改进计划提示词吃画像", t_plan_prompt_injection)

    # ---------------------------------------------------------- 10
    def t_handoff_prompt_context():
        import kb_widget as kb
        cands = [{"title": "T1", "strategy": "稳健", "relevance": 70, "novelty": 60,
                  "feasibility": 80, "reason": "r", "questions": ["q"], "category": "CV",
                  "field": "检测"}]
        bare = kb.expanded_direction_prompt("红外", cands, dict(cands[0]))
        rich = kb.expanded_direction_prompt("红外", cands, dict(cands[0]),
                                            context="【我的情况】\n· 算力：单卡\n")
        assert "我的情况" not in bare
        assert "我的情况" in rich and "单卡" in rich, "交接提示词没吃 context"

    check("交接提示词吃画像", t_handoff_prompt_context)

    # ---------------------------------------------------------- 11
    def t_learn_ideas():
        """learn_from_ideas 以前从没被调用过。"""
        PM, d = _isolate()
        import profile_hooks as PH
        # 真实选题记录用的是 field（细分方向）+ category（大类），
        # 测试数据必须照这个结构，否则测的是一个现实中不会出现的形状
        ideas = [{"title": "红外小目标检测的改进", "field": "红外小目标检测",
                  "category": "计算机视觉", "desc": "轻量化模块", "type": "方法创新"},
                 {"title": "图像融合", "field": "图像融合",
                  "category": "计算机视觉", "desc": "跨模态融合", "type": "结构创新"}]
        assert PH.learn_ideas(ideas) is True, "learn_ideas 返回失败"
        p = PM.load()
        fields = (p.get("preferences") or {}).get("fields") or {}
        assert fields, "从选题库学不到任何方向偏好：" + str(p.get("preferences"))
        assert PH.learn_ideas([]) is False, "空列表不该写盘"

    check("选题库能折算成偏好", t_learn_ideas)

    # ---------------------------------------------------------- 12
    def t_failure_is_counted():
        """写盘失败必须被计数，不能像以前那样 except: pass 静默吞掉。"""
        PM, d = _isolate()
        # 用「父路径是文件」构造必然失败：mkdir(parents=True) 会抛 NotADirectoryError
        blocker = type(PM.PROFILE_FILE)(d) / "blocker"
        blocker.write_text("x", encoding="utf-8")
        import profile_hooks as PH
        PH.reset_stats()
        real = PM.PROFILE_FILE
        try:
            PM.PROFILE_FILE = blocker / "x.json"   # 父路径是文件 → 必失败
            ok = PH.note("这是一条会失败的记录")
        finally:
            PM.PROFILE_FILE = real
        assert ok is False, "写不进去时不该返回 True"
        s = PH.stats()
        assert s["fail"] >= 1, "失败没被计数：" + str(s)
        assert s["last_error"], "失败应保留错误摘要"

    check("写盘失败被计数而不是静默", t_failure_is_counted)

    # ---------------------------------------------------------- 13
    def t_health_when_empty():
        PM, d = _isolate()
        import profile_hooks as PH
        h = PH.health()
        assert h.get("active") is False, "什么都没记时不该判定为活跃：" + str(h)
        assert h.get("exists") is False

    check("空画像 health 判定为未启用", t_health_when_empty)

    # ---------------------------------------------------------- 14
    def t_corrupt_profile():
        """画像文件损坏时，记录要报错但不崩、不覆盖原文件。"""
        PM, d = _isolate()
        PM.PROFILE_FILE.write_text("{这不是 json", encoding="utf-8")
        import profile_hooks as PH
        PH.note("应该还能写")
        # 无论成败，界面不能崩；且 health 要能给出可读状态
        h = PH.health()
        assert isinstance(h, dict) and "active" in h, "health 崩了：" + str(h)

    check("画像损坏时不崩", t_corrupt_profile)

    print("\n==== 结果 ====")
    print("通过 %d / 失败 %d" % (len(PASSED), len(FAILED)))
    if FAILED:
        for n, e in FAILED:
            print("  ✗ %s — %s" % (n, e))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())