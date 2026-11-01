# -*- coding: utf-8 -*-
# preview_foot5.py —— 底部第五项候选对比(设备同款画布+字库, 输出即上屏效果)
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PIL import Image, ImageDraw, ImageFont
import gen_week_board as G
import wb_layout

EXTRA = "降水体感风力紫外级气压 "   # 候选标签用字
S = G.build_font(G.POOL_S + EXTRA, 15)
M = G.build_font(G.POOL_M + EXTRA, 17)
D = G.build_font(G.POOL_D, 30)
F = {"s": S, "m": M, "d": D}

SAMPLE = {
    "city": "青岛", "wk": "周六",
    "date": (2026, 10, 31, 5),
    "cur": (15, "毛毛雨"),
    "labels": ["今天", "明天", "周一", "周二", "周三", "周四", "周五"],
    "days": [(31, 5, 18.3, 11.2, ""), (1, 6, 18.0, 12.8, "晴"),
             (2, 0, 16.9, 9.1, "多云"), (3, 1, 18.3, 10.7, "阴"),
             (4, 2, 19.2, 14.7, "小雨"), (5, 3, 19.5, 11.3, "晴"),
             (6, 4, 13.6, 5.0, "阵雪")],
    "sun": ("06:20", "17:03"), "hum": 54, "upd": "18:45",
    "lunar": "农历九月廿二",
}

VARIANTS = [
    ("当前 4 项", None),
    ("加「降水」概率 100%", ("降水", "100%")),
    ("加「体感」温度 15°", ("体感", "15°")),
    ("加「风力」3 级", ("风力", "3级")),
    ("加「紫外线」2", ("紫外", "2")),
    ("加「气压」1016", ("气压", "1016")),
]


def render(extra):
    d = dict(SAMPLE)
    d["extra"] = extra
    cv = G.PILCanvas()
    wb_layout.render(cv, F, d)
    return cv.img.resize((1200, 900), Image.NEAREST)   # 与正式预览一致: 3x


strips = []
for name, extra in VARIANTS:
    im = render(extra)
    strips.append((name, im.crop((0, 236 * 3, 1200, 900))))

Z = 1
LAB_W = 330
w = max(s.width for _, s in strips) + LAB_W
h = sum(s.height + 18 for _, s in strips) + 10
out = Image.new("RGB", (w, h), (255, 255, 255))
d = ImageDraw.Draw(out)
try:
    lab = ImageFont.truetype("/System/Library/Fonts/Hiragino Sans GB.ttc", 22, index=1)
except Exception:
    lab = ImageFont.load_default()
y = 6
for name, s in strips:
    d.text((8, y + s.height // 2 - 12), name, font=lab, fill=(0, 0, 0))
    out.paste(s, (LAB_W, y))
    d.line((LAB_W, y) + (LAB_W, y + s.height), fill=(200, 200, 200))
    y += s.height + 18
out.save(os.path.join(HERE, "layout_foot5_compare.png"))
print("compare:", out.size)

# 推荐方案整屏
render(("降水", "100%")).save(os.path.join(HERE, "layout_foot5_full.png"))
print("full ok")
