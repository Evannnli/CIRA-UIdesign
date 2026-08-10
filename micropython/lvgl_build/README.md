# CIRA · 方案 A：编译带 ST77916 驱动的 lv_micropython 固件

本目录是真正把 LVGL 烧进板子所需的**全部构建物料**：

```
micropython/lvgl_build/
├── cira_st77916/            # ST77916 圆屏 QSPI 驱动（MicroPython C 扩展模块）
│   ├── st77916.c            #   自包含 C 驱动（init/blit/on/off/fill/set_nit）
│   ├── st77916_init_data.h  #   181 条初始化寄存器（由 st77916_init.py 自动生成）
│   ├── micropython.mk       #   （旧 make 体系用，CMake 构建实际用下面的 .cmake）
│   └── micropython.cmake    #   ★ CMake 构建注册（lv_micropython esp32 端口用这个）
└── README.md                #   你正在看的：本机构建/烧录步骤
```

> 这是**重活**：要装 ESP-IDF（约 1.5GB）+ 编译 C 固件。沙盒无法做，全在 Mac 上跑。
> 编译/运行若报错，把报错原文贴回给 AI，据此改 `st77916.c` 后重编即可（常见坑见末尾）。

---

## 0. 最关键的两个坑（先读，否则必失败）

1. **Python 版本**：ESP-IDF v5.2 只支持 Python **3.8–3.12**。本机 `python3` 默认可能是 3.13
   （WorkBuddy 自带的），会直接被 `python_version_checker.py` 拒掉 → `install.sh`/`make` 立刻退出。
   **解决**：每次构建前先 `export PATH=/usr/bin:/bin:/usr/sbin:/sbin:$PATH`，让 `python3` 指向系统 3.9.6。
   验证：`python3 --version` 必须显示 `Python 3.9.x`。

2. **`USER_C_MODULES` 是 `.cmake` 文件路径，不是目录**（lv_micropython 的 esp32 端口是 CMake 构建，
   不是旧的 make）。指错成目录 → 我们的 C 驱动根本不会被编进固件。

---

## 1. 环境准备（装 ESP-IDF 工具链）

```bash
# 强制系统 Python 3.9.6（见上方坑 1）
export PATH=/usr/bin:/bin:/usr/sbin:/sbin:$PATH
python3 --version        # 必须 3.9.x

export IDF_PATH=/Users/evanli/esp-idf
export ESPIDF=$IDF_PATH

cd $IDF_PATH
./install.sh esp32s3              # 装编译器/ openocd 等到 ~/.espressif（约 1.5GB，几分钟）
. $IDF_PATH/export.sh             # 把 xtensa-esp32s3-elf-gcc 等加进 PATH（每次新终端都要）
```

> `install.sh` 只装工具链，不碰 git 子模块（那些已手动放好）。装完必须 `source export.sh`，
> 否则后面 `make` 找不到交叉编译器。

---

## 2. lv_micropython 源码布局（已就绪，无需再 clone）

源码已在 `~/lv_micropython`，且子模块已就位：
- `~/lv_micropython/user_modules/lv_binding_micropython/` —— LVGL Python 绑定
- `~/lv_micropython/user_modules/lv_binding_micropython/lvgl/` —— LVGL 库本体

（若为空，需补全：`lib/lv_bindings` → `user_modules/lv_binding_micropython`，
其内 `lvgl/` 子目录放 LVGL 源码。）

---

## 3. 把 cira_st77916 接进构建

`USER_C_MODULES` 指向 `micropython.cmake` **文件**（绝对路径）：

```bash
export CIRA_ST77916_CMAKE=/Users/evanli/WorkBuddy/2026-07-28-22-33-31/cira-prototype/micropython/lvgl_build/cira_st77916/micropython.cmake
export PORT=/dev/cu.usbmodem101     # 板子端口（插上板子确认：ls /dev/cu.usbmodem*）
```

---

## 4. 编译 + 烧录

先**整片备份当前固件**（万一要回退原厂小智）：

```bash
esptool.py --chip esp32s3 --port $PORT --baud 460800 \
  read_flash 0x0 0x1000000 ~/xiaozhi_backup.bin
```

编译并烧录。**`LV_CFLAGS` 必须 export 成环境变量**（构建脚本读 `$ENV{LV_CFLAGS}`，
不会从 make 参数读取）：

```bash
cd ~/lv_micropython
export LV_CFLAGS="-DLV_COLOR_DEPTH=16 -DLV_COLOR_16_SWAP=0"   # ★ 关键：export，不是 make 参数
export PATH=/usr/bin:/bin:/usr/sbin:/sbin:$PATH               # ★ 关键：python 锁 3.9.6
. $IDF_PATH/export.sh                                          # ★ 关键：交叉编译器在 PATH

make -C ports/esp32 BOARD=ESP32_GENERIC_S3 BOARD_VARIANT=SPIRAM_OCT \
     USER_C_MODULES=$CIRA_ST77916_CMAKE \
     PORT=$PORT \
     deploy
```

- `BOARD=ESP32_GENERIC_S3` + `BOARD_VARIANT=SPIRAM_OCT`：板子是 ESP32-S3 + Octal PSRAM。
  若报 "no such board"，`ls ports/esp32/boards/` 找带 S3+Octal 的。
- `deploy` = 构建 + 通过 `idf.py` 烧录（不自动 erase 整片；分区表内 erase）。
- 首次编译约 5–20 分钟（CPU 编译 LVGL 体量很大）。
- `LV_COLOR_DEPTH=16` 与板子 RGB565 帧缓冲一致；`LV_COLOR_16_SWAP=0` 关掉字节交换。

---

## 5. 推 CIRA 的 Python 文件

固件刷好后，板子是「裸 LVGL + 我们的 st77916 模块」，还没有 CIRA 应用。
把 `micropython/` 下这些推上去（**确保 Thonny 已断开释放串口**）：

```bash
MP="mpremote connect $PORT"
$MP fs cp /Users/evanli/WorkBuddy/2026-07-28-22-33-31/cira-prototype/micropython/cira_pins.py        :cira_pins.py
$MP fs cp /Users/evanli/WorkBuddy/2026-07-28-22-33-31/cira-prototype/micropython/cira_expander.py    :cira_expander.py
$MP fs cp /Users/evanli/WorkBuddy/2026-07-28-22-33-31/cira-prototype/micropython/cira_lvgl_display.py :cira_lvgl_display.py
$MP fs cp /Users/evanli/WorkBuddy/2026-07-28-22-33-31/cira-prototype/micropython/cira_lvgl_lifeform.py:cira_lvgl_lifeform.py
$MP fs cp /Users/evanli/WorkBuddy/2026-07-28-22-33-31/cira-prototype/micropython/cira_lvgl_control_center.py :cira_lvgl_control_center.py
# 开机入口：cira_main_lvgl.py 必须推成 :main.py（覆盖会静默失败，先 rm）
$MP fs rm :main.py
$MP fs cp /Users/evanli/WorkBuddy/2026-07-28-22-33-31/cira-prototype/micropython/cira_main_lvgl.py   :main.py
$MP reset
```

---

## 6. 跑探针确认屏点亮

```bash
mpremote connect $PORT run /Users/evanli/WorkBuddy/2026-07-28-22-33-31/cira-prototype/tools/lvgl_hello.py
```

| 现象 | 含义 | 下一步 |
|---|---|---|
| 圆屏显示 `CIRA · LVGL` | 全链路通 🎉 | 直接跳第 7 步切正式运行时 |
| 黑屏，但串口打印 `ST77916 已接入真实 flush`、无报错 | flush 通了但没画出/颜色问题 | 把串口日志贴回 AI（可能 RGB565 字节序） |
| 串口报 `import lvgl 失败` | 固件没编进 LVGL | 重编，确认 lv_binding 子模块拉全 |
| 串口报 `st77916` 相关 C 错误/卡死 | C 驱动问题 | 把报错贴回 AI 改 `st77916.c` 重编 |
| 屏花屏/错位 | 窗口/方向(MADCTL)不对 | 贴图，AI 调 `madctl` 或字节序 |

---

## 7. 切正式运行时

探针通过后，重启板子即可自动跑 `:main.py`（= `cira_main_lvgl.py`），
即 LVGL 版的星云 + 控制中心。观察顺滑度；不够顺把现象贴回 AI 继续调。

---

## 8. 排错速查

- **`esp_lcd_panel_io.h: No such file`** → ESP-IDF 版本不对 / `IDF_PATH` 没设对；确认 `export IDF_PATH=...` 且版本匹配 lv_micropython（v5.2.2）。
- **`MP_DEFINE_CONST_OBJ_TYPE` 未声明** → lv_micropython 较旧，把 `st77916.c` 里该宏改成旧版
  `MP_DEFINE_CONST_TYPE(st77916_type, MP_QSTR_ST77916, ... make_new ... locals_dict ...);`（贴报错 AI 改）。
- **颜色发白/反了** → 改 `st77916.c` 构造里的 `invert` 默认或 blit 字节序（高低字节对调）。
- **编译 `max_transfer_sz` 超限** → 已做分带，一般不会有；若出现，调 `w*80*2` 系数。
- **屏不亮但命令都过** → TCA9554 复位没释放。确认 `cira_lvgl_display.init_lvgl_display()` 里
  `cira_expander.init()` 在创建显示之前调用（当前代码已是）。
- **`Python 3.13 not supported` / install.sh 秒退** → 没锁 Python（坑 1）。`export PATH=/usr/bin:$PATH` 重来。
- **`USER_C_MODULES` 目录下找不到模块** → 指成了目录而非 `micropython.cmake` 文件（坑 2）。

---

## 9. 回退原厂小智

```bash
esptool.py --chip esp32s3 --port $PORT --baud 460800 write_flash -z 0x0 ~/xiaozhi_backup.bin
```
