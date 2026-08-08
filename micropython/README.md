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
| 屏驱 `cira_display.py` | ✅ 真机验证通过 | **复用固件 frozen `st77916` 模块**（硬件 QSPI + `_blit_kernel` 加速，非位模拟）。构造 `st77916.ST77916(W,H,cs=,pclk=,d0..d3=,rst=,bl=,madctl=,invert=)`；LCD 硬复位走 **TCA9554 EXIO2** → 开机须先 `cira_expander.init()` 释放全部 EXIO。封装 `init_display()/screen_on/off()/fill()/set_nit()` |
| 光生命体 `cira_lifeform.py` | ✅ 真机验证通过 | 星云粒子渲染器（移植 lifeform.js）：4 层 Fibonacci 球面粒子 + 加色沉积核 + 字幕合成进 220×256 中央窗缓冲，每帧一次 `blit` 刷屏。后台 `tick()` 线程按 ~1.3–4fps 呼吸。状态态 idle/wake/listen/think/speak 映射情绪色（暖橙/软粉/紫/暖白） |
| 表情后备 `cira_face.py`+`cira_emotions.py` | ✅ 就绪 | 画布抽象 + `draw_emotion()` 静态情绪脸（旧脸模型后备）；`cira_emotions` 提供暖橙/软粉/紫/白调色板（禁高饱和蓝，对齐 Evan 视觉方向）。`subtitle_font` 缺失时字幕降级跳过 |
| 触摸 `cira_touch.py` | ✅ 真机验证通过 | CST816T I2C(0) 0x15, chip_id=0xB5, INT GPIO4, RST=GPIO1; **关键坑: 总线易锁死(SDA 被拉低)→ `cira_i2c.recover()` 补 9 个 SCL 脉冲自愈 + TCA9554 全部 EXIO 拉高释放复位** |
| TCA9554 扩展 `cira_expander.py` | ✅ 真机验证通过 | 0x20, 释放 CST816 RST(EXIO1)/LCD RST(EXIO2); 上电默认全输入(等效复位态), 必须开机 `init(0xFF)` |
| 音频 `cira_audio.py` | ✅ 真机验证通过 | ES8311 I2S1(TX) + PA GPIO15 + MCLK PWM GPIO2(4.096MHz); 16k 16bit 单声道 WAV 直喂 I2S; 防音爆铁律: 功放 warmup 只开一次常开, 出声靠 DAC 静音位切换 |
| 唤醒 `cira_wake.py` + `verify_wake.py` | ✅ 真机验证通过 | **硬件本地唤醒**: 点按→随机播"我在。/哎！"(`wake_wo.wav`/`wake_ai.wav`, 由用户 m4a/mp3 经 afconvert 转 16k 单声道 WAV)→ 不进模型; 播完才 `voice_turn` 发模型侧. 全链路: 本地唤醒音频 + 模型应答音频均经 ES8311 出声 |

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

## 7. 真机验证记录（2026-08-08 晚 · v0.8.2 唤醒里程碑）

**新增文件**：`cira_pins.py`(引脚) / `mclk.py`(MCLK PWM) / `cira_i2c.py`(共享 I2C0+总线自愈) /
`cira_codec.py`(ES8311) / `cira_audio.py`(播放) / `cira_touch.py`(CST816) / `cira_expander.py`(TCA9554) /
`cira_wake.py`(本地唤醒) / `verify_wake.py`(验证) / `wake_wo.wav`+`wake_ai.wav`(用户预录应答, 转 16k 单声道 WAV)。

**关键坑 & 修复**：
1. **唤醒应答是硬件本地、不进模型**（用户确认的设计）：点按→本地随机播"我在。/哎！"→
   才发 `voice_turn` 给模型侧。延迟≈0 且能打断 SPEAKING。
2. **I2C 总线锁死**：CST816/ES8311 偶发传完不释放 SDA → 后续事务 `ENODEV`。修复：
   `cira_i2c.recover()` 补 9 个 SCL 脉冲自愈 + 重建 I2C，驱动读写重试里调用。
3. **CST816 复位门控**：TCA9554(0x20) 上电默认全 EXIO 输入（等效复位态），必须
   `init(0xFF)` 把全部 EXIO 设输出高释放；且 CST816 RST 走 GPIO1 需复位脉冲。
4. **I2C 总线选 I2C(0)**（GPIO10/11, 100kHz），原厂固件统一用 I2C(0)；CST816 仅在此稳定应答。
5. **音频格式**：用户 `哎.m4a`/`我在.mp3` 经 macOS `afconvert -f WAVE -d LEI16@16000 -c 1`
   转 16k 单声道 16bit WAV，与 ES8311 I2S 播放路径一致（剥 44 字节头直喂 I2S）。

**结果**（verify_wake.py / cira_main.py 实测）：
```
[AUDIO] warmup 完成 (功放已上电)
[TOUCH] chip_id=0xB5 awake=True
WiFi OK: 192.168.31.170
[WS] 桥接层已连接
[AUTO DEMO] 自动触发唤醒
[WAKE 1] 播放本地应答: /wake_ai.wav      ← 本地"哎！"播出
[REPLY 1] emotion=happy 音频播放完毕 (len=16044)   ← 模型应答也播出了
```
→ **CIRA 首次真机跑通"硬件本地唤醒音频 + 模型应答音频"全链路**（ES8311 出声, CST816 触摸可唤醒）。

**下一步**：屏驱 ST77916 QSPI（唯一待补设备能力；显示/星云 UI 待移植 `ref_*`）。

## 8. 真机验证记录（2026-08-09 晚 · v0.8.3 显示里程碑）

**核心发现**：板子固件自带 **frozen `st77916` 模块**（硬件 QSPI + `_blit_kernel`/`_solid_kernel` C 加速），
**不是**位模拟驱动。直接 `import st77916; st77916.ST77916(W,H,cs=,pclk=,d0..d3=,rst=,bl=,madctl=,invert=)`
即可点亮 360×360 圆屏。省去了 v0.8.2 时最大的未知（自写 QSPI 位模拟）。
⚠️ **LCD 硬复位走 TCA9554 EXIO2**（非 GPIO3 占位脚）：必须在构造前 `cira_expander.init()` 把全部 EXIO 设输出高，
否则面板被压在复位态、初始化失败。

**新增文件**：`cira_display.py`(frozen ST77916 封装) / `cira_emotions.py`(暖调色板) /
`cira_face.py`(画布+draw_emotion) / `cira_lifeform.py`(星云渲染器) / `verify_display.py`(显示验证) /
`cira_pins.py` 补 LCD 引脚。

**结果**（verify_display.py 实测，34 帧无异常）：
```
=== verify_display v0.8.3 ===
[DISP] canvas 360x360 particles=252
[LF] frame 1 state=idle emotion=calm
[LF] frame 21 state=think emotion=thinking
[DEMO] wake / listen / think / speak(happy) / speak(comfort) / idle / sleep / wake
=== verify_display OK frames=34 err=None ===
```
→ **CIRA 首次真机点亮 ST77916 + 渲染光生命体星云**，全态切换、熄屏/亮屏正常。
`cira_main.py` 已整合：开机亮 idle 光生命体、状态机→光生命体态映射、睡眠熄屏、动画后台线程。
（本验证在 Xiaozhi 背景固件同时运行下测得 ~1.3fps；干净 CIRA boot 单渲染会更快。）

**可选收尾**：把 `cira_main.py` 设为板子 `main.py`（先 `fs mv main.py main_xiaozhi.py` 备份原固件）
即成设备主固件，通电即 CIRA。回退：`fs mv main_xiaozhi.py main.py`。
**待补**：中文全字库字幕字体（`subtitle_font`），当前中文字幕降级跳过。

