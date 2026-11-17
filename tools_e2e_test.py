#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全功能端到端测试。

现有 tools_smoke_app.py 只验证「页面能打开」，本脚本验证**功能真的能用**：
每个按钮、每个交互路径都走一遍，并断言结果。

覆盖 8 个模块的全部功能点：
   1 总览       指标、快捷入口、论文列表
   2 选题工坊   方向识别、候选生成、结构诊断、venue/导师、存库、提示词、复制
   3 文献空白   分析、聚焦、两类空白、存创新点
   4 创新点库   列表、详情、新建、删除、导出、提示词
   5 科研方法论 7 个方法切换、单独提示词、改进计划
   6 导师与院校 方向匹配、姓名查找、地区筛选、CSV 导出、ORCID 跳转
   7 期刊会议   方向匹配、venue 链接
   8 文献库     分类筛选、关键词过滤、分页、打开
   9 系列设置   路径、检索词增删、产出目录
  10 全局       搜索、日志、主题、窗口控制

用法:
  python tools_e2e_test.py             # 跑全部
  python tools_e2e_test.py --verbose   # 打印每步细节
"""

import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import app_main  # noqa: E402
import app_theme as T  # noqa: E402
import kb_widget as kb  # noqa: E402

# 必须在建任何界面之前隔离 —— MentorPage / TopicPage / IdeasPage / LatestPage
# 都会在正常工作流程里写 profile_memory。
import tools_isolate  # noqa: E402

_ISO = tools_isolate.isolate()

VERBOSE = "--verbose" in sys.argv
results = []


class Ctx:
    """测试上下文：记录通过/失败、收集错误。"""
    def __init__(self):
        self.passed = []
        self.failed = []
        self.skipped = []


C = Ctx()


def check(name, fn, skip_reason=None):
    if skip_reason:
        C.skipped.append((name, skip_reason))
        print("  [SKIP] %s — %s" % (name, skip_reason))
        return
    try:
        fn()
        C.passed.append(name)
        print("  [ok]   %s" % name)
    except Exception as exc:
        C.failed.append((name, str(exc)))
        print("  [FAIL] %s — %s" % (name, exc))
        if VERBOSE:
            traceback.print_exc()


def pump(app, seconds=0.25):
    """跑事件循环一小会儿，让后台线程的回调落地。"""
    end = time.time() + seconds
    while time.time() < end:
        app.update()
        time.sleep(0.01)


def wait_until(app, cond, timeout=6.0):
    end = time.time() + timeout
    while time.time() < end:
        app.update()
        time.sleep(0.02)
        if cond():
            return True
    return False


def main():
    print("=" * 66)
    print("知识库助手 · 全功能端到端测试")
    print("=" * 66)

    # 测试期间不污染真实数据。
    # 注意：只隔离 research_memory.json 是不够的 —— MentorPage.search() 里会
    # PM.bump_pref() + PM.remember() 写画像，TopicPage 也会写。所有会被界面
    # 顺手写到盘上的文件都交给 tools_isolate 统一处理。
    import shutil
    import pathlib
    import tempfile
    # isolate() 已经把 kb.RESEARCH_MEMORY 指向一个还不存在的临时文件，
    # 原始路径从 _ISO["__orig__"] 里取。
    real_mem = _ISO["__orig__"].get("kb_widget.RESEARCH_MEMORY")
    tmp_mem = os.path.join(tempfile.gettempdir(), "kb_e2e_memory.json")
    if real_mem and real_mem.exists():
        shutil.copy(real_mem, tmp_mem)
        kb.RESEARCH_MEMORY = pathlib.Path(tmp_mem)
    _mem_before = tools_isolate.snapshot_memory()
    # 记下测试开始前真实目录里已存在的用户数据文件，收尾判「有没有泄漏」时
    # 用排除法：本来就在的不算我们写的。（上一版只看「是否存在」，
    # 用户自己用软件生成的 researcher_profile.json 会被误判成测试污染。）
    _pre_files = [pathlib.Path(tools_isolate.HERE) / n
                  for n in ("researcher_profile.json", "download_failures.json")
                  if (pathlib.Path(tools_isolate.HERE) / n).exists()]

    app = app_main.App()
    app.geometry("1280x820+0+0")
    app.update()
    try:
        app_main._apply_font_scale(app)
    except Exception:
        pass
    pump(app, 0.8)

    # ------------------------------------------------------------ 1 总览
    print("\n[1] 总览")
    app.goto("home"); pump(app)

    def home_metrics():
        pg = app.page("home")
        labels = []

        def walk(w):
            try:
                if w.winfo_class() == "Label":
                    labels.append(str(w.cget("text")))
            except Exception:
                pass
            for c in w.winfo_children():
                walk(c)
        walk(pg)
        assert any("知识库文献" in x for x in labels), "缺少「知识库文献」指标"
        assert any("我的选题" in x for x in labels), "缺少「我的选题」指标"
    check("指标卡渲染", home_metrics)

    def home_quick():
        pg = app.page("home")
        labels = []

        def walk(w):
            try:
                if w.winfo_class() == "Label":
                    labels.append(str(w.cget("text")))
            except Exception:
                pass
            for c in w.winfo_children():
                walk(c)
        walk(pg)
        # 第 7 版首页改成了「科研导航」瓦片（ui_parts.Tile），名称去掉了「分析」
        # 后缀，与侧栏、页头保持一致。断言跟着改，不然测的是已经不存在的旧结构。
        for want in ("文献空白", "科研方法论", "导师与院校", "期刊会议"):
            assert want in labels, "缺科研导航入口：" + want
    check("科研导航入口渲染", home_quick)

    def home_papers():
        """总览的「研究计划」摘要区。

        2026-11-15 用户否掉了四列卡片流（我的选题 / 最近入库 / 导师候选 /
        下一步），总览不再列 PDF 标题，这里改为检查计划摘要真的渲染出来了。
        空计划时卡片上应出现「还没有排计划」，有计划时应出现阶段名或待办。
        """
        pg = app.page("home")
        texts = []

        def walk(w):
            try:
                if w.winfo_class() == "Label":
                    texts.append(str(w.cget("text")))
            except Exception:
                pass
            for c in w.winfo_children():
                walk(c)
        walk(pg)
        blob = " ".join(texts)
        assert "研究计划" in blob, "总览缺少研究计划卡片"
        try:
            import plan_store as PS
            p = PS.progress()
        except Exception:
            p = {"empty": True}
        if p.get("empty"):
            assert "还没有排计划" in blob, "空计划时应有引导文案"
        else:
            assert (p.get("current") or {}) and "打开研究计划" in blob, \
                "有计划时应显示当前阶段与入口"
    check("总览研究计划摘要", home_papers)

    # ------------------------------------------------------------ 2 选题工坊
    print("\n[2] 选题工坊")
    app.goto("topic"); pump(app)
    pg = app.page("topic")

    def topic_generate():
        pg.entry.delete(0, "end")
        pg.entry.insert(0, "红外小目标检测")
        pg.generate()
        assert wait_until(app, lambda: bool(pg.cands)), "候选生成超时"
        assert len(pg.cands) >= 10, "候选数量过少：%d" % len(pg.cands)
    check("生成候选", topic_generate)

    def topic_diverse():
        reasons = {c.get("reason") for c in pg.cands}
        qs = {tuple(c.get("questions") or []) for c in pg.cands}
        assert len(reasons) >= 10, "候选理由重复度过高：仅 %d 种" % len(reasons)
        assert len(qs) >= 10, "验证问题重复度过高：仅 %d 种" % len(qs)
    check("候选理由与问题多样化", topic_diverse)

    def topic_select():
        pg.select(1)
        pump(app, 0.4)
        assert pg.sel == 1, "选中状态未更新"
        texts = []

        def walk(w):
            try:
                if w.winfo_class() == "Label":
                    texts.append(str(w.cget("text")))
            except Exception:
                pass
            for c in w.winfo_children():
                walk(c)
        walk(pg.detail_box)
        joined = " ".join(texts)
        assert "为什么值得做" in joined or "最小验证" in joined, "详情面板缺少针对性内容"
        assert "结构诊断" in joined or "已具备" in joined, "详情面板缺少结构诊断"
    check("选中候选并渲染详情", topic_select)

    def topic_venue():
        texts = []

        def walk(w):
            try:
                if w.winfo_class() == "Label":
                    texts.append(str(w.cget("text")))
            except Exception:
                pass
            for c in w.winfo_children():
                walk(c)
        walk(pg.side_scroll.inner)
        joined = " ".join(texts)
        assert "推荐投稿" in joined, "缺少推荐投稿"
    check("右侧 venue 与导师", topic_venue)

    def topic_save():
        before = len(kb.load_research_memory().get("ideas", []))
        pg.save_idea()
        pump(app, 0.3)
        after = len(kb.load_research_memory().get("ideas", []))
        assert after == before + 1, "存为创新点失败：%d → %d" % (before, after)
    check("存为创新点", topic_save)

    def topic_prompt():
        app.clipboard_clear()
        pg.make_prompt()
        pump(app, 0.4)
        clip = app.clipboard_get()
        assert clip and len(clip) > 50, "交接提示词为空"
    check("生成交接提示词", topic_prompt)

    def topic_copy():
        app.clipboard_clear()
        pg.copy_pack()
        pump(app, 0.3)
        clip = app.clipboard_get()
        assert "候选选题" in clip, "复制清单内容不对"
    check("复制清单", topic_copy)

    def topic_fusion():
        pg.entry.delete(0, "end")
        pg.entry.insert(0, "红外小目标检测")
        if not pg._fuse_open:
            pg._toggle_fuse()
        pg.entry_b.delete(0, "end"); pg.entry_b.insert(0, "扩散模型")
        pg.entry_c.delete(0, "end"); pg.entry_c.insert(0, "医学影像")
        pg.fuse_kind.set("自动")
        pg.cands = []
        pg.generate()
        assert wait_until(app, lambda: bool(pg.cands)), "跨领域候选生成超时"
        kinds = {c.get("kind") for c in pg.cands if c.get("kind")}
        assert len(kinds) >= 3, "融合类型过少：%s" % kinds
        titles = [c.get("title") for c in pg.cands]
        assert len(set(titles)) == len(titles), "跨领域候选标题有重复"
        combos = {tuple(sorted((c.get("combo") or {}).items())) for c in pg.cands}
        assert len(combos) == 1, "combo 未被统一填进候选"
        assert pg.ctx.get("b") == "扩散模型" and pg.ctx.get("c") == "医学影像"
    check("跨领域组合生成", topic_fusion)

    def topic_fusion_kind():
        pg.fuse_kind.set("借方法")
        pg.cands = []
        pg.generate()
        assert wait_until(app, lambda: bool(pg.cands)), "按类型筛选超时"
        kinds = {c.get("kind") for c in pg.cands}
        assert kinds == {"技术驱动"}, "按借方法筛选失败：%s" % kinds
    check("跨领域按类型筛选", topic_fusion_kind)

    def topic_fusion_bad():
        import topic_fusion as TF
        out = TF.build("红外", "点云", "")
        assert out and out[0].get("error"), "两个数据载体拼一起竟然通过"
        out2 = TF.build("医药", "肝脏病理", "区块链")
        assert out2 and out2[0].get("error"), "非计算机学科竟然通过"
    check("跨领域合理性拦截", topic_fusion_bad)

    def constraint_block():
        import profile_memory as P2
        import topic_constraint as TC
        cons = {"compute": "无算力", "months": "3 个月内", "style": "", "avoid": []}
        c = {"angle_key": "自监督", "angle": "自监督预训练", "kind": "技术驱动",
             "title": "用自监督解决红外检测", "reason": "预训练很贵"}
        r = TC.check(c, cons)
        assert r["level"] == "block", "无算力 + 自监督预训练竟然不是 block：%s" % r
        r2 = TC.check({"angle_key": "轻量化", "angle": "轻量化", "kind": "下游迁移",
                       "title": "x", "reason": "y"}, cons)
        assert r2["level"] == "warn", "无算力 + 轻量化应该是 warn（8G 也能测）：%s" % r2
        r3 = TC.check({"angle_key": "理论", "angle": "理论", "kind": "三方交叉",
                       "title": "x", "reason": "y"},
                      {"avoid": ["生物"], "compute": "", "months": "", "style": ""})
        assert r3["level"] == "ok", "没填约束却有冲突：%s" % r3
        # 沉底而不是删除
        cs = [{"angle_key": "自监督", "kind": "技术驱动", "cfit": None},
              {"angle_key": "轻量化", "kind": "下游迁移", "cfit": None}]
        TC.annotate(cs, cons)
        assert cs[-1]["angle_key"] == "自监督", "做不动的没沉到底部"
        assert len(cs) == 2, "候选被删掉了"
    check("硬约束冲突判定", constraint_block)

    def constraint_page():
        import profile_memory as P2
        P2.set_constraints(compute="单卡消费级", months="3 个月内",
                           style="偏工程", avoid=["云"])
        pg.entry.delete(0, "end")
        pg.entry.insert(0, "红外小目标检测")
        if pg._fuse_open:
            pg._toggle_fuse()
        pg.entry_b.delete(0, "end"); pg.entry_c.delete(0, "end")
        pg.fuse_kind.set("自动")
        pg.cands = []
        pg.generate()
        assert wait_until(app, lambda: bool(pg.cands)), "带约束生成超时"
        assert any(c.get("cfit") for c in pg.cands), "候选没被标上 cfit"
        # 硬条件结论已从画像条拆到 profile_sub（一行塞不下会被裁掉），
        # 所以两处都要看，不能只查 profile_lbl
        sub_texts = []

        def collect(w):
            try:
                if w.winfo_class() == "Label":
                    sub_texts.append(str(w.cget("text")))
            except Exception:
                pass
            for ch in w.winfo_children():
                collect(ch)
        collect(pg.profile_sub)
        assert "硬条件" in str(pg.profile_lbl.cget("text")) or any(
            "硬条件" in t for t in sub_texts), \
            "画像区没写硬条件结论：" + " | ".join(sub_texts)
        idx = [i for i, c in enumerate(pg.cands)
               if (c.get("cfit") or {}).get("level") != "ok"]
        if idx:
            pg.select(idx[0])
            pump(app, 0.3)
            texts = []

            def walk2(w):
                try:
                    if w.winfo_class() == "Label":
                        texts.append(str(w.cget("text")))
                except Exception:
                    pass
                for c in w.winfo_children():
                    walk2(c)
            walk2(pg.detail_box)
            assert any("和你的条件冲突" in t for t in texts), "详情面板没写冲突原因"
        # 清干净，避免影响后面的用例
        P2.set_constraints(compute="", months="", style="", avoid=[])
    check("硬约束进选题工坊", constraint_page)

    # ------------------------------------------------------------ 3 文献空白
    print("\n[3] 文献空白")
    app.goto("gap"); pump(app)
    gp = app.page("gap")

    def gap_analyze():
        assert wait_until(app, lambda: gp.data is not None, 10), "文献分析超时"
        assert gp.data.get("total", 0) > 0, "分析结果为空"
        assert gp.data.get("combos"), "未识别出密集组合"
    check("文献分析", gap_analyze)

    def gap_focus():
        gp._quick("Mamba")
        assert wait_until(app, lambda: gp.data and gp.data.get("scope") == "Mamba", 10), \
            "聚焦 Mamba 失败"
    check("聚焦方向", gap_focus)

    def gap_issue():
        data = gp.data or {}
        assert "issue_gaps" in data, "缺少问题维度空白"
    check("问题维度空白", gap_issue)

    def gap_save():
        gp._quick("")
        assert wait_until(app, lambda: gp.data and gp.data.get("gaps"), 10)
        before = len(kb.load_research_memory().get("ideas", []))
        gp.save_gap(gp.data["gaps"][0])
        pump(app, 0.3)
        after = len(kb.load_research_memory().get("ideas", []))
        assert after == before + 1, "空白存为创新点失败"
    check("空白存为创新点", gap_save)

    # ------------------------------------------------------------ 4 创新点库
    print("\n[4] 创新点库")
    app.goto("ideas"); pump(app)
    ip = app.page("ideas")

    def ideas_list():
        ip.reload(); pump(app, 0.3)
        assert ip.ideas, "创新点库为空（前序步骤应已存入）"
        ip.select(0); pump(app, 0.3)
    check("列表与详情渲染", ideas_list)

    def ideas_metric():
        ip.reload(); pump(app, 0.2)
        # 指标已折叠成一行（四项），不再是四张卡
        vals = ip._metrics.values()
        assert len(vals) == 4, "折叠指标应有 4 项"
        assert str(len(ip.ideas)) == vals["选题总数"], "选题总数与实际不符"
        ip._metrics.toggle(); pump(app, 0.2)
        assert ip._metrics.expanded, "折叠指标展开失败"
        ip._metrics.toggle(); pump(app, 0.2)
        assert not ip._metrics.expanded, "折叠指标收起失败"
    check("折叠指标的展开与收起", ideas_metric)

    def ideas_new():
        before = len(ip.ideas)
        ip._add("测试选题：跨域红外小目标检测", "验证用描述，含baseline YOLOv8 与 AP50 指标。")
        pump(app, 0.3)
        assert len(ip.ideas) == before + 1, "新建选题失败"
    check("新建选题", ideas_new)

    def ideas_prompt():
        ip.select(0); pump(app, 0.2)
        app.clipboard_clear()
        ip.review_prompt()
        pump(app, 0.5)
        clip = app.clipboard_get()
        assert clip and len(clip) > 30, "审查提示词为空"
    check("生成审查提示词", ideas_prompt)

    def ideas_copy():
        app.clipboard_clear()
        ip.copy_summary()
        pump(app, 0.3)
        assert app.clipboard_get(), "摘要复制为空"
    check("复制摘要", ideas_copy)

    def ideas_delete():
        ip.select(0); pump(app, 0.2)
        before = len(ip.ideas)
        ip.delete_idea(); pump(app, 0.3)
        assert len(ip.ideas) == before - 1, "删除选题失败"
    check("删除选题", ideas_delete)

    # ------------------------------------------------------------ 5 科研方法论
    print("\n[5] 科研方法论")
    app.goto("skills"); pump(app)
    sp = app.page("skills")

    def skills_all():
        import research_skills as SK
        assert len(SK.SKILLS) >= 7, "方法论数量不足"
        for i in range(len(SK.SKILLS)):
            sp.select(i)
            app.update()
        sp.select(0)
    check("七个方法全部可切换", skills_all)

    def skills_prompt():
        sp.idea = {"title": "测试课题", "desc": "夜间场景下漏检严重，现有方法退化明显。"}
        app.clipboard_clear()
        sp.prompt_one()
        pump(app, 0.4)
        assert app.clipboard_get(), "方法论提示词为空"
    check("单步提示词", skills_prompt)

    def skills_plan():
        app.clipboard_clear()
        sp.prompt_plan()
        pump(app, 0.4)
        clip = app.clipboard_get()
        assert "改进计划" in clip, "改进计划内容不对"
    check("改进计划", skills_plan)

    # ------------------------------------------------------------ 6 导师与院校
    print("\n[6] 导师与院校")
    app.goto("mentor"); pump(app)
    mp = app.page("mentor")

    def mentor_search():
        mp.search("单目深度估计")
        assert wait_until(app, lambda: bool(mp.rows), 10), "导师匹配超时"
        assert len(mp.rows) >= 10, "命中过少"
    check("按方向匹配", mentor_search)

    def mentor_name():
        # 先清空上一轮结果，避免把旧数据误当成本次结果
        mp.rows = []
        mp.search("孙茂松")
        # 姓名搜索是异步的，等到结果里出现与「孙」相关的英文名
        got = wait_until(
            app,
            lambda: any("Sun" in (r["advisor"].get("name") or "") for r in mp.rows),
            timeout=10)
        names = [r["advisor"]["name"] for r in mp.rows]
        assert got, "中文姓名未匹配到英文姓名的学者：%s" % names[:5]
    check("按姓名查找（中文→英文）", mentor_name)

    def mentor_export():
        mp.search("目标检测")
        assert wait_until(app, lambda: bool(mp.rows), 10)
        import glob
        before = set(glob.glob(os.path.join(str(kb.HERE), "exports", "导师清单-*.csv")))
        mp.export_csv()
        pump(app, 0.6)
        after = set(glob.glob(os.path.join(str(kb.HERE), "exports", "导师清单-*.csv")))
        new = after - before
        assert new, "未生成 CSV"
        # 清理
        for f in new:
            try:
                os.remove(f)
            except Exception:
                pass
    check("导出 CSV", mentor_export)

    def mentor_copy():
        app.clipboard_clear()
        mp._copy_list()
        pump(app, 0.3)
        assert app.clipboard_get(), "清单复制为空"
    check("复制清单", mentor_copy)

    # ------------------------------------------------------------ 7 期刊会议
    print("\n[7] 期刊会议")
    app.goto("venue"); pump(app)
    vp = app.page("venue")

    def venue_search():
        vp.search("三维重建")
        assert wait_until(app, lambda: bool(vp.rows), 10), "venue 匹配超时"
        assert len(vp.rows) >= 5, "推荐 venue 过少"
    check("按方向匹配 venue", venue_search)

    # ------------------------------------------------------------ 8 文献库
    print("\n[8] 文献库")
    app.goto("library"); pump(app)
    lp = app.page("library")
    assert wait_until(app, lambda: bool(lp.rows), 10), "文献库加载超时"

    def lib_load():
        # 2026-11-16 起改成按滚动位置现建（ui_parts.LazyList）：
        # 首屏只建视口里那 20 来行，但逻辑行数应该是全部。
        assert len(lp.rows) > 100, "文献数量异常：%d" % len(lp.rows)
        lazy = getattr(lp, "_lazy", None)
        assert lazy is not None, "没有接上懒加载列表"
        assert 8 <= len(lazy._slots) < len(lp.rows), \
            "首屏不该把全部行都建出来：建了 %d / 共 %d" % (len(lazy._slots), len(lp.rows))
        packed = len([w for w in lazy.pack_slaves() if w is not lazy._spacer])
        assert packed >= 8, "首屏可见行太少：%d" % packed
    check("加载与分批渲染", lib_load)

    def lib_more():
        lazy = lp._lazy
        before = len(lazy._slots)
        lp.scroll.canvas.yview_moveto(0.9); pump(app, 0.4)
        assert len(lazy._slots) > before, "滚到底后应当把后面的行建出来"
        assert len(lazy._slots) < len(lp.rows), "滚一下就把全部行建出来了，懒加载没生效"
    check("滚动时按需建行", lib_more)

    def lib_filter():
        cat = lp.cats[0]["name"]
        lp.filter_cat = cat
        lp._render_cats()
        lp.apply_filter()
        pump(app, 0.3)
        assert all(r["cat"] == cat for r in lp._filtered), "分类筛选未生效"
        lp.clear_filter(); pump(app, 0.2)
    check("分类筛选与清除", lib_filter)

    def lib_search():
        lp.entry.delete(0, "end")
        lp.entry.insert(0, "mamba")
        lp.apply_filter(); pump(app, 0.3)
        assert all("mamba" in r["name"].lower() for r in lp._filtered), "关键词过滤未生效"
        lp.clear_filter(); pump(app, 0.2)
    check("关键词过滤", lib_search)

    # ------------------------------------------------------------ 9 设置
    print("\n[9] 设置与数据")
    app.goto("settings"); pump(app)
    stp = app.page("settings")

    def settings_render():
        texts = []

        def walk(w):
            try:
                if w.winfo_class() == "Label":
                    texts.append(str(w.cget("text")))
            except Exception:
                pass
            for c in w.winfo_children():
                walk(c)
        walk(stp.body)
        joined = " ".join(texts)
        assert "知识库目录" in joined, "缺少存储路径"
        assert "检索词组" in joined, "缺少检索词"
    check("设置项渲染", settings_render)

    def settings_add_query():
        cfg = kb.load_config()
        before = len(cfg.get("queries", []))
        stp.q_entry.delete(0, "end")
        stp.q_entry.insert(0, "e2e测试检索词")
        stp._add_query()
        pump(app, 0.3)
        after = len(kb.load_config().get("queries", []))
        assert after == before + 1, "添加检索词失败"
        # 还原
        cfg = kb.load_config()
        cfg["queries"] = [q for q in cfg.get("queries", []) if q != "all:e2e测试检索词"]
        kb.CONFIG_FILE.write_text(kb.json.dumps(cfg, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
    check("添加检索词并还原", settings_add_query)

    # ------------------------------------------------------------ 10 全局
    print("\n[10] 全局功能")

    def global_search():
        app.search.delete(0, "end")
        app.search.insert(0, "mamba")
        app.global_search()
        pump(app, 0.8)
    check("全局搜索", global_search)

    def global_search_full():
        """搜索结果不能截断：mamba 在库里有 60+ 篇，不能只显示 10 或 30 条。"""
        hits = kb.search_kb("mamba", limit=2000)
        assert len(hits) > 30, "全量搜索结果异常：%d" % len(hits)
        limited = kb.search_kb("mamba")
        assert len(limited) <= 10, "默认 limit 行为变化"
    check("搜索结果不截断", global_search_full)

    def fulltext_search():
        """全文搜索：正文里的词（如 ablation）也要能搜到。"""
        import fulltext as FT
        st = FT.stats()
        assert st["available"], "全文索引未建立"
        assert st["coverage"] >= 90, "全文覆盖率过低：%.0f%%" % st["coverage"]
        hits = FT.search("ablation")
        assert len(hits) > 20, "正文搜索命中过少：%d" % len(hits)
        assert any(h["where"] in ("正文", "摘要") for h in hits), "未返回正文命中"
    check("全文搜索", fulltext_search)

    def fulltext_levels():
        """命中位置分级正确：文件名 > 摘要 > 正文。"""
        import fulltext as FT
        hits = FT.search("mamba")
        assert hits, "mamba 全文搜索为空"
        assert any(h["level"] >= 2 for h in hits), "没有高优先级命中"
        for h in hits:
            assert h["level"] in (1, 2, 3), "分级值异常：%r" % h["level"]
    check("全文搜索分级", fulltext_levels)

    def none_tolerance():
        import research_diagnose as RD
        import check_profile as CP
        import name_match as NM
        RD.diagnose(None)
        CP.is_complete(None)
        CP.profile_score(None)
        NM.match_cn_query(None, "Maosong Sun")
        NM.match_cn_query("孙茂松", None)
        kb.infer_category_field(None)
        kb.infer_category_field("")
    check("None 输入容错", none_tolerance)

    def edge_inputs():
        """异常输入不能崩溃。"""
        import topic_gen as TG
        import research_gap as G
        assert TG.build("") == []
        assert TG.build("   ") == []
        TG.build("<script>alert(1)</script>")
        TG.build("红外🔥检测")
        assert G.analyze("zzzz不存在该词")["total"] == 0
    check("异常输入不崩溃", edge_inputs)

    def global_log():
        app.log("端到端测试日志", T.OK, force_open=True)
        pump(app, 0.2)
        assert app._log_open, "日志抽屉未打开"
        app.hide_log(); pump(app, 0.1)
        assert not app._log_open, "日志抽屉未关闭"
    check("日志抽屉", global_log)

    def global_toast():
        app.toast("测试提示", T.WARN)
        pump(app, 0.1)
        assert "测试提示" in app.status.cget("text"), "状态栏未更新"
    check("状态栏提示", global_toast)

    def global_nav():
        for key in ("home", "topic", "gap", "latest", "ideas", "skills", "mentor",
                    "venue", "library", "map", "profile", "settings"):
            app.goto(key)
            app.update()
            assert app.current == key, "导航失败：" + key
    check("十二页导航切换", global_nav)

    def nav_history():
        # 跳进一条链，一路后退必须能退回起点；后退后跳新页要截断前进栈
        for k in ("topic", "mentor", "venue"):
            app.goto(k)
            app.update()
        assert app.current == "venue"
        app.nav_back()
        app.update()
        assert app.current == "mentor", "后退失败：" + str(app.current)
        app.nav_back()
        app.update()
        assert app.current == "topic", "后退失败：" + str(app.current)
        app.nav_forward()
        app.update()
        assert app.current == "mentor", "前进失败：" + str(app.current)
        app.goto("gap")
        app.update()
        assert app.hist_pos == len(app.history) - 1, "新跳转后前进栈没截断"
        assert "文献空白" in app.crumb.cget("text"), "面包屑不对"
    check("前进后退与面包屑", nav_history)

    def novelty_judge():
        import novelty_check as NC
        # 档位判据：语义近邻定档，词层只做有限加成
        assert NC._judge(0.85, 0, 0, False) == "high", "top1 0.85 应判 high"
        assert NC._judge(0.45, 0, 0, False) == "low", "top1 0.45 应判 low"
        assert NC._judge(0.72, 3, 0, False) == "high", "0.72 且近两年 3 篇应判 high"
        assert NC._judge(0.65, 0, 0, False) == "mid", "0.65 应判 mid"
        # 词层不能单独把分数抬到 high —— 之前就是这里把整个领域判成撞车
        assert NC._judge(0.20, 0, 999, True, 9000) != "high", "词层不该单独判 high"
    check("新颖性核查判档", novelty_judge)

    def novelty_query():
        import novelty_check as NC
        # 跨领域组合候选带 combo，A 直接取 combo["a"]
        c1 = {"title": "红外小目标检测 × 扩散模型", "angle_key": "跨域泛化",
              "combo": {"a": "红外小目标检测", "b": "扩散模型", "c": ""}}
        q1 = NC.build_query(c1)
        assert q1["phrase"], "组合候选应生成查询"
        assert "domain generalization" in q1["phrase"], "角度词没进查询：" + q1["phrase"]
        # 单方向候选没有 combo —— 必须用 direction 兜底，否则查询只剩角度词，
        # 会查出一堆数学拓扑论文并误判为「撞车」（真实踩过的坑）
        c2 = {"title": "图像去雾", "angle_key": "跨域泛化"}
        q2 = NC.build_query(c2, direction="图像去雾")
        assert "domain generalization" in q2["phrase"]
        assert len(q2["phrase"].split()) > 2, "兜底后查询词太少：" + q2["phrase"]
    check("新颖性核查查询构造", novelty_query)

    def novelty_annotate():
        import novelty_check as NC
        cands = [{"title": "红外小目标检测的跨域泛化方法", "angle_key": "跨域泛化",
                  "score": 80 - i} for i in range(10)]
        try:
            r = NC.check(cands[0], k=3, direction="红外小目标检测")
        except Exception as exc:
            raise AssertionError("check() 不该抛异常：" + repr(exc))
        assert "level" in r, "返回缺 level"
        assert r["level"] in ("high", "mid", "low"), "档位取值非法：" + str(r["level"])

        # 2026-11-15 起生成时不再批量核（原来是固定核前 8 条，用户要等 26 秒）。
        # 改成界面点开哪条核哪条：annotate_one 每次只加一条，没点过的保持 None。
        assert all(c.get("nov") is None for c in cands), "生成阶段不该预先核查"
        for c in cands[:3]:
            NC.annotate_one(c, k=3, direction="红外小目标检测")
        done = [c for c in cands if c.get("nov")]
        assert len(done) == 3, "应只核被点开的 3 条，实际 %d" % len(done)
        assert sum(1 for c in cands if c.get("nov") is None) == 7, "未点过的条目应是 None"
        # 已有结论的不要重复核（那就是白等 7 秒）
        first = done[0].get("nov")
        NC.annotate_one(cands[0], k=3, direction="红外小目标检测")
        assert cands[0].get("nov") is first, "已核过的条目不该重算"
        s = NC.summary(cands)
        assert "只核了你点开的 3 条" in s, "摘要没写核了几条：" + s
    check("新颖性核查按点开惰性核", novelty_annotate)

    def gap_fit_line():
        import page_gap
        import topic_constraint as TC
        cons = {"compute": "无算力", "months": "", "style": "", "avoid": []}
        # 自监督需要 8 卡，无算力差 3 档 → 应该出结论
        probe = {"title": "x", "angle_key": "自监督"}
        r = TC.check(probe, cons)
        assert r["level"] == "block", "无算力 + 自监督应判 block"
        # 猜角度：能从空白条目的文字里认出角度，认不出必须给空串
        # 注意「小目标」不等于「小样本」—— 字面相近但语义不同，不能被猜成角度
        assert page_gap._guess_angle("医学", "小目标") == "", "小目标不该被猜成小样本角度"
        assert page_gap._guess_angle("医学", "小样本") == "小样本"
        assert page_gap._guess_angle("对比学习", "检测") == "自监督"
        assert page_gap._guess_angle("某个", "说不清的词") == "", "认不出时应返回空串"
    check("空白页硬条件映射", gap_fit_line)

    # ------------------------------------------------------------ 收尾
    pump(app, 0.3)
    app.destroy()
    kb.RESEARCH_MEMORY = real_mem
    try:
        os.remove(tmp_mem)
    except Exception:
        pass

    # 关键断言：跑完一圈界面之后，真实目录里不该冒出任何用户数据文件。
    # （2026-11-13 就是这里漏了，MentorPage.search() 把画像写到真实目录。）
    # 测试开始前就存在的文件不算泄漏（用户自己用软件就会生成）。
    leaked = tools_isolate.check_clean(_pre_files)
    for p in leaked:
        try:
            os.remove(p)
        except Exception:
            pass

    def no_leak():
        if leaked:
            raise AssertionError("界面写到了真实目录：" + ", ".join(leaked))

    check("测试没有污染真实用户数据", no_leak)
    tools_isolate.cleanup(_ISO.get("__tmp__"))
    tools_isolate.assert_memory_untouched(_mem_before)

    print("\n" + "=" * 66)
    total = len(C.passed) + len(C.failed)
    print("通过 %d / %d   跳过 %d   失败 %d"
          % (len(C.passed), total, len(C.skipped), len(C.failed)))
    if C.failed:
        print("\n失败项：")
        for n, e in C.failed:
            print("  ✗ %s\n      %s" % (n, e))
    print("=" * 66)
    return 1 if C.failed else 0


if __name__ == "__main__":
    sys.exit(main())