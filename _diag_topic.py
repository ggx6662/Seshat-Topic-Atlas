# -*- coding: utf-8 -*-
import os, sys, time
import tools_isolate
_ISO = tools_isolate.isolate()
import app_theme as T
import app_main as A

app = A.App() if hasattr(A, "App") else A.TopicAtlas()
app.geometry("1440x900")
app.update(); time.sleep(0.6); app.update()
app.goto("topic")
app.update(); time.sleep(0.8); app.update()

pg = app.pages["topic"]
for name, w in (("welcome", pg._welcome), ("wcard", pg._welcome_card),
                ("graph", pg._hero_graph), ("entry", pg.entry)):
    try:
        print(name, w.winfo_ismapped(), w.winfo_width(), w.winfo_height(), w.winfo_rootx(), w.winfo_rooty())
    except Exception as e:
        print(name, "ERR", e)
print("stats frame", [(s.winfo_ismapped(), s.winfo_width(), s.winfo_height(), s.winfo_rootx(), s.winfo_rooty()) for s in pg._hero_stats])
for i, sc in enumerate(pg._welcome_steps.winfo_children()):
    print("step", i, sc.winfo_ismapped(), sc.winfo_width(), sc.winfo_height(), sc.winfo_rootx(), sc.winfo_rooty(), sc.cget("bg"))
app.destroy()
tools_isolate.cleanup(_ISO.get("__tmp__"))