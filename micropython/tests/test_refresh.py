# test_refresh.py —— 虚拟时钟验证课表 main() 的刷新策略
# 期望: 天气不变时 24h 只刷 启动1 + 固定时刻3 = 4 次; 温度跳变时多补刷 1 次
import sys, os, types, datetime, calendar, io, contextlib

MP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # micropython
SRC = os.path.join(MP, "week_class_list.py")
START = calendar.timegm((2026, 11, 8, 16, 0, 0))   # UTC 16:00 = 北京 11-09 00:00
clock = [START]


def _utc(ts):
    """无时区 UTC 时间(替代已废弃的 utcfromtimestamp)"""
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).replace(tzinfo=None)

class _Pin:
    IN, OUT, PULL_UP = 1, 2, 3
    def __init__(self, id, mode=-1, pull=None, value=None): self._v = 1 if value else 0
    def value(self, v=None):
        if v is None: return self._v
        self._v = v

class _SoftSPI:
    def __init__(self, **kw): pass
    def write(self, data): pass

m = types.ModuleType("machine"); m.Pin = _Pin; m.SoftSPI = _SoftSPI
sys.modules["machine"] = m
n = types.ModuleType("network"); n.STA_IF = 1
class _WLAN:
    def __init__(self, i): pass
    def active(self, f): pass
    def isconnected(self): return True
    def connect(self, *a): pass
    def disconnect(self): pass
n.WLAN = _WLAN; sys.modules["network"] = n
sys.modules["socket"] = types.ModuleType("socket")
nt = types.ModuleType("ntptime"); nt.host = ""; nt.settime = lambda: None
sys.modules["ntptime"] = nt
s = types.ModuleType("secrets")
s.SSID, s.PWD, s.CITY, s.LAT, s.LON, s.TZ = "x", "x", "青岛", "36.07", "120.38", 8 * 3600
sys.modules["secrets"] = s
u = types.ModuleType("ujson")
import json
u.loads, u.dumps = json.loads, json.dumps
sys.modules["ujson"] = u


def _localtime(t=None):
    dt = _utc(START if t is None else t)
    yday = (dt - datetime.datetime(dt.year, 1, 1)).days + 1
    return (dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second,
            dt.weekday(), yday)


def _sleep(sec):
    clock[0] += sec
    if clock[0] > START + 24 * 3600:
        raise SystemExit("24h done")


t = types.ModuleType("time")
t.time = lambda: clock[0]
t.localtime = _localtime
t.sleep = _sleep
t.sleep_ms = lambda ms: None
t.ticks_ms = lambda: 0
t.ticks_diff = lambda a, b: a - b
sys.modules["time"] = t

src = open(SRC, encoding="utf-8").read().replace("\nmain()\n", "\n")


def run(jump=False):
    clock[0] = START
    g = {"__name__": "refresh_sim"}
    exec(compile(src, SRC, "exec"), g)
    draws = []

    def _fetch():
        h = _utc(clock[0] + 8 * 3600).hour  # 北京时间
        return {"cur": (26 if jump and h >= 15 else 22, "晴"), "aqi": 52}

    def _draw(d):
        dt = _utc(clock[0] + 8 * 3600)   # 显示北京时间
        draws.append("%02d:%02d" % (dt.hour, dt.minute))
    g["draw"] = _draw
    g["fetch"] = _fetch
    g["save_cache"] = lambda f: None
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            g["main"]()
    except SystemExit:
        pass
    return draws


a = run(False)
b = run(True)
print("天气不变 24h 全刷次数:", len(a), "时刻(北京):", a)
print("15:00温度跳变 24h 全刷次数:", len(b), "时刻(北京):", b)
assert len(a) == 5, a          # 启动 + 7/12/17 固定 + 次日跨天
assert a[1:4] == ["07:00", "12:00", "17:00"], a
assert len(b) == 6 and "15:00" in b, b   # 多出 15:00 温度跳变补刷
print("刷新策略验证: PASS (旧策略 24 次/天 -> 5 次/天, 降 79%)")
