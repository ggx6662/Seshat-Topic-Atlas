"""窗口截图工具。

用法：
    w = find_window("塞莎特——题谱", exact=True)   # 返回 (hwnd, title, RECT, area)
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

# 独立运行截图时必须先声明 DPI 感知：系统缩放 125% 时，未声明的进程拿到
# 的是虚拟化后的窗口尺寸（实测 1337 宽的真实窗口报成 1070），位图也会
# 按 1070 建，截出来的右侧整块界面（含窗口按钮）直接消失，看着像 UI 被裁。
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

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

    2026-11-19：不再用 FindWindowW 直接取第一个命中。打开「文献库」后，
    进程里会多出一个 175x34、同样叫「塞莎特——题谱」的小窗口（在右下角，可见），
    FindWindowW 按 Z 序先返回它，尺寸检查把它当空壳跳过，整个主窗口
    就找不到了，冒烟截图从第 7 页起全部「未找到窗口」。
    现在统一枚举所有标题匹配的顶层窗，再按面积挑最大；排序会自然跳过
    Tk 启动瞬间那个 RECT 在 -32000 的占位壳和上面这种小窗。
    IsIconic 仍只用来还原被最小化的主窗口（枚举出的窗口均先过可见性）。
    """
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
        title = buf.value
        hit = (title == keyword) if exact else (keyword.lower() in title.lower())
        if hit:
            found.append((hwnd, title))
        return True

    user32.EnumWindows(cb, 0)
    hwnds = [h for h, _ in found]

    best = None
    for hwnd in dict.fromkeys(hwnds):
        r = RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        # 最小化时 RECT 在 -32000，下面会被当成空壳跳过；真有标题的窗口先还原
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)
            time.sleep(0.4)
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


DWMWA_EXTENDED_FRAME_BOUNDS = 9


def force_foreground(hwnd):
    """把窗口顶到前台。

    Windows 的前台锁会让 SetForegroundWindow 静默失败（返回 0、窗口仍在后面），
    实测此时屏幕截图截到的是前面那个应用（曾把 DeepSeek 窗口当成塞莎特——题谱存了 12 张）。
    临时把当前线程挂到前台线程的输入队列上，就能合法地抢焦点。
    """
    if user32.GetForegroundWindow() == hwnd:
        return True
    try:
        cur = ctypes.windll.kernel32.GetCurrentThreadId()
        fg = user32.GetForegroundWindow()
        ft = user32.GetWindowThreadProcessId(fg, None) if fg else 0
        attached = False
        if ft and ft != cur:
            attached = bool(user32.AttachThreadInput(cur, ft, True))
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        if attached:
            user32.AttachThreadInput(cur, ft, False)
    except Exception:
        pass
    time.sleep(0.3)
    return user32.GetForegroundWindow() == hwnd


def visible_rect(hwnd):
    """DWM 的可见窗口边界（不含 Win11 那圈约 8px 的不可见拖拽边框）。

    GetWindowRect 含不可见边框；PrintWindow 会把那圈画成纯黑，
    屏幕截图又会把窗口背后的内容截进来。两种都得按可见边界裁掉。
    """
    r = RECT()
    try:
        hr = ctypes.windll.dwmapi.DwmGetWindowAttribute(
            wt.HWND(hwnd), DWMWA_EXTENDED_FRAME_BOUNDS,
            ctypes.byref(r), ctypes.sizeof(r))
        if hr == 0 and r.right > r.left and r.bottom > r.top:
            return r
    except Exception:
        pass
    return None


def grab(hwnd, r, path):
    """截窗口。优先级：前台的 PrintWindow → 顶到最前的屏幕像素 → 后台 PrintWindow。

    2026-11-14 的教训（三条都实测过）：
      1. PrintWindow 对「被脚本改过色的控件」不重画背景，会留未初始化的黑块
         （切到浅色主题后卡片描边那一整条全是 (23,24,26)）——所以要检查。
      2. 非前台的窗口直接 PrintWindow，截到的是它上次重绘的旧内容；
         更糟的是有时**整张图其实是屏幕**，于是截到浏览器。
      3. 所以顺序是：先确认自己在前台再 PrintWindow（快、不闪）；
         不在前台就把窗口顶到最前面抢屏幕像素（准）；最后才退回 PrintWindow。

    2026-11-18：两条路都按 DWM 可见边界裁掉不可见边框。
    PrintWindow 会把那圈边框画成 12px 纯黑（看着像界面缺陷，实际屏幕上看不到）；
    屏幕截图若按 GetWindowRect 取景，会把窗口左侧的桌面一起截进来。
    """
    w, h = r.right - r.left, r.bottom - r.top

    # 最小化时 GetWindowRect 在 -32000 附近，DWM 边界也会给出荒唐值，
    # 直接截会把画面裁掉一大块。先还原、等动画结束再量。
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)
        time.sleep(0.5)
        r = RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        w, h = r.right - r.left, r.bottom - r.top
    force_foreground(hwnd)
    own_fg = (user32.GetForegroundWindow() == hwnd)

    vr = visible_rect(hwnd)
    # 正常只有 8–16px 的不可见边框；超过 24px 说明拿到的是最小化 / 动画中的
    # 中间态（实测曾返回 36px，截出来连侧栏文字都被裁掉）。这时不裁。
    if vr and vr.right > vr.left and vr.bottom > vr.top:
        m = (max(0, vr.left - r.left), max(0, vr.top - r.top),
             max(0, r.right - vr.right), max(0, r.bottom - vr.bottom))
        if max(m) > 24 or (vr.right - vr.left) * (vr.bottom - vr.top) < w * h * 0.9:
            m = (0, 0, 0, 0)
    else:
        m = (0, 0, 0, 0)
    bw, bh = max(1, w - m[0] - m[2]), max(1, h - m[1] - m[3])

    def _fit(img):
        if any(m) and img.size == (w, h):
            img = img.crop((m[0], m[1], w - m[2], h - m[3]))
        return _trim_border(img)

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
            return ok, _fit(Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB"))
        finally:
            gdi32.SelectObject(mdc, old)
            gdi32.DeleteObject(bmp)
            gdi32.DeleteDC(mdc)
            user32.ReleaseDC(hwnd, hdc)

    def _screen():
        from PIL import ImageGrab
        return _fit(ImageGrab.grab(bbox=(r.left, r.top, r.right, r.bottom)))

    def _bad(img):
        # 可见边界裁剪和边缘黑线裁剪各会让尺寸小十几个像素，留出容差
        if abs(img.size[0] - bw) > 24 or abs(img.size[1] - bh) > 24:
            return True
        px = img.load()
        iw, ih = img.size
        dark = total = 0
        for y in range(0, ih, 6):
            for x in range(0, iw, 10):
                total += 1
                c = px[x, y]
                if c[0] < 16 and c[1] < 16 and c[2] < 16:
                    dark += 1
        return bool(total and dark > total * 0.02) or _busy(img, iw, ih)

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
    # 只有真的在前台才抓屏幕像素；否则抓到的就是别的应用（像不像本应用
    # 靠侧栏主色是判断不出来的——对方也可能是浅色侧栏）。
    if force_foreground(hwnd):
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


def _trim_border(img, limit=16):
    """裁掉紧贴边缘、整行/整列几乎纯黑的那几像素。

    Win11 的不可见拖拽边框会被 PrintWindow 画成 ~9px 纯黑；DWM 在窗口
    动画/最小化时又会返回荒唐边界（实测左右相反），指望不上。这里改用
    结果自检：只裁边缘、最多 limit 像素、且该线 90% 以上是近黑，界面
    本身（浅色纸面）不会被误伤。
    """
    w, h = img.size
    if w < 400 or h < 300:
        return img
    px = img.load()

    def dark_row(y):
        n = t = 0
        for x in range(0, w, 4):
            t += 1
            n += max(px[x, y]) < 16
        return n / t > 0.9

    def dark_col(x):
        n = t = 0
        for y in range(0, h, 4):
            t += 1
            n += max(px[x, y]) < 16
        return n / t > 0.9

    left = top = right = bottom = 0
    while left < limit and dark_col(left):
        left += 1
    while right < limit and dark_col(w - 1 - right):
        right += 1
    while top < limit and dark_row(top):
        top += 1
    while bottom < limit and dark_row(h - 1 - bottom):
        bottom += 1
    if not any((left, top, right, bottom)):
        return img
    return img.crop((left, top, w - right, h - bottom))


def _busy(img, w, h):
    """判断截到的是不是本应用：取左上 200x640 的区域（侧栏），
    量化颜色后算主色占比，低于 55% 就认为截到了别的窗口。

    2026-11-14 的旧规则是「侧栏应该一片纯色，颜色种类 > 6 就重截」；
    换到浅色主题后侧栏有 logo、导航图标和文字，这条规则会把每一张
    正确的截图都判成错的（实测误判率 100%），所以改成主色占比。
    2026-11-18 实测侧栏主色占 83%；浏览器页面通常低于 40%。
    """
    if w < 260 or h < 160:
        return False
    px = img.load()
    seen = {}
    total = 0
    for y in range(40, min(h, 640), 3):
        for x in range(8, min(w, 200), 3):
            c = px[x, y]
            k = (c[0] // 8, c[1] // 8, c[2] // 8)
            seen[k] = seen.get(k, 0) + 1
            total += 1
    if not total:
        return True
    return max(seen.values()) / total < 0.55


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
    keyword = "塞莎特——题谱"
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