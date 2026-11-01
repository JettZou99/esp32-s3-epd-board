# wb_layout.py —— 周视图看板版式(与画布实现无关, 设备端与本地预览共用同一份)
# 画布接口: text(font,s,x,y,color) rect(...) hline(...) vline(...) polyline(...) dot(...)
# color: 'k' 黑 / 'r' 红 / 'w' 白(在黑底上挖字)

W, H = 400, 300
ML = 14                 # 左右安全边
DIV_RED_Y = 30          # 头部红色分隔线
STRIP_X0 = 6            # 七列起点
STRIP_W = 388.0 / 7     # 单列宽
LBL_Y = 37              # 星期标签顶(16px字, 底=53 与日期行留1px)
DATE_Y = 54             # 日期数字顶(30px 字)
BOX_Y0, BOX_Y1 = 33, 91 # 今日高亮块
BAR_Y = 94              # 今日红色下划条
WEATHER_Y = 98          # 天气词行(今日列留空, 头部已显示当前天气)
GUIDE_Y0, GUIDE_Y1 = 116, 238   # 导轨下移, 给天气词行让位
PLOT_X0, PLOT_X1 = 46, 386
PLOT_Y0, PLOT_Y1 = 126, 232
RED_LINE2 = 244         # 底部红色分隔线
FOOT_LBL_Y = 251        # 底部标签(16px字, 底=267 与数值行留1px)
FOOT_VAL_Y = 268        # 底部数值
FOOT_BOT = 288


def tw(font, s):
    w = 0
    for ch in s:
        g = font.get(ch)
        w += g[0] if g else 8
    return w


def tc(cv, font, s, cx, y, color):
    """水平居中绘制"""
    cv.text(font, s, int(cx - tw(font, s) / 2), y, color)


def tr(cv, font, s, xr, y, color):
    """右对齐绘制(xr=右边界)"""
    cv.text(font, s, int(xr - tw(font, s)), y, color)


def cx_of(i):
    return STRIP_X0 + STRIP_W * (i + 0.5)


def render(cv, F, d):
    """d = {city,date:(y,m,d,wday),cur:(temp,cond),days:[(m,d,wday,tmax,tmin)],
            sun:(sr,ss),hum,upd}"""
    S, M, D = F["s"], F["m"], F["d"]

    # ---------- 头部: 左=城市/日期/星期, 右=天气/当前温度 ----------
    y, mo, dd, wd = d["date"]
    x = ML
    cv.text(M, d["city"], x, 8, "k")
    x += tw(M, d["city"]) + 10
    dv = "%d月%d日" % (mo, dd)
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

    # 星期与天气之间的空档: 居中放农历(空间不够时去掉"农历"二字)
    lun = d.get("lunar", "")
    if lun and rx - left_end > 24:
        room = rx - left_end - 16
        if tw(M, lun) > room and lun.startswith("农历"):
            lun = lun[2:]
        if tw(M, lun) <= room:
            tc(cv, M, lun, (left_end + rx) // 2, 8, "k")

    cv.hline(ML, W - ML, DIV_RED_Y, "r", 2)

    # ---------- 七列日历条 ----------
    days = d["days"]
    for i, it in enumerate(days):
        dm = it[0]
        cx = cx_of(i)
        lbl = d["labels"][i]
        ds = "%d" % dm
        if i == 0:
            cv.rect(int(cx - 25), BOX_Y0, int(cx + 25), BOX_Y1 - 1, "w")
            cv.rect(int(cx - 25), BOX_Y0, int(cx + 25), BOX_Y1 - 1, "k")
            tc(cv, S, lbl, cx, LBL_Y, "w")
            tc(cv, D, ds, cx, DATE_Y, "w")
            cv.rect(int(cx - 25), BAR_Y, int(cx + 25), BAR_Y + 3, "r")
        else:
            tc(cv, S, lbl, cx, LBL_Y, "k")
            tc(cv, D, ds, cx, DATE_Y, "k")

    # ---------- 天气词行(今日列留空: 头部已显示当前天气与温度) ----------
    for i in range(1, len(days)):
        it = days[i]
        cond = it[4] if len(it) > 4 else ""
        if not cond:
            continue
        c = "r" if ("雨" in cond or "雪" in cond or "雷" in cond) else "k"
        tc(cv, S, cond, cx_of(i), WEATHER_Y, c)

    # ---------- 温度折线 ----------
    hi = max(it[2] for it in days)
    lo = min(it[3] for it in days)
    hi = int(hi + 0.999)
    lo = int(lo)
    span = max(hi - lo, 4)
    pad = (PLOT_Y1 - PLOT_Y0 - 30) / float(span)

    def py(t):
        return int(PLOT_Y1 - (t - lo) * pad - 15)

    # 竖向点线导轨
    for i in range(7):
        cv.vline(int(cx_of(i)), GUIDE_Y0, GUIDE_Y1, "k", 1, 4)

    # 横向刻度线 + 左侧刻度值
    for t in (hi, lo + (hi - lo) // 2, lo):
        yy = py(t)
        cv.hline(PLOT_X0, PLOT_X1, yy, "k", 1, 3)
        tr(cv, S, "%d°" % t, PLOT_X0 - 6, yy - 7, "k")

    # 最高温(红) / 最低温(黑)
    pts_hi = [(int(cx_of(i)), py(days[i][2])) for i in range(7)]
    pts_lo = [(int(cx_of(i)), py(days[i][3])) for i in range(7)]
    cv.polyline(pts_hi, "r", 1)
    cv.polyline(pts_lo, "k", 1)
    for i in range(7):
        px, pyh = pts_hi[i]
        cv.dot(px, pyh, 2, "r")
        s = "%d°" % int(days[i][2] + 0.999)
        if i == 0:
            cv.text(M, s, px + 9, pyh - 22, "r")
        elif i == 6:
            tr(cv, M, s, px - 9, pyh - 22, "r")
        else:
            tc(cv, M, s, px, pyh - 22, "r")
        qx, pql = pts_lo[i]
        cv.dot(qx, pql, 2, "k")
        s = "%d°" % int(days[i][3])
        if i == 0:
            cv.text(M, s, qx + 9, pql + 6, "k")
        elif i == 6:
            tr(cv, M, s, qx - 9, pql + 6, "k")
        else:
            tc(cv, M, s, qx, pql + 6, "k")

    # ---------- 底部指标(4~5 项自适应列宽) ----------
    cv.hline(ML, W - ML, RED_LINE2, "r", 2)
    cols = [("日出", d["sun"][0]), ("日落", d["sun"][1]),
            ("湿度", "%d%%" % d["hum"])]
    if d.get("extra"):                     # 可选第五项: (标签, 数值)
        cols.append(tuple(d["extra"]))
    cols.append(("更新", d["upd"]))
    last = len(cols) - 1
    span_w = (W - 2 * ML) / float(len(cols))
    for k, (lbl, val) in enumerate(cols):
        cx = ML + span_w * (k + 0.5)
        tc(cv, S, lbl, cx, FOOT_LBL_Y, "k")
        tc(cv, M, val, cx, FOOT_VAL_Y, "r" if k == last else "k")
        if k:
            cv.vline(int(ML + span_w * k), FOOT_LBL_Y - 2, FOOT_BOT, "k", 1)
