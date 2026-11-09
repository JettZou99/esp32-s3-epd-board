# gen_info_clock.py — 生成 4.2寸墨水屏「信息时钟」脚本 epd_info_clock.py + 本地预览图（本地运行）
#
# 版式(优化版, 400x300 黑白红):
#   头部  青岛 2026年10月30日  ←左        晴转霾 ● 21°C  ←右(温度红)  + 红色分隔线
#   时钟        0 8 : 3 0                  (居中, 自适应字号, 上限 fs=160 约屏宽93%)
#   副标题          周 五                  (大时钟下方, 居中)
#   农历      农历九月廿一 · 霜降           (居中)
#   信息  湿度 37% · 日出 06:19 日落 17:05  (居中)
#
# 数据链路: NTP对时(UTC+8) + wttr.in实时天气(HTTP,免密钥,已实测可达)
#           + 本地农历/节气(与lunardate全量校验1990-2030)
# 关键实现: 黑底白字渲染取墨迹(getbbox)再反色; 位图位定义 1=黑墨
#           设备端字库格式: bytes([宽,高])+逐行打包位图(MSB优先)
import os
import sys
from PIL import Image, ImageFont, ImageDraw

W, H = 400, 300
HERE = os.path.dirname(os.path.abspath(__file__))


def _pick_font():
    """跨平台中文字体: Windows 优先(粗体), macOS 回退"""
    for p in ("C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/msyh.ttc",
              "C:/Windows/Fonts/simhei.ttf",
              "/System/Library/Fonts/Hiragino Sans GB.ttc"):
        if os.path.exists(p):
            return p
    raise SystemExit("no CJK font found")


FONT_PATH = _pick_font()
OUT_PY = os.path.join(HERE, "epd_info_clock.py")
OUT_PNG = os.path.join(HERE, "info_clock_preview.png")

MARGIN_X = 16           # 头部左右安全边
BIG_MARGIN = 8          # 大时钟左右安全边(略小于头部, 让时钟更突出)
BIG_MAXW = W - 2 * BIG_MARGIN   # 大时钟可用宽度("88:88" 约 fs=160 触顶 400px)
BIG_MAXFS = 160         # 大时钟字号上限(再大超屏宽)
BIG_MAXH = 130          # 大时钟高度上限(防挤压下方信息)
HEAD_Y = 16             # 头部(城市/日期 左; 天气/温度 右)顶y
DIV_Y = 52              # 头部下方分隔线y
CLOCK_TOP = 56          # 大时钟顶y(分隔线下方)
WEEK_GAP = 12           # 大时钟与星期副标题间距
BLOCK_GAP = 26          # 信息行之间间距
MID_FS = 18             # 小字字号
DOT_R = 4               # 天气与温度间红点半径
DIV_COLOR = "red"       # 头部分隔线颜色("red"/"black")

# ---------- 字符池(必须覆盖运行时所有可能文本) ----------
POOL_SMALL = (
    " "
    "0123456789"
    ":·%°，"
    "AQIC"
    "年月日周一二三四五六日"          # 日期/星期
    "青岛"                            # 城市
    "晴多云阴雨雪雾霾雷阵小中暴冰雹尘沙扬浮夹转"  # 天气
    "风雨冻毛毛吹粒"                  # 暴风雪/冻雨/毛毛雨/吹雪/冰粒
    "农历初十廿正二三四五六七八九冬腊闰"  # 农历
    "小寒大立春水惊蛰分明清谷夏满芒种至暑秋处白露霜降"  # 24节气
    "优良轻度污染重严"                # AQI等级
    "湿度出落"                        # 指标
    "元宵端七夕重阳除夕节"            # 农历节日
    "元旦情妇劳动儿童师国圣"          # 公历节日
    "人午女庆教诞"                    # 节日补字(情人节/端午/妇女/国庆/教师/圣诞)
    "时间同步中网络异常请检查…"        # 状态提示
)
POOL_SMALL = "".join(dict.fromkeys(POOL_SMALL))

# wttr.in 英文天气 -> 中文(映射值必须都在 POOL_SMALL 内)
WX_MAP = {
    "Sunny": "晴", "Clear": "晴", "Partly cloudy": "多云", "Cloudy": "阴",
    "Overcast": "阴", "Mist": "雾", "Fog": "雾", "Haze": "霾", "Smoke": "霾",
    "Smoky haze": "霾", "Light rain": "小雨", "Moderate rain": "中雨",
    "Heavy rain": "大雨", "Torrential rain": "暴雨", "Light drizzle": "毛毛雨",
    "Light rain shower": "阵雨", "Moderate or heavy rain shower": "阵雨",
    "Patchy rain nearby": "阵雨", "Patchy light rain": "小雨",
    "Patchy light rain with thunder": "雷阵雨", "Thundery outbreaks": "雷阵雨",
    "Light snow": "小雪", "Moderate snow": "中雪", "Heavy snow": "大雪",
    "Light sleet": "雨夹雪", "Moderate or heavy sleet": "雨夹雪",
    "Light freezing rain": "冻雨", "Sand": "沙", "Dust": "浮尘",
    "Blowing snow": "吹雪", "Blizzard": "暴风雪", "Ice pellets": "冰粒",
}
AQI_LEVELS = ("优", "良", "轻度污染", "中度污染", "重度污染", "严重污染")
FEST_LUNAR = {(1, 1): "春节", (1, 15): "元宵节", (5, 5): "端午节",
              (7, 7): "七夕节", (8, 15): "中秋节", (9, 9): "重阳节"}
FEST_SOLAR = {(1, 1): "元旦", (2, 14): "情人节", (3, 8): "妇女节",
              (5, 1): "劳动节", (6, 1): "儿童节", (9, 10): "教师节",
              (10, 1): "国庆节", (12, 25): "圣诞节"}

# ---------- 字形渲染(4x超采样抗锯齿; 位定义 1=黑墨) ----------
# 字形格式: (w, h, dy, data)  dy=墨迹顶相对本字体统一参考顶的偏移(基线对齐用)
SS = 4                      # 超采样倍率: 细横线在1x直接阈值化会丢失(如"青"少横)
THRESH = 170                # 墨迹覆盖率阈值: 偏高以保住字内留白(128会使笔画粘连)


def render_glyph(ch, size):
    """渲染单字 -> (w, h, y_off, data); y_off=墨迹顶相对绘制锚点顶的偏移"""
    c1 = size * 3                    # 1x 画布边长
    pad = size                       # 1x 锚点边距
    tmp = Image.new("L", (c1 * SS, c1 * SS), 0)
    ImageDraw.Draw(tmp).text((pad * SS, pad * SS), ch,
                             font=ImageFont.truetype(FONT_PATH, size * SS), fill=255)
    bbox = tmp.getbbox()
    if bbox is None:                      # 空白字符(空格)
        sw = max(2, size // 3)
        return (sw, 1, 0, b"\x00" * ((sw + 7) >> 3))
    x0, y0, x1, y1 = bbox
    g = tmp.crop(bbox)
    w = max(1, round((x1 - x0) / SS))
    h = max(1, round((y1 - y0) / SS))
    g = g.resize((w, h), Image.LANCZOS)
    y_off = round(y0 / SS) - pad
    bw = (w + 7) >> 3
    px = g.load()
    rows = bytearray(bw * h)
    for y in range(h):
        for xb in range(bw):
            v = 0
            for k in range(8):
                x = xb * 8 + k
                if x < w and px[x, y] > THRESH:   # 墨迹=白(高灰度); 1=黑墨
                    v |= 0x80 >> k
            rows[y * bw + xb] = v        # 1=黑墨
    return (w, h, y_off, bytes(rows))


def build_font(chars, size):
    f = {}
    for ch in chars:
        g = render_glyph(ch, size)
        if g:
            f[ch] = g
    if f:
        # 统一参考顶=本字体最高的墨迹顶(CJK即字顶; 数字字体即数字顶)
        # 使 "一"/":" 等矮字相对同排文字垂直居中, 而非被顶对齐拉到最上面
        ref = min(g[2] for g in f.values())
        for ch in f:
            w, h, yo, data = f[ch]
            f[ch] = (w, h, yo - ref, data)
    return f


# ---------- 农历算法(与设备端同源; 已与 lunardate 全量校验 1990-2030) ----------
LUNAR_INFO = (
0x04bd8,0x04ae0,0x0a570,0x054d5,0x0d260,0x0d950,0x16554,0x056a0,0x09ad0,0x055d2,
0x04ae0,0x0a5b6,0x0a4d0,0x0d250,0x1d255,0x0b540,0x0d6a0,0x0ada2,0x095b0,0x14977,
0x04970,0x0a4b0,0x0b4b5,0x06a50,0x06d40,0x1ab54,0x02b60,0x09570,0x052f2,0x04970,
0x06566,0x0d4a0,0x0ea50,0x06e95,0x05ad0,0x02b60,0x186e3,0x092e0,0x1c8d7,0x0c950,
0x0d4a0,0x1d8a6,0x0b550,0x056a0,0x1a5b4,0x025d0,0x092d0,0x0d2b2,0x0a950,0x0b557,
0x06ca0,0x0b550,0x15355,0x04da0,0x0a5d0,0x14573,0x052b0,0x0a9a8,0x0e950,0x06aa0,
0x0aea6,0x0ab50,0x04b60,0x0aae4,0x0a570,0x05260,0x0f263,0x0d950,0x05b57,0x056a0,
0x096d0,0x04dd5,0x04ad0,0x0a4d0,0x0d4d4,0x0d250,0x0d558,0x0b540,0x0b5a0,0x195a6,
0x095b0,0x049b0,0x0a974,0x0a4b0,0x0b27a,0x06a50,0x06d40,0x0af46,0x0ab60,0x09570,
0x04af5,0x04970,0x064b0,0x074a3,0x0ea50,0x06b58,0x05ac0,0x0ab60,0x096d5,0x092e0,
0x0c960,0x0d954,0x0d4a0,0x0da50,0x07552,0x056a0,0x0abb7,0x025d0,0x092d0,0x0cab5,
0x0a950,0x0b4a0,0x0baa4,0x0ad50,0x055d9,0x04ba0,0x0a5b0,0x15176,0x052b0,0x0a930,
0x07954,0x06aa0,0x0ad50,0x05b52,0x04b60,0x0a6e6,0x0a4e0,0x0d260,0x0ea65,0x0d530,
0x05aa0,0x076a3,0x096d0,0x04afb,0x04ad0,0x0a4d0,0x1d0b6,0x0d250,0x0d520,0x0dd45,
0x0b5a0,0x056d0,0x055b2,0x049b0,0x0a577,0x0a4b0,0x0aa50,0x1b255,0x06d20,0x0ada0,
0x14b63,0x09370,0x049f8,0x04970,0x064b0,0x168a6,0x0ea50,0x06aa0,0x1a6c4,0x0aae0,
0x092e0,0x0d2e3,0x0c960,0x0d557,0x0d4a0,0x0da50,0x05d55,0x056a0,0x0a6d0,0x055d4,
0x052d0,0x0a9b8,0x0a950,0x0b4a0,0x0b6a6,0x0ad50,0x055a0,0x0aba4,0x0a5b0,0x052b0,
0x0b273,0x06930,0x07337,0x06aa0,0x0ad50,0x14b55,0x04b60,0x0a570,0x054e4,0x0d160,
0x0e968,0x0d520,0x0daa0,0x16aa6,0x056d0,0x04ae0,0x0a9d4,0x0a2d0,0x0d150,0x0f252,
0x0d520)


def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def days_from_civil(y, m, d):
    # 自 1900-01-01 起 0 基天数, 与 datetime 差值精确一致
    n = 0
    for Y in range(1900, y):
        if _is_leap(Y):
            n += 1
    cum = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
    doy = cum[m - 1] + d - 1 + (1 if m > 2 and _is_leap(y) else 0)
    return (y - 1900) * 365 + n + doy


def leap_month(y):
    return LUNAR_INFO[y - 1900] & 0xF


def leap_days(y):
    if leap_month(y) != 0:
        return 30 if (LUNAR_INFO[y - 1900] & 0xF0000) else 29
    return 0


def month_days(y, m):
    return 30 if (LUNAR_INFO[y - 1900] & 0x0FFFF & (1 << (16 - m))) else 29


def year_days(y):
    s = 29 * 12
    i = 0x8000
    while i >= 0x8:
        if LUNAR_INFO[y - 1900] & 0xFFF0 & i:
            s += 1
        i >>= 1
    return s + leap_days(y)


def solar2lunar(y, m, d):
    offset = days_from_civil(y, m, d) - days_from_civil(1900, 1, 31)
    if offset < 0 or y < 1900 or y > 2100:
        return None
    ly = 1900
    while ly < 2100:
        t = year_days(ly)
        if offset < t:
            break
        offset -= t
        ly += 1
    leap = leap_month(ly)
    lm = 1
    leap_used = False
    while lm <= 12:
        if leap != 0 and not leap_used and lm == leap + 1:
            ld = leap_days(ly)
            if offset < ld:
                return ly, leap, offset + 1, leap, True
            offset -= ld
            leap_used = True
        ld = month_days(ly, lm)
        if offset < ld:
            return ly, lm, offset + 1, leap, False
        offset -= ld
        lm += 1
    return ly, 12, 30, leap, False


LMONTHS = ("正", "二", "三", "四", "五", "六", "七", "八", "九", "十", "冬", "腊")
LNUM = ("一", "二", "三", "四", "五", "六", "七", "八", "九")


def lunar_day_str(d):
    if d == 10:
        return "初十"
    if d == 20:
        return "二十"
    if d == 30:
        return "三十"
    p = {1: "十", 2: "廿", 3: "三"}.get(d // 10, "初")
    return p + LNUM[d % 10 - 1]


def lunar_str(y, m, d):
    r = solar2lunar(y, m, d)
    if r is None:
        return ""
    ly, lm, ld, leap, lflag = r
    return "农历" + ("闰" if lflag else "") + LMONTHS[lm - 1] + "月" + lunar_day_str(ld)


TERM_C = (5.4055, 20.12, 3.87, 18.73, 5.63, 20.646, 4.81, 20.1,
          5.52, 21.04, 5.678, 21.37, 7.108, 22.83, 7.5, 23.13,
          7.646, 23.042, 8.318, 23.438, 7.438, 22.36, 7.18, 21.94)
TERM_MONTH = (1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6,
              7, 7, 8, 8, 9, 9, 10, 10, 11, 11, 12, 12)
TERM_NAMES = ("小寒", "大寒", "立春", "雨水", "惊蛰", "春分",
              "清明", "谷雨", "立夏", "小满", "芒种", "夏至",
              "小暑", "大暑", "立秋", "处暑", "白露", "秋分",
              "寒露", "霜降", "立冬", "小雪", "大雪", "冬至")


def term_day(y, i):
    yk = y - 2000
    return int(yk * 0.2422 + TERM_C[i]) - int(yk // 4)


def solar_term(y, m, d):
    """返回当天节气名(仅节气当天), 否则 None"""
    for i in range(24):
        if TERM_MONTH[i] != m:
            continue
        if term_day(y, i) == d:
            return TERM_NAMES[i]
    return None


def current_term(y, m, d):
    """返回当前所处节气(最近一个已过去的节气; 与小寒之间算冬至)"""
    best = None
    for i in range(24):
        if TERM_MONTH[i] != m:
            continue
        dd = term_day(y, i)
        if dd <= d:
            if best is None or dd > best[0]:
                best = (dd, TERM_NAMES[i])
    if best:
        return best[1]
    if m == 1 and d < term_day(y, 0):
        return "冬至"
    return None


def festival(y, m, d):
    if (m, d) in FEST_SOLAR:
        return FEST_SOLAR[(m, d)]
    r = solar2lunar(y, m, d)
    if r:
        ly, lm, ld, leap, lflag = r
        if not lflag:
            if (lm, ld) in FEST_LUNAR:
                return FEST_LUNAR[(lm, ld)]
            if lm == 12 and ld == month_days(ly, 12):
                return "除夕"
    return None


# ---------- 天气解析(设备端同源; 字符串抽取, 避免整包 ujson 解析的内存峰值) ----------
def jval(seg, key):
    """在 seg 中找 "key": "值" 或 "key":值, 返回第一个字符串值"""
    k = seg.find('"' + key + '"')
    if k < 0:
        return None
    i = seg.find(":", k)
    if i < 0:
        return None
    i += 1
    n = len(seg)
    while i < n and seg[i] in " \t\r\n":
        i += 1
    if i >= n:
        return None
    if seg[i] == '"':
        j = seg.find('"', i + 1)
        if j < 0:
            return None
        return seg[i + 1:j]
    j = i
    while j < n and seg[j] not in ",}\r\n \t":
        j += 1
    return seg[i:j]


def hourly_conds(body):
    """取当天(第一个天气日) hourly 段全部 weatherDesc 值"""
    i = body.find('"hourly"')
    if i < 0:
        return []
    end = body.find('"date"', i)          # 下一个 "date" 即第二天, 截断
    seg = body[i:end] if end > 0 else body[i:]
    out = []
    p = 0
    while True:
        j = seg.find('"weatherDesc"', p)
        if j < 0:
            break
        v = jval(seg[j:], "value")
        if v:
            out.append(v)
        p = j + 13
    return out


def wx_zh(en):
    if en in WX_MAP:
        return WX_MAP[en]
    low = en.lower()
    for k, v in WX_MAP.items():
        if low.find(k.lower()) >= 0:
            return v
    return "多云"


def trend_zh(conds, current):
    seq = []
    for c in conds:
        z = wx_zh(c)
        if not seq or seq[-1] != z:
            seq.append(z)
    if not seq:
        return wx_zh(current)
    if len(seq) == 1:
        return seq[0]
    if seq[0] == seq[-1]:                # 首尾相同(如 晴霾晴) -> 只显示一种
        return seq[0]
    t = seq[0] + "转" + seq[-1]
    if len(t) > 6:                     # 过长(如"小雨夹雪转雷阵雨")只显示当前实况
        return wx_zh(current)
    return t


def hhmm(s):
    """"06:19 AM"/"05:05 PM" -> "06:19"/"17:05" """
    s = s.strip()
    if s[-2:] in ("AM", "PM"):
        ap = s[-2:]
        s = s[:-2].strip()
        h, m = s.split(":")
        h = int(h) % 12
        if ap == "PM":
            h += 12
        return "%02d:%02d" % (h, int(m))
    return s[:5]


def aqi_level(a):
    if a <= 50:
        return AQI_LEVELS[0]
    if a <= 100:
        return AQI_LEVELS[1]
    if a <= 150:
        return AQI_LEVELS[2]
    if a <= 200:
        return AQI_LEVELS[3]
    if a <= 300:
        return AQI_LEVELS[4]
    return AQI_LEVELS[5]


# ---------- 版式(与设备端 draw() 同构的绘制指令) ----------
def text_w(font, s):
    w = 0
    for ch in s:
        g = font.get(ch)
        w += g[0] if g else 9
    return w


def build_ops(mid, big, qf, sample):
    """sample 含: city,temp,cond,hm,big_h,lunar,info,quote,week,head_left"""
    ops = []
    # ---- 头部: 左=城市·日期  右=天气·红点·温度 ----
    ops.append({"k": "text", "f": mid, "t": sample["head_left"],
                "x": MARGIN_X, "y": HEAD_Y, "c": "black"})
    cond = sample["cond"]
    cw = text_w(mid, cond)
    tempw = text_w(mid, "%d°C" % sample["temp"])
    blockw = cw + 8 + 2 * DOT_R + 4 + tempw
    rx = W - MARGIN_X - blockw
    ops.append({"k": "text", "f": mid, "t": cond, "x": rx, "y": HEAD_Y, "c": "black"})
    ops.append({"k": "disc", "x": rx + cw + 8 + DOT_R, "y": HEAD_Y + 9, "r": DOT_R, "c": "red"})
    ops.append({"k": "text", "f": mid, "t": "%d°C" % sample["temp"],
                "x": rx + cw + 8 + 2 * DOT_R + 4, "y": HEAD_Y, "c": "red"})
    # ---- 头部分隔线 ----
    ops.append({"k": "hline", "x0": MARGIN_X, "x1": W - MARGIN_X, "y": DIV_Y, "c": DIV_COLOR})
    # ---- 大时钟(居中, 垂直位置由 CLOCK_TOP + big_h 推导) ----
    bh = sample["big_h"]
    TIME_CY = CLOCK_TOP + bh // 2
    WEEK_Y = CLOCK_TOP + bh + WEEK_GAP
    LUNAR_Y = WEEK_Y + BLOCK_GAP
    INFO_Y = LUNAR_Y + BLOCK_GAP
    th = text_w(big, sample["hm"])
    ops.append({"k": "text", "f": big, "t": sample["hm"],
                "x": (W - th) // 2, "y": TIME_CY - bh // 2, "c": "black"})
    # ---- 星期(大时钟下方副标题, 居中) ----
    if sample.get("week"):
        wk = sample["week"]
        ops.append({"k": "text", "f": mid, "t": wk,
                    "x": (W - text_w(mid, wk)) // 2, "y": WEEK_Y, "c": "black"})
    # ---- 农历 · 节气/节日 (居中) ----
    t3 = sample["lunar"]
    ops.append({"k": "text", "f": mid, "t": t3,
                "x": (W - text_w(mid, t3)) // 2, "y": LUNAR_Y, "c": "black"})
    # ---- AQI·湿度·日出日落 (居中) ----
    t4 = sample["info"]
    ops.append({"k": "text", "f": mid, "t": t4,
                "x": (W - text_w(mid, t4)) // 2, "y": INFO_Y, "c": "black"})
    return ops


# ---------- 预览渲染(直接用生成的位图, 4倍放大) ----------
def glyph_rgb(g, color, scale):
    w, h, data = g[0], g[1], g[3]
    bw = (w + 7) >> 3
    mask = Image.new("1", (w, h))
    px = mask.load()
    for yy in range(h):
        row = data[yy * bw:(yy + 1) * bw]
        for xx in range(w):
            if row[xx >> 3] & (0x80 >> (xx & 7)):
                px[xx, yy] = 1
    solid = Image.new("RGB", (w, h), color)
    out = Image.composite(solid, Image.new("RGB", (w, h), "white"), mask)
    return out.resize((w * scale, h * scale), Image.NEAREST)


def render_preview(ops, scale=4, path=OUT_PNG):
    img = Image.new("RGB", (W * scale, H * scale), "white")
    for op in ops:
        if op["k"] == "text":
            x, y = op["x"] * scale, op["y"] * scale
            for ch in op["t"]:
                g = op["f"].get(ch)
                if g is None:
                    x += 9 * scale
                    continue
                img.paste(glyph_rgb(g, (200, 30, 30) if op["c"] == "red" else (20, 20, 20), scale),
                          (x, y + g[2] * scale))
                x += g[0] * scale
        elif op["k"] == "disc":
            cx, cy, r = op["x"] * scale, op["y"] * scale, op["r"] * scale
            ImageDraw.Draw(img).ellipse([cx - r, cy - r, cx + r, cy + r],
                                        fill=(200, 30, 30))
        elif op["k"] == "hline":
            cx0, cx1, cy = op["x0"] * scale, op["x1"] * scale, op["y"] * scale
            col = (200, 30, 30) if op["c"] == "red" else (20, 20, 20)
            ImageDraw.Draw(img).rectangle([cx0, cy, cx1, cy + 2 * scale], fill=col)
    img.save(path)
    return path


# ---------- 设备脚本模板 ----------
DEV_SCRIPT = r'''# epd_info_clock.py (auto-generated by gen_info_clock.py)
# 4.2寸 400x300 黑白红墨水屏「信息时钟」(优化版式)
# 版式: 头部 左=城市·日期 / 右=天气·红温度 + 红色分隔线 | 中部 大时钟+星期副标题 |
#       下部 农历·节气/节日 | AQI·湿度·日出日落
# 硬件: ESP32-S3 + SSD1683; BUSY=GPIO7 RST=GPIO8 DC=GPIO9 CS=GPIO10 MOSI=GPIO11 SCK=GPIO12
# 数据: NTP对时(UTC+8) + wttr.in实时天气(HTTP免密钥) + 本地农历/节气
# 极性(实物调试确认): 黑白RAM 0x00=黑/0xFF=白(反相); 红色RAM 0xFF=红
import machine, time, network, socket, gc, os

# ================= 用户配置 =================
# 凭据与城市等私有配置在 secrets.py(见 secrets.example.py), 不入库
import secrets
SSID, PWD = secrets.SSID, secrets.PWD
CITY = secrets.CITY           # wttr.in 查询城市(设备端做URL编码)
TZ = secrets.TZ               # 时区偏移(秒): 北京时间
BW_WHITE = 0xFF               # 黑白RAM中"白"的位型; 本屏反相(0xFF=白,0x00=黑)。
                              # 若整屏黑白颠倒(黑底白字), 改为 0x00
RED_ON = 0xFF                 # 红色RAM中"红"的位型; 0xFF=红。若红色元素不显示/整屏红, 改 0x00
MAXW = 368                    # 文本可用宽度(超出时自动降级: 行1缩趋势/行4去AQI)
REFRESH_SEC = 20              # 主循环间隔(秒)
CLOCK_STEP_MIN = 1            # 时钟刷新粒度(分钟): 1=每分钟全刷一次(有白闪); 改5可降为5分钟一闪
WEATHER_MIN = 30              # 天气刷新间隔(分钟)
NTP_MIN = 180                 # NTP重新对时间隔(分钟)
AQI_URL = ""                  # 可选: 自建AQI数据代理(http, 返回 {"aqi":52}); 留空则隐藏AQI段

# ================= 版式(生成器注入, 与本地预览一致) =================
MARGIN_X = @@MARGIN_X@@       # 头部左右对齐基准
HEAD_Y = @@HEAD_Y@@           # 头部(城市/日期 左; 天气/温度 右)顶y
DIV_Y = @@DIV_Y@@             # 头部分隔线y
TIME_CY = @@TIME_CY@@         # 大时钟垂直中心
WEEK_Y = @@WEEK_Y@@           # 大时钟下方星期副标题顶y
LUNAR_Y = @@LUNAR_Y@@         # 农历行顶y
INFO_Y = @@INFO_Y@@           # 指标行顶y
DOT_R = @@DOT_R@@             # 天气与温度间红点半径
DIV_COLOR = "@@DIV_COLOR@@"   # 头部分隔线颜色("red"/"black")

# 断网时的兜底数据(首次且无缓存时使用)
WX_DEFAULT = {"temp": 18, "cond": "霾转多云", "hum": 45,
              "sr": "06:12", "ss": "17:08", "aqi": None}

# ================= EPD 驱动 =================
W, H = 400, 300
RB = W // 8
N = RB * H

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
    cmd(0x01, b"\x8f\x01\x00")   # 400行
    cmd(0x21, b"\x00\x00")       # 启用彩色RAM
    cmd(0x3C, b"\x05")           # border waveform
    cmd(0x11, b"\x03")           # 寻址模式
    cmd(0x18, b"\x80")           # 温度
    cmd(0x22, b"\xf7")           # 三色刷新
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
    cmd(0x07, b"\x03")           # 深度休眠: 隔离接触噪声/省电; 下次 init() 硬复位自动唤醒


def conv_bw(fb):
    # fb: 位1=黑墨 -> 原地转换为面板格式(避免再分配15KB)
    if BW_WHITE == 0xFF:
        for i in range(N):
            fb[i] ^= 0xFF
    return fb


def conv_red(fr):
    # fr: 位1=红 -> 原地转换
    if RED_ON != 0xFF:
        for i in range(N):
            fr[i] ^= 0xFF
    return fr


def disc(fr, cx, cy, r):
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dx * dx + dy * dy <= r * r:
                x, y = cx + dx, cy + dy
                if 0 <= x < W and 0 <= y < H:
                    fr[y * RB + (x >> 3)] |= 0x80 >> (x & 7)


def hline(fb, fr, x0, x1, y, color):
    """画水平线(2px厚). color='red' 用红RAM, 否则黑RAM."""
    tgt = fr if color == "red" else fb
    x0 = max(0, x0); x1 = min(W - 1, x1)
    for yy in (y, y + 1):
        if 0 <= yy < H:
            base = yy * RB
            for x in range(x0, x1 + 1):
                tgt[base + (x >> 3)] |= 0x80 >> (x & 7)


WK = ("一", "二", "三", "四", "五", "六", "日")
def week_str(wd):
    return "周" + WK[wd % 7]


def text_w(font, s):
    w = 0
    for ch in s:
        g = font.get(ch)
        w += g[0] if g else 9
    return w


def draw_text(fb, font, s, x, y):
    cx = x
    for ch in s:
        g = font.get(ch)
        if g is None:
            cx += 9
            continue
        w, h, dy = g[0], g[1], g[2]
        data = g[3:]
        bw = (w + 7) >> 3
        for ry in range(h):
            row = y + dy + ry
            if row < 0 or row >= H:
                continue
            base = row * RB
            for xb in range(bw):
                v = data[ry * bw + xb]
                if not v:
                    continue
                px = cx + xb * 8
                bi = px >> 3
                sh = px & 7
                if bi < RB:
                    fb[base + bi] |= v >> sh
                if sh and bi + 1 < RB:
                    fb[base + bi + 1] |= (v << (8 - sh)) & 0xFF
        cx += w


# ================= 字库(位图: 位1=黑墨; 头部2字节为宽/高) =================
@@MID@@

@@BIG@@

# ================= 农历/节气/节日 =================
@@LUNAR@@

# ================= 天气解析 =================
WX_MAP = {
    "Sunny": "晴", "Clear": "晴", "Partly cloudy": "多云", "Cloudy": "阴",
    "Overcast": "阴", "Mist": "雾", "Fog": "雾", "Haze": "霾", "Smoke": "霾",
    "Smoky haze": "霾", "Light rain": "小雨", "Moderate rain": "中雨",
    "Heavy rain": "大雨", "Torrential rain": "暴雨", "Light drizzle": "毛毛雨",
    "Light rain shower": "阵雨", "Moderate or heavy rain shower": "阵雨",
    "Patchy rain nearby": "阵雨", "Patchy light rain": "小雨",
    "Patchy light rain with thunder": "雷阵雨", "Thundery outbreaks": "雷阵雨",
    "Light snow": "小雪", "Moderate snow": "中雪", "Heavy snow": "大雪",
    "Light sleet": "雨夹雪", "Moderate or heavy sleet": "雨夹雪",
    "Light freezing rain": "冻雨", "Sand": "沙", "Dust": "浮尘",
    "Blowing snow": "吹雪", "Blizzard": "暴风雪", "Ice pellets": "冰粒",
}


def wx_zh(en):
    if en in WX_MAP:
        return WX_MAP[en]
    low = en.lower()
    for k, v in WX_MAP.items():
        if low.find(k.lower()) >= 0:
            return v
    return "多云"


def trend_zh(conds, current):
    seq = []
    for c in conds:
        z = wx_zh(c)
        if not seq or seq[-1] != z:
            seq.append(z)
    if not seq:
        return wx_zh(current)
    if len(seq) == 1:
        return seq[0]
    if seq[0] == seq[-1]:
        return seq[0]
    t = seq[0] + "转" + seq[-1]
    if len(t) > 6:
        return wx_zh(current)
    return t


def jval(seg, key):
    k = seg.find('"' + key + '"')
    if k < 0:
        return None
    i = seg.find(":", k)
    if i < 0:
        return None
    i += 1
    n = len(seg)
    while i < n and seg[i] in " \t\r\n":
        i += 1
    if i >= n:
        return None
    if seg[i] == '"':
        j = seg.find('"', i + 1)
        if j < 0:
            return None
        return seg[i + 1:j]
    j = i
    while j < n and seg[j] not in ",}\r\n \t":
        j += 1
    return seg[i:j]


def hourly_conds(body):
    i = body.find('"hourly"')
    if i < 0:
        return []
    end = body.find('"date"', i)
    seg = body[i:end] if end > 0 else body[i:]
    out = []
    p = 0
    while True:
        j = seg.find('"weatherDesc"', p)
        if j < 0:
            break
        v = jval(seg[j:], "value")
        if v:
            out.append(v)
        p = j + 13
    return out


def hhmm(s):
    s = s.strip()
    if s[-2:] in ("AM", "PM"):
        ap = s[-2:]
        s = s[:-2].strip()
        h, m = s.split(":")
        h = int(h) % 12
        if ap == "PM":
            h += 12
        return "%02d:%02d" % (h, int(m))
    return s[:5]


def http_get(url, timeout=12):
    """极简HTTP GET(仅HTTP), 返回 body 字符串; 失败返回 None(仅用于小响应, 如AQI)"""
    try:
        parts = url.split("/", 3)
        host = parts[2]
        path = "/" + parts[3] if len(parts) > 3 else "/"
        ai = socket.getaddrinfo(host, 80)[0][-1]
        s = socket.socket()
        s.settimeout(timeout)
        s.connect(ai)
        req = ("GET %s HTTP/1.0\r\nHost: %s\r\nUser-Agent: esp32-epd\r\n"
               "Connection: close\r\n\r\n" % (path, host))
        s.send(req.encode())
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


def _url_encode(s):
    out = ""
    for ch in s:
        o = ord(ch)
        if o > 127:
            for b in ch.encode("utf-8"):
                out += "%%%02X" % b
        elif ch in " ":
            out += "%20"
        else:
            out += ch
    return out


def _kv(buf, key):
    """buf 中找 "key": "值" 或 "key":值; 返回 (值str, 结束pos); 不完整返回 None"""
    k = buf.find(b'"' + key + b'"')
    if k < 0:
        return None
    i = buf.find(b":", k)
    if i < 0:
        return None
    i += 1
    n = len(buf)
    while i < n and buf[i] in (32, 9, 13, 10):
        i += 1
    if i >= n:
        return None
    if buf[i] == 34:                      # 引号 -> 字符串值
        j = buf.find(b'"', i + 1)
        if j < 0:
            return None
        return buf[i + 1:j].decode("utf-8", "ignore"), j + 1
    j = i                                # 数字值
    while j < n and buf[j] not in (44, 125, 13, 10, 32, 9):
        j += 1
    if j >= n:
        return None
    return buf[i:j].decode(), j


def fetch_weather():
    """wttr.in j1 流式解析: 边收边抽取(字段顺序 current_condition->weather->astronomy->hourly),
    全程驻留缓冲 <2KB, 避免整包 23KB 响应撑爆内存"""
    gc.collect()
    url = "http://wttr.in/" + _url_encode(CITY) + "?format=j1"
    try:
        parts = url.split("/", 3)
        host = parts[2]
        path = "/" + parts[3] if len(parts) > 3 else "/"
        ai = socket.getaddrinfo(host, 80)[0][-1]
        s = socket.socket()
        s.settimeout(15)
        s.connect(ai)
        s.send(("GET %s HTTP/1.0\r\nHost: %s\r\nUser-Agent: esp32-epd\r\n"
                "Connection: close\r\n\r\n" % (path, host)).encode())
    except Exception as e:
        print("[http]", e)
        return None
    buf = b""
    temp = hum = cur = sr = ss = None
    conds = []
    stage = 0
    try:
        while stage < 9:
            chunk = s.recv(1024)
            if not chunk:
                break
            buf += chunk
            progress = True
            while progress:
                progress = False
                if stage == 0:                      # 等 current_condition(顺带跳过HTTP头)
                    i = buf.find(b'"current_condition"')
                    if i >= 0:
                        buf = buf[i:]
                        stage = 1
                        progress = True
                    elif len(buf) > 4096:
                        buf = buf[-256:]
                elif stage == 1:                    # humidity
                    r = _kv(buf, b"humidity")
                    if r:
                        hum = int(float(r[0]))
                        buf = buf[r[1]:]
                        stage = 2
                        progress = True
                elif stage == 2:                    # temp_C
                    r = _kv(buf, b"temp_C")
                    if r:
                        temp = int(float(r[0]))
                        buf = buf[r[1]:]
                        stage = 3
                        progress = True
                elif stage == 3:                    # 当前天气(weatherDesc 内的 value)
                    i = buf.find(b'"weatherDesc"')
                    if i >= 0:
                        r = _kv(buf[i:], b"value")
                        if r:
                            cur = r[0]
                            buf = buf[i + r[1]:]
                            stage = 4
                            progress = True
                elif stage == 4:                    # astronomy
                    i = buf.find(b'"astronomy"')
                    if i >= 0:
                        buf = buf[i:]
                        stage = 5
                        progress = True
                elif stage == 5:                    # sunrise
                    r = _kv(buf, b"sunrise")
                    if r:
                        sr = hhmm(r[0])
                        buf = buf[r[1]:]
                        stage = 6
                        progress = True
                elif stage == 6:                    # sunset
                    r = _kv(buf, b"sunset")
                    if r:
                        ss = hhmm(r[0])
                        buf = buf[r[1]:]
                        stage = 7
                        progress = True
                elif stage == 7:                    # hourly(当天)
                    i = buf.find(b'"hourly"')
                    if i >= 0:
                        buf = buf[i:]
                        stage = 8
                        progress = True
                elif stage == 8:                    # 逐条收 weatherDesc(到第二天或满8条即止)
                    i = 0
                    got = False
                    while True:
                        j = buf.find(b'"weatherDesc"', i)
                        if j < 0:
                            break
                        r = _kv(buf[j:], b"value")
                        if r is None:
                            break
                        conds.append(r[0])
                        i = j + r[1]
                        got = True
                    if got:
                        buf = buf[i:]
                        progress = True
                    if len(conds) >= 8 or buf.find(b'"date"') >= 0:
                        stage = 9
                        progress = True
    except Exception as e:
        print("[http]", e)
        try:
            s.close()
        except Exception:
            pass
        return None
    try:
        s.close()
    except Exception:
        pass
    if temp is None or hum is None:
        print("[wx] incomplete")
        return None
    return {"temp": temp, "cond": trend_zh(conds, cur or "Sunny"),
            "hum": hum, "sr": sr or "06:00", "ss": ss or "18:00"}


def fetch_aqi():
    """尽力获取AQI(需自建代理); 失败返回 None -> 界面隐藏AQI段"""
    if not AQI_URL:
        return None
    try:
        body = http_get(AQI_URL, 10)
        if not body:
            return None
        v = jval(body, "aqi")
        if v is None:
            return None
        return int(float(v))
    except Exception:
        return None


def aqi_level(a):
    if a <= 50:
        return "优"
    if a <= 100:
        return "良"
    if a <= 150:
        return "轻度污染"
    if a <= 200:
        return "中度污染"
    if a <= 300:
        return "重度污染"
    return "严重污染"


def save_cache(w):
    try:
        with open("/wcache.json", "w") as f:
            f.write('{"t":%d,"temp":%d,"cond":"%s","hum":%d,"sr":"%s","ss":"%s"}'
                    % (time.time(), w["temp"], w["cond"], w["hum"], w["sr"], w["ss"]))
    except Exception:
        pass


def load_cache():
    try:
        body = open("/wcache.json").read()
        return {"temp": int(jval(body, "temp")), "cond": jval(body, "cond"),
                "hum": int(jval(body, "hum")), "sr": jval(body, "sr"),
                "ss": jval(body, "ss")}
    except Exception:
        return None


# ================= 网络 =================
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


# ================= 主绘制 =================
def draw(lt, wx, aqi):
    gc.collect()
    fb = bytearray(N)     # 位1=黑墨
    fr = bytearray(N)     # 位1=红
    y, mo, d, hh, mi = lt[0], lt[1], lt[2], lt[3], lt[4]
    ok_time = y >= 2020

    # ---- 头部: 左=城市·日期  右=天气·红点·温度 ----
    if ok_time:
        hl = "%s %d年%d月%d日" % (CITY, y, mo, d)
        draw_text(fb, MID, hl, MARGIN_X, HEAD_Y)
        cond = wx["cond"]
        cw = text_w(MID, cond)
        tempw = text_w(MID, "%d°C" % wx["temp"])
        blockw = cw + 8 + 2 * DOT_R + 4 + tempw
        rx = W - MARGIN_X - blockw
        draw_text(fb, MID, cond, rx, HEAD_Y)
        disc(fr, rx + cw + 8 + DOT_R, HEAD_Y + 9, DOT_R)
        draw_text(fr, MID, "%d°C" % wx["temp"], rx + cw + 8 + 2 * DOT_R + 4, HEAD_Y)
    else:
        draw_text(fb, MID, "%s 时间同步中…" % CITY, MARGIN_X, HEAD_Y)
    # 头部分隔线
    hline(fb, fr, MARGIN_X, W - MARGIN_X, DIV_Y, DIV_COLOR)

    # ---- 大时钟(居中) ----
    if ok_time:
        hm = "%02d:%02d" % (hh, mi)
        gh = BIG["8"][1]
        tw = text_w(BIG, hm)
        draw_text(fb, BIG, hm, (W - tw) // 2, TIME_CY - gh // 2)
        wk = week_str(lt[6])
        draw_text(fb, MID, wk, (W - text_w(MID, wk)) // 2, WEEK_Y)
    else:
        draw_text(fb, MID, "时间同步中…", (W - text_w(MID, "时间同步中…")) // 2, TIME_CY - 9)

    # ---- 农历 · 节气/节日 ----
    if ok_time:
        t3 = lunar_str(y, mo, d)
        f = festival(y, mo, d)
        if f:
            t3 = t3 + " · " + f
        else:
            ct = current_term(y, mo, d)
            if ct:
                t3 = t3 + " · " + ct
        draw_text(fb, MID, t3, (W - text_w(MID, t3)) // 2, LUNAR_Y)

    # ---- AQI · 湿度 · 日出日落 (AQI超宽自动隐藏) ----
    if ok_time:
        parts = []
        if aqi is not None:
            parts.append("AQI %d %s" % (aqi, aqi_level(aqi)))
        parts.append("湿度 %d%%" % wx["hum"])
        parts.append("日出 %s 日落 %s" % (wx["sr"], wx["ss"]))
        t4 = " · ".join(parts)
        if text_w(MID, t4) > MAXW and aqi is not None:
            parts = parts[1:]
            t4 = " · ".join(parts)
        draw_text(fb, MID, t4, (W - text_w(MID, t4)) // 2, INFO_Y)

    init()
    window()
    cmd(0x24, conv_bw(fb))       # bytearray 可直接送 SoftSPI, 无需拷贝
    window()
    cmd(0x26, conv_red(fr))
    refresh()
    gc.collect()


# ================= 主流程 =================
def main():
    print("[boot] info clock start")
    WX = dict(WX_DEFAULT)
    aqi = None
    if wifi_up():
        print("[wifi] ok")
        ntp_sync()
        w = fetch_weather()
        if w:
            WX = w
            save_cache(w)
            print("[wx]", w)
        else:
            c = load_cache()
            if c:
                WX = c
                print("[wx] use cache")
        aqi = fetch_aqi()
    else:
        print("[wifi] FAILED -> 缓存/兜底数据")
        c = load_cache()
        if c:
            WX = c

    last_draw = None
    last_wx = time.time()
    last_ntp = time.time()
    err_n = 0
    while True:
        try:
            lt = time.localtime(time.time() + TZ)
            key = (lt[0], lt[1], lt[2], lt[3], lt[4] // CLOCK_STEP_MIN)
            now = time.time()
            if now - last_wx > WEATHER_MIN * 60:
                w = fetch_weather()
                if w:
                    WX = w
                    save_cache(w)
                last_wx = now
                aqi = fetch_aqi()
            if now - last_ntp > NTP_MIN * 60:
                if wifi_up():
                    ntp_sync()
                    last_ntp = now
            if key != last_draw:
                print("[draw]", "%04d-%02d-%02d %02d:%02d" % (lt[0], lt[1], lt[2], lt[3], lt[4]),
                      "free=%d" % gc.mem_free())
                draw(lt, WX, aqi)
                last_draw = key
                err_n = 0
            time.sleep(REFRESH_SEC)
        except Exception as e:
            import sys
            err_n += 1
            backoff = min(30 * err_n, 300)
            print("[err]", e, "-> 重绘退避", backoff, "s (第", err_n, "次)")
            sys.print_exception(e)
            time.sleep(backoff)


main()
'''


def emit_font(name, font):
    lines = ["%s = {" % name]
    for ch in sorted(font.keys()):
        w, h, dy, data = font[ch]
        blob = bytes([w, h, dy]) + data
        lines.append("%r: %r," % (ch, blob))
    lines.append("}")
    return "\n".join(lines)


def emit_lunar():
    return (
        "LUNAR_INFO = (\n" +
        ",\n".join(",".join("0x%04x" % v for v in LUNAR_INFO[i:i + 10])
                  for i in range(0, len(LUNAR_INFO), 10)) +
        ",\n)\n\n"
        "TERM_C = %r\nTERM_MONTH = %r\nTERM_NAMES = %r\n\n"
        "LMONTHS = %r\nLNUM = %r\n\n"
        % (TERM_C, TERM_MONTH, TERM_NAMES, LMONTHS, LNUM)
    ) + r'''
def _is_leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def days_from_civil(y, m, d):
    n = 0
    for Y in range(1900, y):
        if _is_leap(Y):
            n += 1
    cum = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
    doy = cum[m - 1] + d - 1 + (1 if m > 2 and _is_leap(y) else 0)
    return (y - 1900) * 365 + n + doy


def leap_month(y):
    return LUNAR_INFO[y - 1900] & 0xF


def leap_days(y):
    if leap_month(y) != 0:
        return 30 if (LUNAR_INFO[y - 1900] & 0xF0000) else 29
    return 0


def month_days(y, m):
    return 30 if (LUNAR_INFO[y - 1900] & 0x0FFFF & (1 << (16 - m))) else 29


def year_days(y):
    s = 29 * 12
    i = 0x8000
    while i >= 0x8:
        if LUNAR_INFO[y - 1900] & 0xFFF0 & i:
            s += 1
        i >>= 1
    return s + leap_days(y)


def solar2lunar(y, m, d):
    offset = days_from_civil(y, m, d) - days_from_civil(1900, 1, 31)
    if offset < 0 or y < 1900 or y > 2100:
        return None
    ly = 1900
    while ly < 2100:
        t = year_days(ly)
        if offset < t:
            break
        offset -= t
        ly += 1
    leap = leap_month(ly)
    lm = 1
    leap_used = False
    while lm <= 12:
        if leap != 0 and not leap_used and lm == leap + 1:
            ld = leap_days(ly)
            if offset < ld:
                return ly, leap, offset + 1, leap, True
            offset -= ld
            leap_used = True
        ld = month_days(ly, lm)
        if offset < ld:
            return ly, lm, offset + 1, leap, False
        offset -= ld
        lm += 1
    return ly, 12, 30, leap, False


def lunar_day_str(d):
    if d == 10:
        return "初十"
    if d == 20:
        return "二十"
    if d == 30:
        return "三十"
    p = {1: "十", 2: "廿", 3: "三"}.get(d // 10, "初")
    return p + LNUM[d % 10 - 1]


def lunar_str(y, m, d):
    r = solar2lunar(y, m, d)
    if r is None:
        return ""
    ly, lm, ld, leap, lflag = r
    return "农历" + ("闰" if lflag else "") + LMONTHS[lm - 1] + "月" + lunar_day_str(ld)


def term_day(y, i):
    yk = y - 2000
    return int(yk * 0.2422 + TERM_C[i]) - int(yk // 4)


def current_term(y, m, d):
    best = None
    for i in range(24):
        if TERM_MONTH[i] != m:
            continue
        dd = term_day(y, i)
        if dd <= d:
            if best is None or dd > best[0]:
                best = (dd, TERM_NAMES[i])
    if best:
        return best[1]
    if m == 1 and d < term_day(y, 0):
        return "冬至"
    return None


FEST_SOLAR = {(1, 1): "元旦", (2, 14): "情人节", (3, 8): "妇女节",
              (5, 1): "劳动节", (6, 1): "儿童节", (9, 10): "教师节",
              (10, 1): "国庆节", (12, 25): "圣诞节"}
FEST_LUNAR = {(1, 1): "春节", (1, 15): "元宵节", (5, 5): "端午节",
              (7, 7): "七夕节", (8, 15): "中秋节", (9, 9): "重阳节"}


def festival(y, m, d):
    if (m, d) in FEST_SOLAR:
        return FEST_SOLAR[(m, d)]
    r = solar2lunar(y, m, d)
    if r:
        ly, lm, ld, leap, lflag = r
        if not lflag:
            if (lm, ld) in FEST_LUNAR:
                return FEST_LUNAR[(lm, ld)]
            if lm == 12 and ld == month_days(ly, 12):
                return "除夕"
    return None
'''


def main():
    print("=== 1. 渲染字库 ===")
    mid = build_font(POOL_SMALL, MID_FS)
    # 大时钟字号: 自动适配 "88:88" <= BIG_MAXW 且 高 <= BIG_MAXH, 不超过 BIG_MAXFS
    fs = BIG_MAXFS
    big = None
    big_h = 0
    while fs > 80:
        cand = build_font("0123456789:", fs)
        tw = sum(cand[c][0] for c in "88:88")
        if tw <= BIG_MAXW and cand["8"][1] <= BIG_MAXH:
            big, big_h = cand, cand["8"][1]
            break
        fs -= 2
    if big is None:
        raise SystemExit("big font fit failed")
    print("MID %d字 / BIG 字号=%d (88:88宽=%d, 高=%d)"
          % (len(mid), fs, sum(big[c][0] for c in "88:88"), big_h))

    # 字符池完整性自检: 运行时可能出现的所有字符都必须在字库中
    need = set()
    for v in WX_MAP.values():
        need |= set(v)
    for v in AQI_LEVELS:
        need |= set(v)
    for v in list(FEST_LUNAR.values()) + list(FEST_SOLAR.values()) + ["除夕"]:
        need |= set(v)
    for v in TERM_NAMES:
        need |= set(v)
    need |= set("青岛 · 年月日时间同步中…湿度出落AQI农历初十廿正二三四五六七八九冬腊闰转")
    miss = need - set(mid.keys())
    if miss:
        raise SystemExit("MID池缺字: %r" % sorted(miss))
    print("字符池自检: PASS (MID=%d)" % len(mid))

    print("=== 2. 农历/节气自检 ===")
    checks = [
        (2026, 10, 30, "农历九月廿一", None),
        (2026, 10, 23, "农历九月十四", "霜降"),
        (2026, 2, 17, "农历正月初一", None),
        (2026, 9, 25, "农历八月十五", None),
        (2026, 10, 18, "农历九月初九", None),
        (2026, 6, 19, "农历五月初五", None),
        (2026, 12, 31, "农历冬月廿三", None),
        (2027, 2, 6, "农历正月初一", None),
    ]
    allok = True
    for y, m, d, el, et in checks:
        s = lunar_str(y, m, d)
        t = solar_term(y, m, d)
        ok = (s == el) and (et is None or t == et)
        allok = allok and ok
        print("  %04d-%02d-%02d %s term=%s -> %s" % (y, m, d, s, t, "PASS" if ok else "FAIL"))
    ct = current_term(2026, 10, 30)
    print("  当前节气(2026-10-30):", ct, "PASS" if ct == "霜降" else "FAIL")
    print("自检:", "ALL PASS" if allok else "HAS FAILURE")

    print("=== 3. 天气解析自检(真实样本) ===")
    sample_json = None
    p = os.path.join(HERE, "tests", "fixtures", "wttr_qd.json")
    if os.path.exists(p):
        sample_json = open(p, encoding="utf-8").read()
        cc = sample_json[sample_json.find('"current_condition"'):][:4000]
        temp = int(float(jval(cc, "temp_C")))
        hum = int(float(jval(cc, "humidity")))
        cur = jval(cc, "value")
        conds = hourly_conds(sample_json)
        trend = trend_zh(conds, cur)
        ast = sample_json[sample_json.find('"astronomy"'):][:1200]
        sr = hhmm(jval(ast, "sunrise"))
        ss = hhmm(jval(ast, "sunset"))
        print("  实测: temp=%d cond=%s hum=%d sr=%s ss=%s hourly=%d"
              % (temp, trend, hum, sr, ss, len(conds)))
        sample = {"city": "青岛", "temp": temp, "cond": trend, "hum": hum,
                  "sr": sr, "ss": ss, "aqi": 52}
    else:
        print("  (无真实样本, 用设计稿数值)")
        sample = {"city": "青岛", "temp": 18, "cond": "霾转多云", "hum": 45,
                  "sr": "06:12", "ss": "17:08", "aqi": 52}

    # 组装与设备端 draw() 完全一致的各行文本
    lt = (2026, 10, 30, 8, 30, 0, 4, 303)
    y, mo, d = lt[0], lt[1], lt[2]
    sample["head_left"] = "%s %d年%d月%d日" % (sample["city"], y, mo, d)
    sample["hm"] = "%02d:%02d" % (lt[3], lt[4])
    sample["lunar"] = lunar_str(y, mo, d) + " · " + (current_term(y, mo, d) or "")
    info_parts = []
    if sample.get("aqi") is not None:
        info_parts.append("AQI %d %s" % (sample["aqi"], aqi_level(sample["aqi"])))
    info_parts.append("湿度 %d%%" % sample["hum"])
    info_parts.append("日出 %s 日落 %s" % (sample["sr"], sample["ss"]))
    sample["info"] = " · ".join(info_parts)
    sample["big_h"] = big_h
    sample["week"] = "周" + "一二三四五六日"[lt[6]]
    # 垂直版式: 分隔线下方放大时钟, 之后星期/农历/信息 依次下排, 利用移除格言后的富余空间
    TIME_CY = CLOCK_TOP + big_h // 2
    WEEK_Y = CLOCK_TOP + big_h + WEEK_GAP
    LUNAR_Y = WEEK_Y + BLOCK_GAP
    INFO_Y = LUNAR_Y + BLOCK_GAP
    assert INFO_Y + 20 <= H - 2, "布局越界: INFO_Y=%d" % INFO_Y
    print("  头部L:", sample["head_left"])
    print("  头部R: %s ● %d°C" % (sample["cond"], sample["temp"]))
    print("  时钟 :", sample["hm"], sample["week"], "(字号=%d, 高=%d)" % (fs, big_h))
    print("  农历 :", sample["lunar"])
    print("  信息 :", sample["info"], "(宽=%d)" % text_w(mid, sample["info"]))

    print("=== 4. 渲染预览 ===")
    ops = build_ops(mid, big, None, sample)
    render_preview(ops)
    print("written:", OUT_PNG, os.path.getsize(OUT_PNG), "bytes")

    print("=== 5. 生成设备脚本 ===")
    src = DEV_SCRIPT
    src = src.replace("@@MARGIN_X@@", str(MARGIN_X))
    src = src.replace("@@HEAD_Y@@", str(HEAD_Y))
    src = src.replace("@@DIV_Y@@", str(DIV_Y))
    src = src.replace("@@TIME_CY@@", str(TIME_CY))
    src = src.replace("@@WEEK_Y@@", str(WEEK_Y))
    src = src.replace("@@LUNAR_Y@@", str(LUNAR_Y))
    src = src.replace("@@INFO_Y@@", str(INFO_Y))
    src = src.replace("@@DOT_R@@", str(DOT_R))
    src = src.replace("@@DIV_COLOR@@", DIV_COLOR)
    src = src.replace("@@MID@@", emit_font("MID", mid))
    src = src.replace("@@BIG@@", emit_font("BIG", big))
    src = src.replace("@@LUNAR@@", emit_lunar())
    with open(OUT_PY, "w", encoding="utf-8") as f:
        f.write(src)
    print("written:", OUT_PY, os.path.getsize(OUT_PY), "bytes")


if __name__ == "__main__":
    main()
