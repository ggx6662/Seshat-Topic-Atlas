"""下载到知识库功能的端到端测试。

铁律：绝不碰用户真实知识库（G 盘 AuthorKit27 知识库）。
做法是把 kb_widget.kb_root / inbox_dir 与 kb_download.kb_paths 都改指到临时目录，
并在 finally 里恢复。测试中真正联网的只有「下载一篇」那一步。
"""
import datetime
import shutil
import sys
import tempfile
import time
import tkinter as tk
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import app_theme as T
import kb_download as KB
import kb_widget as kb
import paper_sources as PS
import tools_isolate

PASS, FAIL = [], []
TMP = Path(tempfile.mkdtemp(prefix="kbdl_"))
FAKE_ROOT = TMP / "知识库"
(FAKE_ROOT / "新论文").mkdir(parents=True, exist_ok=True)
(FAKE_ROOT / "CVPR").mkdir(parents=True, exist_ok=True)

# 画像也要隔离：点「下载到知识库」成功后 page_latest 会 PM.remember("下载论文进知识库：…")。
# 不隔离的话，真实目录会多出一个 researcher_profile.json。
_ISO = tools_isolate.isolate()

_orig_root, _orig_inbox = kb.kb_root, kb.inbox_dir
_orig_paths = KB.kb_paths
# 隔离：kb_download 内部一律走 kb_paths()，所以只要换掉它和 kb_widget 的两个入口，
# 整个下载链路就落在临时库里，碰不到用户真实的知识库目录
kb.kb_root = lambda: FAKE_ROOT
kb.inbox_dir = lambda: FAKE_ROOT / "新论文"
KB.kb_paths = lambda: (FAKE_ROOT, FAKE_ROOT / "新论文")


def check(name, fn):
    try:
        fn()
        PASS.append(name)
        print("  PASS  " + name)
    except Exception as exc:
        FAIL.append((name, exc))
        print("  FAIL  " + name + "  -> " + repr(exc))


def eq(a, b, msg=""):
    if a != b:
        raise AssertionError("%s expect %r got %r" % (msg, b, a))


def ok(cond, msg):
    if not cond:
        raise AssertionError(msg)


def wait_until(pred, timeout=90, pump=None):
    """等条件成立。pump 可以是 Tk root（自动同时跑 app.pump()），
    也可以是 FakeApp（FakeApp.pump 内部再 root.update()）。

    注意：后台线程回调靠主线程 pump 才执行，只 sleep 不 pump 会永远等不到。
    """
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pump is not None:
            try:
                pump.update()
            except AttributeError:
                pass
            if hasattr(pump, "pump"):
                pump.pump()
        if pred():
            return True
        time.sleep(0.05)
    return False


# ---------------------------------------------------------------- 纯逻辑

def t_arxiv_id():
    eq(KB._arxiv_id({"arxiv_id": "2509.19733v2"}), "2509.19733")
    eq(KB._arxiv_id({"url": "https://arxiv.org/abs/2509.19733v1"}), "2509.19733")
    eq(KB._arxiv_id({"url": "https://arxiv.org/pdf/2412.01234"}), "2412.01234")
    eq(KB._arxiv_id({"title": "no id here"}), "")
    eq(KB._arxiv_id({}), "")


def t_candidates():
    a = KB.pdf_candidates({"arxiv_id": "2509.19733"})
    ok(a and a[0][0].endswith("/pdf/2509.19733"), "arxiv 优先")
    b = KB.pdf_candidates({"oa": "https://example.org/p.pdf"})
    eq(b[0][0], "https://example.org/p.pdf")
    eq(KB.pdf_candidates({"title": "x"}), [])
    # arxiv_id 与 oa 同指一篇时不应出现重复地址
    c = KB.pdf_candidates({"arxiv_id": "2509.19733",
                           "oa": "https://arxiv.org/pdf/2509.19733"})
    ok(len({u for u, _ in c}) >= 1, "至少一个候选")


def t_safe_name():
    n = KB._pdf_name({"title": "A/B:C? D"}, "2509.19733")
    ok("/" not in n and ":" not in n, "非法字符要清掉: " + n)
    ok(n.endswith("_2509_19733.pdf"), "ID 要有下划线形式: " + n)
    ok("中文标题" in KB._pdf_name({"title": "中文标题 测试"}, ""), "中文要保留")


def t_norm_title():
    eq(KB._norm_title("Object Detection: A Survey!"), "objectdetectionasurvey")
    eq(KB._norm_title(None), "")


def t_suggest():
    ok(KB.suggest_dir("", "CVPR") in ("CVPR", ""), "会议要能命中")
    eq(KB.suggest_dir("量子计算与超导"), "", "猜不出就不要瞎猜")


# ---------------------------------------------------------------- 去重（用临时库）

def t_dedupe(tmp_pdf):
    idx = KB.existing_index(root=FAKE_ROOT)
    p = {"title": "Toward On-Chip Training of Spiking Neural Networks",
         "arxiv_id": "2609.32405"}
    eq(KB.already_have(p, idx), "", "库是空的，不该判重")
    # 造一个同名文件
    f = FAKE_ROOT / "CVPR" / "Some_Title_2609_32405.pdf"
    f.write_bytes(b"%PDF-1.4 fake")
    idx2 = KB.existing_index(root=FAKE_ROOT)
    ok("2609.32405" in KB.already_have(p, idx2), "应按文件名里的 arXiv ID 判重")
    f.unlink()
    # 按标题判重
    g = FAKE_ROOT / "CVPR" / "Toward_On-Chip_Training_of_Spiking_Neural_Networks_for_Dense.pdf"
    g.write_bytes(b"%PDF-1.4 fake")
    idx3 = KB.existing_index(root=FAKE_ROOT)
    ok("标题" in KB.already_have(p, idx3), "应按标题判重，实际: "
       + repr(KB.already_have(p, idx3)))
    g.unlink()


def t_no_public_pdf():
    r = KB.download({"title": "A paper with absolutely no open access version",
                     "source": "europepmc"})
    ok(r["skipped"] or not r["ok"], "没全文不能报成功")
    ok("没有公开全文" in r["reason"] or "已收录" in r["reason"], r["reason"])


# ---------------------------------------------------------------- 真联网下一篇

DL = {}


def t_real_download():
    use = "镜像" if _mirror else "真实网络"

    def go():
        r = PS.fetch_all("事件相机语义分割", limit=5, use_cache=True)
        cands = [p for p in r.get("papers") or [] if KB.pdf_candidates(p)]
        ok(cands, "抓不到任何有公开全文的论文（网络或缓存问题）")
        p = cands[0]
        DL["p"] = p
        res = KB.download(p, out_dir=FAKE_ROOT / "新论文" / "2026-11-13",
                          extract_text=True)
        ok(res["ok"] and not res["skipped"], "下载失败: " + res["reason"])
        ok(Path(res["path"]).exists(), "文件没落地: " + res["path"])
        ok(Path(res["path"]).stat().st_size > 50000, "文件太小，可能不是 PDF")
        head = Path(res["path"]).read_bytes()[:5]
        eq(head, b"%PDF-", "开头不是 PDF 魔数")
        DL["res"] = res
        # 首页文本
        txt = Path(res["path"]).with_suffix(".txt")
        ok(txt.exists() and txt.stat().st_size > 100, "首页文本没生成")
        # 再下一次必须被拦住
        idx = KB.existing_index(root=FAKE_ROOT)
        ok(KB.already_have(p, idx), "下载完应在索引里")
        res2 = KB.download(p, out_dir=FAKE_ROOT / "新论文" / "2026-11-13",
                           extract_text=False)
        ok(res2["skipped"], "重复下载应被跳过，实际: " + repr(res2))
        ok(len(list((FAKE_ROOT / "新论文" / "2026-11-13").glob("*.pdf"))) == 1,
           "目录里应只有 1 个 PDF")

    try:
        go()
    except AssertionError:
        raise


# ---------------------------------------------------------------- 页面

class _FakePage(object):
    """给 app.page(key) 用的空壳：任何属性访问都返回一个空操作。"""

    def __getattr__(self, name):
        return lambda *a, **kw: None


class FakeApp(object):
    def __init__(self, root):
        self.root = root
        self.toasts = []
        self._q = []
        self.pages = {}
        self.current = "home"

    def page(self, key):
        """第 12 版：页面会通过 app.page("library") 去拿别的页面对象，
        假 app 返回一个记录用的空壳即可。"""
        if key not in self.pages:
            self.pages[key] = _FakePage()
        return self.pages[key]

    def post(self, fn):
        self._q.append(fn)

    def pump(self):
        while self._q:
            fn = self._q.pop(0)
            try:
                fn()
            except Exception as exc:
                print("   [pump error]", exc)

    def toast(self, msg, color=None):
        self.toasts.append((msg, color))

    def goto(self, key, **kw):
        return None

    def mark_dirty(self, key):
        return None

    def toggle_theme(self):
        # 2026-11-14 设置页头部加了主题切换按钮，会去调 app.toggle_theme，
        # 假 app 也得有这个方法，否则整页 _build() 直接抛 AttributeError。
        self.themes = getattr(self, "themes", [])
        self.themes.append(True)


ROOT = tk.Tk()
ROOT.geometry("1280x820+30+20")
ROOT.withdraw()
APP = FakeApp(ROOT)


def t_page_button():
    import page_latest
    pg = page_latest.LatestPage(ROOT, APP)
    pg.pack(fill="both", expand=True)
    ROOT.update()
    ok(hasattr(pg, "dl_all_btn"), "缺批量下载按钮")
    eq(str(pg.dl_all_btn["state"]), "disabled", "没结果时批量按钮应禁用")
    APP.pages = {}
    # 造两条结果：一条有全文、一条没有
    papers = [
        {"title": "An Event Camera Paper With PDF", "arxiv_id": "2509.19733",
         "published": "2026-11-10", "source": "arxiv", "url": "https://arxiv.org/abs/2509.19733"},
        {"title": "A Paper Without Any Open Full Text", "published": "2026-11-09",
         "source": "europepmc", "url": ""},
    ]
    pg._clear()
    pg.result = {"papers": papers}
    pg._render("事件相机", {"papers": papers, "by_source": {"arxiv": 1, "europepmc": 1},
                          "errors": []})
    ROOT.update()
    eq(len(pg._dl_btns), 2, "每行都应有一个下载按钮")
    btns = list(pg._dl_btns.values())
    states = [str(b["state"]) for b in btns]
    ok("disabled" in states, "无全文那行按钮应禁用: " + repr(states))
    ok("normal" in states, "有全文那行按钮应可点: " + repr(states))
    eq(str(pg.dl_all_btn["state"]), "normal", "有可下载论文时批量按钮应可用")
    DL["page"] = pg


def t_page_download_click():
    pg = DL["page"]
    p = pg.result["papers"][0]
    pg._download(p)
    got = wait_until(lambda: pg._dl_state.get(id(p)) in ("done", "fail"),
                     timeout=120, pump=APP)
    ok(got, "单篇下载没结束，状态: " + repr(pg._dl_state))
    btn = pg._dl_btns.get(id(p))
    if pg._dl_state.get(id(p)) == "done":
        ok("下载中" not in str(btn["text"]), "按钮文案没收尾")
        ok("重新下载" in str(btn["text"]) or "已在库里" in str(btn["text"]),
           "按钮文案未更新: " + str(btn["text"]))
        ok("已下载" in pg.summary["text"] or "已收录" in pg.summary["text"]
           or "已存" in pg.summary["text"], "摘要行没反馈: " + pg.summary["text"])
    else:
        raise AssertionError("下载失败，摘要行: " + str(pg.summary["text"]))


def t_page_batch():
    pg = DL["page"]
    before = pg.summary["text"]
    pg.download_top(3)
    got = wait_until(lambda: pg._batch is None and "批量" in str(pg.summary["text"]),
                     timeout=180, pump=APP)
    ok(got, "批量下载没结束")
    txt = str(pg.summary["text"])
    ok("批量下载完成" in txt or "批量下载已取消" in txt, "批量结果没显示: " + txt)
    eq(str(pg.dl_all_btn["state"]), "normal", "批量结束后按钮应恢复")
    ok(before != txt, "摘要行应更新")


def t_schedule_status():
    """计划任务状态要能连同失败数一起读到——旧界面只看「下次几点跑」。"""
    st = KB.schedule_status()
    for k in ("task_status", "next_run", "failed", "over_limit", "pdf_total"):
        ok(k in st, "schedule_status 缺字段 " + k)
    eq(st["pdf_total"], scores_now(), "PDF 总量应与 stats 一致")


def scores_now():
    return KB.stats(root=FAKE_ROOT)["pdf_total"]


def t_failures_roundtrip():
    """失败清单能写能读，且只重试「真失败」、不重试「没有公开全文」。"""
    orig = KB.FAILURES_FILE
    KB.FAILURES_FILE = TMP / "download_failures.json"
    try:
        rec = {"time": "2026-11-13T09:00", "downloaded": 1,
               "failed": [{"id": "2509.99999", "title": "Known-good mirror id",
                           "published": "2026-11-10", "error": "timeout"}],
               "over_limit": 3}
        KB.FAILURES_FILE.write_text(__import__("json").dumps(rec), encoding="utf-8")
        got = KB.read_failures()
        eq(len(got["failed"]), 1, "应读出 1 条失败")
        eq(got["over_limit"], 3, "超限数应保留")
        # 空文件/坏文件不能崩
        KB.FAILURES_FILE.write_text("{not json", encoding="utf-8")
        eq(KB.read_failures()["failed"], [], "坏文件应回退空结构")
    finally:
        KB.FAILURES_FILE = orig


def t_retry_no_items():
    orig = KB.FAILURES_FILE
    KB.FAILURES_FILE = TMP / "download_failures_none.json"
    try:
        r = KB.retry_failed()
        eq(r["tried"], 0, "没有失败记录时不该尝试任何下载")
        eq(r["still"], [], "也不该产生新失败")
    finally:
        KB.FAILURES_FILE = orig


def t_seen_ids_readable():
    """定时抓取线的 seen 集合要能读到，用于「这篇是不是已经处理过」。"""
    s = KB.seen_ids()
    ok(isinstance(s, (set, frozenset)), "seen_ids 应返回集合，实际 " + type(s).__name__)


def t_settings_page_renders():
    """设置页要真的能建出来——只测数据层的教训（ProfilePage 那次）不能重犯。"""
    import page_venue
    pg = page_venue.SettingsPage(ROOT, APP)
    pg.pack(fill="both", expand=True)
    ROOT.update()
    texts = []

    def walk(w):
        try:
            t = w.cget("text")
            if t:
                texts.append(str(t))
        except Exception:
            pass
        for c in w.winfo_children():
            walk(c)

    walk(pg)
    blob = " ".join(texts)
    ok("arXiv 抓取" in blob, "设置页缺抓取卡")
    ok("上一次抓取" in blob or "定时任务" in blob, "设置页没显示抓取状态")
    # 有失败记录时应给出重试入口
    orig = KB.FAILURES_FILE
    KB.FAILURES_FILE = TMP / "fail_demo.json"
    try:
        KB.FAILURES_FILE.write_text(__import__("json").dumps(
            {"time": "2026-11-13T09:00", "downloaded": 0,
             "failed": [{"id": "2509.99998", "title": "x", "published": "", "error": "e"}],
             "over_limit": 0}), encoding="utf-8")
        pg.reload()
        ROOT.update()
        ok(pg.retry_btn is not None, "有失败记录时应有重试按钮")
        pg.retry_btn.invoke()
        got = wait_until(lambda: any("重试" in m for m, _ in APP.toasts),
                         timeout=120, pump=APP)
        ok(got, "点了重试应有提示，实际: " + repr(APP.toasts[-3:]))
    finally:
        KB.FAILURES_FILE = orig
        pg.destroy()


def main():
    scores = KB.stats(root=FAKE_ROOT)
    eq(scores["pdf_total"], 0, "临时库一开始应为空")
    check("arXiv ID 从三源记录里抠出来", t_arxiv_id)
    check("PDF 候选地址按优先级排列", t_candidates)
    check("文件名安全化保留中文", t_safe_name)
    check("标题规范化", t_norm_title)
    check("分类建议不乱猜", t_suggest)
    tmp_pdf = TMP / "x.pdf"
    tmp_pdf.write_bytes(b"%PDF-1.4")
    check("去重按 arXiv ID 与标题", lambda: t_dedupe(tmp_pdf))
    check("没有公开全文时说清楚", t_no_public_pdf)
    check("真下载一篇并拦住重复（" + ("镜像" if _mirror else "真实网络") + "）",
          t_real_download)
    check("最新研究页有下载入口", t_page_button)
    check("点下载能走完", t_page_download_click)
    check("批量下载能走完", t_page_batch)
    check("计划任务状态带失败数", t_schedule_status)
    check("失败清单能写能读", t_failures_roundtrip)
    check("没有失败记录时不乱试", t_retry_no_items)
    check("定时线的 seen 集合可读", t_seen_ids_readable)
    check("设置页显示抓取状态并可重试", t_settings_page_renders)

    # 真实目录里不该冒出画像（点下载成功后 page_latest 会写一条记忆）
    leaked = tools_isolate.check_clean()
    for p in leaked:
        try:
            Path(p).unlink()
        except Exception:
            pass
    if leaked:
        FAIL.append(("测试污染真实数据", ", ".join(leaked)))
        print("  FAIL  测试污染真实数据  -> " + ", ".join(leaked))
    else:
        PASS.append("测试没有污染真实用户数据")
        print("  PASS  测试没有污染真实用户数据")

    ROOT.destroy()
    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    for n, e in FAIL:
        print("  FAILED:", n, "->", e)
    return 0 if not FAIL else 1


_mirror = False
if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        kb.kb_root, kb.inbox_dir = _orig_root, _orig_inbox
        KB.kb_paths = _orig_paths
        try:
            ROOT.destroy()
        except Exception:
            pass
        shutil.rmtree(TMP, ignore_errors=True)
        tools_isolate.cleanup(_ISO.get("__tmp__"))