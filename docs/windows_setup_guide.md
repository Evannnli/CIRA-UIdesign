# CIRA 固件 Windows 开发环境搭建指南

## 前提条件
- Windows 10/11 笔记本
- 约 30 分钟时间
- 约 2GB 磁盘空间

---

## 第一步：安装 ESP-IDF v5.2.2

### 1.1 下载 ESP-IDF Windows 安装器
访问：https://dl.espressif.com/dl/idf-installer/esp-idf-tools-setup-offline-5.2.2.exe
（约 1.5GB，离线安装包，包含所有工具链）

### 1.2 运行安装器
- 双击运行
- 安装路径保持默认（`C:\Espressif`）
- **重要**：勾选 "Git for Windows"（如果没有的话）
- 完成安装

### 1.3 验证安装
打开 **ESP-IDF 5.2 CMD**（开始菜单里找），运行：
```cmd
idf.py --version
```
应该输出 `ESP-IDF v5.2.2`

---

## 第二步：克隆源码

### 2.1 打开 ESP-IDF 5.2 CMD
（开始菜单 → ESP-IDF 5.2 CMD）

### 2.2 克隆 lv_micropython
```cmd
cd C:\
git clone https://github.com/lvgl/lv_micropython.git
cd lv_micropython
git checkout v1.22.0  # 或你之前用的版本
```

### 2.3 复制 C 驱动源码
从 Mac 上复制这些文件到 Windows：
- `cira-prototype/micropython/lvgl_build/cira_st77916/` 整个目录

放到 `C:\lv_micropython\ports\esp32\cira_st77916\`

---

## 第三步：编译固件

### 3.1 进入 ESP32 端口目录
```cmd
cd C:\lv_micropython\ports\esp32
```

### 3.2 设置目标芯片
```cmd
set IDF_TARGET=esp32s3
```

### 3.3 编译
```cmd
idf.py -DUSER_C_MODULES=%cd%\cira_st77916\micropython.cmake -B build build
```
（约 5-10 分钟）

### 3.4 验证编译成功
编译完成后，应该有：
```
build\micropython.bin  (约 2.7MB)
```

---

## 第四步：烧录到板子

### 4.1 连接板子
- 用 USB-C 线连接 ESP32-S3 板子到 Windows 笔记本
- Windows 应该自动识别为 "USB Serial/JTAG" 设备
- 如果没识别，安装驱动：https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers

### 4.2 查找串口号
打开 **设备管理器** → **端口 (COM 和 LPT)** → 找到类似 `COM3` 的端口

### 4.3 烧录
在 ESP-IDF 5.2 CMD 中运行：
```cmd
esptool.py --chip esp32s3 -p COM3 --before default_reset --after hard_reset write_flash @build\flash_args
```
（把 `COM3` 替换成你实际的端口号）

烧录约 30 秒，完成后板子会自动重启。

---

## 第五步：验证显示

### 5.1 连接 REPL
在 ESP-IDF 5.2 CMD 中运行：
```cmd
mpremote connect COM3 repl
```
（按 `Ctrl+]` 退出 REPL）

### 5.2 运行诊断脚本
把 `color_test_diag.py` 复制到 Windows，然后：
```cmd
mpremote connect COM3 run color_test_diag.py
```

**预期结果**：屏幕依次显示红→绿→蓝→白，最后停在白色。

---

## 常见问题

### Q: 编译报错 "IDF_TARGET not set"
A: 确保在 ESP-IDF 5.2 CMD 中运行，不要用普通的 cmd 或 PowerShell

### Q: 烧录报错 "Could not open COM3"
A: 检查设备管理器，确认板子被识别为 COM 端口。如果没有，可能需要安装驱动。

### Q: 屏幕不亮
A: 检查 I2C 扩展器是否正常（运行 `cira_expander.py` 测试）

### Q: 红蓝颜色反了
A: 修改 `cira_pins.py` 中的 `LCD_MADCTL`，加上 `0x08`

---

## 下一步
如果 Windows 上测试成功，我们可以：
1. 把 Windows 作为主要开发环境
2. Mac 上只做代码编辑，不做编译/烧录
3. 或者用 Git 同步代码到 Windows 编译

---

## 附录：关键文件路径
- ESP-IDF: `C:\Espressif\esp-idf\`
- 源码: `C:\lv_micropython\`
- C 驱动: `C:\lv_micropython\ports\esp32\cira_st77916\`
- 编译产物: `C:\lv_micropython\ports\esp32\build\`
