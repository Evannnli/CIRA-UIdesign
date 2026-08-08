# CIRA · 方案 A：编译带 ST77916 驱动的 lv_micropython 固件

本目录是把 LVGL 真正烧进板子所需的**全部构建物料**：

```
micropython/lvgl_build/
├── cira_st77916/            # ST77916 圆屏 QSPI 驱动（MicroPython C 扩展模块）
│   ├── st77916.c            #   自包含 C 驱动（init/blit/on/off/fill/set_nit）
│   ├── st77916_init_data.h  #   181 条初始化寄存器（由 st77916_init.py 自动生成）
│   └── micropython.mk       #   USER_C_MODULES 注册
└── README.md                #   你正在看的：本机构建/烧录步骤
```

> 这是**重活**：要在你本机装 ESP-IDF（约 1.5GB）+ 编译 C 固件。沙盒无法做，全在你 Mac 上跑。
> 编译/运行若报错，把报错原文贴回给 AI，据此改 `st77916.c` 后重编即可（常见坑见末尾）。

---

## 0. 一次性前置

```bash
# 1) 装 esptool + mpremote（已装可跳过）
pip install esptool mpremote

# 2) 装 ESP-IDF —— 版本必须和 lv_micropython 要求的一致！
#    先克隆 lv_micropython，再按其 ports/esp32/README.md 指定的版本装 ESP-IDF。
#    （lv_micropython 通常要求 ESP-IDF v5.0.x / v5.1.x / v5.2.x 中的某一个，
#      不要自己猜，克隆后看 README 写的是哪个就装哪个。）
git clone https://github.com/espressif/esp-idf.git
cd esp-idf && git checkout <lv_micropython 要求的版本> && ./install.sh esp32s3 && . ./export.sh
```

> `install.sh` 后要 `source` 一下把 `IDF_PATH` / 工具链加进当前 shell（每次新开终端都要）。

---

## 1. 取 lv_micropython 源码

```bash
cd ~                              # 随便放，和 cira-prototype 分开
git clone --recursive https://github.com/lvgl/lv_micropython.git
cd lv_micropython
git submodule update --init --recursive lib/lv_bindings
make -C mpy-cross                 # 先编 mpy-cross
```

---

## 2. 把 cira_st77916 接进构建

USER_C_MODULES 指向上面 `cira_st77916/` 目录（用**绝对路径**）：

```bash
export CIRA_ST77916=/abs/path/to/cira-prototype/micropython/lvgl_build/cira_st77916
export ESPIDF=/abs/path/to/esp-idf
export PORT=/dev/cu.usbmodem101
```

> 板子端口确认：`ls /dev/cu.usbmodem*`（插上板子应是 `/dev/cu.usbmodem101`）。

---

## 3. 编译 + 烧录

先**整片备份当前固件**（万一要回退原厂小智）：

```bash
esptool.py --chip esp32s3 --port $PORT --baud 460800 \
  read_flash 0x0 0x1000000 ~/xiaozhi_backup.bin
```

编译并烧录（LVGL 用 16bit RGB565）：

```bash
cd ~/lv_micropython
make -C ports/esp32 BOARD=GENERIC_S3 \
     USER_C_MODULES=$CIRA_ST77916 \
     LV_CFLAGS="-DLV_COLOR_DEPTH=16 -DLV_COLOR_16_SWAP=0" \
     deploy
```

- `BOARD=GENERIC_S3` 是 lv_micropython 的 ESP32-S3 板名；若报错 "no such board"，
  执行 `ls ports/esp32/boards/`，挑带 **S3 + Octal PSRAM** 的那个（如 `ESP32_GENERIC_S3` +
  `BOARD_VARIANT=SPIRAM_OCT`），把命令里的 BOARD/BOARD_VARIANT 换掉。
- `deploy` 会自动 `erase_flash` + 烧录。若只想先出固件不烧，去掉 `deploy` 看是否编过。
- 编译约 5–15 分钟，首次会拉 ESP-IDF 组件。

---

## 4. 推 CIRA 的 Python 文件

lv_micropython 刷好后，板子是「裸 LVGL + 我们的 st77916 模块」，还没有 CIRA 应用。
把 `micropython/` 下这些推上去（**确保 Thonny 已断开释放串口**）：

```bash
MP="mpremote connect $PORT"
# 依赖模块（先推）
$MP fs cp ../cira-prototype/micropython/cira_pins.py        :cira_pins.py
$MP fs cp ../cira-prototype/micropython/cira_expander.py    :cira_expander.py
$MP fs cp ../cira-prototype/micropython/cira_lvgl_display.py :cira_lvgl_display.py
$MP fs cp ../cira-prototype/micropython/cira_lvgl_lifeform.py:cira_lvgl_lifeform.py
$MP fs cp ../cira-prototype/micropython/cira_lvgl_control_center.py :cira_lvgl_control_center.py
# 开机入口：cira_main_lvgl.py 必须推成 :main.py（覆盖会静默失败，先 rm）
$MP fs rm :main.py
$MP fs cp ../cira-prototype/micropython/cira_main_lvgl.py   :main.py
$MP reset
```

---

## 5. 跑探针确认屏点亮

```bash
mpremote connect $PORT run ../cira-prototype/tools/lvgl_hello.py
```

看现象（对照）：

| 现象 | 含义 | 下一步 |
|---|---|---|
| 圆屏显示 `CIRA · LVGL` | 全链路通 🎉 | 直接跳第 6 步切正式运行时 |
| 黑屏，但串口打印 `ST77916 已接入真实 flush`、无报错 | flush 通了但没画出/颜色问题 | 把串口日志贴回 AI（可能 RGB565 字节序） |
| 串口报 `import lvgl 失败` | 固件没编进 LVGL | 重编，确认 lv_micropython 子模块拉全 |
| 串口报 `st77916` 相关 C 错误/卡死 | C 驱动问题 | 把报错贴回 AI 改 `st77916.c` 重编 |
| 屏花屏/错位 | 窗口/方向(MADCTL)不对 | 贴图，AI 调 `madctl` 或字节序 |

---

## 6. 切正式运行时

探针通过后，重启板子即可自动跑 `:main.py`（= `cira_main_lvgl.py`），
即 LVGL 版的星云 + 控制中心。观察顺滑度；不够顺把现象贴回 AI 继续调。

---

## 7. 排错速查

- **`esp_lcd_panel_io.h: No such file`** → ESP-IDF 版本不对 / `ESPIDF` 没设对；确认 `export ESPIDF=...` 且版本匹配 lv_micropython。
- **`MP_DEFINE_CONST_OBJ_TYPE` 未声明** → 你的 lv_micropython 较旧，把 `st77916.c` 里该宏改成旧版
  `MP_DEFINE_CONST_TYPE(st77916_type, MP_QSTR_ST77916, ... make_new ... locals_dict ...);`（贴报错 AI 改）。
- **颜色发白/反了** → 改 `st77916.c` 构造里的 `invert` 默认或 blit 字节序（高低字节对调）。
- **编译 `max_transfer_sz` 超限** → 已做分带，一般不会有；若出现，调 `w*80*2` 系数。
- **屏不亮但命令都过** → TCA9554 复位没释放。确认 `cira_lvgl_display.init_lvgl_display()` 里
  `cira_expander.init()` 在创建显示之前调用（当前代码已是）。

---

## 8. 回退原厂小智

```bash
esptool.py --chip esp32s3 --port $PORT --baud 460800 write_flash -z 0x0 ~/xiaozhi_backup.bin
```
