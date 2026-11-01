# gen_week_board.py —— 生成「周视图看板」设备脚本 epd_week_board.py + 本地预览 PNG
# 版式: 头部(城市/日期/星期 + 天气/当前温度) | 红色分隔线 | 七列日历(今日高亮块)
#       | 七天温度折线(红色最高温/黑色最低温 + 刻度) | 底部四项指标
# 用法: python gen_week_board.py
import os, sys
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = "/System/Library/Fonts/Hiragino Sans GB.ttc"
FONT_INDEX = 1  # ttc 内字重选择: 1=细体(W2)。小字号点阵化只有细体不糊字(idx0=W3粗体会粘连)
OUT_PY = os.path.join(HERE, "epd_week_board.py")
OUT_PNG = os.path.join(HERE, "week_board_preview.png")

W, H = 400, 300
SS = 4          # 超采样倍数
THRESH = 110

# ---------- 字符池 ----------
POOL_S = ("0123456789:°%·/"
          "青岛年月日周一二三四五六日今明天"
          "晴多云阴雾毛毛雨小中大阵暴雪雷冻米"
          "日出落湿度更新降水体感风力")
POOL_M = ("0123456789-°:%"
          "青岛年月日周一二三四五六日今明天"
          "农历闰正腊冬初廿七八九十"
          "晴多云阴雾毛毛雨小中大阵暴雪雷冻米降水体感风力")
POOL_D = "0123456789"


def render_glyph(ch, size):
    c1 = size * 3
    pad = size
    tmp = Image.new("L", (c1 * SS, c1 * SS), 0)
    ImageDraw.Draw(tmp).text((pad * SS, pad * SS), ch,
                             font=ImageFont.truetype(FONT_PATH, size * SS, index=FONT_INDEX), fill=255)
    bbox = tmp.getbbox()
    if bbox is None:
        sw = max(2, size // 3)
        return bytes((sw, 1, 0)) + b"\x00" * ((sw + 7) >> 3)
    x0, y0, x1, y1 = bbox
    # 字间距: 位图左右各垫 padx 列空白, 否则按墨迹宽度步进会导致相邻字粘连
    padx = max(1, round(size / 16.0))
    w0 = max(1, round((x1 - x0) / SS))
    h = max(1, round((y1 - y0) / SS))
    g = tmp.crop(bbox)
    g = g.resize((w0, h), Image.LANCZOS)
    w = w0 + padx * 2
    gpad = Image.new("L", (w, h), 0)
    gpad.paste(g, (padx, 0))
    y_off = round(y0 / SS) - pad
    bw = (w + 7) >> 3
    px = gpad.load()
    rows = bytearray(bw * h)
    for yy in range(h):
        for xb in range(bw):
            v = 0
            for k in range(8):
                xx = xb * 8 + k
                if xx < w and px[xx, yy] > THRESH:
                    v |= 0x80 >> k
            rows[yy * bw + xb] = v
    return bytes((w, h, y_off & 0xFF)) + bytes(rows)


# HZK16: 16x16 汉字点阵(GB2312 区位码索引, 每字模32字节)
# 小字号汉字用矢量缩放会丢点/粘连(出落度新等), 点阵字库是专为 16px 设计的, 完整清晰
HZK_PATH = os.path.join(HERE, "HZK16")
_HZK = open(HZK_PATH, "rb").read() if os.path.exists(HZK_PATH) else b""


def hzk_glyph(ch):
    try:
        gb = ch.encode("gb2312")
    except UnicodeEncodeError:
        return None
    off = ((gb[0] - 0xA0 - 1) * 94 + (gb[1] - 0xA0 - 1)) * 32
    if off < 0 or off + 32 > len(_HZK):
        return None
    data = _HZK[off:off + 32]
    if not any(data):
        return None
    # 16行x2字节, MSB=左 → (w,h,y_off)+行数据
    return bytes((16, 16, 0)) + data


def build_font(chars, size):
    f = {}
    for ch in "".join(dict.fromkeys(chars)):
        g = hzk_glyph(ch) if ord(ch) > 127 else None
        f[ch] = g if g is not None else render_glyph(ch, size)
    ref = min(g[2] for g in f.values())
    out = {}
    for ch in f:
        g = f[ch]
        out[ch] = bytes((g[0], g[1], (g[2] - ref) & 0xFF)) + g[3:]
    return out


def emit_font(name, font):
    lines = ["%s = {" % name]
    for ch, g in font.items():
        body = "".join("\\x%02x" % b for b in g)
        key = ch.replace("\\", "\\\\").replace("'", "\\'")
        lines.append("'%s': b'%s'," % (key, body))
    lines.append("}")
    return "\n".join(lines)


# ---------- 预览画布 ----------
class PILCanvas:
    def __init__(self):
        self.img = Image.new("RGB", (W, H), (255, 255, 255))
        self.d = ImageDraw.Draw(self.img)

    def _px(self, x, y, color):
        if 0 <= x < W and 0 <= y < H:
            c = {"k": (0, 0, 0), "r": (204, 32, 32), "w": (255, 255, 255)}[color]
            self.d.point((x, y), fill=c)

    def text(self, font, s, x, y, color="k"):
        cx = x
        for ch in s:
            g = font.get(ch)
            if not g:
                cx += 8
                continue
            w, h, dy, data = g[0], g[1], g[2], g[3:]
            bw = (w + 7) >> 3
            for ry in range(h):
                for xb in range(w):
                    if data[ry * bw + (xb >> 3)] & (0x80 >> (xb & 7)):
                        self._px(cx + xb, y + dy + ry, color)
            cx += w

    def rect(self, x0, y0, x1, y1, color="k"):
        for y in range(int(y0), int(y1) + 1):
            for x in range(int(x0), int(x1) + 1):
                self._px(x, y, color)

    def hline(self, x0, x1, y, color="k", w=2, dash=0):
        for t in range(w):
            for x in range(int(x0), int(x1) + 1):
                if not dash or (x // dash) % 2 == 0:
                    self._px(x, y + t, color)

    def vline(self, x, y0, y1, color="k", w=1, dash=0):
        for t in range(w):
            for y in range(int(y0), int(y1) + 1):
                if not dash or (y // dash) % 2 == 0:
                    self._px(x + t, y, color)

    def polyline(self, pts, color="k", w=1):
        for i in range(len(pts) - 1):
            (x0, y0), (x1, y1) = pts[i], pts[i + 1]
            dx, dy = abs(x1 - x0), -abs(y1 - y0)
            sx = 1 if x0 < x1 else -1
            sy = 1 if y0 < y1 else -1
            err = dx + dy
            while True:
                self.dot(x0, y0, w, color)
                if x0 == x1 and y0 == y1:
                    break
                e2 = 2 * err
                if e2 >= dy:
                    err += dy
                    x0 += sx
                if e2 <= dx:
                    err += dx
                    y0 += sy

    def dot(self, cx, cy, r, color="k"):
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if dx * dx + dy * dy <= r * r:
                    self._px(cx + dx, cy + dy, color)


def main():
    # S=15px: 13px 下"出落度新"等字的点笔画物理上放不下会丢, 15px 起完整
    F = {"s": build_font(POOL_S, 15), "m": build_font(POOL_M, 17), "d": build_font(POOL_D, 30)}

    # ---- 本地预览(假数据, 覆盖双位数温度与跨月) ----
    sys.path.insert(0, HERE)
    import wb_layout

    sample = {
        "city": "青岛", "wk": "周六",
        "date": (2026, 10, 31, 5),
        "cur": (15, "毛毛雨"),
        "labels": ["今天", "明天", "周一", "周二", "周三", "周四", "周五"],
        "days": [(31, 5, 18.3, 11.2, ""), (1, 6, 18.0, 12.8, "晴"),
                 (2, 0, 16.9, 9.1, "多云"), (3, 1, 18.3, 10.7, "阴"),
                 (4, 2, 19.2, 14.7, "小雨"), (5, 3, 19.5, 11.3, "晴"),
                 (6, 4, 13.6, 5.0, "阵雪")],
        "sun": ("06:20", "17:03"), "hum": 54, "upd": "18:45",
        "lunar": "农历九月廿二",
        "extra": ("降水", "100%"),
    }
    cv = PILCanvas()
    wb_layout.render(cv, F, sample)
    cv.img.resize((W * 3, H * 3), Image.NEAREST).save(OUT_PNG)
    print("preview:", OUT_PNG)

    # ---- 生成设备端脚本 ----
    layout_src = open(os.path.join(HERE, "wb_layout.py"), encoding="utf-8").read()
    layout_src = "\n".join(l for l in layout_src.split("\n")
                           if not l.startswith("# wb_layout.py"))
    print("fonts:", {k: len(v) for k, v in F.items()})
    lunar_src = open(os.path.join(HERE, "wb_lunar.py"), encoding="utf-8").read()
    lunar_src = "\n".join(l for l in lunar_src.split("\n") if not l.startswith("# wb_lunar.py"))
    emit = (DEV_TAIL
            .replace("__FONTS__", "S = " + repr_dict(F["s"]) + "\n\nM = " + repr_dict(F["m"]) + "\n\nD = " + repr_dict(F["d"]))
            .replace("__LAYOUT__", layout_src)
            .replace("__LUNAR__", lunar_src))
    with open(OUT_PY, "w", encoding="utf-8") as fp:
        fp.write(emit)
    print("device script:", OUT_PY, os.path.getsize(OUT_PY), "bytes")



def repr_dict(font):
    lines = ["{"]
    for ch, g in font.items():
        body = "".join("\\x%02x" % b for b in g)
        key = ch.replace("\\", "\\\\").replace("'", "\\'")
        lines.append("'%s': b'%s'," % (key, body))
    lines.append("}")
    return "\n".join(lines)



# ============================================================
# 设备端模板
# ============================================================
DEV_TAIL = r"""# epd_week_board.py (auto-generated by gen_week_board.py)
# 4.2寸 400x300 黑白红墨水屏「周视图看板」
# 版式: 头部(城市/日期/星期 + 天气/当前温度) + 七列日历(今日黑块高亮)
#       + 七天温度折线(红=最高温 黑=最低温) + 底部四项指标(日出/日落/湿度/更新)
# 硬件: ESP32-S3 + SSD1683; BUSY=7 RST=8 DC=9 CS=10 MOSI=11 SCK=12
# 数据: NTP对时 + open-meteo 七天预报(HTTP免密钥) + 本地缓存
# 刷新: 每 REFRESH_MIN 分钟一次(默认180); OFFGRID=True 时深睡定时唤醒(电池模式)
import machine, time, network, socket, gc, os, ujson

# ================= 配置 =================
# 凭据与城市等私有配置在 secrets.py(见 secrets.example.py), 不入库
import secrets
SSID, PWD = secrets.SSID, secrets.PWD
CITY = secrets.CITY
LAT, LON = secrets.LAT, secrets.LON
TZ = secrets.TZ
REFRESH_MIN = 180            # 刷新间隔(分钟)
OFFGRID = False              # True=每次刷新后深睡(电池); False=常驻循环(USB)
CACHE = "wcache2.json"

API = ("http://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s"
       "&daily=temperature_2m_max,temperature_2m_min,sunrise,sunset,weather_code,precipitation_probability_max"
       "&current=temperature_2m,relative_humidity_2m,weather_code"
       "&timezone=Asia%%2FShanghai&forecast_days=7") % (LAT, LON)

WMO = {0: "晴", 1: "晴", 2: "多云", 3: "阴", 45: "雾", 48: "雾",
       51: "小雨", 53: "小雨", 55: "小雨", 56: "冻雨", 57: "冻雨",
       61: "小雨", 63: "中雨", 65: "大雨", 66: "冻雨", 67: "冻雨",
       71: "小雪", 73: "中雪", 75: "大雪", 77: "米雪", 80: "阵雨",
       81: "阵雨", 82: "暴雨", 85: "阵雪", 86: "阵雪",
       95: "雷阵雨", 96: "雷阵雨", 99: "雷阵雨"}
WK = ("一", "二", "三", "四", "五", "六", "日")

W, H = 400, 300
RB = W // 8
N = RB * H

__FONTS__

# ================= EPD 驱动 =================
busy = machine.Pin(7, machine.Pin.IN, machine.Pin.PULL_UP)
rst = machine.Pin(8, machine.Pin.OUT, value=1)
dc = machine.Pin(9, machine.Pin.OUT, value=1)
cs = machine.Pin(10, machine.Pin.OUT, value=1)
spi = machine.SoftSPI(baudrate=2000000, polarity=0, phase=0,
                      sck=machine.Pin(12), mosi=machine.Pin(11), miso=machine.Pin(6))


def wait_busy(ms=60000):
    t = time.ticks_ms()
    while busy.value():
        if time.ticks_diff(time.ticks_ms(), t) > ms:
            raise RuntimeError("BUSY timeout")
        time.sleep_ms(5)


def cmd(c, data=None):
    dc.value(0)
    cs.value(0)
    spi.write(bytes((c,)))
    if data is not None:
        dc.value(1)
        spi.write(data)
    cs.value(1)
    dc.value(1)


def reset():
    rst.value(0)
    time.sleep_ms(10)
    rst.value(1)
    time.sleep_ms(10)
    wait_busy()


def init():
    reset()
    cmd(0x01, b"\x8f\x01\x00")
    cmd(0x21, b"\x00\x00")
    cmd(0x3C, b"\x05")
    cmd(0x11, b"\x03")
    cmd(0x18, b"\x80")
    cmd(0x22, b"\xf7")
    time.sleep_ms(50)


def window():
    cmd(0x44, b"\x00\x31")
    cmd(0x45, b"\x00\x00\x2b\x01")
    cmd(0x4E, b"\x00")
    cmd(0x4F, b"\x00\x00")


def refresh():
    cmd(0x20)
    wait_busy()
    cmd(0x02)
    wait_busy()
    cmd(0x07, b"\x03")


def conv_bw(fb):
    for i in range(N):
        fb[i] ^= 0xFF
    return fb


def conv_red(fr):
    return fr


# ================= 画布(位1=黑墨/红墨; 'w'=在黑底上挖白) =================
class Canvas:
    def __init__(self):
        self.fb = bytearray(N)
        self.fr = bytearray(N)

    def _set(self, buf, x, y):
        if 0 <= x < W and 0 <= y < H:
            buf[y * RB + (x >> 3)] |= 0x80 >> (x & 7)

    def _clr(self, x, y):
        if 0 <= x < W and 0 <= y < H:
            i = y * RB + (x >> 3)
            m = (0x80 >> (x & 7)) ^ 0xFF
            self.fb[i] &= m
            self.fr[i] &= m

    def text(self, font, s, x, y, color="k"):
        cx = x
        for ch in s:
            g = font.get(ch)
            if g is None:
                cx += 8
                continue
            w, h, dy, data = g[0], g[1], g[2], g[3:]
            bw = (w + 7) >> 3
            if color == "w":
                for ry in range(h):
                    row = y + dy + ry
                    if row < 0 or row >= H:
                        continue
                    for xb in range(w):
                        if data[ry * bw + (xb >> 3)] & (0x80 >> (xb & 7)):
                            self._clr(cx + xb, row)
            else:
                buf = self.fr if color == "r" else self.fb
                for ry in range(h):
                    row = y + dy + ry
                    if row < 0 or row >= H:
                        continue
                    base = row * RB
                    for xb2 in range(bw):
                        v = data[ry * bw + xb2]
                        if not v:
                            continue
                        px = cx + xb2 * 8
                        bi = px >> 3
                        sh = px & 7
                        if bi < RB:
                            buf[base + bi] |= v >> sh
                        if sh and bi + 1 < RB:
                            buf[base + bi + 1] |= (v << (8 - sh)) & 0xFF
            cx += w

    def rect(self, x0, y0, x1, y1, color="k"):
        for y in range(int(y0), int(y1) + 1):
            for x in range(int(x0), int(x1) + 1):
                if color == "w":
                    self._clr(x, y)
                else:
                    self._set(self.fr if color == "r" else self.fb, x, y)

    def hline(self, x0, x1, y, color="k", w=2, dash=0):
        for t in range(w):
            for x in range(int(x0), int(x1) + 1):
                if not dash or (x // dash) % 2 == 0:
                    self._set(self.fr if color == "r" else self.fb, x, y + t)

    def vline(self, x, y0, y1, color="k", w=1, dash=0):
        for t in range(w):
            for y in range(int(y0), int(y1) + 1):
                if not dash or (y // dash) % 2 == 0:
                    self._set(self.fr if color == "r" else self.fb, x + t, y)

    def dot(self, cx, cy, r, color="k"):
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if dx * dx + dy * dy <= r * r:
                    self._set(self.fr if color == "r" else self.fb, cx + dx, cy + dy)

    def polyline(self, pts, color="k", w=1):
        for i in range(len(pts) - 1):
            x0, y0 = pts[i][0], pts[i][1]
            x1, y1 = pts[i + 1][0], pts[i + 1][1]
            dx = abs(x1 - x0)
            dy = -abs(y1 - y0)
            sx = 1 if x0 < x1 else -1
            sy = 1 if y0 < y1 else -1
            err = dx + dy
            while True:
                self.dot(x0, y0, w, color)
                if x0 == x1 and y0 == y1:
                    break
                e2 = 2 * err
                if e2 >= dy:
                    err += dy
                    x0 += sx
                if e2 <= dx:
                    err += dx
                    y0 += sy


F = {"s": S, "m": M, "d": D}

__LAYOUT__

# ================= 农历 =================
__LUNAR__

# ================= 数据 =================
def http_get(url, timeout=15):
    try:
        parts = url.split("/", 3)
        host = parts[2]
        path = "/" + parts[3] if len(parts) > 3 else "/"
        ai = socket.getaddrinfo(host, 80)[0][-1]
        s = socket.socket()
        s.settimeout(timeout)
        s.connect(ai)
        s.send(("GET %s HTTP/1.0\r\nHost: %s\r\nUser-Agent: esp32-epd\r\n"
                "Connection: close\r\n\r\n" % (path, host)).encode())
        buf = bytearray()
        while True:
            d = s.recv(1024)
            if not d:
                break
            buf += d
            if len(buf) > 65536:
                break
        s.close()
        i = bytes(buf).find(b"\r\n\r\n")
        if i < 0:
            return None
        return bytes(buf[i + 4:]).decode("utf-8", "ignore")
    except Exception as e:
        print("[http]", e)
        return None


def hhmm(s):
    i = s.find("T")
    return s[i + 1:i + 6] if i >= 0 else s


def fetch():
    body = http_get(API)
    if not body:
        return None
    try:
        j = ujson.loads(body)
        dly = j["daily"]
        cur = j["current"]
        days = []
        for i in range(7):
            days.append((int(dly["time"][i][8:10]), 0,
                         float(dly["temperature_2m_max"][i]),
                         float(dly["temperature_2m_min"][i]),
                         WMO.get(int(dly["weather_code"][i]), "")))
        return {"days": days,
                "cur": (int(float(cur["temperature_2m"]) + 0.5),
                        WMO.get(int(cur["weather_code"]), "阴")),
                "sun": (hhmm(dly["sunrise"][0]), hhmm(dly["sunset"][0])),
                "hum": int(float(cur["relative_humidity_2m"]) + 0.5),
                "pop": int(dly["precipitation_probability_max"][0])}
    except Exception as e:
        print("[parse]", e)
        return None


def save_cache(f):
    try:
        with open(CACHE, "w") as fp:
            fp.write(ujson.dumps(f))
    except Exception as e:
        print("[cache]", e)


def load_cache():
    try:
        with open(CACHE) as fp:
            return ujson.loads(fp.read())
    except Exception:
        return None


def fallback():
    lt = time.localtime(time.time() + TZ)
    mo, dd = lt[1], lt[2]
    days = []
    for i in range(7):
        d2 = dd + i
        m2 = mo
        while d2 > 30:
            d2 -= 30
            m2 += 1
        days.append((d2, 0, 18, 10, ""))
    return {"cur": (15, "阴"), "sun": ("06:20", "17:03"), "hum": 50,
            "pop": 30, "days": days}


def build_data(f):
    lt = time.localtime(time.time() + TZ)
    y, mo, dd, wd = lt[0], lt[1], lt[2], lt[6]
    labels = ["今天", "明天"] + ["周" + WK[(wd + i) % 7] for i in range(2, 7)]
    return {"city": CITY, "wk": "周" + WK[wd], "date": (y, mo, dd, wd),
            "cur": f["cur"], "labels": labels,
            # 旧缓存(4元组)兼容: 缺天气词时补空串, 该列不画天气
            "days": [it if len(it) > 4 else (it[0], it[1], it[2], it[3], "")
                     for it in f["days"]],
            "sun": f["sun"], "hum": f["hum"], "lunar": lunar_str(y, mo, dd),
            # 第五项: 今日降水概率(旧缓存无 pop 字段时自动退回四列)
            "extra": ("降水", "%d%%" % f["pop"]) if "pop" in f else None,
            "upd": "%02d:%02d" % (lt[3], lt[4])}


def draw(d):
    gc.collect()
    cv = Canvas()
    render(cv, F, d)
    init()
    window()
    cmd(0x24, conv_bw(cv.fb))
    window()
    cmd(0x26, conv_red(cv.fr))
    refresh()
    gc.collect()


def wifi_up():
    w = network.WLAN(network.STA_IF)
    w.active(True)
    if w.isconnected():
        return True
    try:
        w.disconnect()
    except Exception:
        pass
    time.sleep(0.5)
    w.connect(SSID, PWD)
    t = time.ticks_ms()
    while not w.isconnected():
        if time.ticks_diff(time.ticks_ms(), t) > 20000:
            return False
        time.sleep_ms(300)
    return True


def ntp_sync():
    import ntptime
    for host in ("cn.pool.ntp.org", "ntp.aliyun.com", "pool.ntp.org"):
        try:
            ntptime.host = host
            ntptime.settime()
            print("[ntp] ok via", host)
            return True
        except Exception as e:
            print("[ntp] fail", host, e)
    return False


def main():
    print("[boot] week board start")
    gc.collect()
    have_net = wifi_up()
    print("[wifi]", "ok" if have_net else "FAILED")
    if have_net:
        ntp_sync()
    f = fetch() if have_net else None
    if f:
        print("[wx] ok")
        save_cache(f)
    else:
        f = load_cache()
        print("[wx]", "cache" if f else "fallback")
        if not f:
            f = fallback()
    draw(build_data(f))
    if OFFGRID:
        machine.deepsleep(REFRESH_MIN * 60 * 1000)
    nxt = time.time() + REFRESH_MIN * 60
    last_day = time.localtime(time.time() + TZ)[2]
    while True:
        time.sleep(30)
        lt = time.localtime(time.time() + TZ)
        if time.time() < nxt and lt[2] == last_day:
            continue
        last_day = lt[2]
        if wifi_up():
            f2 = fetch()
            if f2:
                save_cache(f2)
                f = f2
        draw(build_data(f))
        nxt = time.time() + REFRESH_MIN * 60


main()
"""



if __name__ == "__main__":
    main()
