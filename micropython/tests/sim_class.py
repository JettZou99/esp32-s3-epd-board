# sim_class.py — 课表设备脚本端到端仿真: 桩模块执行 week_class_list.py,
# 捕获 0x24/0x26 RAM 数据并按面板极性渲染
import sys
import os
import types
import time as _real_time
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))   # micropython/tests
MP = os.path.dirname(HERE)                          # micropython
SRC = os.path.join(MP, "week_class_list.py")
OUT = os.path.join(MP, "week_class_sim.png")

captured = {"bw": None, "red": None, "cmds": []}


class _Pin:
    IN = 1
    OUT = 2
    PULL_UP = 3

    def __init__(self, id, mode=-1, pull=None, value=None):
        self._v = 1 if value else 0

    def value(self, v=None):
        if v is None:
            return self._v
        self._v = v


class _SoftSPI:
    def __init__(self, **kw):
        pass

    def write(self, data):
        cmd = captured["cmds"][-1] if captured["cmds"] else None
        if cmd == 0x24:
            captured["bw"] = bytes(data)
        elif cmd == 0x26:
            captured["red"] = bytes(data)


machine_mod = types.ModuleType("machine")
machine_mod.Pin = _Pin
machine_mod.SoftSPI = _SoftSPI
sys.modules["machine"] = machine_mod

network_mod = types.ModuleType("network")
network_mod.STA_IF = 1


class _WLAN:
    def __init__(self, id):
        pass
    def active(self, f):
        pass
    def isconnected(self):
        return True
    def connect(self, *a):
        pass
    def disconnect(self):
        pass


network_mod.WLAN = _WLAN
sys.modules["network"] = network_mod

socket_mod = types.ModuleType("socket")


def _fail(*a):
    raise OSError("no net in sim")


socket_mod.socket = _fail
socket_mod.getaddrinfo = _fail
sys.modules["socket"] = socket_mod

ntptime_mod = types.ModuleType("ntptime")
ntptime_mod.host = ""
ntptime_mod.settime = lambda: None
sys.modules["ntptime"] = ntptime_mod

secrets_mod = types.ModuleType("secrets")
secrets_mod.SSID = "TEST-SSID"
secrets_mod.PWD = "test-pwd"
secrets_mod.CITY = "青岛"
secrets_mod.LAT = "36.07"
secrets_mod.LON = "120.38"
secrets_mod.TZ = 8 * 3600
sys.modules["secrets"] = secrets_mod

ujson_mod = types.ModuleType("ujson")
import json as _json
ujson_mod.dumps = _json.dumps
ujson_mod.loads = _json.loads
sys.modules["ujson"] = ujson_mod

# 固定时刻: 2026-11-09(周一) 14:30
_MON = (2026, 11, 9, 14, 30, 0, 0, 313)
time_mod = types.ModuleType("time")
time_mod.time = lambda: 1000.0
time_mod.localtime = lambda t=None: _MON
time_mod.ticks_ms = lambda: 0
time_mod.ticks_diff = lambda a, b: a - b
time_mod.sleep_ms = lambda ms: None
time_mod.sleep = lambda s: None
sys.modules["time"] = time_mod

src = open(SRC, encoding="utf-8").read()
src = src.replace("\nmain()\n", "\n")
g = {"__name__": "week_class_sim", "__file__": SRC}   # __file__ 供外置 JSON 路径回退
exec(compile(src, SRC, "exec"), g)

_real_cmd = g["cmd"]


def _cmd(c, data=None):
    captured["cmds"].append(c)
    return _real_cmd(c, data)


g["cmd"] = _cmd

d = g["build_data"]({"cur": (22, "晴"), "aqi": 52})
print("build_data:", d)
assert d["wk"] == "周一" and d["lunar"] and d["aqi"] == 52, d

# ---- 外置课表数据: 几何 / 缺字 / 每次刷新重读 ----
cls = g["get_class"]()
assert cls["nrow"] == 6 and cls["ncols"] == 5, (cls["nrow"], cls["ncols"])
assert len(cls["ys"]) == 9 and cls["ys"][-1] == 288, cls["ys"]
assert len(cls["disp"]) == 7 and cls["disp"][4][0] is None and cls["disp"][4][1] == "-", cls["disp"]
assert g["missing_glyphs"](cls, g["S"]) == [], g["missing_glyphs"](cls, g["S"])
print("class_data.json: OK (6x5, break after row4, all glyphs present)")

# 断网兜底: 无 aqi 字段时该段应自动隐藏且不报错
d_no_aqi = g["build_data"]({"cur": (22, "晴")})
assert d_no_aqi["aqi"] is None
g["render"](g["Canvas"](), g["F"], d_no_aqi)
print("no-AQI fallback: OK")

g["draw"](d)
assert d.get("class") is not None, "draw() 未重读外置课表 JSON"
bw, red = captured["bw"], captured["red"]
assert bw is not None and red is not None
print("captured BW %d bytes, RED %d bytes" % (len(bw), len(red)))

# ---- AQI 配色: 标签 "AQI" 黑, 数字 "52" 红(逐像素检查帧缓冲) ----
S, M, tw = g["F"]["s"], g["F"]["m"], g["tw"]
cond, ts, alab, anum = "晴", "22°", "AQI", "52"
blockw = tw(M, cond) + 8 + tw(M, ts) + 6 + tw(S, alab + anum)
rx = 400 - 14 - blockw
ax = rx + tw(M, cond) + 8 + tw(M, ts) + 6
lx0, lx1 = ax, ax + tw(S, alab)
nx0, nx1 = lx1, lx1 + tw(S, anum)
RB = 50


def bits(x0, x1, y0, y1, buf, on):
    n = 0
    for yy in range(y0, y1):
        for xx in range(x0, x1):
            v = buf[yy * RB + (xx >> 3)] & (0x80 >> (xx & 7))
            if bool(v) == on:
                n += 1
    return n


# BW 极性: 位0=黑墨; RED 极性: 位1=红墨
lab_black = bits(lx0, lx1, 0, 29, bw, False)
lab_red = bits(lx0, lx1, 0, 29, red, True)
num_black = bits(nx0, nx1, 0, 29, bw, False)
num_red = bits(nx0, nx1, 0, 29, red, True)
print("AQI label: black=%d red=%d | digits: black=%d red=%d"
      % (lab_black, lab_red, num_black, num_red))
assert lab_black > 20 and lab_red == 0, "AQI 标签应为纯黑"
assert num_red > 10 and num_black == 0, "AQI 数值应为纯红"
print("AQI color: OK")

# 极性: conv_bw 后 RAM 0=黑墨; RED 位1=红
W, H, RB = 400, 300, 50
img = Image.new("RGB", (W, H), "white")
px = img.load()
for y in range(H):
    for xb in range(RB):
        b = bw[y * RB + xb]
        r = red[y * RB + xb]
        for k in range(8):
            m = 0x80 >> k
            x = xb * 8 + k
            if not b & m:
                px[x, y] = (10, 10, 10)
            elif r & m:
                px[x, y] = (204, 32, 32)
img.resize((W * 3, H * 3), Image.NEAREST).save(OUT)
print("sim image:", OUT)
