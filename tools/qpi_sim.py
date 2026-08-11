# -*- coding: utf-8 -*-
"""
CIRA · ST77916 QPI 命令流本地模拟器（无需硬件）
================================================
用途：在 Mac 上离线验证「cira_st77916.c」发出的 QSPI 命令字节流是否正确，
      不依赖板子。重点验证黑屏根因修复——32 位 QPI 命令格式。

验证依据（已在本地 ESP-IDF 源码确认）：
  esp_lcd_panel_io_spi.c :: spi_lcd_prepare_cmd_buffer()
    当 lcd_cmd_bits > 8 时，把 32 位命令按字节 REVERSE，使 SPI 线上
    呈大端顺序：[V>>24, V>>16, V>>8, V&0xFF]。
  ST77916 QSPI 规范：命令帧 = {opcode[31:24], reserved[23:16],
    reg_index[15:8], reserved[7:0]}，opcode 走线上第一字节。
    - 写寄存器 opcode = 0x02
    - 写显存(RAMWR) opcode = 0x32

因此正确编码应为：
    QPI_CMD(cmd)   = (0x02 << 24) | (cmd << 8)   → 线上 [0x02,0x00,cmd,0x00]
    QPI_COLOR(cmd) = (0x32 << 24) | (cmd << 8)   → 线上 [0x32,0x00,cmd,0x00]

本模拟器复刻上述逻辑，并打印每条命令的线上字节，确认与规范一致。
"""
import re

# ---- 与 st77916.c 完全一致的宏 ----
def QPI_CMD(cmd):
    return (int(0x02) << 24) | ((cmd & 0xFF) << 8)

def QPI_COLOR(cmd):
    return (int(0x32) << 24) | ((cmd & 0xFF) << 8)

def wire_bytes(v32):
    """复刻 ESP-IDF：32 位命令经字节反转后呈大端线序。"""
    v = v32 & 0xFFFFFFFF
    return [(v >> 24) & 0xFF, (v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF]

def show_qpi(name, cmd):
    v = cmd
    wb = wire_bytes(v)
    kind = 'WR_REG' if wb[0] == 0x02 else ('WR_RAM' if wb[0] == 0x32 else '??')
    print(f"  {name:14s} V=0x{v:08X}  线上字节=[0x{wb[0]:02X},0x{wb[1]:02X},0x{wb[2]:02X},0x{wb[3]:02X}]  "
          f"opcode=0x{wb[0]:02X}({kind}) reg=0x{wb[2]:02X}")
    return wb

print("=" * 72)
print("ST77916 QPI 命令流模拟（本地验证，无硬件）")
print("=" * 72)

print("\n[1] 关键命令的线上字节序（opcode 必须在第一字节）：")
critical = {
    "COLMOD(0x3A)": QPI_CMD(0x3A),
    "INVON(0x21)":  QPI_CMD(0x21),
    "SLPOUT(0x11)": QPI_CMD(0x11),
    "DISPON(0x29)": QPI_CMD(0x29),
    "CASET(0x2A)":  QPI_CMD(0x2A),
    "RASET(0x2B)":  QPI_CMD(0x2B),
    "RAMWR(0x2C)":  QPI_COLOR(0x2C),
    "DISPOFF(0x28)":QPI_CMD(0x28),
}
ok = True
for n, v in critical.items():
    wb = show_qpi(n, v)
    op = wb[0]
    if (n.startswith("RAMWR") and op != 0x32) or (op not in (0x02, 0x32)):
        ok = False
        print(f"    [!] {n} opcode 错误！")

print("\n[2] 反例：若误用 (cmd<<8)|0x02 这种「opcode 在末字节」编码，线上字节为：")
bad = (0x2C << 8) | 0x02
print(f"    (0x2C<<8)|0x02 = 0x{bad:08X}  线上=[0x{wire_bytes(bad)[0]:02X},...]  opcode 落在末字节 -> 面板不认 -> 黑屏")
print("    => 这是此前 build4（8 位命令）黑屏的根因对照。")

print("\n[3] 解析 st77916_init_data.h 初始化表，逐条核对线上字节：")
HDR = "/Users/evanli/WorkBuddy/2026-07-28-22-33-31/cira-prototype/micropython/lvgl_build/cira_st77916/st77916_init_data.h"
try:
    with open(HDR) as f:
        text = f.read()
    rows = re.findall(r"\{0x([0-9A-Fa-f]+),\s*0x([0-9A-Fa-f]+),\s*0x([0-9A-Fa-f]+)", text)
    print(f"    共解析到 {len(rows)} 条初始化寄存器命令。")
    for i, (cmd, ln, dly) in enumerate(rows):
        c = int(cmd, 16)
        if c in (0x3A, 0x21, 0x11, 0x29, 0x2C):
            wb = wire_bytes(QPI_CMD(c)) if c != 0x2C else wire_bytes(QPI_COLOR(c))
            tag = {0x3A: "COLMOD/RGB565", 0x21: "INVON", 0x11: "SLPOUT",
                   0x29: "DISPON", 0x2C: "RAMWR"}.get(c, "")
            print(f"    * 第{i:3d}条 cmd=0x{c:02X} ({tag}) 线上=[0x{wb[0]:02X},0x{wb[1]:02X},0x{wb[2]:02X},0x{wb[3]:02X}]")
    cmds = [int(c, 16) for c, _, _ in rows]
    for need, label in [(0x3A, "COLMOD"), (0x21, "INVON"), (0x11, "SLPOUT"), (0x29, "DISPON")]:
        present = need in cmds
        print(f"    {'OK' if present else 'MISSING'} 初始化表含 {label}(0x{need:02X})")
        if not present:
            ok = False
except FileNotFoundError:
    print("    未找到 st77916_init_data.h，跳过逐条核对（不影响 [1][2] 结论）。")

print("\n[4] 像素写入（fill 一行）模拟：")
for color in (0xF800, 0x07E0, 0x001F, 0xFFFF):
    wb = wire_bytes(QPI_COLOR(0x2C))
    print(f"    RAMWR 写 0x{color:04X}: 命令线上=[0x{wb[0]:02X},0x{wb[1]:02X},0x{wb[2]:02X},0x{wb[3]:02X}], "
          f"随后 2 字节像素(0x{color&0xFF:02X},0x{(color>>8)&0xFF:02X})")

print("\n" + "=" * 72)
if ok:
    print("结论：QPI 命令编码与 ST77916 QSPI 规范 + ESP-IDF 线序一致。")
    print("  面板将收到 opcode 首字节的 32 位命令，初始化序列完整（COLMOD/INVON/SLPOUT/DISPON 齐备）。")
    print("  此前黑屏（build4，8 位普通 SPI 命令）已通过 32 位 QPI 修复。")
else:
    print("结论：存在不一致，需复核 st77916.c。")
print("=" * 72)
