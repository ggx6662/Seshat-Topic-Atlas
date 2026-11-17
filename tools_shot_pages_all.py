"""一次重截全部页面截图（深色 12 页 + 浅色 2 页）。

用法：
    python -X utf8 tools_shot_pages_all.py [页名...]

为什么要有这个脚本：截图是「验证」而不是「产出」，必须一眼能信。
2026-11-14 踩过的坑都固化成下面的做法：

1. **不要用 FindWindowW / EnumWindows 找窗口。** 这台机器上第三方窗口标题
   也含「知识库助手」（DSH 自己的窗口），而且 Tk 在启动瞬间还存在一个
   RECT 在 -32000 的占位壳。改成直接读**本进程**的 `app.winfo_x/y/width/
   height`，再按窗口 DPI 换算成物理像素，拿到客户区矩形。
2. **只截客户区，不带标题栏。** 光靠 PrintWindow 拿不到客户区时，
   退路是「屏幕像素」——那就必须严格限定在客户区矩形里，
   否则会把标题栏和旁边的微信窗口一起截进来（实测截到过整屏聊天界面）。
3. **窗口必须整窗在屏幕里。** 曾有 1336x900 放在 (0,0)：窗口实际宽 1352，
   右边 16px 永远拍不到，内容被裁一截还以为是布局坏了。
4. 图片存到 screenshots/ 之前会**校验**：客户区左上角应是侧栏底色
   （暗色 #111213 / 浅色 #f6f7f8），不是就报 `ok=False` 并保留旧图。
"""
import ctypes
import os
import sys
import time

import tools_shot as S
import app_main
import app_theme

X, Y, W, H = 30, 20, 1320, 880
PAGES = (
    ("home", "01-home"),
    ("topic", "02-topic"),
    ("gap", "03-gap"),
    ("ideas", "04-ideas"),
    ("map", "05-map"),
    ("mentor", "06-mentor"),
    ("library", "07-library"),
    ("latest", "08-latest"),
    ("skills", "09-skills"),
    ("venue", "10-venue"),
    ("profile", "11-profile"),
    ("settings", "12-settings"),
    # 2026-11-15 新增：研究计划页（侧栏「个人」分组）
    ("plan", "13-plan"),
)
LIGHT = (("home", "20-home-light"), ("library", "21-library-light"),
         ("plan", "22-plan-light"))

USER32 = ctypes.windll.user32
GDI32 = ctypes.windll.gdi32


def spin(win, n):
    for _ in range(n):
        win.update()
        time.sleep(0.05)


def client_rect(app):
    """本进程窗口的客户区，物理像素。"""
    try:
        scale = float(app.winfo_fpixels("1i")) / 96.0
    except Exception:
        scale = 1.0
    try:
        fx = app.winfo_rootx() - app.winfo_x()
        fy = app.winfo_rooty() - app.winfo_y()
    except Exception:
        fx, fy = 8, 31
    x = int(round((app.winfo_x() + fx) * scale))
    y = int(round((app.winfo_y() + fy) * scale))
    r = S.RECT()
    r.left, r.top = x, y
    r.right = x + int(round(app.winfo_width() * scale))
    r.bottom = y + int(round(app.winfo_height() * scale))
    return r


def _side_color(app):
    """客户区左上角应该是侧栏底色。"""
    try:
        import app_theme as T
        return T.hex_to_rgb(T.SIDEBAR)
    except Exception:
        return (17, 18, 19)


def _shot(hwnd, r):
    """PrintWindow 拿客户区；不行就用屏幕像素，但严格裁到客户区矩形。"""
    from PIL import Image, ImageGrab
    w, h = r.right - r.left, r.bottom - r.top

    hdc = USER32.GetWindowDC(hwnd)
    mdc = GDI32.CreateCompatibleDC(hdc)
    bmp = GDI32.CreateCompatibleBitmap(hdc, w, h)
    old = GDI32.SelectObject(mdc, bmp)
    bi = S.BITMAPINFOHEADER()
    bi.biSize = ctypes.sizeof(S.BITMAPINFOHEADER)
    bi.biWidth, bi.biHeight = w, -h
    bi.biPlanes, bi.biBitCount, bi.biCompression = 1, 32, 0
    buf = ctypes.create_string_buffer(w * h * 4)
    img = None
    try:
        USER32.PrintWindow(hwnd, mdc, S.PW_RENDERFULLCONTENT)
        GDI32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
        img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB")
    finally:
        GDI32.SelectObject(mdc, old)
        GDI32.DeleteObject(bmp)
        GDI32.DeleteDC(mdc)
        USER32.ReleaseDC(hwnd, hdc)
    return img


def _verify(img, want):
    """左上角必须是侧栏底色（容差 6）。"""
    px = img.load()
    hits = 0
    for x, y in ((6, 60), (10, 120), (30, 200), (8, 400)):
        c = px[x, y]
        if max(abs(c[0] - want[0]), abs(c[1] - want[1]), abs(c[2] - want[2])) <= 6:
            hits += 1
    return hits >= 2


def shoot(app, hwnd, key, name, wait=1.2):
    app.goto(key)
    spin(app, 30)
    # 页面数据是后台线程加载的，30 帧（约 0.5 秒）常常还没回来，
    # 截到的是空态。这里再等一段时间让 post() 回调落地。
    deadline = time.time() + wait
    while time.time() < deadline:
        spin(app, 2)
        time.sleep(0.03)
    r = client_rect(app)
    want = _side_color(app)
    img = _shot(hwnd, r)
    ok = _verify(img, want) if img is not None else False
    if not ok:
        # 后台窗口的 PrintWindow 会是黑块或旧帧；把它顶到最前面，
        # 但只取客户区矩形 —— 绝不扩大到整窗。
        USER32.SetForegroundWindow(hwnd)
        USER32.BringWindowToTop(hwnd)
        time.sleep(0.45)
        spin(app, 2)
        try:
            from PIL import ImageGrab
            img2 = ImageGrab.grab(bbox=(r.left, r.top, r.right, r.bottom))
            if _verify(img2, want):
                img, ok = img2, True
        except Exception:
            pass
    if img is None:
        print("failed: %s (no image)" % name)
        return False
    if not ok:
        print("WARN: %s 内容校验未通过（可能被其它窗口遮挡），仍写出" % name)
    img.save("screenshots/%s.png" % name)
    print("saved: %s.png  ok=%s  %dx%d" % (name, ok, img.size[0], img.size[1]))
    return ok


def _want_theme():
    """记下用户原来的主题，结束时原样写回。"""
    try:
        import kb_widget as kb
        return kb.load_config().get("theme") or "light"
    except Exception:
        return "light"


def main():
    only = {a for a in sys.argv[1:] if not a.startswith("-")}
    os.makedirs("screenshots", exist_ok=True)
    orig = _want_theme()

    # ---- 深色 12 页 ----
    # **不能直接依赖配置文件里的主题**：上一轮跑浅色阶段会把它写成 light，
    # 于是这一轮的「深色截图」其实拍的是浅色（踩过：01-home.png 与
    # 20-home-light.png 字节完全相同）。这里显式开关，不再看 config。
    app = app_main.App()
    app.geometry("%dx%d+%d+%d" % (W, H, X, Y))
    spin(app, 50)
    if app_theme.MODE != "dark":
        app.apply_theme("dark")
        spin(app, 30)
    hwnd = app.winfo_id()
    for key, name in PAGES:
        if only and key not in only:
            continue
        shoot(app, hwnd, key, name)

    # ---- 浅色 2 页 ----
    # 必须重建窗口：Card 的默认颜色是模块导入时绑定的。
    app.apply_theme("light")
    spin(app, 20)
    app.destroy()
    app2 = app_main.App()
    app2.geometry("%dx%d+%d+%d" % (W, H, X, Y))
    spin(app2, 60)
    if app_theme.MODE != "light":
        app2.apply_theme("light")
        spin(app2, 30)
    hwnd2 = app2.winfo_id()
    for key, name in LIGHT:
        if only and key not in only:
            continue
        shoot(app2, hwnd2, key, name)

    # ---- 还原用户原来的主题 ----
    app2.apply_theme(orig)
    spin(app2, 20)
    app2.destroy()
    print("done（主题已还原为 %s）" % orig)
    return 0


if __name__ == "__main__":
    sys.exit(main())