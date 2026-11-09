# test_sim.py — 本地仿真: 用桩模块执行 epd_info_clock.py 的绘制逻辑,
# 捕获写入面板的 0x24(黑白)/0x26(红) RAM 数据, 按本屏极性渲染成图, 端到端验证
import sys
import os
import types
import json
import time as _time
from PIL import Image  # 必须在安装 time 桩之前导入

HERE = os.path.dirname(os.path.abspath(__file__))   # micropython/tests
MP = os.path.dirname(HERE)                          # micropython
SRC = os.path.join(MP, "epd_info_clock.py")
WTTR = os.path.join(HERE, "fixtures", "wttr_qd.json")
OUT = os.path.join(MP, "info_clock_sim.png")

# ---------- 桩: machine ----------
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

    def on(self):
        self._v = 1

    def off(self):
        self._v = 0


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
machine_mod.Pin_IN = 1
machine_mod.Pin_OUT = 2
machine_mod.Pin_PULL_UP = 3
sys.modules["machine"] = machine_mod

# ---------- 桩: network ----------
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
    def ifconfig(self):
        return ("192.168.102.116", "255.255.255.0", "192.168.102.254", "202.102.134.68")
    def scan(self):
        return []

network_mod = types.ModuleType("network")
network_mod.STA_IF = 1
network_mod.WLAN = _WLAN
sys.modules["network"] = network_mod

# ---------- 桩: socket(返回真实 wttr.in 样本) ----------
_wttr_body = open(WTTR, encoding="utf-8").read().encode("utf-8")


class _Sock:
    def settimeout(self, t):
        pass
    def connect(self, ai):
        pass
    def send(self, b):
        pass
    def recv(self, n):
        global _sent
        chunk = _wttr_body[:_sent] if not _sent else b""
        _sent = len(_wttr_body)
        return _wttr_body if not _sent_done["d"] else b""
    def close(self):
        pass


_sent_done = {"d": False}


class _Sock2:
    def __init__(self):
        self._pos = 0
        self._hdr = b"HTTP/1.0 200 OK\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n"

    def settimeout(self, t):
        pass

    def connect(self, ai):
        pass

    def send(self, b):
        pass

    def recv(self, n):
        # 分块喂整个响应(含HTTP头), 考验流式解析的跨块边界
        if self._pos < len(self._hdr):
            d = self._hdr[self._pos:self._pos + n]
            self._pos += len(d)
            return d
        p = self._pos - len(self._hdr)
        d = _wttr_body[p:p + n]
        self._pos += len(d)
        return d

    def close(self):
        pass


def _getaddrinfo(host, port):
    return [(2, 1, 0, "", ("5.9.243.187", 80))]


socket_mod = types.ModuleType("socket")
socket_mod.socket = _Sock2
socket_mod.getaddrinfo = _getaddrinfo
sys.modules["socket"] = socket_mod

# ---------- 桩: ntptime ----------
ntptime_mod = types.ModuleType("ntptime")
ntptime_mod.host = "pool.ntp.org"
ntptime_mod.settime = lambda: None
sys.modules["ntptime"] = ntptime_mod

# ---------- 桩: secrets(测试不依赖本机私有 secrets.py) ----------
secrets_mod = types.ModuleType("secrets")
secrets_mod.SSID, secrets_mod.PWD = "TEST-SSID", "test-pwd"
secrets_mod.CITY, secrets_mod.TZ = "青岛", 8 * 3600
sys.modules["secrets"] = secrets_mod

# ---------- 桩: time(MicroPython API) ----------
import time as _real_time

time_mod = types.ModuleType("time")
time_mod.time = _real_time.time
time_mod.localtime = lambda t=None: _real_time.localtime(t if t is not None else _real_time.time())
time_mod.ticks_ms = lambda: int(_real_time.time() * 1000) & 0x3FFFFFFF
time_mod.ticks_diff = lambda a, b: a - b
time_mod.sleep_ms = lambda ms: None
time_mod.sleep = lambda s: None
sys.modules["time"] = time_mod

# ---------- 执行设备脚本(去掉末尾 main() 调用, 手动驱动) ----------
src = open(SRC, encoding="utf-8").read()
src = src.replace("\nmain()\n", "\n")
g = {"__name__": "epd_info_clock_sim"}
exec(compile(src, SRC, "exec"), g)

# 捕获 cmd() 的命令字(用于识别 0x24/0x26 数据)
_real_cmd = g["cmd"]


def _cmd(c, data=None):
    captured["cmds"].append(c)
    return _real_cmd(c, data)


g["cmd"] = _cmd

# ---------- 驱动一次 draw ----------
# 固定时刻: 2026-10-30 08:30 (北京), 与设计稿一致
lt = (2026, 10, 30, 8, 30, 0, 4, 303)
print("--- 流式 fetch_weather 测试(分块接收) ---")
w = g["fetch_weather"]()
print("fetch_weather ->", w)
assert w is not None, "fetch_weather 失败"
assert w["temp"] == 21 and w["hum"] == 37, w
assert w["sr"] == "06:19" and w["ss"] == "17:05", w
assert "转" in w["cond"] or len(w["cond"]) <= 4, w
print("--- draw(用真实抓取结果) ---")
g["draw"](lt, w, 52)
bw, red = captured["bw"], captured["red"]
assert bw is not None and red is not None, "no RAM captured"
print("captured BW %d bytes, RED %d bytes" % (len(bw), len(red)))

# ---------- 按本屏极性渲染: BW 0x00=黑/0xFF=白; RED 位1=红 ----------
W, H, RB = 400, 300, 50
img = Image.new("RGB", (W, H), "white")
px = img.load()
for y in range(H):
    for xb in range(RB):
        b = bw[y * RB + xb]
        r = red[y * RB + xb]
        for k in range(8):
            x = xb * 8 + k
            if (r >> (7 - k)) & 1:
                px[x, y] = (200, 30, 30)      # 红
            elif not ((b >> (7 - k)) & 1):
                px[x, y] = (20, 20, 20)       # 黑(BW反相: 位0=黑)
img = img.resize((W * 4, H * 4), Image.NEAREST)
img.save(OUT)
print("saved:", OUT)

# ---------- 基本断言 ----------
ink = sum(1 for y in range(H) for x in range(W) if px[x, y] != (255, 255, 255))
print("非白像素数:", ink)
assert ink > 3000, "墨迹太少, 疑似绘制失败"
print("SIM OK")
