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
| 集成接缝 `cira_ws.py` | ✅ 真机验证通过 | WS 客户端, 协议本地+mock **真机均验证** (voice_turn/respond/synthesize/wake_ack/ping); 底层 `websocket` 模块非标准(无 WebSocket 类)已弃用, 改 `ws_native.py`(原生 socket 手写握手/帧) |
| 状态机 `main.py` | ✅ 真机验证通过 | 2026-08-08 板子连 WiFi(192.168.31.170)→握手 mock(192.168.31.33:8788)→三轮 voice_turn 全过, REPL 可见完整链路; 显示/音频接好前用打印验证 |
| 屏驱 `cira_display.py` | ⏳ 待写 | ST77916 初始化序列已抽取 (`st77916_init.py`, 181条). **风险点: ST77916 为 QSPI**, 标准 MicroPython 无 QSPI 类; 固件里屏驱是 frozen module (无 st77916.py 文件); 需从 waveshare MP 驱动移植. **Xiaozhi 参考已拉: `ref_face.py`/`ref_lifeform.py`/`ref_emotions.py`** |
| 触摸 `cira_touch.py` | ⏳ 待写(有参考) | CST816T I2C 0x15, INT GPIO4; **参考 `ref_cst816.py` 已拉** |
| 音频 `cira_audio.py` | ⏳ 待写(有参考) | ES8311 I2S + PA GPIO15, 解码 base64→播放; **参考 `ref_es8311.py`/`ref_es7210.py`/`ref_audio_out.py`/`ref_audio_in.py` 已拉** |
| 唤醒 | ⏳ 待写 | 触摸唤醒 + 本地"我在。/哎！"预录音频(高优先级打断) |

## 5. 协议（与模型侧桥接层对齐，无需改）

见 `MODULE_INTERFACES.md §4` + 模型侧 `integration/README.md`。
客户端→服务端: `{"action":"voice_turn","input":{"transcript":...},"format":"wav","tts":true}`
服务端→客户端: `{heard, reply, emotion(5值), crisis, packageId, audio(base64), format, durationMs, _ext}`。

## 6. 真机验证记录（2026-08-08 · v0.8.1 里程碑）

**环境**：板子 ESP32-S3-Touch-LCD-1.85C-BOX (V2) 插 Mac，端口 `/dev/cu.usbmodem101`；
Thonny `Run▸Disconnect` 释放端口；WiFi `叮当的智能家居`/`15295601676yw`。
板子自带 **完整 Xiaozhi AI 固件**（flash 里有 main.py/cst816.py/es8311.py/face.py 等全套），
故 CIRA 文件**改名推送不覆盖原 main.py**（可逆，想回 Xiaozhi 只需重烧/不跑 cira_main）。

**推送**（改名避免破坏 Xiaozhi）：
```bash
mpremote connect /dev/cu.usbmodem101 cp main.py        :cira_main.py
mpremote connect /dev/cu.usbmodem101 cp cira_ws.py     :cira_ws.py
mpremote connect /dev/cu.usbmodem101 cp ws_native.py   :ws_native.py
mpremote connect /dev/cu.usbmodem101 run verify_once.py   # 有限轮次, 跑完即退
```

**结果**（verify_once.py 三轮 voice_turn 全过）：
```
WiFi OK: 192.168.31.170
[V] 桥接层已连接
TURN 0 | reply=太棒啦！我们再来画一只小兔子好不好？ | emotion=happy | audio_len=21392 | dur=500
TURN 1 | ... happy | audio_len=21392
TURN 2 | ... happy | audio_len=21392
```
→ 板子 WiFi → 原生 WS 客户端 → Mac mock 桥接层(:8788) → 冻结契约(含 base64 音频) 全链路通。
**这是 CIRA 第一次在真机跑通端到端链路。**

**踩坑**：板子自带 `websocket` 模块是非标准流式封装（无 `WebSocket` 类），弃用，
改 `ws_native.py`（原生 socket 手写 WS 握手+帧，client 掩码，支持 text/ping/pong/close）。

**下一步**（驱动参考已从 Xiaozhi 拉到 `backups/ref_*.py`）：
1. 屏驱 ST77916 QSPI（frozen module，需从 waveshare MP 驱动移植）
2. 触摸 CST816T（ref_cst816.py）
3. 音频 ES8311（ref_es8311/es7210/audio_out.py）
4. 唤醒：触摸+本地预录音频高优先级打断
