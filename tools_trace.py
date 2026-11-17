#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""诊断脚本：把每一步写进文件，用于定位卡死位置。"""
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
LOG = os.path.join(os.environ.get("TEMP", "."), "kb_trace.log")


def mark(msg):
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write("%.3f  %s\n" % (time.time(), msg))
        fh.flush()


def main():
    open(LOG, "w", encoding="utf-8").close()
    import faulthandler
    fh = open(os.path.join(os.environ.get("TEMP", "."), "kb_stack.txt"), "w", encoding="utf-8")
    faulthandler.dump_traceback_later(8, repeat=True, file=fh)
    mark("start")
    import app_main
    mark("imported")
    app = app_main.App()
    app.geometry("1240x800+0+0")
    mark("app created")
    for _ in range(6):
        app.update()
        time.sleep(0.1)
    mark("first update ok")
    app.goto("topic")
    app.update()
    mark("topic page ok")
    pg = app.page("topic")
    pg.entry.insert(0, "红外小目标检测")
    mark("before generate")
    # 直接调用 _apply，绕开线程，定位是不是渲染本身卡死
    import kb_widget as kb
    cat, field, conf = kb.infer_category_field("红外小目标检测")
    rels = kb.load_research_relations()
    pk = kb.field_profile(cat, field, rels)
    prof = (rels.get("profiles") or {}).get(pk, {})
    mark("before expand")
    cands = kb.expand_direction_candidates("红外小目标检测", "自动混合", 18)
    mark("expand ok %d" % len(cands))
    pg._apply("红外小目标检测", cat, field, conf, pk, prof, cands)
    mark("_apply done")
    app.update()
    mark("update after apply ok")
    pg.select(0)
    mark("select done")
    app.update()
    mark("update after select ok")
    t = time.time()
    pg.select(0)
    mark("select done %.2fs" % (time.time() - t))
    app.update()
    mark("after select update")
    # 逐个 scroll 检查
    for name in ("cand_scroll", "detail_scroll", "side_scroll"):
        sc = getattr(pg, name)
        mark("%s canvas=%d master=%d" % (name, sc.canvas.winfo_height(),
                                         sc.master.winfo_height()))
    app.update()
    mark("final update ok")
    app.destroy()
    mark("done")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        mark("EXC " + traceback.format_exc())