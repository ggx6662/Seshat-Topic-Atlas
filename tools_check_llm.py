# -*- coding: utf-8 -*-
"""验证 paper_sources 的 override_query 路径与 llm_bridge 降级行为。"""
import paper_sources as P
import llm_bridge as L

Q = 'abs:"semantic segmentation" AND abs:"event camera" AND (cat:cs.CV OR cat:cs.LG)'
r = P.fetch_all("事件相机语义分割", limit=10, use_cache=False, override_query=Q)
print("override 各源:", r["by_source"], "错误:", r["errors"], "共", len(r["papers"]))
for p in r["papers"][:3]:
    print("  ", p["published"], p["title"][:70])

r2 = P.fetch_all("红外小目标检测", limit=5, use_cache=True)
print("普通路径仍正常:", r2["by_source"], len(r2["papers"]))

print("\n--- llm_bridge 降级 ---")
print("is_ready:", L.is_ready())
print("rewrite_query:", L.rewrite_query("红外小目标检测"))
print("explain_direction:", L.explain_direction("x", [{"title": "a"}]))
print("critique_ideas:", L.critique_ideas("x", [{"title": "a"}]))

print("\n--- 检索式校验 ---")
from page_latest import _valid_arxiv_query
cases = [
    ('abs:"object detection" AND abs:infrared', True),
    ("好的，检索式如下：abs:x", False),
    ('(abs:"a b") AND (cat:cs.CV', False),
    ("", False),
    ("cat:cs.CV AND abs:fusion", True),
]
for q, want in cases:
    got = _valid_arxiv_query(q)
    print(("OK  " if got == want else "FAIL"), repr(q)[:50], "->", got)