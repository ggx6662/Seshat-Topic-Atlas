"""窗口截图工具。

用法：
    w = find_window("知识库助手", exact=True)   # 返回 (hwnd, title, RECT, area)
    grab(w[0], w[2], "shot.png")

两条踩过的坑：
1. `find_window` 返回**四元组**，RECT 在第 3 位（w[2]），不是 w[1]。
2. PrintWindow 对「被脚本改过色的控件」不重画背景，会留下未初始化的黑块
   （2026-11-14 实测：切到浅色主题后卡片描边那一整条全是 (23,24,26)）。
   所以黑像素占比超过 2% 时，改用 ImageGrab 抓屏幕真实像素。
"""
import ctypes
import ctypes.wintypes as wt
import sys
import time

from PIL import Image

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
PW_RENDERFULLCONTENT = 0x00000002
WM_PRINT = 0x0317
PRF_NONCLIENT = 0x00000002
PRF_CLIENT = 0x00000004
PRF_ERASEBKGND = 0x00000008
PRF_CHILDREN = 0x00000010
PRF_OWNED = 0x00000020


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", ctypes.c_long),
                ("biHeight", ctypes.c_long), ("biPlanes", wt.WORD),
                ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wt.DWORD),
                ("biClrImportant", wt.DWORD)]


def find_window(keyword, exact=False):
    """按标题找窗口，返回 (hwnd, title, RECT, area) 或 None。

    用 FindWindowW 拿 Tk 的**顶层**窗口，而不是 EnumWindows + 挑最大面积。
    2026-11-14 两次踩坑都出在这里：
      1. Tk 在启动瞬间会有一个标题已设好、但还没摆位置的占位壳（RECT 在
         -32000 附近），按面积排序会和真窗口争，截出 199x34 的一条标题栏；
      2. EnumWindows 返回的句柄不一定是我们自己的进程（实测拿到了 DSH 的
         窗口），而且 `IsIconic` 只对属于本进程的顶层窗有效 —— 对别人的
         窗口可能因为 UIPI 直接返回 1（看着像「最小化了」），于是全部跳过。
    FindWindowW 命中标题即返回，条件最少、最可靠。
    """
    hwnds = []
    try:
        h = user32.FindWindowW(None, keyword if exact else None)
    except Exception:
        h = 0
    if h:
        hwnds.append(h)
    if not exact:
        found = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
        def cb(hwnd, _):
            if not user32.IsWindowVisible(hwnd):
                return True
            n = user32.GetWindowTextLengthW(hwnd)
            if n <= 0:
                return True
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if keyword.lower() in buf.value.lower():
                found.append((hwnd, buf.value))
            return True

        user32.EnumWindows(cb, 0)
        hwnds.extend(h for h, _ in found)

    best = None
    for hwnd in dict.fromkeys(hwnds):
        r = RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        w, h = r.right - r.left, r.bottom - r.top
        # 还没摆好位置的空壳：RECT 在 -32000 附近，或尺寸小得不像主窗口
        if w < 400 or h < 300 or r.left < -10000 or r.top < -10000:
            continue
        if best is None or w * h > best[3]:
            best = (hwnd, None, r, w * h)
    if best is None:
        return None
    n = user32.GetWindowTextLengthW(best[0])
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(best[0], buf, n + 1)
    return (best[0], buf.value, best[2], best[3])


def grab(hwnd, r, path):
    """截窗口。优先级：前台的 PrintWindow → 顶到最前的屏幕像素 → 后台 PrintWindow。

    2026-11-14 的教训（三条都实测过）：
      1. PrintWindow 对「被脚本改过色的控件」不重画背景，会留未初始化的黑块
         （切到浅色主题后卡片描边那一整条全是 (23,24,26)）——所以要检查。
      2. 非前台的窗口直接 PrintWindow，截到的是它上次重绘的旧内容；
         更糟的是有时**整张图其实是屏幕**，于是截到浏览器。
      3. 所以顺序是：先确认自己在前台再 PrintWindow（快、不闪）；
         不在前台就把窗口顶到最前面抢屏幕像素（准）；最后才退回 PrintWindow。
    """
    w, h = r.right - r.left, r.bottom - r.top
    own_fg = (user32.GetForegroundWindow() == hwnd)

    def _printwindow():
        hdc = user32.GetWindowDC(hwnd)
        mdc = gdi32.CreateCompatibleDC(hdc)
        bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
        old = gdi32.SelectObject(mdc, bmp)
        bi = BITMAPINFOHEADER()
        bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bi.biWidth = w
        bi.biHeight = -h
        bi.biPlanes = 1
        bi.biBitCount = 32
        bi.biCompression = 0
        buf = ctypes.create_string_buffer(w * h * 4)
        try:
            ok = user32.PrintWindow(hwnd, mdc, PW_RENDERFULLCONTENT) or user32.PrintWindow(hwnd, mdc, 0)
            gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
            return ok, Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB")
        finally:
            gdi32.SelectObject(mdc, old)
            gdi32.DeleteObject(bmp)
            gdi32.DeleteDC(mdc)
            user32.ReleaseDC(hwnd, hdc)

    def _screen():
        from PIL import ImageGrab
        return ImageGrab.grab(bbox=(r.left, r.top, r.right, r.bottom))

    def _bad(img):
        if img.size != (w, h):
            return True
        px = img.load()
        dark = total = 0
        for y in range(0, h, 6):
            for x in range(0, w, 6):
                total += 1
                c = px[x, y]
                if c[0] < 16 and c[1] < 16 and c[2] < 16:
                    dark += 1
        return bool(total and dark > total * 0.02) or _busy(img, w, h)

    def _frame_shell():
        """（已废弃，保留说明）截 Tk 外层窗壳的尝试。

        2026-11-14 实测：`WM_PRINT` 对 Tk 的 `TkTopLevel` 壳只画得出标题栏和
        边框，客户区整片黑，但**返回 1**（看起来成功）。这条路走不通，
        grab() 已不再调用它。留着是为了让下一个人别再试一次。
        """
        return None

    shots = []
    if own_fg:
        ok, img = _printwindow()
        if not _bad(img):
            img.save(path)
            return bool(ok)
        shots.append((ok, img))

    # 非前台时把窗口顶上来再抢屏幕像素吃掉焦 —— 这是唯一能拿到「当前真实
    # 渲染」的路。注意：**不要**退回 WM_PRINT 截 Tk 外层窗壳，实测它只画得出
    # 标题栏，客户区整片黑却返回 1（看起来成功，比报错更难发现）。
    user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002)
    user32.ShowWindow(hwnd, 9)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.4)
    try:
        img = _screen()
        if not _bad(img):
            img.save(path)
            user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, 0x0001 | 0x0002)
            return True
        shots.append((True, img))
    except Exception:
        pass
    user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, 0x0001 | 0x0002)

    try:
        ok2, img2 = _printwindow()
        shots.append((ok2, img2))
    except Exception:
        pass

    # 实在拿不到干净的就用最接近的那张，但**必须**在日志里说清楚，
    # 并用返回值把「这张图不可信」传出去 —— 截图是用来验证的，
    # 曾把 Edge 的页面当成自己的界面看过。
    if not shots:
        return False
    shots.sort(key=lambda s: _bad(s[1]))
    ok, img = shots[0]
    img.save(path)
    return not _bad(img)


def _busy(img, w, h):
    """左侧栏应该是一片纯色。抽左上角 200x600 的布点区，
    颜色种类超过 6 种就认为截到了别的窗口（需要重抢）。"""
    if w < 260 or h < 160:
        return False
    px = img.load()
    seen = set()
    for y in range(40, min(h, 640), 4):
        for x in range(8, 200, 4):
            c = px[x, y]
            seen.add((c[0] // 8, c[1] // 8, c[2] // 8))
            if len(seen) > 6:
                return True
    return False


def _logical_size(hwnd, w, h):
    """按窗口 DPI 把物理像素换算成 PrintWindow 实际绘制的逻辑像素。"""
    try:
        dpi = ctypes.windll.user32.GetDpiForWindow(hwnd)
        if dpi:
            return (int(round(w * 96.0 / dpi)), int(round(h * 96.0 / dpi)))
    except Exception:
        pass
    return w, h


def main():
    args = [a for a in sys.argv[1:]]
    path = args[0] if args else "shot.png"
    keyword = "知识库助手"
    exact = "--exact" in args
    size = None
    for a in args:
        if a.startswith("--size="):
            w, h = a.split("=", 1)[1].lower().split("x")
            size = (int(w), int(h))
        elif a == "--exact":
            continue
        elif not a.startswith("--") and a != path:
            keyword = a
    hit = find_window(keyword, exact)
    if not hit:
        print("no window:", keyword)
        return 1
    hwnd, title, r, _ = hit
    if size:
        sw = user32.GetSystemMetrics(0)
        sh = user32.GetSystemMetrics(1)
        w = min(size[0], sw - 40)
        h = min(size[1], sh - 80)
        user32.ShowWindow(hwnd, 9)
        user32.SetWindowPos(hwnd, 0, 20, 10, w, h, 0x0004)
        time.sleep(0.8)
        user32.GetWindowRect(hwnd, ctypes.byref(r))
    ok = grab(hwnd, r, path)
    print("%s -> %s (%sx%s) ok=%s" % (title, path, r.right - r.left, r.bottom - r.top, ok))
    return 0


if __name__ == "__main__":
    sys.exit(main())