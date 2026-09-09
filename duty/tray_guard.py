# -*- coding: utf-8 -*-
"""tray_guard — 量化看守·系统托盘壳 (2026-09-09)
给值守引擎一个状态栏图标 + 右键菜单操控, 为以后可视化操作打底。
只做"看护/操控", 不放真单: 菜单动作 = 查看状态/启动/重启/打开日志与目录/退出壳;
真实买卖仍只由 duty_engine 在 14:44 执行段自动做(单实例锁兜底, 本壳绝不代下单)。

图标颜色:  绿=引擎在岗(心跳<20s)  黄=心跳过期(引擎可能挂)  红=引擎不在
依赖:      pystray + pillow (E:\\python 已装)
启动(生产): E:\\python\\量化看守.exe -B duty\\tray_guard.py   (登录计划任务 QuantTrayOnLogon)
"""
import io, os, subprocess, sys, threading, time
from pathlib import Path

# 高DPI感知: 不声明的话 Windows 会把Tk窗口按位图拉伸(文字/圆角全糊), 必须进程级声明
try:
    if os.name == "nt":
        ctypes_shcore = __import__("ctypes").windll.shcore
        ctypes_shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        __import__("ctypes").windll.user32.SetProcessDPIAware()
    except Exception:
        pass

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

import pystray
from PIL import Image, ImageDraw

HEART = ROOT / "outputs" / "watch_heartbeat.txt"
TRAY_LOG = ROOT / "outputs" / "tray_guard_log.txt"
ENGINE = ROOT / "duty" / "duty_engine.py"
EXE = sys.executable or r"E:\python\量化看守.exe"

_stop = threading.Event()

import ctypes
from ctypes import wintypes

# Win32 回调相关函数: 统一设64位参数/返回类型(否则 lParam 等大值按32位转会溢出)
_u32 = ctypes.windll.user32
_u32.DefWindowProcW.argtypes = (ctypes.c_void_p, ctypes.c_uint,
                                ctypes.c_size_t, ctypes.c_longlong)
_u32.DefWindowProcW.restype = ctypes.c_longlong


def tlog(msg):
    try:
        with open(TRAY_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def now_s():
    return time.time()


def heart_age():
    """心跳文件年龄秒; 无文件/异常返回很大"""
    try:
        return now_s() - HEART.stat().st_mtime
    except Exception:
        return 10 ** 6


def heart_state():
    """解析心跳内容 state=duty|盘后|tasks=4 -> (ts, session)"""
    try:
        line = HEART.read_text(encoding="utf-8").strip()
        ts = line[:19]
        sess = line.split("state=")[1].split("|")[1] if "state=" in line else "?"
        return ts, sess
    except Exception:
        return "", "?"


def engine_alive():
    return heart_age() < 20


def engine_pids():
    """找正在跑 duty_engine.py 的进程PID (按命令行匹配, 避免误杀托盘自身)
    GUI进程内调控制台程序必须带 CREATE_NO_WINDOW, 否则闪cmd框"""
    pids = []
    try:
        script = (
            "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' OR Name='python.exe'"
            " OR Name='量化看守.exe'\" | Where-Object { $_.CommandLine -like '*duty_engine.py*' }"
            " | ForEach-Object { $_.ProcessId }"
        )
        out = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                             capture_output=True, text=True, timeout=20,
                             creationflags=0x08000000).stdout
        for ln in out.splitlines():
            ln = ln.strip()
            if ln.isdigit():
                pids.append(int(ln))
    except Exception as e:
        tlog(f"engine_pids err: {repr(e)[:80]}")
    return pids


def _spawn_engine():
    """无条件拉起引擎进程(单实例锁由引擎自己挡双跑); 返回 bool
    stderr/stdout 捕获到文件: 定位'Popen返回但进程没起来'类问题"""
    try:
        errf = open(ROOT / "outputs" / "engine_spawn_stderr.log", "ab")
        subprocess.Popen([EXE, "-B", str(ENGINE)], cwd=str(ROOT),
                         creationflags=0x08000000,
                         stdout=errf, stderr=errf)
        return True
    except Exception as e:
        tlog(f"_spawn err: {repr(e)[:80]}")
        return False


def start_engine():
    """启动引擎: 进程检测为准(心跳判断会误判刚kill的实例还'在岗')"""
    pids = engine_pids()
    if pids:
        return f"引擎已在跑 PID={pids}"
    ok = _spawn_engine()
    tlog(f"拉起 duty_engine -> {'OK' if ok else 'FAIL'}")
    return "已拉起" if ok else "拉起失败, 看日志"


def restart_engine():
    dead = []
    for pid in engine_pids():
        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True,
                           timeout=10, creationflags=0x08000000)
            dead.append(pid)
        except Exception:
            pass
    if dead:
        time.sleep(2.0)          # 等旧进程彻底退出(OS释放 resident.lock)
    ok = _spawn_engine()          # 无条件起新的, 锁会挡掉任何漏网旧实例
    msg = "已重启" if ok else "重启失败"
    tlog(f"重启引擎 旧PID={dead} -> {msg}")
    return msg


def make_icon(color):
    """64x64 纯色状态灯: 整块实色圆角方块(无高光/渐变, 托盘缩放下颜色才准)"""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([2, 2, 62, 62], radius=12, fill=color)
    return img


GREEN = (46, 160, 67, 255)
YELLOW = (240, 180, 41, 255)
RED = (214, 69, 65, 255)


def status_lines():
    ts, sess = heart_state()
    age = heart_age()
    if engine_alive():
        st = "运行中"
        color = GREEN
    elif age < 90:
        st = "心跳过期(可能挂)"
        color = YELLOW
    else:
        st = "未运行"
        color = RED
    return color, [
        f"量化看守 · {st}",
        f"时段: {sess}   心跳: {ts or '--'}",
    ]


def snapshot():
    """状态快照 -> (color, head, line)
    head/line 为纯文本(Windows菜单单色, 彩灯在左键面板里画); color 同时驱动托盘图标色"""
    ts, sess = heart_state()
    age = heart_age()
    if engine_alive():
        st, color = "运行中", GREEN
    elif age < 90:
        st, color = "心跳过期", YELLOW
    else:
        st, color = "未运行", RED
    head = f"量化看守 · {st}"
    line = f"时段: {sess}    心跳: {ts or '--'}"
    return color, head, line


# ---------------- 自绘右键菜单(紧凑倒角面板 + 渐隐分隔 + 文字不动的平滑高亮) ----------------
_MENU_W = 222
_MENU_H = 27          # 行高(贴近系统菜单的紧凑度)
_MENU_SEP = 10        # 分隔区高
_R = 11              # 四角圆角半径(圆弧, 非斜切) —— 老板要的"倒角"=圆角
_M = 1                # 外衬边距(canvas底色形成1px衬边)
_TC = "#010203"       # 透明色(把窗口四角切成倒角用; 与界面色不相撞)
_BG = "#f7f8fa"       # 面板底
_OUT = "#e7eaef"      # 面板外衬(倒角露出的颜色)
_FG = "#1b1f24"       # 主文字
_FG2 = "#5a6472"      # 次要文字(信息行)
_HOV = "#dfe6f2"      # hover 高亮
_SEP_C = "#b8bfc9"    # 分隔线中心色
_FONT = ("Microsoft YaHei UI", 9)
_FONT2 = ("Microsoft YaHei UI", 8)
_CURRENT_ICON = [None]


def _rgb(hx):
    """'#rrggbb' -> (r,g,b) (PIL putpixel 只要tuple/int, 传字符串会崩)"""
    return (int(hx[1:3], 16), int(hx[3:5], 16), int(hx[5:7], 16))


def _apply_color_key(hwnd, hexcolor):
    """用 Win32 SetLayeredWindowAttributes 把 hexcolor 变透明(颜色键)。
    Tk 的 -transparentcolor 在 DPI感知+Win11 下常失效 -> 绕过它手工设。"""
    try:
        u = ctypes.windll.user32
        GWL_EXSTYLE = -20
        WS_EX_LAYERED = 0x80000
        LWA_COLORKEY = 1
        hwnd = int(hwnd)
        ex = u.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        u.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex | WS_EX_LAYERED)
        b = int(hexcolor[5:7], 16)
        g = int(hexcolor[3:5], 16)
        r = int(hexcolor[1:3], 16)
        colref = (b << 16) | (g << 8) | r      # 0x00BBGGRR
        u.SetLayeredWindowAttributes(hwnd, colref, 0, LWA_COLORKEY)
        return True
    except Exception as e:
        tlog(f"apply_color_key err: {repr(e)[:80]}")
        return False


def _round_rgn(hwnd, w, h, r):
    """把窗口区域(SetWindowRgn+CreateRoundRectRgn)裁成圆角形状。
    不依赖透明颜色键(不受 Win11/DPI 失效影响), 是 Windows 圆角窗的可靠做法。"""
    try:
        gdi = ctypes.windll.gdi32
        u = ctypes.windll.user32
        hwnd = int(hwnd)
        rgn = gdi.CreateRoundRectRgn(0, 0, w + 1, h + 1, r * 2, r * 2)
        u.SetWindowRgn(hwnd, rgn, True)
        return True
    except Exception as e:
        tlog(f"round_rgn err: {repr(e)[:80]}")
        return False

def _acrylic_blur(hwnd):
    """Win11 Acrylic 磨砂(系统实时模糊): 失败静默返回False, 面板仍可用普通配色"""
    try:
        from BlurWindow.blurWindow import blur as _blur
        # 8位ABGR着色: '#RRGGBBAA' -> 半透深玻璃
        _blur(int(hwnd), hexColor="#23272e90", Acrylic=True)
        return True
    except Exception as e:
        tlog(f"acrylic err: {repr(e)[:80]}")
        return False



def _tray_rect():
    """托盘图标屏幕矩形(left,top,right,bottom), 用 Shell_NotifyIconGetRect(标准做法);
    拿不到返回 None(调用方用右下角兜底)"""
    icon = _CURRENT_ICON[0]
    if icon is None:
        return None
    try:
        hwnd = int(icon._hwnd)
        uid = id(icon)

        class NID(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_size_t), ("hWnd", ctypes.c_void_p),
                        ("uID", ctypes.c_uint), ("guidItem", ctypes.c_byte * 16)]

        class RC(ctypes.Structure):
            _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                        ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

        n = NID()
        n.cbSize = ctypes.sizeof(NID)
        n.hWnd = ctypes.c_void_p(hwnd)
        n.uID = uid
        rc = RC()
        if ctypes.windll.shell32.Shell_NotifyIconGetRect(ctypes.byref(n),
                                                         ctypes.byref(rc)) == 0:
            return (rc.left, rc.top, rc.right, rc.bottom)
    except Exception as e:
        tlog(f"tray_rect err: {repr(e)[:60]}")
    return None


# 右键菜单单例(防止重复右键叠出多个框)
_popup_lock = threading.Lock()
_popup_active = [False]


def _sep_image(w, master=None):
    """分隔渐变图: 中间实->两端融进面板底(PhotoImage 必须绑当前线程的 root, 否则崩)"""
    from PIL import Image as _I, ImageDraw as _ID
    from PIL import ImageTk
    h = 1
    img = _I.new("RGB", (w, h), _BG)
    d = _ID.Draw(img)
    for x in range(w):
        k = 1 - abs(x - w / 2) / (w / 2)
        a = int(255 * (0.10 + 0.90 * (k ** 1.6)))
        r = int(int(_SEP_C[1:3], 16) * a / 255 + int(_BG[1:3], 16) * (1 - a / 255))
        g = int(int(_SEP_C[3:5], 16) * a / 255 + int(_BG[3:5], 16) * (1 - a / 255))
        b = int(int(_SEP_C[5:7], 16) * a / 255 + int(_BG[5:7], 16) * (1 - a / 255))
        d.line([(x, 0), (x, 0)], fill=(r, g, b))
    return ImageTk.PhotoImage(img, master=master)


def _rounded_bg(w, h, r, corner=None, master=None):
    """整面板圆角底图: 圆角矩形, 圆角外像素=corner(默认 _TC, 由
    -transparentcolor 挖成真透明)。先超采样抗锯齿, 再按几何距离做二值化,
    避免颜色键透明下出现灰边。 corner 可为 '#rrggbb' 字符串, 内部转 tuple。"""
    from PIL import Image as _I, ImageDraw as _ID, ImageTk
    ss = 3
    W, H, R = w * ss, h * ss, r * ss
    corner_s = _TC if corner is None else corner
    corner = _rgb(corner_s)
    img = _I.new("RGB", (W, H), corner)
    d = _ID.Draw(img)
    d.rounded_rectangle([0, 0, W - 1, H - 1], radius=R, fill=_BG)
    # 圆角外区域强制画回 corner(像素级精确, 不吃 AA 灰边)
    px = img.load()
    rr = R * R
    for cx, cy in ((R, R), (W - 1 - R, R), (R, H - 1 - R), (W - 1 - R, H - 1 - R)):
        for yy in range(max(0, cy - R - 1), min(H, cy + R + 2)):
            for xx in range(max(0, cx - R - 1), min(W, cx + R + 2)):
                if (xx - cx) ** 2 + (yy - cy) ** 2 > rr:
                    px[xx, yy] = corner
    img = img.resize((w, h), _I.Resampling.LANCZOS)
    return ImageTk.PhotoImage(img, master=master)


def show_popup():
    """托盘右键: 紧贴图标上方弹出 Win32 逐像素抗锯齿自绘菜单(单例, 点外部/ESC关闭)"""
    with _popup_lock:
        if _popup_active[0]:
            return          # 已在显示 -> 不再叠开
        _popup_active[0] = True
    threading.Thread(target=_menu_call, daemon=True).start()


# ---------------- Win32 逐像素抗锯齿自绘菜单(UpdateLayeredWindow) ----------------
_menu_state = {}          # hwnd -> dict(hit, do, redraw, hover, hwnd, geo)
WM_MOUSEMOVE = 0x0200
WM_LBUTTONUP = 0x0202
WM_TIMER = 0x0113
WM_NCHITTEST = 0x0084
WM_DESTROY = 0x0002
HTCLIENT = 1
AC_SRC_OVER = 0


def _menu_items():
    color, head, line = snapshot()
    return color, [
        ("head", head, color, False, None),
        ("info", line, None, True, None),
        ("sep", "", None, False, None),
        ("act", "打开状态面板", None, False, lambda: show_panel()),
        ("act", "启动值守引擎", None, False, lambda: _act(_start_or_tip)),
        ("act", "重启值守引擎", None, False, lambda: _act(restart_engine)),
        ("sep", "", None, False, None),
        ("act", "打开值守日志", None, False, lambda: _open(ROOT / "outputs" / "duty_log.txt")),
        ("act", "打开 outputs 目录", None, False, lambda: _open(ROOT / "outputs")),
        ("sep", "", None, False, None),
        ("act", "退出量化看守", None, False, lambda: _quit(_CURRENT_ICON[0])),
    ]


def _render_menu(items, W, H, scale, hover_idx):
    """渲染整窗 ARGB 位图(超采样抗锯齿) -> (premul BGRA bytes, W, H)"""
    from PIL import Image as _I, ImageDraw as _ID
    from PIL import ImageFont
    S = 3
    bw, bh = W * S, H * S
    img = _I.new("RGBA", (bw, bh), (0, 0, 0, 0))
    d = _ID.Draw(img)
    r = int(_R * scale)
    d.rounded_rectangle([0, 0, bw - 1, bh - 1], radius=r * S, fill=_BG)
    IN = int(6 * scale)
    tx = int(IN + 22 * scale)
    dotx = int(IN + 9 * scale)
    f_main = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", int(13 * scale * S))
    f_min = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", int(12 * scale * S))
    y = int(IN * S)
    for idx, (kind, text, dot, small, act) in enumerate(items):
        hh = int(_MENU_H * scale) * S if kind != "sep" else int(_MENU_SEP * scale) * S
        cy = y + hh // 2
        if kind == "sep":
            # 渐隐分隔线: 中间实->两端消失
            for xx in range(int(IN * S), bw - int(IN * S)):
                k = 1 - abs(xx - bw / 2) / (bw / 2 - int(IN * S))
                a = (0.10 + 0.90 * (k ** 1.6))
                col = tuple(int(255 - (255 - int(_SEP_C[i:i + 2], 16)) * a)
                            for i in (1, 3, 5))
                d.line([(xx, y), (xx, y + max(1, S))], fill=col)
        else:
            if idx == hover_idx:
                d.rounded_rectangle([int(3 * scale * S), y, (W - 3) * S, y + hh],
                                    radius=int(7 * scale * S), fill=_HOV)
            if dot:
                d.ellipse([dotx * S - 4 * S, cy - 4 * S, dotx * S + 4 * S, cy + 4 * S],
                          fill=_hex(dot))
            d.text((tx * S, cy), text, font=(f_min if small else f_main),
                   fill="#2b313a" if small else "#14161c", anchor="lm")
        y += hh
    # 关键: 用 premultiplied-alpha 模式(RGBa)缩放, 防止透明边渗色出"黄线/彩边"
    img = img.convert("RGBa").resize((W, H), _I.Resampling.LANCZOS).convert("RGBA")
    # 转 premultiplied BGRA
    px = img.load()
    out = bytearray(W * H * 4)
    i = 0
    for yy in range(H):
        for xx in range(W):
            a_, r_, g_, b_ = px[xx, yy]
            if a_ == 0:
                i += 4
                continue
            f = a_ / 255.0
            out[i] = int(b_ * f)
            out[i + 1] = int(g_ * f)
            out[i + 2] = int(r_ * f)
            out[i + 3] = a_
            i += 4
    return bytes(out)


_WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, ctypes.c_void_p, ctypes.c_uint,
                              ctypes.c_size_t, ctypes.c_longlong)


def _menu_call():
    """在 popup 线程建一个逐像素抗锯齿自绘菜单窗口"""
    try:
        u = ctypes.windll.user32
        g = ctypes.windll.gdi32
    except Exception as e:
        tlog(f"menu无windll: {repr(e)[:60]}")
        with _popup_lock:
            _popup_active[0] = False
        return
    try:
        color, items = _menu_items()
        scale = max(1.0, u.GetDpiForSystem() / 96.0)
        IN = int(6 * scale)
        hh = int(_MENU_H * scale)
        sephh = int(_MENU_SEP * scale)
        W = int(_MENU_W * scale)
        y = IN
        geo = []
        for kind, *_ in items:
            h0 = sephh if kind == "sep" else hh
            geo.append((kind, y, y + h0))
            y += h0
        H = y + IN

        mx = 0
        my = 0

        def _hit(x, y2):
            for i, (kind, y0, y1) in enumerate(geo):
                if kind != "sep" and y0 <= y2 <= y1:
                    return i
            return None

        def _update(hover):
            data = _render_menu(items, W, H, scale, hover)

            class BIH(ctypes.Structure):
                _fields_ = [("biSize", ctypes.c_uint), ("biWidth", ctypes.c_long),
                            ("biHeight", ctypes.c_long), ("biPlanes", ctypes.c_ushort),
                            ("biBitCount", ctypes.c_ushort), ("biCompression", ctypes.c_uint),
                            ("biSizeImage", ctypes.c_uint), ("biXPelsPerMeter", ctypes.c_long),
                            ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", ctypes.c_uint),
                            ("biClrImportant", ctypes.c_uint)]
            class BI(ctypes.Structure):
                _fields_ = [("bmiHeader", BIH)]
            class POINT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
            class SIZE(ctypes.Structure):
                _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]
            class BLEND(ctypes.Structure):
                _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                            ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]
            bmi = BI()
            bmi.bmiHeader.biSize = ctypes.sizeof(BIH)
            bmi.bmiHeader.biWidth = W
            bmi.bmiHeader.biHeight = -H
            bmi.bmiHeader.biPlanes = 1
            bmi.bmiHeader.biBitCount = 32
            hdc_screen = u.GetDC(None)
            hdc_mem = g.CreateCompatibleDC(hdc_screen)
            bits = ctypes.c_void_p()
            hbmp = g.CreateDIBSection(hdc_mem, ctypes.byref(bmi), 0,
                                      ctypes.byref(bits), None, 0)
            ctypes.memmove(bits.value, data, len(data))
            old = g.SelectObject(hdc_mem, hbmp)
            pt = POINT(mx, my)
            sz = SIZE(W, H)
            src = POINT(0, 0)
            blend = BLEND(AC_SRC_OVER, 0, 255, 1)
            u.UpdateLayeredWindow(hwnd, hdc_screen, ctypes.byref(pt), ctypes.byref(sz),
                                  hdc_mem, ctypes.byref(src), 0, ctypes.byref(blend), 2)
            g.SelectObject(hdc_mem, old)
            g.DeleteObject(hbmp)
            g.DeleteDC(hdc_mem)
            u.ReleaseDC(None, hdc_screen)
            return None

        @_WNDPROC
        def _wndproc(hw, msg, wp, lp):
            st = _menu_state.get(hw)
            if st is None:
                return u.DefWindowProcW(hw, msg, wp, lp)
            if msg == WM_MOUSEMOVE:
                x = lp & 0xffff
                yy = (lp >> 16) & 0xffff
                idx = st["hit"](x, yy)
                if idx != st["hover"]:
                    st["hover"] = idx
                    try:
                        st["update"](idx)
                    except Exception:
                        pass
                return 0
            if msg == WM_LBUTTONUP:
                x = lp & 0xffff
                yy = (lp >> 16) & 0xffff
                idx = st["hit"](x, yy)
                u.DestroyWindow(st["hwnd"])
                if idx is not None and items[idx][4]:
                    try:
                        items[idx][4]()
                    except Exception as ex:
                        tlog(f"menu act err: {repr(ex)[:80]}")
                return 0
            if msg == WM_NCHITTEST:
                return HTCLIENT
            if msg == WM_DESTROY:
                _menu_state.pop(hw, None)
                u.PostQuitMessage(0)
                return 0
            return u.DefWindowProcW(hw, msg, wp, lp)

        class WNDCLASSW(ctypes.Structure):
            _fields_ = [("style", ctypes.c_uint), ("lpfnWndProc", _WNDPROC),
                        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                        ("hInstance", ctypes.c_void_p), ("hIcon", ctypes.c_void_p),
                        ("hCursor", ctypes.c_void_p), ("hbrBackground", ctypes.c_void_p),
                        ("lpszMenuName", ctypes.c_wchar_p), ("lpszClassName", ctypes.c_wchar_p)]
        cls = "量化看守Menu" + str(int(time.time() * 1000))
        wc = WNDCLASSW()
        wc.lpfnWndProc = _wndproc
        k32 = ctypes.windll.kernel32
        k32.GetModuleHandleW.restype = ctypes.c_void_p   # 64位HMODULE, 否则按32位截断/溢出
        hinst = k32.GetModuleHandleW(None)
        wc.hInstance = hinst
        wc.lpszClassName = cls
        u.RegisterClassW(ctypes.byref(wc))

        hwnd = u.CreateWindowExW(0x80000 | 0x00000008 | 0x00000080,  # LAYERED|TOPMOST|TOOLWINDOW
                                 cls, "", 0x80000000, 0, 0, W, H,
                                 None, None, ctypes.c_void_p(hinst), None)
        if not hwnd:
            tlog("menu CreateWindow 失败")
            return

        # 位置: 以鼠标右键点击点为锚(经典 TrackPopupMenu 行为), 贴近鼠标, 出屏则收回来
        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
        pt = POINT()
        u.GetCursorPos(ctypes.byref(pt))
        sw = u.GetSystemMetrics(0)
        sh = u.GetSystemMetrics(1)
        mx = pt.x
        my = pt.y + 4
        if mx + W > sw - 4:
            mx = sw - W - 4
        if my + H > sh - 4:
            my = pt.y - H - 4
        if mx < 0:
            mx = 0
        if my < 0:
            my = 0

        _menu_state[hwnd] = {"hwnd": hwnd, "items": items, "geo": geo,
                             "hit": _hit, "update": _update, "hover": None}
        _update(None)
        u.ShowWindow(hwnd, 5)         # SW_SHOW
        u.SetTimer(hwnd, 1, 60, None)

        class MSG(ctypes.Structure):
            _fields_ = [("hwnd", ctypes.c_void_p), ("message", ctypes.c_uint),
                        ("wParam", ctypes.c_size_t), ("lParam", ctypes.c_longlong),
                        ("time", ctypes.c_uint), ("pt_x", ctypes.c_long),
                        ("pt_y", ctypes.c_long)]
        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
        msg = MSG()
        while u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_TIMER:
                if u.GetAsyncKeyState(1) & 1:
                    cur = POINT()
                    u.GetCursorPos(ctypes.byref(cur))
                    if not (mx <= cur.x <= mx + W and my <= cur.y <= my + H):
                        u.DestroyWindow(hwnd)
            u.TranslateMessage(ctypes.byref(msg))
            u.DispatchMessageW(ctypes.byref(msg))
        u.KillTimer(hwnd, 1)
        u.UnregisterClassW(cls, ctypes.c_void_p(hinst))
    except Exception as e:
        tlog(f"menu崩: {repr(e)}")
        import traceback
        tlog(traceback.format_exc(limit=5))
    with _popup_lock:
        _popup_active[0] = False


def _popup_run():
    global _CURRENT_ICON
    try:
        import tkinter as tk
        from PIL import ImageTk
    except Exception as e:
        tlog(f"popup无tk: {repr(e)[:60]}")
        with _popup_lock:
            _popup_active[0] = False
        return
    try:
        color, head, line = snapshot()
        rows = [
            dict(t=head, dot=color, small=False),
            dict(t=line, dot=None, small=True),
            dict(sep=True),
            dict(t="打开状态面板", act=lambda: show_panel()),
            dict(t="启动值守引擎", act=lambda: _act(_start_or_tip)),
            dict(t="重启值守引擎", act=lambda: _act(restart_engine)),
            dict(sep=True),
            dict(t="打开值守日志", act=lambda: _open(ROOT / "outputs" / "duty_log.txt")),
            dict(t="打开 outputs 目录", act=lambda: _open(ROOT / "outputs")),
            dict(sep=True),
            dict(t="退出量化看守", act=lambda: _quit(_CURRENT_ICON[0])),
        ]
        root = tk.Tk()
        root.withdraw()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        hwnd = root.winfo_id()

        # 行几何(内容从面板内边距起)
        IN = 6
        geo = []
        y = IN
        for r in rows:
            hh = _MENU_SEP if r.get("sep") else _MENU_H
            r["y0"], r["y1"] = y, y + hh
            geo.append((r, y, y + hh))
            y += hh
        y += IN
        W = _MENU_W
        H = y
        hwnd = int(hwnd)

        cv = tk.Canvas(root, width=W, height=H, bg=_BG,
                       highlightthickness=0, bd=0)
        cv.pack()

        sep_img = _sep_image(W - 2 * IN, master=root)
        hover_row = [None]

        def draw(h):
            cv.delete("all")
            for r, y0, y1 in geo:
                if r.get("sep"):
                    sx, sy = IN, (y0 + y1) // 2
                    cv.create_image(sx, sy, image=sep_img, anchor="nw")
                    continue
                is_hover = (h == id(r))
                if is_hover:
                    cv.create_rectangle(3, y0 + 1, W - 3, y1 - 1, fill=_HOV, outline="")
                dotx = IN + 10
                tx = IN + 24
                if r.get("dot"):
                    cy = y0 + (y1 - y0) / 2
                    cv.create_oval(dotx - 4, cy - 4, dotx + 4, cy + 4,
                                   fill=_hex(r["dot"]), outline="")
                col = _FG2 if r.get("small") else _FG
                font = _FONT2 if r.get("small") else _FONT
                cv.create_text(tx, y0 + (y1 - y0) / 2, text=r["t"], anchor="w",
                               fill=col, font=font)

        def hit(e):
            for r, y0, y1 in geo:
                if y0 <= e.y <= y1 and not r.get("sep"):
                    return r
            return None

        def on_motion(e):
            r = hit(e)
            nid = id(r) if r else None
            if nid != hover_row[0]:
                hover_row[0] = r if r else None
                draw(id(r) if r else None)

        def _close():
            try:
                root.destroy()
            except Exception:
                pass

        def _any_click(e):
            # grab_set_global 时窗口内外的点击都路由到本窗口: 窗内->执行行, 窗外->关闭
            inside = (0 <= e.x <= W and 0 <= e.y <= H)
            r = hit(e) if inside else None
            _close()
            if r and r.get("act"):
                try:
                    r["act"]()
                except Exception as ex:
                    tlog(f"popup act err: {repr(ex)[:80]}")

        cv.bind("<Motion>", on_motion)
        root.bind("<Button-1>", _any_click)
        root.bind("<Escape>", lambda e: _close())
        # 位置: 紧贴托盘图标上方(标准做法 Shell_NotifyIconGetRect), 取不到则右下角
        pos = _tray_rect()
        if pos:
            l, t, r, b = pos
            mx = r - W            # 菜单右缘对齐图标右缘
            my = t - H            # 菜单贴图标正上方
            if mx < 0:
                mx = 0
            if my < 0:
                my = sh - H - 48
        else:
            sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
            mx = sw - W - 10
            my = sh - H - 48
        root.geometry(f"+{mx}+{my}")
        draw(None)
        root.deiconify()
        _round_rgn(hwnd, W, H, _R)          # 窗口区域裁成圆角(不依赖透明键, 可靠)
        try:
            root.grab_set_global()          # 抓全局输入 -> 点外部即可关闭
        except Exception:
            pass
        root.focus_force()
        root.mainloop()
    except Exception as e:
        import traceback
        tlog(f"popup崩: {e}\n{traceback.format_exc(limit=5)}")
    finally:
        with _popup_lock:
            _popup_active[0] = False


def _start_or_tip():
    if engine_alive():
        return "引擎已在岗(心跳正常), 无需启动"
    return start_engine()


def _act(fn):
    msg = fn()
    try:
        pystray.notify(msg, "量化看守")
    except Exception:
        pass


def _open(path):
    try:
        os.startfile(str(path))
    except Exception as e:
        tlog(f"open err {path}: {repr(e)[:60]}")


def _quit(icon):
    _stop.set()
    icon.stop()


# ---------------- 状态面板(托盘左键单击弹出; 菜单是单色文本带不了彩灯, 灯画在这里) ----------------
_panel_lock = threading.Lock()
_panel_root = None


def _hex(c):
    return "#%02x%02x%02x" % c[:3]


def _panel_run():
    """状态面板(第一版白色经典): 白底+绿色顶栏+大绿点+状态+按钮, 每秒刷新"""
    global _panel_root
    try:
        import tkinter as tk
    except Exception as e:
        tlog(f"面板不可用(无tkinter): {repr(e)[:60]}")
        return
    root = tk.Tk()
    root.title("量化看守")
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"420x240+{sw - 460}+{sh - 330}")
    bg = "#f2f2f2"
    root.configure(bg=bg)

    # 顶栏(绿色, 可拖动, ✕关闭)
    bar = tk.Frame(root, bg="#1f6f43", height=34)
    bar.pack(fill="x")
    bar.pack_propagate(False)
    tk.Label(bar, text="量化看守", bg="#1f6f43", fg="white",
             font=("Microsoft YaHei UI", 11, "bold")).pack(side="left", padx=10)
    close_lab = tk.Label(bar, text="✕", bg="#1f6f43", fg="white",
                         font=("Microsoft YaHei UI", 12), cursor="hand2")
    close_lab.pack(side="right", padx=10, pady=2)
    close_lab.bind("<Button-1>", lambda e: root.destroy())

    def sm(e):
        root._dx, root._dy = e.x_root - root.winfo_x(), e.y_root - root.winfo_y()
    def mv(e):
        root.geometry(f"+{e.x_root - root._dx}+{e.y_root - root._dy}")
    bar.bind("<Button-1>", sm)
    bar.bind("<B1-Motion>", mv)

    body = tk.Frame(root, bg=bg)
    body.pack(fill="both", expand=True, padx=14, pady=10)
    lamp = tk.Canvas(body, width=110, height=110, bg=bg, highlightthickness=0)
    lamp.pack(side="left")
    circ = lamp.create_oval(5, 5, 105, 105, fill=_hex(GREEN), outline="")
    info = tk.Frame(body, bg=bg)
    info.pack(side="left", fill="both", expand=True, padx=(12, 0))
    st_lab = tk.Label(info, text="运行中", bg=bg, fg="#1a1a1a",
                      font=("Microsoft YaHei UI", 16, "bold"), anchor="w")
    st_lab.pack(fill="x")
    dt_lab = tk.Label(info, text="时段: --", bg=bg, fg="#444",
                      font=("Microsoft YaHei UI", 10), anchor="w")
    dt_lab.pack(fill="x", pady=(2, 0))
    hb_lab = tk.Label(info, text="心跳: --", bg=bg, fg="#444",
                      font=("Microsoft YaHei UI", 10), anchor="w")
    hb_lab.pack(fill="x")

    btns = tk.Frame(root, bg=bg)
    btns.pack(fill="x", padx=14, pady=(0, 10))

    def _btn(txt, fn):
        tk.Button(btns, text=txt, command=fn, bg="#ffffff", fg="#1a1a1a",
                  relief="flat", bd=1, highlightthickness=1,
                  font=("Microsoft YaHei UI", 9)).pack(side="left", expand=True, fill="x", padx=3)
    _btn("重启引擎", lambda: _act(restart_engine))
    _btn("值守日志", lambda: _open(ROOT / "outputs" / "duty_log.txt"))
    _btn("outputs", lambda: _open(ROOT / "outputs"))
    _btn("隐藏", root.destroy)

    def tick():
        if not root.winfo_exists():
            return
        color, head, line = snapshot()
        try:
            cc = _hex(color)
            lamp.itemconfig(circ, fill=cc)
            st = head.split("· ")[-1] if "· " in head else head
            st_lab.config(text=st, fg=cc)
            dt_lab.config(text=line.split("心跳")[0].strip())
            hb_lab.config(text="心跳" + line.split("心跳")[1] if "心跳" in line else line)
        except Exception:
            pass
        root.after(1000, tick)

    with _panel_lock:
        _panel_root = root
    root.after(300, tick)
    root.deiconify()
    root.mainloop()
    with _panel_lock:
        _panel_root = None

def show_panel():
    """托盘左键双击: 打开白色状态面板(已开则置顶)"""
    with _panel_lock:
        if _panel_root is not None:
            try:
                _panel_root.lift()
                _panel_root.attributes("-topmost", True)
                return
            except Exception:
                pass
    threading.Thread(target=_panel_run, daemon=True).start()


def updater(icon):
    """每2秒: 强制重绘图标(顶掉旧渲染/缓存, 透明度100%), 刷新菜单文本; 引擎死透自动拉起"""
    last_sig = None
    last_pull = 0.0
    while not _stop.is_set():
        try:
            color, head, line = snapshot()
            # 每2秒无条件重设图标 —— 保证状态灯永远在最上层、不被旧图标/缓存盖住
            icon.icon = make_icon(color)
            if (color, head, line) != last_sig:
                icon.title = f"{head} | {line}"
                last_sig = (color, head, line)
            # 看护: 心跳停>75s 视为引擎死(进程不在才拉, 防误拉还在跑的实例)
            age = heart_age()
            if age > 75 and not engine_pids() and now_s() - last_pull > 90:
                tlog(f"看护: 心跳停{age:.0f}s且无引擎进程 -> 自动拉起")
                start_engine()
                last_pull = now_s()
        except Exception as e:
            tlog(f"updater err: {repr(e)[:80]}")
        _stop.wait(2)


# ---------------- 系统原生右键菜单(pystray; 圆角/hover/点外关闭/黑字/位置都由系统负责) ----------------
def sys_menu():
    """系统原生右键菜单: 简短三项(重启=没跑启动/在跑重置)"""
    return pystray.Menu(
        pystray.MenuItem("重启", lambda ic, it: _act(restart_engine)),
        pystray.MenuItem("日志", lambda ic, it: _open(ROOT / "outputs" / "duty_log.txt")),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("退出", lambda ic, it: _quit(ic)),
    )


def _patch_dblclick():
    """托盘左键双击 -> 打开状态面板(单击保持无动作)"""
    try:
        from pystray import _win32 as _pw
        _orig = _pw.Icon._on_notify

        def wrap(self, wp, lp):
            if lp == 0x0203:  # WM_LBUTTONDBLCLK
                try:
                    show_panel()
                except Exception as e:
                    tlog(f"dblclick err: {repr(e)[:60]}")
                return None
            return _orig(self, wp, lp)

        _pw.Icon._on_notify = wrap
        return True
    except Exception as e:
        tlog(f"patch_dblclick err: {repr(e)[:80]}")
        return False

def main():
    _patch_dblclick()
    tlog(f"tray_guard 启动 exe={EXE}")
    # 图标预览导出(核对渲染: 灯=满不透明色块, 无被盖/半透明)
    try:
        for nm, c in (("green", GREEN), ("yellow", YELLOW), ("red", RED)):
            make_icon(c).save(ROOT / "outputs" / f"tray_lamp_{nm}.png")
    except Exception as e:
        tlog(f"preview save err: {repr(e)[:60]}")
    icon = pystray.Icon("量化看守", make_icon(GREEN), "量化看守")
    _CURRENT_ICON[0] = icon
    icon.menu = sys_menu()      # 系统原生右键菜单(不再自绘)
    # 不再挂系统菜单(右键已 patch 到自绘圆角菜单)
    # 冷启动看护: 引擎没在岗就拉起
    if not engine_alive():
        tlog("引擎不在岗, 冷启动拉起")
        start_engine()
    th = threading.Thread(target=updater, args=(icon,), daemon=True)
    th.start()
    try:
        icon.run()
    except Exception as e:
        import traceback
        tlog(f"tray主循环异常退出: {e}\n{traceback.format_exc(limit=6)}")
    finally:
        _stop.set()
        tlog("tray_guard 退出")


if __name__ == "__main__":
    main()
