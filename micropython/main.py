# main.py —— 开机自启动: 4.2" 三色墨水屏课表
# 部署: main.py / week_class_list.py / secrets.py / class_data.json 同放设备根目录
# 改课表内容: 只需覆盖 :class_data.json, 下一次刷新即生效(无需重启、无需重传主程序)
#             若出现字库里没有的新汉字, 需同步改本地 class_data.json 并重跑 gen_week_class.py
# 切换应用: 想回到周看板, 把下面 import week_class_list 改成 import epd_week_board
# 维护: USB 连上后按 Ctrl-C 可中断进入 REPL, Ctrl-D 软复位重新开始
import sys
import time

try:
    import week_class_list         # 模块被导入时即执行主循环(阻塞)
except Exception as e:             # 网络抖动/数据异常时不让设备变砖
    print("[main] failed:", e)
    try:
        sys.print_exception(e)
    except Exception:
        pass
    time.sleep(60)                 # 保留屏上上一帧, 1 分钟后重试
    import machine
    machine.reset()
