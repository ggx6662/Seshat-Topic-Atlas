#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""新功能的端到端验证：语义检索 + 最新研究 + 设置区。

和 tools_e2e_test.py 的区别：那边测的是原有 43 项；这里只测这轮新加的，
而且要连真实网络（arXiv/OpenAlex），所以单独一个文件、可以单独跑。
"""
import os
import sys
import time
import tkinter as tk

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import app_theme as T   # noqa: E402
import app_main          # noqa: E402

PASS, FAIL = [], []


def check(name, fn):
    try:
        fn()
        PASS.append(name)
        print("  [ok] " + name)
    except Exception as exc:
        FAIL.append((name, exc))
        print("  [FAIL] %s → %s" % (name, exc))


def wait_until(pred, timeout=60, step=0.05, pump=None):
    """等待条件成立。

    **必须持续 pump 事件循环**：app.post() 把回调塞进队列，靠 after(50ms)
    的 _poll() 取出来执行。如果只是 sleep，Tk 不会跑 _poll，回调永远不执行
    ——之前就是这样一直等到超时。
    """
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pump is not None:
            try:
                pump.update()
            except Exception:
                pass
        if pred():
            return True
        time.sleep(step)
    return False


def main():
    app = app_main.App()
    app.update()
    for _ in range(20):
        app.update()
        time.sleep(0.02)

    # ---------------------------------------------------- 语义检索
    def t_semantic_build():
        import semantic_search as S
        st = S.stats()
        # 键名是 indexed（不是 docs）
        assert st.get("indexed", 0) >= 300, "索引文档数不足：%s" % st
        assert st.get("has_index"), "索引文件不存在"
    check("语义索引存在且覆盖全库", t_semantic_build)

    def t_semantic_cn():
        import semantic_search as S
        r = S.search("红外小目标漏检", limit=10)
        assert r, "中文查询返回空"
        # search() 只返回 path/score/reasons，**不带标题**，
        # 标题是界面拿 meta_index 补的。所以这里用 path + meta 一起判断。
        import meta_index
        blob = " ".join(
            ((meta_index.get(x.get("path")).get("title") or "") + " " +
             os.path.basename(x.get("path") or "")
             for x in r[:5])).lower()
        assert ("infrared" in blob or "thermal" in blob or "ir" in blob), \
            "中文查询 Top5 里没有红外相关论文：%s" % blob[:200]
        assert all(x.get("reasons") for x in r[:3]), "缺 reasons"
    check("中文查询能检索英文论文", t_semantic_cn)

    def t_semantic_scores():
        import semantic_search as S
        r = S.search("Mamba 分割", limit=10)
        assert r, "返回空"
        s = [x.get("score", 0) for x in r]
        assert s == sorted(s, reverse=True), "分数没有降序"
        assert s[0] > s[-1], "所有结果分数相同，说明评分没起作用"
        assert all(x.get("reasons") for x in r[:3]), "缺 reasons"
    check("匹配度分数有区分且降序", t_semantic_scores)

    # ---------------------------------------------------- 最新研究
    def t_sources_fetch():
        import paper_sources as PS
        r = PS.fetch_all("红外小目标检测", sources=("arxiv", "openalex"),
                         limit=10, days_back=180, use_cache=True)
        ps = r.get("papers") or []
        assert len(ps) >= 5, "论文太少：%d" % len(ps)
        assert r.get("by_source", {}).get("arxiv", 0) > 0, "arxiv 0 条"
        latest = ps[0].get("published") or ""
        assert latest >= "2026-06", "最新日期异常：%s" % latest
    check("多源抓取能拿到近期论文", t_sources_fetch)

    def t_sources_dedupe():
        import paper_sources as PS
        r = PS.fetch_all("Mamba 分割", sources=("arxiv", "openalex"),
                         limit=20, days_back=365, use_cache=True)
        ts = [PS._norm_title(p.get("title")) for p in r.get("papers", [])]
        assert len(ts) == len(set(ts)), "去重后仍有重复标题"
    check("跨源去重生效", t_sources_dedupe)

    # ---------------------------------------------------- 界面
    def t_latest_page():
        # 注意：goto() 没有返回值（它只负责切换页面），
        # 要拿页面对象得从 app.pages 取。
        app.goto("latest")
        app.update()
        assert "latest" in app.pages, "页面没注册：%s" % list(app.pages)
        pg = app.pages["latest"]
        assert hasattr(pg, "search"), "缺 search 方法"
    check("最新研究页能打开", t_latest_page)

    def t_latest_render():
        pg = app.pages["latest"]
        pg.entry.delete(0, "end")
        pg.entry.insert(0, "红外小目标检测")
        pg.search()
        ok = wait_until(lambda: pg.result is not None, timeout=90, pump=app)
        assert ok, "抓取超时"
        for _ in range(30):
            app.update()
            time.sleep(0.02)
        n = len(pg.box.inner.winfo_children())
        assert n > 0, "页面没渲染出任何内容"
        txt = pg.summary.cget("text")
        assert "红外小目标检测" in txt, "摘要行没显示方向：%s" % txt
    check("最新研究页能渲染抓取结果", t_latest_render)

    def t_library_semantic():
        app.goto("library")
        app.update()
        pg = app.pages.get("library")
        assert pg is not None, "文献库页没打开"
        assert hasattr(pg, "smart_search"), "文献库缺语义检索入口"
    check("文献库语义检索入口存在", t_library_semantic)

    app.destroy()

    print("\n==== 结果 ====")
    print("通过: %d   失败: %d" % (len(PASS), len(FAIL)))
    for n, e in FAIL:
        print("  失败: %s → %s" % (n, e))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())