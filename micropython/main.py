# main.py —— 开机自启动: 4.2" 三色墨水屏周视图看板
# 部署: 本文件与 epd_week_board.py 同放设备根目录, 上电/reset 后自动运行
# 更新看板: 只需覆盖 :epd_week_board.py (本文件无需改动), 然后硬复位
# 维护: USB 连上后按 Ctrl-C 可中断进入 REPL, Ctrl-D 软复位重新开始
import sys
import time

try:
    import epd_week_board          # 模块被导入时即执行主循环(阻塞)
except Exception as e:             # 网络抖动/数据异常时不让设备变砖
    print("[main] failed:", e)
    try:
        sys.print_exception(e)
    except Exception:
        pass
    time.sleep(60)                 # 保留屏上上一帧, 1 分钟后重试
    import machine
    machine.reset()
