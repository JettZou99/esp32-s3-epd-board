# test_class_data.py —— 外置课表数据的单元级验证(纯 CPython, 不接硬件)
# 覆盖: JSON 校验 / 几何自适应 / 三级兜底 / 热重载 / 缺字自检
# 用法: python tests/test_class_data.py
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MP = os.path.dirname(HERE)
sys.path.insert(0, MP)
import wb_class_layout as L

DATA = os.path.join(MP, "class_data.json")
raw = json.load(open(DATA, encoding="utf-8-sig"))

# 1) 真实数据: 6节5列, 午休行插在第4节后, 网格底恰好 288, 无重复横线
cls = L.normalize_class(raw)
assert cls is not None
assert (cls["nrow"], cls["ncols"], cls["cw"]) == (6, 5, 70), cls
assert cls["break_after"] == 4 and cls["break"] == ["", "体育活动", "", "体育活动", ""]
assert len(cls["ys"]) == 9 and len(set(cls["ys"])) == 9 and cls["ys"][-1] == 288, cls["ys"]
assert [x[0] for x in cls["disp"]] == [0, 1, 2, 3, None, 4, 5], cls["disp"]
assert [x[1] for x in cls["disp"]] == ["1", "2", "3", "4", "-", "5", "6"], cls["disp"]
assert cls["rows"][3][2] == ("艺术", "（音乐）"), "JSON 数组应归一化为两行折行"
print("1) 真实 JSON 解析与几何: PASS")

# 2) 行数/列数变化自动适配, 末行吸收余数
c7 = L.normalize_class({"weekdays": list("一二三四五六日"),
                        "rows": [["语文"] * 7 for _ in range(7)]})
assert c7["cw"] == 50 and c7["ys"][-1] == 288 and c7["break"] is None
c8 = L.normalize_class({"weekdays": ["一", "二", "三", "四", "五"],
                        "rows": [["语文"] * 5 for _ in range(8)],
                        "break_after": 4, "break": ["", "体育活动", "", "", ""]})
assert c8["ys"][-1] == 288 and len(c8["disp"]) == 9
assert c8["disp"][4][0] is None
print("2) 7列7节 / 8节带午休行 自适应: PASS")

# 3) 非法数据一律拒绝(交给兜底), 不静默画歪
bad = [
    {},
    {"rows": []},
    {"rows": [["语文"] * 4]},                       # 列数不足
    {"rows": [["语文"] * 5, ["数学"] * 5, [1] * 5]},  # 非字符串单元格
    {"rows": [["语文"] * 5 for _ in range(9)]},     # 超过 8 节
    {"rows": [["语文"] * 5], "weekdays": "一二三四五"},
]
for b in bad:
    assert L.normalize_class(b) is None, b
print("3) 非法数据拒绝: PASS")

# 4) 文件缺失 / 内容损坏 -> 内嵌 JSON 快照; 连快照也没有 -> 占位课表
L.DEFAULT_CLASS = raw                          # 模拟生成器注入的快照
orig = L.CLASS_FILE
L.CLASS_FILE = "__no_such_class__.json"
L._CLASS = None
c = L.load_class()
assert c["rows"] == cls["rows"] and c["nrow"] == 6, "应使用内嵌快照"
print("4a) 文件缺失 -> 快照兜底: PASS")

tmp = os.path.join(HERE, "__broken_class__.json")
open(tmp, "w", encoding="utf-8").write("{ not json")
L.CLASS_FILE = tmp
L._CLASS = None
c = L.load_class()
assert c["rows"] == cls["rows"], "JSON 损坏也应回退快照"
os.remove(tmp)
print("4b) JSON 损坏 -> 快照兜底: PASS")

L.DEFAULT_CLASS = None
L._CLASS = None
c = L.load_class()
assert c["rows"][0] == ["-"] * 5 and c["break"] is None, "应回退占位课表"
print("4c) 无文件无快照 -> 占位课表: PASS")

# 5) 热重载: 改 JSON 后 get_class(True) 立即拿到新内容
L.DEFAULT_CLASS = raw
L.CLASS_FILE = orig
L._CLASS = None
edited = json.loads(json.dumps(raw))
edited["rows"][0][0] = "班会"
tmplive = os.path.join(HERE, "__live_class__.json")
json.dump(edited, open(tmplive, "w", encoding="utf-8"), ensure_ascii=False)
L.CLASS_FILE = tmplive
c1 = L.get_class(True)
assert c1["rows"][0][0] == "班会", "热重载未生效"
edited["rows"][0][0] = "自习"
json.dump(edited, open(tmplive, "w", encoding="utf-8"), ensure_ascii=False)
c2 = L.get_class(False)
assert c2["rows"][0][0] == "班会", "未 force 时应使用缓存"
c3 = L.get_class(True)
assert c3["rows"][0][0] == "自习", "force 后应重读"
os.remove(tmplive)
L.CLASS_FILE = orig
L._CLASS = None
print("5) 热重载 / 缓存: PASS")

# 6) 字符池自检: 新汉字必须能被检出
chars = {}
chars.update(L.class_chars(c1))
chars.update(L.class_chars(c3))
assert all(ch in chars for ch in ("班", "会", "自", "习", "语", "文", "周", "一", "-"))
fake_font = {ch: 1 for ch in chars if ch not in ("班", "自", "习")}
assert set(L.missing_glyphs(c1, fake_font)) == {"班"}
assert set(L.missing_glyphs(c3, fake_font)) == {"自", "习"}
assert L.missing_glyphs(cls, {ch: 1 for ch in L.class_chars(cls)}) == []
print("6) 字符收集 / 缺字自检: PASS")

print("ALL PASS")
