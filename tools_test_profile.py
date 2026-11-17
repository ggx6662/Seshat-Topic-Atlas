#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""个体画像记忆层自测 —— 不依赖 Tk，可直接跑。

    python tools_test_profile.py
"""
import shutil
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import profile_memory as PM  # noqa: E402

PASS, FAIL = 0, 0


def check(name, fn):
    global PASS, FAIL
    try:
        fn()
        PASS += 1
        print("  [OK]   %s" % name)
    except AssertionError as e:
        FAIL += 1
        print("  [FAIL] %s  -> %s" % (name, e))
    except Exception as e:
        FAIL += 1
        print("  [ERR]  %s  -> %r" % (name, e))


def _isolate():
    """把数据文件指到临时目录，绝不碰用户真实画像。"""
    tmp = Path(tempfile.mkdtemp(prefix="kbtest-profile-"))
    PM.PROFILE_FILE = tmp / "researcher_profile.json"
    PM._cache["mtime"] = None
    PM._cache["data"] = None
    return tmp


def main():
    tmp = _isolate()
    print("临时目录: %s" % tmp)
    print()

    # ------------------------------------------------ 纯函数
    def t_has_tag():
        assert PM.has_tag("debug session", "bug") is False, "bug 不该命中 debug"
        assert PM.has_tag("this is a bug", "bug") is True
        assert PM.has_tag("chatter", "chat") is False, "chat 不该命中 chatter"
        assert PM.has_tag("数据跑不通了", "跑不") is True, "中文应走子串"

    def t_urgency_linear():
        assert PM.urgency_weights(30) == (1.0, 1.0), "平静时应为 1/1"
        assert PM.urgency_weights(100) == (3.0, 0.1), "极限应激应为 3/0.1"
        mid = PM.urgency_weights(60)
        assert 1.0 < mid[0] < 3.0 and 0.1 < mid[1] < 1.0, "中间应线性插值 %r" % (mid,)

    def t_ddl():
        assert PM.urgency_from_ddl("") == 20.0
        assert PM.urgency_from_ddl("2000-01-01") == 100.0, "过期应 100"
        import datetime as dt
        d = (dt.datetime.now() + dt.timedelta(days=1)).strftime("%Y-%m-%d")
        u = PM.urgency_from_ddl(d)
        assert 85 <= u <= 100, "还剩一天应 >=85，实际 %r" % u

    def t_relevance():
        assert PM.literal_relevance("", "abc") == 0.0
        assert PM.literal_relevance("红外", "做红外小目标检测") > 0
        assert PM.literal_relevance("量子计算", "做红外小目标检测") == 0.0

    check("has_tag 词边界（bug≠debug / 中文子串）", t_has_tag)
    check("urgency_weights 线性插值", t_urgency_linear)
    check("urgency_from_ddl 对数刻度", t_ddl)
    check("literal_relevance 字面重合", t_relevance)

    print()

    # ------------------------------------------------ 存取
    def t_default():
        p = PM.load()
        assert p["identity"]["stage"] == "硕士在读"
        assert p["anchors"] == []

    def t_save_load():
        PM.set_identity(school="某大学", lab="视觉实验室", goal="发一篇顶会")
        p = PM.load()
        assert p["identity"]["school"] == "某大学"
        assert PM.PROFILE_FILE.exists(), "应落盘"
        raw = PM.PROFILE_FILE.read_text(encoding="utf-8")
        assert "某大学" in raw, "中文应原样存储（ensure_ascii=False）"

    def t_set_state():
        PM.set_state(urgency=95, interest=80, mood="焦虑", note="三天后截稿")
        st = PM.load()["state"]
        assert st["urgency"] == 95 and st["mood"] == "焦虑"
        PM.set_state(urgency=999)
        assert PM.load()["state"]["urgency"] == 100.0, "应被 clamp 到 100"

    check("默认画像结构", t_default)
    check("保存后能读回（中文不乱码）", t_save_load)
    check("set_state 并 clamp", t_set_state)

    print()

    # ------------------------------------------------ 偏好
    def t_pref():
        for _ in range(3):
            PM.bump_pref("categories", "计算机视觉")
        PM.bump_pref("fields", "目标检测", delta=-1)
        w = PM.pref_weight("categories", "计算机视觉")
        assert 0 < w <= 1, "偏好应归一化到 0..1，实际 %r" % w
        assert PM.pref_weight("fields", "目标检测") < 0
        for _ in range(50):
            PM.bump_pref("categories", "计算机视觉")
        assert PM.pref_weight("categories", "计算机视觉") == 1.0, "应有上限"
        PM.bump_pref("avoid", "纯光学")

    def t_learn():
        # 必须独立起一份干净画像：前一个用例已经把「计算机视觉」加满了，
        # 这里要验的是「从零开始，≥3 次才加权」这条规则本身。
        tmp2 = _isolate()
        try:
            ideas = [{"category": "计算机视觉"}] * 4 + [{"category": "自然语言处理"}]
            r = PM.learn_from_ideas(ideas)
            assert r["touched"] >= 1, r
            w = PM.pref_weight("categories", "计算机视觉")
            assert w > 0, "出现 4 次应加权"
            once = PM.pref_weight("categories", "自然语言处理")
            assert 0 < once < w, "只出现 1 次只给轻推，必须小于 4 次的权重"
        finally:
            shutil.rmtree(tmp2, ignore_errors=True)

    check("偏好加减权 + 上限 + 回避", t_pref)
    check("从选题台账反推偏好（≥3 次才真正加权，1–2 次只轻推）", t_learn)

    print()

    # ------------------------------------------------ 记忆与倾斜（核心）
    def t_anchor_crisis():
        PM.set_state(urgency=95, mood="焦虑")
        PM.remember("被审稿人拒了，说缺少消融实验", tags=["被拒"])
        PM.remember("以后有空看看扩散模型在分割上的应用", tags=["以后"])

    def t_tilt():
        r = PM.recall()
        assert r["total"] == 2, "两条都要在，不能删"
        top = r["items"][0]
        assert top["detail"]["kind"] == "crisis", \
            "应激时危机类应排第一，实际 %r" % (top["detail"]["kind"],)
        assert r["tilt"]["crisis"] == 3.0
        assert r["tilt"]["daily"] == 0.1

    def t_calm_no_tilt():
        PM.set_state(urgency=10, mood="平静")
        r = PM.recall()
        assert r["tilt"] == {"crisis": 1.0, "daily": 1.0}, "平静时倍率应为 1"

    def t_anchor_mood_counts():
        PM.set_state(urgency=10, mood="平静")
        PM.remember("这条本身没什么情绪词", mood="焦虑")
        r = PM.recall(limit=1)
        k = PM.classify("这条本身没什么情绪词", anchor_mood="焦虑")
        assert k == "crisis", "存它时在焦虑 -> 应记为 crisis"

    def t_query_relevance():
        PM.set_state(urgency=50, mood="平静")
        PM.remember("红外小目标检测的数据集一直没找到合适的")
        PM.remember("今天午饭吃了食堂新出的面")
        r = PM.recall(query="红外 数据集")
        assert r["total"] >= 2
        first = r["items"][0]
        assert "红外" in first["record"]["text"], \
            "带 query 时相关条目应排前，实际 %r" % first["record"]["text"]

    def t_budget_compress():
        for i in range(10):
            PM.remember("很长的记忆内容" * 60)
        r = PM.recall(limit=10, budget_chars=600)
        assert r["shown"] == 10, "预算不足只能压缩，不能丢条"
        assert any(x.get("compressed") for x in r["items"]), "应有条目被压缩"
        assert r["total"] >= 12

    def t_forget():
        n0 = len(PM.load()["anchors"])
        aid = PM.load()["anchors"][0]["id"]
        assert PM.forget(aid) == 1
        assert len(PM.load()["anchors"]) == n0 - 1

    check("存记忆打情绪锚点", t_anchor_crisis)
    check("应激时危机记忆顶到最前、总数不减", t_tilt)
    check("平静时不倾斜", t_calm_no_tilt)
    check("存时焦虑也算 crisis（闪光灯记忆）", t_anchor_mood_counts)
    check("带 query 时相关记忆压过无关", t_query_relevance)
    check("字符预算只压缩不丢条", t_budget_compress)
    check("forget 真删除", t_forget)

    print()

    # ------------------------------------------------ 对外
    def t_brief():
        # `t_learn` 会切到一个干净的临时画像再删掉，所以这里必须重新填一次身份，
        # 否则会被误判成「profile_brief 不输出目标」。
        PM.set_identity(school="某大学", goal="发一篇顶会")
        b = PM.profile_brief()
        assert "身份" in b and "目标" in b, b[:80]

    def t_recall_text():
        t = PM.recall_text(query="红外", limit=3)
        assert "这位同学自己的状态" in t, t[:80]

    def t_public():
        pub = PM.export_public()
        blob = str(pub)
        assert "某大学" not in blob, "对外导出不能带学校名"
        assert "导师" not in blob

    def t_stats():
        s = PM.stats()
        assert s["exists"] is True and s["anchors"] > 0

    check("profile_brief 给大模型", t_brief)
    check("recall_text 渲染", t_recall_text)
    check("export_public 脱敏（不含学校/导师）", t_public)
    check("stats", t_stats)

    print()

    # ------------------------------------------------ 页面渲染（曾经的盲区）
    # 教训：加了「这个画像怎么影响选题」卡之后，代码里误写 T.CARD_ALT 直接抛
    # AttributeError，但整套测试照样 20/20 通过 —— 因为没有任何用例真的把
    # ProfilePage 建出来。下面这几条专门补这个洞：真建控件、真渲染。
    def t_page_renders():
        import tkinter as tk
        import page_profile as PP

        class FakeApp(object):
            def __init__(self):
                self.toasts = []

            def toast(self, msg, color=None):
                self.toasts.append(msg)

            def post(self, fn):
                fn()

            def goto(self, key, **kw):
                pass

        PM.set_identity(school="某大学", goal="发一篇顶会")
        PM.set_state(urgency=95, interest=80, mood="焦虑")
        PM.remember("三天后要交初稿", tags=["截止"])

        root = tk.Tk()
        root.withdraw()
        try:
            page = PP.ProfilePage(root, FakeApp())
            # 走真实路径：构造 → reload → 里面的每个 _render_* 都得跑通
            page.reload()
            root.update()
            kids = page.area.inner.winfo_children()
            assert len(kids) >= 7, "画像页至少七段，实际 %d" % len(kids)
        finally:
            root.destroy()

    def t_page_effect_card():
        """「这个画像怎么影响选题」必须真的调通 topic_gen 并能显示排序理由。"""
        import tkinter as tk

        import topic_gen
        tilt = PM.tilt_inputs()
        assert tilt is not None, "已有画像时 tilt_inputs 不应返回 None"
        cs = topic_gen.build("红外小目标检测", "自动混合", 18, profile=tilt)
        assert len(cs) == 18, "加画像后候选数量不能变"
        assert any(c.get("tilt_reason") for c in cs), "焦虑状态下应有候选被调整并带理由"

    def t_page_no_profile():
        """全新的机器上（没有任何画像数据）画像页也得能开。"""
        import tkinter as tk

        import page_profile as PP
        tmp3 = _isolate()

        class FakeApp(object):
            def toast(self, msg, color=None):
                pass

            def post(self, fn):
                fn()

            def goto(self, key, **kw):
                pass

        root = tk.Tk()
        root.withdraw()
        try:
            page = PP.ProfilePage(root, FakeApp())
            page.reload()
            root.update()
            assert page.area.inner.winfo_children(), "空画像也要渲染出骨架"
            assert PM.tilt_inputs() is None, "没画像时 tilt_inputs 应为 None"
        finally:
            root.destroy()
            shutil.rmtree(tmp3, ignore_errors=True)

    check("画像页真实渲染（7 段以上）", t_page_renders)
    check("画像→选题排序联动可跑", t_page_effect_card)
    check("空画像时页面也能开", t_page_no_profile)

    print()
    print("=" * 56)
    print("通过 %d / 失败 %d" % (PASS, FAIL))
    try:
        shutil.rmtree(tmp, ignore_errors=True)
    except Exception:
        pass
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())