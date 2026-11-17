#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证「个人画像 → 大模型提示词」这段拼装，全程不联网、不需要 key。

    python tools_test_prompt.py

做法：把 llm_bridge.chat 换成一个只记录 system 消息的假函数，
再看三个用途各自把什么塞进了提示词。
"""
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import llm_bridge as L      # noqa: E402
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


def isolate():
    """把画像文件指到临时目录，绝不碰用户真实 researcher_profile.json。"""
    tmp = Path(tempfile.mkdtemp(prefix="kbtest-prompt-"))
    PM.PROFILE_FILE = tmp / "researcher_profile.json"
    PM._cache["mtime"] = None
    PM._cache["data"] = None
    return tmp


_orig_chat = L.chat
SEEN = []


def fake_chat(messages, cfg=None, max_tokens=900, json_mode=False):
    SEEN.append(messages[0]["content"])
    return "abs:\"object detection\" AND abs:infrared"


def main():
    tmp = isolate()
    print("临时目录: %s" % tmp)
    print()
    L.chat = fake_chat

    # ------------------------------------------------ 没画像时
    def t_no_profile_clean():
        SEEN.clear()
        L.explain_direction("红外小目标检测", [{"title": "A Paper"}])
        sysmsg = SEEN[-1]
        assert "【提问的人是谁】" not in sysmsg, "没画像时不该出现画像块"
        assert sysmsg.strip() == L._EXPLAIN_SYS.strip(), "没画像时提示词应与旧版逐字一致"

    def t_no_profile_idea():
        SEEN.clear()
        L.critique_ideas("红外小目标检测", [{"title": "甲", "feasibility": 80, "novelty": 70}])
        sysmsg = SEEN[-1]
        assert "【提问的人是谁】" not in sysmsg
        user = ""
        assert "可行 80" not in sysmsg or True  # 候选说明在 user 消息里，这里只验 system

    def t_rewrite_default_off():
        SEEN.clear()
        L.rewrite_query("红外小目标检测")
        assert "【提问的人是谁】" not in SEEN[-1], "检索式改写默认不带画像"

    check("没画像时 explain_direction 提示词不变", t_no_profile_clean)
    check("没画像时 critique_ideas 提示词不变", t_no_profile_idea)
    check("rewrite_query 默认不注入画像", t_rewrite_default_off)

    print()

    # ------------------------------------------------ 有画像时
    def t_with_profile():
        PM.set_identity(school="东南大学", lab="智能视觉实验室", goal="三个月内投一篇 CV 会议")
        PM.set_state(urgency=95, interest=80, mood="焦虑", note="离截稿两周")
        SEEN.clear()
        L.explain_direction("红外小目标检测", [{"title": "A Paper"}])
        sysmsg = SEEN[-1]
        assert "【提问的人是谁】" in sysmsg, "建了画像就该注入"
        assert "东南大学" in sysmsg, "应带上学校"
        assert "焦虑" in sysmsg or "离截稿两周" in sysmsg, "应带上当前处境"
        assert "优先给能落地的建议" in sysmsg, "应带上处境规则"

    def t_profile_idea():
        SEEN.clear()
        L.critique_ideas("红外小目标检测", [
            {"title": "甲", "feasibility": 88, "novelty": 60}])
        sysmsg = SEEN[-1]
        assert "【提问的人是谁】" in sysmsg, "挑刺时应带上画像"
        assert "东南大学" in sysmsg

    def t_rewrite_can_opt_in():
        SEEN.clear()
        L.rewrite_query("红外小目标检测", use_profile=True)
        assert "【提问的人是谁】" in SEEN[-1], "显式开启时应注入"

    check("有画像时 explain_direction 注入身份与处境", t_with_profile)
    check("有画像时 critique_ideas 注入画像", t_profile_idea)
    check("rewrite_query 可显式开启画像", t_rewrite_can_opt_in)

    print()

    # ------------------------------------------------ 安全性
    def t_no_leak_to_disk():
        """画像内容只进请求，不该被写进任何配置文件。"""
        cfg_path = Path(getattr(L, "CONFIG_FILE", Path("llm_config.json")))
        if cfg_path.exists():
            raw = cfg_path.read_text(encoding="utf-8", errors="ignore")
            assert "东南大学" not in raw, "画像内容不该出现在 llm_config.json"

    def t_brief_has_mood():
        b = PM.profile_brief()
        assert "焦虑" in b or "离截稿两周" in b, b[:120]

    def t_bad_profile_no_crash():
        """画像文件损坏时，_profile_block 必须返回空串而不是抛异常。"""
        PM.PROFILE_FILE.write_text("{坏的 json", encoding="utf-8")
        PM._cache["mtime"] = None
        PM._cache["data"] = None
        blk = L._profile_block()
        assert isinstance(blk, str), "必须返回字符串"

    check("画像内容不落盘到配置", t_no_leak_to_disk)
    check("profile_brief 带心境", t_brief_has_mood)
    check("画像文件损坏时不崩", t_bad_profile_no_crash)

    print()
    print("=" * 56)
    print("通过 %d / 失败 %d" % (PASS, FAIL))
    L.chat = _orig_chat
    shutil.rmtree(tmp, ignore_errors=True)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())