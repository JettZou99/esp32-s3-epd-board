# epd_partial_test.py —— SSD1683 三色屏"局部刷新"可行性实测
# 目的: 判断该屏是否支持只刷新窗口区域(不整屏闪烁)
# 结果判据: BUSY 时长。三色全刷 ~15-18s; 局部刷新应 <3s
import machine, time, gc

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
        time.sleep_ms(2)
    return time.ticks_diff(time.ticks_ms(), t)


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
    time.sleep_ms(50)


def set_window(x0, x1, y0, y1):
    cmd(0x44, bytes((x0 >> 3, x1 >> 3)))
    cmd(0x45, bytes((y0 & 0xFF, y0 >> 8, y1 & 0xFF, y1 >> 8)))
    cmd(0x4E, bytes((x0 >> 3,)))
    cmd(0x4F, bytes((y0 & 0xFF, y0 >> 8)))


def full_white():
    buf = bytearray(b"\xff" * N)
    set_window(0, W - 1, 0, H - 1)
    cmd(0x24, buf)
    set_window(0, W - 1, 0, H - 1)
    cmd(0x26, buf)


def region_black(x0, x1, y0, y1):
    """只构造窗口区域的字节(黑=0x00)"""
    bw = (x1 >> 3) - (x0 >> 3) + 1
    return bytearray(b"\x00" * (bw * (y1 - y0 + 1)))


def main():
    gc.collect()
    print("[t] free", gc.mem_free())
    init()

    t0 = time.ticks_ms()
    full_white()
    cmd(0x22, b"\xf7")
    d = wait_busy()
    print("[full] white clear busy=%dms" % d)

    # ---- 第一次局部尝试: 0xFF (partial LUT) ----
    x0, x1, y0, y1 = 32, 88, 32, 72
    set_window(x0, x1, y0, y1)
    cmd(0x24, region_black(x0, x1, y0, y1))
    t = time.ticks_ms()
    cmd(0x22, b"\xff")
    t_send = time.ticks_diff(time.ticks_ms(), t)
    cmd(0x20)
    d1 = wait_busy()
    print("[partial A] 0x22=0xFF send=%dms busy=%dms" % (t_send, d1))

    time.sleep(2)

    # ---- 第二次局部尝试: 更远的位置, 验证是否只影响窗口 ----
    x0, x1, y0, y1 = 300, 356, 220, 260
    set_window(x0, x1, y0, y1)
    cmd(0x24, region_black(x0, x1, y0, y1))
    t = time.ticks_ms()
    cmd(0x22, b"\xff")
    cmd(0x20)
    d2 = wait_busy()
    print("[partial B] busy=%dms" % d2)

    time.sleep(2)

    # ---- 对照: 同样小窗口, 但用全刷波形 0xF7 ----
    x0, x1, y0, y1 = 160, 216, 120, 160
    set_window(x0, x1, y0, y1)
    cmd(0x24, region_black(x0, x1, y0, y1))
    t = time.ticks_ms()
    cmd(0x22, b"\xf7")
    cmd(0x20)
    d3 = wait_busy()
    print("[windowed full] busy=%dms" % d3)

    print("[done] 屏幕应出现 3 个黑方块; 观察每次是否有整屏闪烁")
    print("[done] A/B 若 <3s 且只闪小块 => 支持局部; 若 ~15s 且整屏闪 => 不支持")


main()
