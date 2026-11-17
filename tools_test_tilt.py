# -*- coding: utf-8 -*-
"""画像加权测试：只重排、不删减、理由说得清。

关键断言（都是容易悄悄坏掉的）：
  1. 传不传 profile，候选**数量必须一样**（画像不能当过滤器用）
  2. 传不传 profile，候选**集合必须一样**（不能凭空多出一个）
  3. 不同状态下排序应当不同（否则加权等于没写）
  4. 被调整过的候选必须有 tilt_reason，否则用户不知道为啥它排第一
  5. 调整幅度不得超过 TILT_CAP
"""
import sys

sys.path.insert(0, ".")
import topic_gen  # noqa: E402

OK = [0]
BAD = []


def check(name, cond, detail=""):
    if cond:
        OK[0] += 1
        print("  [ok]  ", name)
    else:
        BAD.append(name)
        print("  [FAIL]", name, detail)


def titles(cs):
    return [c["title"] for c in cs]


def main():
    d = "红外小目标检测"
    base = topic_gen.build(d, "自动混合", 18)
    check("无画像也能出候选", len(base) > 0, str(len(base)))

    stressed = {"urgency": 95, "interest": 30, "mood": "焦虑",
                "prefs": {"angle": {}, "strategy": {}}}
    relaxed = {"urgency": 10, "interest": 90, "mood": "兴奋",
               "prefs": {"angle": {}, "strategy": {}}}
    a = topic_gen.build(d, "自动混合", 18, profile=stressed)
    b = topic_gen.build(d, "自动混合", 18, profile=relaxed)

    check("加画像后数量不变", len(a) == len(base) == len(b),
          "%d / %d / %d" % (len(a), len(base), len(b)))
    check("加画像后集合不变", set(titles(a)) == set(titles(base)) == set(titles(b)))
    check("两种状态排序不同", titles(a) != titles(b))
    check("紧急时可行性高的更靠前", a[0]["feasibility"] >= a[-1]["feasibility"] or
          a[0].get("tilt", 0) > 0,
          "top=%s feas=%s" % (a[0]["angle"], a[0]["feasibility"]))

    bad_cap = [c for c in a if abs(c.get("tilt", 0)) > topic_gen.TILT_CAP + 0.01]
    check("调整幅度不超上限", not bad_cap, str(bad_cap[:2]))

    movers = [c for c in a if c.get("tilt")]
    check("被调整的候选都带理由", all(c.get("tilt_reason") for c in movers),
          str([c["angle"] for c in movers if not c.get("tilt_reason")]))
    check("确实有候选被调整", len(movers) > 0, str(len(movers)))

    # 偏好积累：同一角度存 5 次，应该往上走
    pref = {"urgency": 50, "interest": 50, "mood": "平静",
            "prefs": {"angle": {"轻量化": 5}, "strategy": {}}}
    c = topic_gen.build(d, "自动混合", 18, profile=pref)
    q = [x for x in c if x.get("angle_key") == "轻量化" or x.get("angle") == "轻量化"]
    check("偏好积累对选中角度生效",
          bool(q) and q[0].get("tilt", 0) > 0,
          str(q[0] if q else "找不到轻量化候选"))

    # 回归：bump_pref 的白名单曾经漏掉 "angle"/"strategy"，
    # 于是 page_topic / page_profile 写角度偏好时被静默丢弃，
    # 「你以前多次挑这类角度」这条规则永远不会触发。
    import profile_memory as PM
    import pathlib as _pl
    import tempfile as _tf
    _tmp = _pl.Path(_tf.mkdtemp(prefix="kbtest-tilt-"))
    PM.PROFILE_FILE = _tmp / "researcher_profile.json"
    PM._cache["mtime"] = None
    PM._cache["data"] = None
    PM.set_identity(school="测试大学")
    for _ in range(3):
        PM.bump_pref("angle", "跨域泛化")
    PM.bump_pref("strategy", "稳健邻接")
    _p = PM.load()["preferences"]
    check("angle/strategy 偏好桶能写入",
          (_p.get("angle") or {}).get("跨域泛化") == 3.0
          and (_p.get("strategy") or {}).get("稳健邻接") == 1.0,
          str(_p))
    _t = PM.tilt_inputs() or {}
    check("tilt_inputs 能带出角度偏好",
          ((_t.get("prefs") or {}).get("angle") or {}).get("跨域泛化") == 3.0,
          str(_t.get("prefs")))
    _after = topic_gen.build(d, "自动混合", 18, profile=_t)
    _hit = [x for x in _after if x.get("angle_key") == "跨域泛化"
            or x.get("angle") == "跨域泛化"]
    check("写成偏好后确实抬高了该角度",
          bool(_hit) and _hit[0].get("tilt", 0) > 0,
          str(_hit[0]["tilt"] if _hit else "找不到候选"))

    print("\n==== 结果 ====")
    print("通过 %d / 失败 %d" % (OK[0], len(BAD)))
    for x in BAD:
        print("  -", x)
    return 0 if not BAD else 1


if __name__ == "__main__":
    sys.exit(main())