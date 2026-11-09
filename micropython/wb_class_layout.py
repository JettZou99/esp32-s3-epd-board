# wb_class_layout.py —— 课表版式(与画布实现无关, 设备端与本地预览共用同一份)
# 版式(方案A·经典全框线, 已确认): 头部沿用周看板(城市/日期/星期 + 农历 + 天气/红温度)
#       + 红色分隔线 + 课表全框线表格(节次列红数字, 今日列黑底白字高亮)
# 课表数据: 外置到 class_data.json(设备根目录 / 本地同目录), 见文件内 _说明 与 README
# 画布接口: text(font,s,x,y,color) rect(...) hline(...) vline(...)
# color: 'k' 黑 / 'r' 红 / 'w' 白(在黑底上挖字)

W, H = 400, 300
ML = 14                 # 左右安全边
DIV_RED_Y = 30          # 头部红色分隔线

X0 = 12                 # 表格左缘
PW = 26                 # 节次列宽
CW = 70                 # 5 列时的列宽(实际按 weekdays 数量在 normalize_class 里算)
Y0 = 40                 # 表格顶
HH = 24                 # 表头行高
BH = 20                 # 午休行高
BOT = 288               # 表格底(固定, 下留 12px)

CLASS_FILE = "class_data.json"      # 外置课表数据(设备根目录)
DEFAULT_CLASS = None  # __CLASS_SNAPSHOT__   (生成器注入 JSON 快照, 文件缺失时兜底)
WK5 = ("一", "二", "三", "四", "五")


def tw(font, s):
    w = 0
    for ch in s:
        g = font.get(ch)
        w += g[0] if g else 8
    return w


def tc(cv, font, s, cx, y, color):
    """水平居中绘制"""
    cv.text(font, s, int(cx - tw(font, s) / 2), y, color)


# ================= 外置课表数据 =================
def _json_mod():
    try:
        import ujson as j            # 设备端
    except ImportError:
        import json as j             # 本地预览/仿真
    return j


def normalize_class(obj):
    """校验 JSON 并预计算网格几何; 数据非法时返回 None"""
    if not isinstance(obj, dict):
        return None
    raw_rows = obj.get("rows")
    if not isinstance(raw_rows, list) or not (1 <= len(raw_rows) <= 8):
        print("[class] rows invalid")
        return None
    wds = obj.get("weekdays") or list(WK5)
    if not isinstance(wds, list) or not (1 <= len(wds) <= 7):
        print("[class] weekdays invalid")
        return None
    for w in wds:
        if not isinstance(w, str):
            print("[class] weekdays invalid")
            return None
    ncols = len(wds)

    rows = []
    for row in raw_rows:
        if not isinstance(row, list) or len(row) != ncols:
            print("[class] row length != %d" % ncols)
            return None
        rr = []
        for cell in row:
            if isinstance(cell, str):
                rr.append(cell)                       # 单行
            elif (isinstance(cell, (list, tuple)) and len(cell) == 2
                  and isinstance(cell[0], str) and isinstance(cell[1], str)):
                rr.append(tuple(cell))                # 两行折行
            else:
                print("[class] bad cell:", cell)
                return None
        rows.append(rr)
    nrow = len(rows)

    brk = obj.get("break")
    if brk is not None:
        if not isinstance(brk, list) or len(brk) != ncols or not any(brk):
            brk = None
        else:
            brk = [t if isinstance(t, str) else "" for t in brk]
    after = obj.get("break_after", 4)
    if not isinstance(after, int):
        after = 4
    has_break = brk is not None and 0 <= after < nrow
    if not has_break:
        brk, after = None, -1

    bl = obj.get("break_label", "-")
    if not isinstance(bl, str) or not bl:
        bl = "-"
    per = obj.get("periods")
    if (not isinstance(per, list) or len(per) != nrow
            or not all(isinstance(t, str) for t in per)):
        per = None

    # 行高按节数自适应, 末行吸收余数, 保证表格底恰好落在 BOT
    avail = BOT - Y0 - HH - (BH if has_break else 0)
    rh = avail // nrow
    extra = avail - rh * nrow
    if rh < 12:
        print("[class] too many rows to fit")
        return None
    cw = (W - 2 * X0 - PW) // ncols

    ys = [Y0, Y0 + HH]
    disp = []                    # (正课行索引 / None=午休行, 节次标签, 行中心 y)
    y = Y0 + HH
    for i in range(nrow):
        if has_break and i == after:
            disp.append((None, bl, y + BH / 2))
            y += BH
            ys.append(y)
        h = rh + (extra if i == nrow - 1 else 0)
        disp.append((i, per[i] if per else str(i + 1), y + h / 2))
        y += h
        ys.append(y)
    return {"rows": rows, "weekdays": wds, "break": brk, "break_after": after,
            "disp": disp, "ys": ys, "cw": cw, "nrow": nrow, "ncols": ncols}


def placeholder_class():
    """文件与快照都不可用时的占位课表(全 "-"), 保证不黑屏"""
    return normalize_class({"weekdays": list(WK5),
                            "rows": [["-"] * 5 for _ in range(6)],
                            "break": [None] * 5})


def load_class():
    """读取外置 JSON → 内嵌快照 → 占位, 三级兜底"""
    j = _json_mod()
    name = CLASS_FILE.rsplit("/", 1)[-1]
    cands = [CLASS_FILE, "/" + name]
    try:
        p = __file__.replace("\\", "/")
        cands.append(p.rsplit("/", 1)[0] + "/" + name)
    except Exception:
        pass
    for p in cands:
        try:
            with open(p, "rb") as fp:
                txt = fp.read().decode("utf-8").lstrip("\ufeff")
            cls = normalize_class(j.loads(txt))
            if cls:
                print("[class] json ok:", p, "rows=%d cols=%d" % (cls["nrow"], cls["ncols"]))
                return cls
            print("[class] json invalid:", p)
            break                     # 找到文件但内容不合法, 不再试其他路径
        except OSError:
            continue                  # 该路径没有文件
        except Exception as e:
            print("[class] json error:", p, e)
            break
    print("[class] json unavailable, use embedded snapshot")
    return normalize_class(DEFAULT_CLASS) if DEFAULT_CLASS else placeholder_class()


_CLASS = None


def get_class(force=False):
    """force=True 每次刷屏重读 JSON —— 改课表后下一次刷新即生效, 无需重启"""
    global _CLASS
    if _CLASS is None or force:
        _CLASS = load_class()
    return _CLASS


def class_chars(cls):
    """课表用到的全部字符(供生成器构建字库 / 设备端缺字自检)"""
    d = {}

    def add(s):
        for ch in s:
            d[ch] = 1

    for w in cls["weekdays"]:
        add("周" + w)
    add("节")
    for _, label, _ in cls["disp"]:
        add(label)
    for row in cls["rows"]:
        for cell in row:
            if isinstance(cell, (list, tuple)):
                for t in cell:
                    add(t)
            else:
                add(cell)
    if cls["break"]:
        for t in cls["break"]:
            if t:
                add(t)
    return d


def missing_glyphs(cls, font):
    return [ch for ch in class_chars(cls) if ch not in font]


# ================= 渲染 =================
def render(cv, F, d):
    """d = {city, date:(y,m,d,wd), cur:(temp,cond), lunar, aqi, class?}"""
    S, M = F["s"], F["m"]

    # ---------- 头部: 左=城市/日期/星期, 中=农历, 右=天气/红温度 + AQI ----------
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
    aqi = d.get("aqi")
    alab = "AQI" if aqi is not None else ""
    anum = "%d" % aqi if aqi is not None else ""     # 数值单独绘制成红色
    aqs = alab + anum
    blockw = tw(M, cond) + 8 + tw(M, ts) + (6 + tw(S, aqs) if aqs else 0)
    rx = W - ML - blockw
    cv.text(M, cond, rx, 8, "k")
    tx = rx + tw(M, cond) + 8
    cv.text(M, ts, tx, 8, "r")
    if aqs:
        ax = tx + tw(M, ts) + 6
        cv.text(S, alab, ax, 8, "k")                 # 标签 "AQI" 黑色
        cv.text(S, anum, ax + tw(S, alab), 8, "r")  # 数字红色

    lun = d.get("lunar", "")
    if lun and rx - left_end > 24:
        room = rx - left_end - 16
        if tw(M, lun) > room and lun.startswith("农历"):
            lun = lun[2:]
        if tw(M, lun) <= room:
            tc(cv, M, lun, (left_end + rx) // 2, 8, "k")

    cv.hline(ML, W - ML, DIV_RED_Y, "r", 2)

    # ---------- 课表 ----------
    cls = d.get("class") or get_class()
    rows, wds, cw = cls["rows"], cls["weekdays"], cls["cw"]
    ncols, right = cls["ncols"], X0 + PW + cls["ncols"] * cls["cw"]

    # 今日表头格黑底白字(周一~周五), 周末不高亮
    if wd < ncols:
        jx0 = X0 + PW + cw * wd
        cv.rect(jx0 + 1, Y0 + 1, jx0 + cw - 1, Y0 + HH - 1, "k")
    for yy in cls["ys"]:
        cv.hline(X0, right, yy, "k", 1)
    xs = [X0]
    for j in range(ncols + 1):
        xs.append(X0 + PW + cw * j)
    for xx in xs:
        cv.vline(xx, Y0, BOT, "k", 1)

    # 表头: 节 + 周一~周五(今日白字); 16px 字在 24px 行高内垂直居中(上下各留4px)
    hy = Y0 + (HH - 16) // 2
    for j, wname in enumerate(wds):
        cx = X0 + PW + cw * j + cw / 2
        tc(cv, S, "周" + wname, cx, hy, "w" if j == wd else "k")
    tc(cv, S, "节", X0 + PW / 2, hy, "k")

    # 逐行: 节次列(红数字 / 黑色 "-") + 单元格内容
    for kind, label, yc in cls["disp"]:
        yy = int(yc - 8)
        tc(cv, S, label, X0 + PW / 2, yy, "k" if kind is None else "r")
        if kind is None:                       # 午休行内容
            for j, t in enumerate(cls["break"] or ()):
                if t and j < ncols:
                    tc(cv, S, t, X0 + PW + cw * j + cw / 2, yy, "k")
            continue
        for j, cell in enumerate(rows[kind]):
            if j >= ncols:
                break
            cx = X0 + PW + cw * j + cw / 2
            if isinstance(cell, (list, tuple)):
                tc(cv, S, cell[0], cx, int(yc - 16), "k")
                tc(cv, S, cell[1], cx, int(yc + 1), "k")
            else:
                tc(cv, S, cell, cx, yy, "k")
