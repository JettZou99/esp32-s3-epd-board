# gen_week_class.py —— 生成「课表」设备脚本 week_class_list.py + 本地预览 PNG
# 版式(方案A·已确认): 周看板同款头部(城市/日期/星期 + 农历 + 天气/红温度 + 红色AQI数值)
#       + 红色分隔线 + 课表全框线表格: 节次列红数字, 今日列黑底白字, 午休行节次="-"
# 课表内容外置: class_data.json —— 生成器读取该文件动态构建字库, 并把 JSON 快照注入设备脚本兜底
# 用法: python gen_week_class.py   (改完 class_data.json 后必须重新运行, 否则新汉字缺字)
import os, sys, json
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
def _pick_font():
    for p in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf",
              "/System/Library/Fonts/Hiragino Sans GB.ttc"):
        if os.path.exists(p):
            return p
    raise SystemExit("no CJK font found")


FONT_PATH = _pick_font()
FONT_INDEX = 0
OUT_PY = os.path.join(HERE, "week_class_list.py")
OUT_PNG = os.path.join(HERE, "week_class_preview.png")
CLASS_JSON = os.path.join(HERE, "class_data.json")

W, H = 400, 300
SS = 4
THRESH = 110

# ---------- 字符池 ----------
# S 池 = 固定基础字符 + class_data.json 里出现的全部字符(数据改动后自动补齐字库)
POOL_S_BASE = ("0123456789-°%·/"
               "AQI"
               "周节一二三四五六日"
               "晴多云阴雾毛雨小中大阵暴雪雷冻米出落")
POOL_M = ("0123456789-°:%"
          "青岛年月日周一二三四五六日今明天"
          "农历闰正腊冬初廿七八九十"
          "晴多云阴雾毛毛雨小中大阵暴雪雷冻米降水体感风力")


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
    return bytes((16, 16, 0)) + data


def build_font(chars, size):
    """汉字=HZK16 点阵; ASCII=PIL 渲染。
    ASCII 必须按【墨迹中心】对齐到 HZK16 字模中心, 否则数字/符号明显下沉
    (HZK16 墨迹占满 16px; msyh 的 x-height 数字只有 13px 且框顶偏下)。"""
    f = {}
    hzk = set()
    for ch in "".join(dict.fromkeys(chars)):
        g = hzk_glyph(ch) if ord(ch) > 127 else None
        if g is not None:
            f[ch] = g
            hzk.add(ch)
        else:
            f[ch] = render_glyph(ch, size)
    HAN_CY = 7.5                      # HZK16 字模(16px高)的墨迹中心, 相对绘制 y
    out = {}
    for ch, g in f.items():
        if ch in hzk:
            out[ch] = g              # dy=0, 汉字保持原点阵框
            continue
        w, h, data = g[0], g[1], g[3:]
        bw = (w + 7) >> 3
        rows = [yy for yy in range(h) if any(data[yy * bw + xb] for xb in range(bw))]
        if not rows:
            out[ch] = g              # 空白字符
            continue
        c = (min(rows) + max(rows)) / 2
        dy = int(round(HAN_CY - c))
        if dy < 0:                   # dy 为 1 字节无符号, 不允许负偏移
            dy = 0
        out[ch] = bytes((w, h, dy & 0xFF)) + data
    return out


def repr_dict(font):
    lines = ["{"]
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


def main():
    sys.path.insert(0, HERE)
    import wb_class_layout as L
    import wb_lunar

    # ---- 读取外置课表数据(字库与兜底快照均来自同一份 JSON) ----
    if not os.path.exists(CLASS_JSON):
        raise SystemExit("缺少课表数据文件: %s" % CLASS_JSON)
    with open(CLASS_JSON, encoding="utf-8-sig") as fp:
        raw = json.load(fp)
    cls = L.normalize_class(raw)
    if cls is None:
        raise SystemExit("class_data.json 数据不合法, 请检查 rows / weekdays / break 字段")
    print("课表数据: %d节 x %d列, 午休行=%s, 用到 %d 个不同字符"
          % (cls["nrow"], cls["ncols"], cls["break"] is not None, len(L.class_chars(cls))))

    pool_s = POOL_S_BASE + "".join(L.class_chars(cls))
    F = {"s": build_font(pool_s, 15), "m": build_font(POOL_M, 17)}

    # ---- 自检: 版式 + 课表所需字符必须全部在字库内 ----
    need = set("AQI-0123456789节") | set(L.class_chars(cls))
    miss = sorted(need - set(F["s"].keys()))
    if miss:
        raise SystemExit("S池缺字: %r" % miss)
    print("字符池自检: PASS (S=%d, M=%d)" % (len(F["s"]), len(F["m"])))

    # ---- 本地预览(今日=周一 实时农历; 不传 class, 顺便验证 JSON 读取路径) ----
    sample = {"city": "青岛", "wk": "周一", "date": (2026, 11, 9, 0),
              "cur": (22, "晴"), "aqi": 52, "lunar": wb_lunar.lunar_str(2026, 11, 9)}
    cv = PILCanvas()
    L.render(cv, F, sample)
    cv.img.resize((W * 3, H * 3), Image.NEAREST).save(OUT_PNG)
    print("preview:", OUT_PNG)

    # ---- 生成设备端脚本 ----
    layout_lines = open(os.path.join(HERE, "wb_class_layout.py"), encoding="utf-8").read().split("\n")
    layout_lines = [l for l in layout_lines if not l.startswith("# wb_class_layout.py")]
    for i, ln in enumerate(layout_lines):
        if ln.startswith("DEFAULT_CLASS = None  # __CLASS_SNAPSHOT__"):
            layout_lines[i] = "DEFAULT_CLASS = " + repr(raw)   # JSON 快照, 文件缺失时兜底
            break
    else:
        raise SystemExit("wb_class_layout.py 缺少 __CLASS_SNAPSHOT__ 标记")
    layout_src = "\n".join(layout_lines)
    lunar_src = open(os.path.join(HERE, "wb_lunar.py"), encoding="utf-8").read()
    lunar_src = "\n".join(l for l in lunar_src.split("\n") if not l.startswith("# wb_lunar.py"))
    emit = (DEV_TAIL
            .replace("__FONTS__", "S = " + repr_dict(F["s"]) + "\n\nM = " + repr_dict(F["m"]))
            .replace("__LAYOUT__", layout_src)
            .replace("__LUNAR__", lunar_src))
    with open(OUT_PY, "w", encoding="utf-8") as fp:
        fp.write(emit)
    print("device script:", OUT_PY, os.path.getsize(OUT_PY), "bytes")


# ============================================================
# 设备端模板
# ============================================================
DEV_TAIL = r"""# week_class_list.py (auto-generated by gen_week_class.py)
# 4.2寸 400x300 黑白红墨水屏「课表」(方案A·经典全框线)
# 版式: 头部(城市/日期/星期 + 农历 + 天气/红温度 + 红AQI数值) + 红色分隔线
#       + 课表全框线表格(节次红数字, 今日列黑底白字, 午休行"-")
# 硬件: ESP32-S3 + SSD1683; BUSY=7 RST=8 DC=9 CS=10 MOSI=11 SCK=12
# 课表: 外置 class_data.json(根目录), 每次刷屏重读; 缺失时用生成时注入的 JSON 快照兜底
# 数据: NTP对时 + open-meteo 实时天气/AQI(HTTP免密钥, 与周看板共用 wcache2.json) + 本地农历
# 刷新: 每日固定时刻(REFRESH_HOURS) + 天气显著变化补刷 + 跨天必刷; 轮询只取数不刷屏
#       ——课表按日变化, 避免三色屏每60分钟一次15s全刷(24次/天 -> 3~5次/天)
import machine, time, network, socket, gc, os, ujson

# ================= 配置 =================
# 凭据与城市等私有配置在 secrets.py(见 secrets.example.py), 不入库
import secrets
SSID, PWD = secrets.SSID, secrets.PWD
CITY = secrets.CITY
LAT, LON = secrets.LAT, secrets.LON
TZ = secrets.TZ
REFRESH_HOURS = (7, 12, 17)  # 每日固定刷新时刻(整点); 启动/跨天也必刷
CHECK_MIN = 60               # 天气轮询间隔(分钟), 轮询只取数不刷屏
TEMP_DELTA = 3               # 温度变化>=该值 或 天气现象变化 才补刷
CACHE = "wcache2.json"       # 与周看板共用; aqi为可选字段, 缺失时头部自动隐藏该段
# 课表数据在 class_data.json (外置): 改内容只需覆盖该 JSON, 下一次刷新生效;
# 若引入了字库里没有的新汉字, 需同步修改本地 class_data.json 并重跑 gen_week_class.py

API = ("http://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s"
       "&daily=temperature_2m_max,temperature_2m_min,sunrise,sunset,weather_code,precipitation_probability_max"
       "&current=temperature_2m,relative_humidity_2m,weather_code"
       "&timezone=Asia%%2FShanghai&forecast_days=7") % (LAT, LON)

# 空气质量是独立域名(不是 api.open-meteo.com); 设备端 HTTP 实测可达
AQI_API = ("http://air-quality-api.open-meteo.com/v1/air-quality?latitude=%s&longitude=%s"
           "&current=us_aqi&timezone=Asia%%2FShanghai") % (LAT, LON)

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


F = {"s": S, "m": M}

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
        cur = j["current"]
        out = {"cur": (int(float(cur["temperature_2m"]) + 0.5),
                       WMO.get(int(cur["weather_code"]), "阴"))}
    except Exception as e:
        print("[parse]", e)
        return None
    ab = http_get(AQI_API)
    if ab:
        try:
            out["aqi"] = int(ujson.loads(ab)["current"]["us_aqi"])
            print("[aqi] ok", out["aqi"])
        except Exception as e:
            print("[aqi]", e)
    return out


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
    return {"cur": (15, "阴")}


def build_data(f):
    lt = time.localtime(time.time() + TZ)
    y, mo, dd, wd = lt[0], lt[1], lt[2], lt[6]
    return {"city": CITY, "wk": "周" + WK[wd], "date": (y, mo, dd, wd),
            "cur": f["cur"], "aqi": f.get("aqi"), "lunar": lunar_str(y, mo, dd)}


def draw(d):
    gc.collect()
    d["class"] = get_class(True)   # 每次刷屏重读外置 JSON, 改课表无需重启
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
    print("[boot] class list start")
    gc.collect()
    cls = get_class()                       # 开机先校验课表数据
    miss = missing_glyphs(cls, S)
    if miss:
        print("[class] missing glyphs:", "".join(miss),
              "-> 重跑 gen_week_class.py 并重新上传 week_class_list.py")
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
        print("[wx]", "cache" if f and "cur" in f else "fallback")
        if not f or "cur" not in f:
            f = fallback()
    draw(build_data(f))
    lt0 = time.localtime(time.time() + TZ)
    last_day, last_hour = lt0[2], lt0[3]
    last_fixed = (last_day, last_hour) if last_hour in REFRESH_HOURS else None
    last_cur = f["cur"]
    nxt = time.time() + CHECK_MIN * 60
    while True:
        time.sleep(30)
        if time.time() < nxt:
            continue
        nxt = time.time() + CHECK_MIN * 60
        lt = time.localtime(time.time() + TZ)
        day, hour = lt[2], lt[3]
        if wifi_up():
            f2 = fetch()
            if f2:
                save_cache(f2)
                f = f2
        cur = f["cur"]
        fixed = hour in REFRESH_HOURS and (day, hour) != last_fixed
        changed = cur[1] != last_cur[1] or abs(cur[0] - last_cur[0]) >= TEMP_DELTA
        newday = day != last_day
        if not (fixed or changed or newday):
            continue
        print("[draw]", "fixed=%s changed=%s newday=%s" % (fixed, changed, newday))
        draw(build_data(f))
        last_cur = cur
        last_day = day
        if fixed:
            last_fixed = (day, hour)


main()
"""

if __name__ == "__main__":
    main()
