# test_week_board_headless.py —— 本地桩跑周看板设备脚本, 逐像素比对设备画布 vs 预览画布
# 用法: python tests/test_week_board_headless.py (0 差异才算通过)
import sys, os, types, json, time as _time

HERE = os.path.dirname(os.path.abspath(__file__))   # micropython/tests
MP = os.path.dirname(HERE)                          # micropython
sys.path.insert(0, MP)
sys.path.insert(0, HERE)

# ---- 桩: machine ----
machine = types.ModuleType("machine")


class FakePin:
    IN = 0
    OUT = 1
    PULL_UP = 2

    def __init__(self, *a, **k):
        pass

    def value(self, *a):
        return 0


machine.Pin = FakePin
machine.SoftSPI = lambda **k: types.SimpleNamespace(write=lambda b: None)
machine.deepsleep = lambda ms: (_ for _ in ()).throw(SystemExit)
machine.freq = lambda *a: 160000000
sys.modules["machine"] = machine

# ---- 桩: network ----
network = types.ModuleType("network")


class WLAN:
    def __init__(self, *a):
        pass

    def active(self, *a):
        pass

    def isconnected(self):
        return False

    def connect(self, *a):
        pass

    def disconnect(self):
        pass


network.WLAN = WLAN
network.STA_IF = 0
sys.modules["network"] = network

# ---- 桩: ujson ----
sys.modules["ujson"] = json

# ---- 桩: time(ticks 系) ----
tmod = types.ModuleType("time")
tmod.time = _time.time
tmod.sleep = lambda s: (_ for _ in ()).throw(SystemExit)
tmod.sleep_ms = lambda ms: None
tmod.ticks_ms = lambda: int(_time.time() * 1000) & 0x7FFFFFFF
tmod.ticks_diff = lambda a, b: a - b
tmod.localtime = _time.localtime
# PIL/logging 在导入时会用到这些真实 time 属性, 桩必须透传, 否则 import gen_week_board 失败
tmod.time_ns = _time.time_ns
tmod.monotonic = _time.monotonic
tmod.perf_counter = _time.perf_counter
tmod.gmtime = _time.gmtime
tmod.mktime = _time.mktime
tmod.strftime = _time.strftime
sys.modules["time"] = tmod

# ---- 桩: ntptime ----
sys.modules["ntptime"] = types.ModuleType("ntptime")

# ---- 桩: secrets(测试不依赖本机私有 secrets.py) ----
secrets_stub = types.ModuleType("secrets")
secrets_stub.SSID, secrets_stub.PWD = "TEST-SSID", "test-pwd"
secrets_stub.CITY, secrets_stub.TZ = "青岛", 8 * 3600
secrets_stub.LAT, secrets_stub.LON = "36.07", "120.38"
sys.modules["secrets"] = secrets_stub

# ---- 执行设备脚本 ----
src = open(os.path.join(MP, "epd_week_board.py"), encoding="utf-8").read()
ns = {"__name__": "__main__"}
try:
    exec(compile(src, "epd_week_board.py", "exec"), ns)
    print("[warn] 设备脚本正常退出(不应发生)")
except SystemExit:
    pass

Canvas, F, render = ns["Canvas"], ns["F"], ns["render"]
build_data, fallback = ns["build_data"], ns["fallback"]
d = build_data(fallback())

# ---- 设备画布 ----
cv1 = Canvas()
render(cv1, F, d)

# ---- 预览画布 ----
import gen_week_board as g
cv2 = g.PILCanvas()
render(cv2, F, d)

W, H = 400, 300
mismatch = 0
first = None
for y in range(H):
    row = y * 50
    for x in range(W):
        bit = (cv1.fb[row + (x >> 3)] >> (7 - (x & 7))) & 1
        rbit = (cv1.fr[row + (x >> 3)] >> (7 - (x & 7))) & 1
        p = cv2.img.getpixel((x, y))
        exp_b = 1 if p == (0, 0, 0) else 0
        exp_r = 1 if p == (204, 32, 32) else 0
        # 面板显示语义: 红色 RAM 优先于黑色 RAM
        shown_red = rbit
        shown_black = bit and not rbit
        if shown_red != exp_r or shown_black != exp_b:
            mismatch += 1
            if first is None:
                first = (x, y, bit, rbit, exp_b, exp_r, p)
print("mismatch:", mismatch, "/", W * H, "first:", first)

# 统计墨量
bb = sum(bin(b).count("1") for b in cv1.fb)
rr = sum(bin(b).count("1") for b in cv1.fr)
print("black px:", bb, "red px:", rr, "coverage: %.1f%%" % (100 * (bb + rr) / (W * H)))
