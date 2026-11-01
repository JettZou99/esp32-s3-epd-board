# -*- coding: utf-8 -*-
# preview_alt.py —— 三种版式方案对比预览(设备同款画布+字库, 输出即上屏效果)
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PIL import Image, ImageDraw, ImageFont
import gen_week_board as G

POOL_S = G.POOL_S + "高低温降农历闰正腊冬初廿七八九十"
POOL_M = G.POOL_M + "高低温降粒雹"

S = G.build_font(POOL_S, 15)
M = G.build_font(POOL_M, 17)
D = G.build_font(G.POOL_D + "°", 30)
F = {"s": S, "m": M, "d": D}

W, H = 400, 300
RB = W // 8
N = RB * H


class Canvas:
    """与 epd_week_board.py 中完全相同的画布实现"""

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
                    if 0 <= row < H:
                        for xb in range(w):
                            if data[ry * bw + (xb >> 3)] & (0x80 >> (xb & 7)):
                                self._clr(cx + xb, row)
            else:
                buf = self.fr if color == "r" else self.fb
                for ry in range(h):
                    row = y + dy + ry
                    if 0 <= row < H:
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


def tw(font, s):
    return sum(font.get(ch, (8,))[0] for ch in s)


def tc(cv, font, s, cx, y, color):
    cv.text(font, s, int(cx - tw(font, s) / 2), y, color)


def tr(cv, font, s, xr, y, color):
    cv.text(font, s, int(xr - tw(font, s)), y, color)


def is_wet(cond):
    return any(c in cond for c in "雨雪雷")


def knockout(cv, font, s, cx, y):
    """数值标签白底挖空, 避免与网格线/折线叠压"""
    hw = tw(font, s) / 2 + 2
    cv.rect(int(cx - hw), y - 2, int(cx + hw), y + 16, "w")


# ================= 模拟数据 (11-1 周日起 7 天) =================
def mock():
    return {
        "city": "青岛", "wk": "周日", "date": (2026, 11, 1, 6),
        "cur": (15, "毛毛雨"),
        "labels": ["今天", "明天", "周一", "周二", "周三", "周四", "周五"],
        "days": [(1, 20, 11, "晴", 10), (2, 20, 12, "多云", 20),
                 (3, 19, 9, "阴", 30), (4, 17, 10, "小雨", 80),
                 (5, 19, 14, "多云", 20), (6, 20, 11, "晴", 5),
                 (7, 14, 5, "晴", 10)],
        "sun": ("06:20", "17:03"), "hum": 54, "upd": "18:45",
        "lunar": "农历九月廿三",
    }


STRIP_X0 = 6
STRIP_W = 388.0 / 7
ML = 14


def cx_of(i):
    return STRIP_X0 + STRIP_W * (i + 0.5)


def draw_header(cv, d, y_line=30):
    y_, mo, dd_, wd = d["date"]
    x = ML
    cv.text(M, d["city"], x, 8, "k")
    x += tw(M, d["city"]) + 10
    dv = "%d月%d日" % (mo, dd_)
    cv.text(M, dv, x, 8, "k")
    x += tw(M, dv) + 10
    cv.text(M, d["wk"], x, 8, "k")
    left_end = x + tw(M, d["wk"])
    cond, tcur = d["cur"][1], d["cur"][0]
    ts = "%d°" % tcur
    blockw = tw(M, cond) + 8 + tw(M, ts)
    rx = W - ML - blockw
    cv.text(M, cond, rx, 8, "k")
    cv.text(M, ts, rx + tw(M, cond) + 8, 8, "r")
    lun = d.get("lunar", "")
    if lun and rx - left_end > 24:
        room = rx - left_end - 16
        if tw(M, lun) > room and lun.startswith("农历"):
            lun = lun[2:]
        if tw(M, lun) <= room:
            tc(cv, M, lun, (left_end + rx) // 2, 8, "k")
    cv.hline(ML, W - ML, y_line, "r", 2)


def draw_strip(cv, d):
    for i, it in enumerate(d["days"]):
        cx = cx_of(i)
        lbl = d["labels"][i]
        ds = "%d" % it[0]
        if i == 0:
            cv.rect(int(cx - 25), 33, int(cx + 25), 90, "w")
            cv.rect(int(cx - 25), 33, int(cx + 25), 90, "k")
            tc(cv, S, lbl, cx, 37, "w")
            tc(cv, D, ds, cx, 54, "w")
            cv.rect(int(cx - 25), 94, int(cx + 25), 97, "r")
        else:
            tc(cv, S, lbl, cx, 37, "k")
            tc(cv, D, ds, cx, 54, "k")


def draw_plot(cv, d, y0, y1, with_weather_row=False):
    days = d["days"]
    hi = int(max(it[1] for it in days) + 0.999)
    lo = int(min(it[2] for it in days))
    span = max(hi - lo, 4)
    pad = (y1 - y0 - 30) / float(span)

    def py(t):
        return int(y1 - (t - lo) * pad - 15)

    for t in (hi, lo + (hi - lo) // 2, lo):
        yy = py(t)
        cv.hline(46, 386, yy, "k", 1, 3)
        tr(cv, S, "%d°" % t, 40, yy - 7, "k")

    pts_hi = [(int(cx_of(i)), py(days[i][1])) for i in range(7)]
    pts_lo = [(int(cx_of(i)), py(days[i][2])) for i in range(7)]
    cv.polyline(pts_hi, "r", 2)
    cv.polyline(pts_lo, "k", 1)
    for i in range(7):
        px, pyh = pts_hi[i]
        s = "%d°" % int(days[i][1] + 0.999)
        if i == 0:
            knockout(cv, M, s, px + 20, pyh - 22)
            cv.text(M, s, px + 9, pyh - 22, "r")
        elif i == 6:
            knockout(cv, M, s, px - 20, pyh - 22)
            tr(cv, M, s, px - 9, pyh - 22, "r")
        else:
            knockout(cv, M, s, px, pyh - 22)
            tc(cv, M, s, px, pyh - 22, "r")
        cv.dot(px, pyh, 3, "r")
        qx, pql = pts_lo[i]
        s = "%d°" % int(days[i][2])
        if i == 0:
            knockout(cv, M, s, qx + 20, pql + 6)
            cv.text(M, s, qx + 9, pql + 6, "k")
        elif i == 6:
            knockout(cv, M, s, qx - 20, pql + 6)
            tr(cv, M, s, qx - 9, pql + 6, "k")
        else:
            knockout(cv, M, s, qx, pql + 6)
            tc(cv, M, s, qx, pql + 6, "k")
        cv.dot(qx, pql, 2, "k")
        if with_weather_row:
            cond = days[i][3]
            tc(cv, S, cond, cx_of(i), 246, "r" if is_wet(cond) else "k")


def draw_footer(cv, d, cols=None, y_line=244):
    cv.hline(ML, W - ML, y_line, "r", 2)
    cols = cols or [("日出", d["sun"][0]), ("日落", d["sun"][1]),
                    ("湿度", "%d%%" % d["hum"]), ("更新", d["upd"])]
    span_w = (W - 2 * ML) / 4.0
    for k, (lbl, val) in enumerate(cols):
        cx = ML + span_w * (k + 0.5)
        tc(cv, S, lbl, cx, y_line + 7, "k")
        tc(cv, M, val, cx, y_line + 24, "r" if k == 3 else "k")
        if k:
            cv.vline(int(ML + span_w * k), y_line + 5, y_line + 44, "k", 1)


# ================= 方案 A: 天气行增强版 =================
def render_a(cv, d):
    draw_header(cv, d)
    draw_strip(cv, d)
    # 新增: 每天天气词(降水日红字), 数据来自 daily=weather_code
    for i, it in enumerate(d["days"]):
        cond = it[3]
        tc(cv, S, cond, cx_of(i), 98, "r" if is_wet(cond) else "k")
    draw_plot(cv, d, 122, 232)          # 无竖导轨 + 标签白底
    draw_footer(cv, d)


# ================= 方案 B: 双焦点(大温度+今日摘要) =================
def render_b(cv, d):
    y_, mo, dd_, wd = d["date"]
    # --- 头部加高到 46, 当前温度用 30px 大字 ---
    x = ML
    cv.text(M, d["city"], x, 7, "k")
    x += tw(M, d["city"]) + 10
    dv = "%d月%d日" % (mo, dd_)
    cv.text(M, dv, x, 7, "k")
    x += tw(M, dv) + 10
    cv.text(M, d["wk"], x, 7, "k")
    cv.text(S, d["lunar"], ML, 27, "k")
    cond, tcur = d["cur"][1], d["cur"][0]
    ts = "%d°" % tcur
    tw_d = tw(D, ts)
    cv.text(D, ts, W - ML - tw_d, 9, "r")
    cv.text(M, cond, W - ML - tw_d - 10 - tw(M, cond), 22, "k")
    cv.hline(ML, W - ML, 46, "r", 2)
    # --- 今日摘要带: 六项一行 ---
    items = [("高温", "%d°" % int(d["days"][0][1] + 0.999), "r"),
             ("低温", "%d°" % d["days"][0][2], "k"),
             ("湿度", "%d%%" % d["hum"], "k"),
             ("降水", "%d%%" % d["days"][0][4], "r" if d["days"][0][4] >= 40 else "k"),
             ("日出", d["sun"][0], "k"), ("日落", d["sun"][1], "k")]
    cw = (W - 2 * ML) / 6.0
    for k, (lbl, val, col) in enumerate(items):
        cx = ML + cw * (k + 0.5)
        tc(cv, S, lbl, cx, 54, "k")
        tc(cv, M, val, cx, 76, col)
    cv.hline(ML, W - ML, 112, "k", 1, 4)
    # --- 曲线 + 每天天气词 ---
    draw_plot(cv, d, 128, 234, with_weather_row=True)
    tr(cv, S, "更新 " + d["upd"], W - ML, 278, "k")


# ================= 方案 C: 七行列表 =================
def render_c(cv, d):
    draw_header(cv, d)
    y0, rh = 40, 36
    lo, hi = 4.0, 22.0
    bx0, bx1 = 306, 358

    def bx(t):
        return int(bx0 + (t - lo) * (bx1 - bx0) / (hi - lo))

    for i, it in enumerate(d["days"]):
        cy = y0 + i * rh
        today = (i == 0)
        col_lbl = "r" if today else "k"
        tc(cv, S, d["labels"][i], 47, cy + 2, col_lbl)
        tc(cv, M, "%d" % it[0], 100, cy + 1, col_lbl)
        cond = it[3]
        tc(cv, S, cond, 145, cy + 2, "r" if is_wet(cond) else "k")
        if it[4] >= 30:
            tr(cv, M, "%d%%" % it[4], 232, cy + 1, "r" if is_wet(cond) else "k")
        tr(cv, M, "%d°" % int(it[1] + 0.999), 298, cy + 1, "r")
        cv.rect(bx(it[2]), cy + 14, bx(it[1]), cy + 17, "r")
        tr(cv, M, "%d°" % int(it[2]), 386, cy + 1, "k")
        if today:
            cv.hline(ML, W - ML, cy + rh - 4, "r", 2)
        else:
            cv.hline(ML, W - ML, cy + rh - 4, "k", 1, 5)


# ================= 渲染输出 =================
def to_png(cv, path):
    im = Image.new("RGB", (W, H), (255, 255, 255))
    px = im.load()
    for y in range(H):
        for x in range(W):
            i = y * RB + (x >> 3)
            m = 0x80 >> (x & 7)
            if cv.fr[i] & m:
                px[x, y] = (220, 40, 40)
            elif cv.fb[i] & m:
                px[x, y] = (25, 25, 25)
    im.save(path)
    return im


if __name__ == "__main__":
    d = mock()
    outs = []
    for name, fn in (("A", render_a), ("B", render_b), ("C", render_c)):
        cv = Canvas()
        fn(cv, d)
        p = os.path.join(HERE, "layout_%s.png" % name)
        to_png(cv, p)
        outs.append((name, p))
        print("saved", p)

    # 拼 2x 对比图
    Z = 2
    imgs = [Image.open(p) for _, p in outs]
    lab_font = ImageFont.truetype("/System/Library/Fonts/Hiragino Sans GB.ttc", 26, index=1)
    titles = {
        "A": "方案A  天气行增强: 每天天气词(雨日红字) + 去导轨 + 标签白底",
        "B": "方案B  双焦点: 30px大温度 + 今日六项摘要 + 每天天气",
        "C": "方案C  七行列表: 天气/降水概率/温度区间条, 扫读最快",
    }
    LH = 52
    Wt = 800
    Ht = sum(im.height * Z + LH for im in imgs) + 10
    out = Image.new("RGB", (Wt, Ht), (245, 245, 245))
    dr = ImageDraw.Draw(out)
    yy = 5
    for (name, _), im in zip(outs, imgs):
        dr.text((10, yy + 8), titles[name], font=lab_font, fill=(60, 60, 60))
        yy += LH
        out.paste(im.resize((W, H * Z), Image.NEAREST), (0, yy))
        yy += H * Z
    out.save(os.path.join(HERE, "layout_options.png"))
    print("saved layout_options.png")
