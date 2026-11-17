# -*- coding: utf-8 -*-
"""移动端布局检查：在真实浏览器里量尺寸，找出撑破屏幕的元素。

为什么不用肉眼看截图：390px 宽的截图里，「文字被右边切掉」和「字号偏大」
看起来一模一样，但修法完全不同。这里直接问浏览器要数字。

实现要点：
  · 探测页用 file:// 打开，iframe 一个 http://127.0.0.1 的页面。
    这是跨源，正常拿不到 contentDocument —— 必须加 --disable-web-security。
    只用于量尺寸，正式页面绝不能这么干。
  · 用 `--dump-dom` 取结果，所以结果要写进 DOM 文本，不能只 console.log。
  · JSON 用括号配对切（className 里可能有花括号）。

    python tools_check_mobile.py [port]
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

# %E7%BA%A2... 就是「红外小目标检测」，URL 里不能直接写中文
DIRECTION_ENC = "%E7%BA%A2%E5%A4%96%E5%B0%8F%E7%9B%AE%E6%A0%87%E6%A3%80%E6%B5%8B"

PROBE = r"""<!doctype html>
<html><head><meta charset="utf-8">
<style>html,body{margin:0;background:#000;color:#0f0;font:13px monospace}
#r{padding:8px;white-space:pre-wrap;word-break:break-all}</style>
</head><body>
<div id="r">measuring...</div>
<script>
var BASE = "__BASE__";
var D = "__D__";
var fr = document.createElement("iframe");
fr.src = BASE + "/?d=" + D;
fr.style.cssText = "width:390px;height:3200px;border:0";
fr.onload = function () {
  setTimeout(function () {
    try {
      measure();
    } catch (e) {
      document.getElementById("r").textContent = "RESULT:{\"error\":\"" + e + "\"}";
    }
  }, 6000);
};
document.body.appendChild(fr);

function measure() {
  var d = fr.contentDocument, w = fr.contentWindow;
  if (!d) {
    document.getElementById("r").textContent =
      "RESULT:{\"error\":\"contentDocument 为 null（跨源被拦，检查 --disable-web-security）\"}";
    return;
  }
  var W = 390;
  var out = {
    clientWidth: d.documentElement.clientWidth,
    scrollWidth: d.documentElement.scrollWidth,
    overflow: []
  };
  var all = d.querySelectorAll("body *");
  for (var i = 0; i < all.length; i++) {
    var n = all[i], b = n.getBoundingClientRect();
    if (b.width <= 0 || b.right <= W + 1) continue;
    // 故意可横向滚动的容器里的元素不算溢出：导航栏在手机上就是横滑的，
    // 里面的按钮自然会超出可视宽，但它被 overflow-x:auto 的父级裁住了，
    // 并没有把整页撑宽。真正该报的是「把页面撑破」的元素。
    var p = n.parentElement, inScroll = false;
    while (p && p !== d.body) {
      var ov = w.getComputedStyle(p).overflowX;
      if (ov === "auto" || ov === "scroll" || ov === "hidden") { inScroll = true; break; }
      p = p.parentElement;
    }
    if (inScroll) continue;
    out.overflow.push({
      tag: n.tagName,
      cls: String(n.className || "").slice(0, 40),
      right: Math.round(b.right),
      width: Math.round(b.width)
    });
  }
  if (out.overflow.length > 12) out.overflow = out.overflow.slice(0, 12);

  var q = d.getElementById("q");
  if (q) {
    out.inputFont = w.getComputedStyle(q).fontSize;
    out.inputH = Math.round(q.getBoundingClientRect().height);
  }
  var tabs = d.querySelectorAll(".tab");
  if (tabs.length) {
    out.tabH = Math.round(tabs[0].getBoundingClientRect().height);
    out.tabCount = tabs.length;
  }
  var nav = d.querySelector(".tabs");
  if (nav) {
    out.navScrolls = nav.scrollWidth > nav.clientWidth + 1;
    out.navClientW = nav.clientWidth;
    out.navScrollW = nav.scrollWidth;
  }
  var sp = d.querySelector(".stat b");
  if (sp) out.statFont = w.getComputedStyle(sp).fontSize;
  // 「分析」按钮必须完整可见 —— 它被裁掉就等于移动端点不了。
  var go = d.getElementById("go");
  if (go) {
    var gb = go.getBoundingClientRect();
    out.goRight = Math.round(gb.right);
    out.goVisible = gb.right <= W + 1;
  }
  var qb = d.getElementById("q");
  if (qb) out.qRight = Math.round(qb.getBoundingClientRect().right);
  var cols = d.querySelector(".cols");
  if (cols) out.colsColumns = w.getComputedStyle(cols).gridTemplateColumns;
  var cand = d.querySelector(".cand-reason");
  if (cand) out.candW = Math.round(cand.getBoundingClientRect().width);
  out.bodyScroll = d.body.scrollWidth;
  out.rendered = !!d.querySelector(".cand");
  document.getElementById("r").textContent = "RESULT:" + JSON.stringify(out);
}
</script>
</body></html>
"""


def _take_json(s):
    """从字符串里抠出第一个完整的 JSON 对象（括号配对，跳过字符串里的花括号）。"""
    s = s.strip()
    i = s.find("{")
    if i < 0:
        raise ValueError("没找到 JSON 起始")
    depth, in_str, esc = 0, False, False
    for k in range(i, len(s)):
        ch = s[k]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[i:k + 1]
    raise ValueError("JSON 括号没闭合")


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8766
    # 同源才好读 contentDocument：探测页也由 8766 提供。
    # 直接把 probe 写到 web_static 下，用完删掉 —— 比折腾 --disable-web-security
    # 可靠得多（后者在 file:// 页面里实测不生效）。
    probe_path = os.path.join(HERE, "web_static", "__probe.html")
    src = PROBE.replace("__BASE__", "http://127.0.0.1:%d" % port).replace("__D__", DIRECTION_ENC)
    src = src.replace('src = BASE + "/?d=" + D', 'src = "/?d=" + D')
    with open(probe_path, "w", encoding="utf-8") as fh:
        fh.write(src)
    url = "http://127.0.0.1:%d/__probe.html" % port
    tmp = tempfile.mkdtemp(prefix="kbprobe-")

    try:
        proc = subprocess.run(
            [CHROME, "--headless=new", "--disable-gpu",
             "--user-data-dir=" + os.path.join(tmp, "prof"),
             "--window-size=420,3400", "--virtual-time-budget=20000",
             "--dump-dom", url],
            capture_output=True, text=True, encoding="utf-8", timeout=240)
    finally:
        try:
            os.remove(probe_path)
        except OSError:
            pass

    line = ""
    for ln in proc.stdout.splitlines():
        if "RESULT:{" in ln:
            cand = ln.split("RESULT:", 1)[1]
            # 只认真正的 JSON（脚本源码里也有 RESULT: 字样）
            if cand.strip().startswith("{"):
                line = cand
                break
    if not line:
        print("没测到结果。stdout 前 500 字符：")
        print(proc.stdout[:500])
        return 1

    data = json.loads(_take_json(line))
    if data.get("error"):
        print("探测失败：%s" % data["error"])
        return 1
    print(json.dumps(data, ensure_ascii=False, indent=2))

    problems = []
    if not data.get("rendered"):
        problems.append("页面没有渲染出候选卡（数据可能没加载完）")
    if data["scrollWidth"] > data["clientWidth"] + 1:
        problems.append("横向溢出 %dpx" % (data["scrollWidth"] - data["clientWidth"]))
    if data.get("tabH", 99) < 44:
        problems.append("导航可点高度只有 %spx（建议 ≥44px）" % data.get("tabH"))
    try:
        if float(str(data.get("inputFont", "0")).replace("px", "")) < 16:
            problems.append("输入框字号 %s，iOS 聚焦时会自动放大页面" % data.get("inputFont"))
    except Exception:
        pass
    if data.get("overflow"):
        problems.append("有 %d 个元素超出 390px 宽" % len(data["overflow"]))

    if problems:
        print("\n问题：")
        for p in problems:
            print("  - " + p)
        return 1
    print("\n移动端布局检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())