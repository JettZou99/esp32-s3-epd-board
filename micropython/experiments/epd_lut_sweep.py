# epd_lut_sweep.py —— 扫描 0x22 刷新参数, 测各波形耗时
import machine, time

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
            return -1
        time.sleep_ms(2)
    return time.ticks_diff(time.ticks_ms(), t)


def cmd(c, data=None):
    dc.value(0); cs.value(0)
    spi.write(bytes((c,)))
    if data is not None:
        dc.value(1); spi.write(data)
    cs.value(1); dc.value(1)


def init():
    rst.value(0); time.sleep_ms(10); rst.value(1); time.sleep_ms(10); wait_busy()
    cmd(0x01, b"\x8f\x01\x00")
    cmd(0x21, b"\x00\x00")
    cmd(0x3C, b"\x05")
    cmd(0x11, b"\x03")
    cmd(0x18, b"\x80")
    time.sleep_ms(50)


WHITE = b"\xff" * N
BLACK = b"\x00" * N

for p in (0xF7, 0xFF, 0xC7, 0xF4, 0xB9, 0xCF):
    try:
        init()
        cmd(0x44, b"\x00\x31"); cmd(0x45, b"\x00\x00\x2b\x01")
        cmd(0x4E, b"\x00"); cmd(0x4F, b"\x00\x00")
        cmd(0x24, WHITE)
        cmd(0x44, b"\x00\x31"); cmd(0x45, b"\x00\x00\x2b\x01")
        cmd(0x4E, b"\x00"); cmd(0x4F, b"\x00\x00")
        cmd(0x26, WHITE)
        cmd(0x22, bytes((p,)))
        cmd(0x20)
        d = wait_busy()
        print("[lut] 0x%02X -> %dms" % (p, d))
    except Exception as e:
        print("[lut] 0x%02X -> ERR %s" % (p, e))

init()
print("[done] 扫描完成")
