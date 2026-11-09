# boot_capture.py —— 中断主循环 -> 软复位 -> 捕获启动日志
# 用法: python tools/boot_capture.py [端口] [秒数]   例: python tools/boot_capture.py COM3 38
import sys
import time
import serial

PORT = sys.argv[1] if len(sys.argv) > 1 else "COM3"
DUR = int(sys.argv[2]) if len(sys.argv) > 2 else 38
s = serial.Serial(PORT, 115200, timeout=0.2)
s.reset_input_buffer()
s.write(b"\r\x03\r")            # Ctrl-C: 退出当前主循环, 回到 REPL
time.sleep(1.0)
s.read_all()
s.write(b"\x04")                # Ctrl-D: 软复位, 重新执行 main.py
t0 = time.time()
while time.time() - t0 < DUR:
    d = s.read(4096)
    if d:
        sys.stdout.write(d.decode("utf-8", "replace"))
        sys.stdout.flush()
s.close()
print("\n[done] captured %.1fs" % (time.time() - t0))
