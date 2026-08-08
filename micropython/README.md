# CIRA Device Runtime — MicroPython 真机验证

> 目标版本: **v0.8.0** (硬件基线 ESP32-S3-Touch-LCD-1.85C-BOX / HW V2)
> 验证策略: 板子已连 Mac (`/dev/cu.usbmodem101`), 经 mpremote 推 MicroPython 脚本真机跑,
> 不覆盖 Thonny 里的 MicroPython 解释器, 安全可逆。ESP-IDF C 固件 (`firmware/`) 留作生产基线。

## 1. 前置条件

1. **释放串口**: 在 Thonny 里点 **Disconnect（断开串口）**，不用退出 Thonny。否则 esptool/mpremote 报 "port is busy"。
2. **WiFi 凭证**: 编辑 `main.py` 顶部 `WIFI_SSID` / `WIFI_PASS`，让板子连到**与本机同一网段**（桥接层跑在本机 `192.168.31.33:8788`）。
3. **板子需含 `websocket` 模块**: 若 `main.py` 报 ImportError，执行
   `mpremote connect /dev/cu.usbmodem101 mip install websocket`
   （`ujson` 标准 MicroPython 已带）

## 2. 在本机起桥接层（二选一）

- **本地 mock（无需模型侧，先验证链路）**:
  ```
  /Users/evanli/.workbuddy/binaries/python/envs/default/bin/python3 tools/mock_bridge.py
  ```
  监听 `ws://0.0.0.0:8788`，返回形状与冻结契约 §2.2 / §3 完全一致。
- **模型侧真实桥接层** (`integration/cira_bridge.py`，需其 engine 代码):
  ```
  cd <模型侧仓库> && python -m integration.cira_bridge   # ws://0.0.0.0:8788
  ```
  接模型侧时，把 `cira_ws.py` 的 `BRIDGE_HOST` 改成运行桥接层的主机 IP。

## 3. 推送并运行

```bash
# 推脚本
mpremote connect /dev/cu.usbmodem101 cp main.py :main.py
mpremote connect /dev/cu.usbmodem101 cp cira_ws.py :cira_ws.py
# 运行 (或 cp 后 reset 自动跑 main.py)
mpremote connect /dev/cu.usbmodem101 run main.py
```

## 4. 当前进度 / 待真机补齐

| 模块 | 状态 | 说明 |
|------|------|------|
| 集成接缝 `cira_ws.py` | ✅ 完成 | WS 客户端, 协议已本地验证 (voice_turn/respond/synthesize/wake_ack/ping) |
| 状态机 `main.py` | ✅ 完成(链路版) | WiFi→桥接层→状态循环, REPL 可见; 显示/音频接好前用打印验证 |
| 屏驱 `cira_display.py` | ⏳ 待写 | ST77916 初始化序列已抽取 (`st77916_init.py`, 181条). **风险点: ST77916 为 QSPI**, 标准 MicroPython 无 QSPI 类, 需 waveshare MP 驱动或降级 ESP-IDF; 真机首验项 |
| 触摸 `cira_touch.py` | ⏳ 待写 | CST816T I2C 0x15, INT GPIO4 |
| 音频 `cira_audio.py` | ⏳ 待写 | ES8311 I2S + PA GPIO15, 解码 base64→播放 |
| 唤醒 | ⏳ 待写 | 触摸唤醒 + 本地"我在。/哎！"预录音频(高优先级打断) |

## 5. 协议（与模型侧桥接层对齐，无需改）

见 `MODULE_INTERFACES.md §4` + 模型侧 `integration/README.md`。
客户端→服务端: `{"action":"voice_turn","input":{"transcript":...},"format":"wav","tts":true}`
服务端→客户端: `{heard, reply, emotion(5值), crisis, packageId, audio(base64), format, durationMs, _ext}`。
