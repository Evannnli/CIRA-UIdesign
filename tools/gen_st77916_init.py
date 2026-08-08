# -*- coding: utf-8 -*-
"""
从 micropython/st77916_init.py 的 ST77916_INIT 列表生成 C 头文件。

ST77916_INIT 每项: (cmd:int, data:bytes, delay_ms:int)
输出 micropython/lvgl_build/cira_st77916/st77916_init_data.h:
  每行 {cmd, len, delay_ms, data[16]} 的定长表，供 st77916.c 直接 #include。
这是把已验证的 QSPI 初始化序列（原 waveshare esp_lcd_st77916.c 抽取）固化进 C 模块，
避免手工抄 185 条寄存器出错。
"""
import importlib.util
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = os.path.join(ROOT, "micropython", "st77916_init.py")
out_dir = os.path.join(ROOT, "micropython", "lvgl_build", "cira_st77916")
out_path = os.path.join(out_dir, "st77916_init_data.h")

spec = importlib.util.spec_from_file_location("st77916_init", src)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
rows = m.ST77916_INIT

lines = []
lines.append("/* AUTO-GENERATED from micropython/st77916_init.py -- DO NOT EDIT */")
lines.append("#ifndef _ST77916_INIT_DATA_H")
lines.append("#define _ST77916_INIT_DATA_H")
lines.append("/* 每行: {cmd, len, delay_ms, data[16]} (data 左对齐, 余 0 填充) */")
lines.append("static const uint8_t st77916_init_tbl[][20] = {")
for cmd, data, delay in rows:
    if isinstance(data, (bytes, bytearray)):
        db = bytes(data)
    else:
        db = data.encode("latin-1")
    L = len(db)
    if L > 16:
        raise ValueError("init cmd 0x%02X data len %d > 16" % (cmd, L))
    hexes = ", ".join("0x%02X" % b for b in db)
    pad = ", ".join(["0x00"] * (16 - L))
    lines.append("    {0x%02X, 0x%02X, 0x%02X, %s, %s},"
                 % (cmd & 0xFF, L & 0xFF, delay & 0xFF, hexes, pad))
lines.append("};")
lines.append("#define ST77916_INIT_N %d" % len(rows))
lines.append("#endif /* _ST77916_INIT_DATA_H */")

os.makedirs(out_dir, exist_ok=True)
with open(out_path, "w") as f:
    f.write("\n".join(lines) + "\n")

print("wrote", out_path, "rows =", len(rows))
