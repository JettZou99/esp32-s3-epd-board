# secrets.example.py —— 复制为 secrets.py 后填入自己的配置
# secrets.py 已被 .gitignore 排除, 不会提交到仓库; 需上传到设备 flash 根目录

SSID = "YourWiFiSSID"
PWD = "YourWiFiPassword"
CITY = "青岛"          # 显示在头部的城市名(需确保字符在 gen_week_board.py 的字库池中)
LAT = "36.07"          # 纬度(open-meteo 查询用)
LON = "120.38"         # 经度
TZ = 8 * 3600          # 时区偏移(秒), 中国为 UTC+8
