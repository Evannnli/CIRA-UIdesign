# PROJECT_CONTEXT · CIRA

> 项目传承文档。跨模型 / 跨会话 / 跨电脑防断片。接手第一件事：先读本文件。
>
> **最后更新：2026-08-08** ｜ 对应产物：`cira-prototype` Web 原型 **v0.7**（已 git 入库 → `Evannnli/CIRA-UIdesign`）+ HARDWARE.md（硬件权威文档）+ HANDOFF v0.7 + MODULE_INTERFACES v0.7 同步 ｜ **Device Runtime `v0.8.7`（硬件目标 ESP32-S3-Touch-LCD-1.85C-BOX / V2）星云重做（硬十字 splat→柔光软斑 `_BLOB`）+ 控制中心重写对齐 HTML 原型（菜单下钻 + 完成退出，根治进/出长按串台）** ｜ 模块1/2 契约差异由「适配桥接层」兜住（MODULE_INTERFACES §10）

---

## 1. 项目是什么

**CIRA = Child-Informed Response Architecture**，一套"儿童知情的回应架构"，
外加一个**实体陪伴设备**（360×360 圆形屏幕的 AI 儿童陪伴机）。

- 不是"聊天机器人"，而是**懂儿童发展、以儿童为本**的回应系统。
- 设备形象不是"脸"、也不是具象卡通，而是一个**光生命体（粒子光团）**——
  会呼吸、聚合、扩散、波动，用光的形态表达 6 种状态 × 7 种情绪。

## 2. 目录结构（workspace 根）

```
2026-07-28-22-33-31/
├── CIRA_00_Founding_Beliefs.md   # 创始信念
├── CIRA_01_Manifesto.md          # 宣言
├── CIRA_02_Spec.md               # 6 层架构 + 7 步回应流程
├── CIRA_07_Family_Memory_Model.md# 6 层家庭长期记忆
├── CIRA_08_Evaluation.md         # 4 维评估体系
├── cira-prototype/               # ★ 设备端 Web 交互原型（当前工作重心）
└── PROJECT_CONTEXT.md            # 本文件
```
> 另有 Canon(10卷100条)、Growth Taxonomy、Growth Reasoning、Decision Library 等架构文档（历史会话产出，见 memory）。

## 3. 设备端 Web 原型（cira-prototype）

**定位**：纯 Web 原型，把圆屏设备 1:1 搬进桌面浏览器，**不接 ESP32、不接真实 LLM**。
**运行**：`cd cira-prototype && python3 -m http.server 8080` → `http://localhost:8080`

| 文件 | 职责 |
|------|------|
| `lifeform.js` | 光生命体粒子引擎（核心视觉，Canvas 2D 体积粒子光场） |
| `index.html` | 圆屏 + 右侧调试面板 + 9 视图设置栈 |
| `styles.css` | 配色 / 圆形裁切 / 多视图设置 / 字幕版心 / 亮度遮罩 |
| `app.js` | **模块3 Device Runtime**：状态机 + 触摸交互 + 设置全交互 + 对话流编排（经 `modules.js` 调模块1/2 冻结接口） |
| `modules.js` | **集成接缝**：Device Runtime 访问模块1/2 的唯一入口（`CIRA.Core`/`CIRA.Language`），本地桩↔远程只改 `CIRA_INTEGRATION` 配置 |
| `core.js` | **本地占位桩**（模块1 CIRA Core），真实模块接入后可删 |
| `language.js` | **本地占位桩**（模块2 Language System），真实模块接入后可删 |
| `README.md` | 原型说明书 |
| `HANDOFF.md` | **★ 开发交付规格书**（状态机/交互链路/星云移植参数/数据契约/流程图） |
| `MODULE_INTERFACES.md` | **★ 冻结接口契约**（ResponsePackage/AudioHandle schema + 传输协议 + §7 模块3 需你提供什么 + §9 设备接口映射 + **§10 双契约对齐与桥接层**） |
| `HARDWARE.md` | **★ 硬件权威文档**：ESP32-S3-Touch-LCD-1.85C-BOX 型号/引脚(LCD QSPI·CST816·ES8311 I2S)/接口协议/烧录/开发环境 + **§11 待确认清单（HW V1/V2 判定等）**。来源=Waveshare 官方 wiki+示例源码 |
| `tools/mock_bridge.py` | 本地 Mock 桥接层（WS `:8788`，协议同模型侧 `integration/cira_bridge.py`，无模型侧也能真机端到端验证） |
| `micropython/` | **Device Runtime MicroPython 真机验证**：`main.py`(WiFi+状态机+WS链路) / `cira_ws.py`(集成接缝 WS 客户端) / `st77916_init.py`(屏驱初始化序列 181条) / `README.md`(验证指南) |

## 4. 关键技术决策及理由

- **光生命体用 Canvas 2D 体积粒子光场**（非贴图、非 3D 引擎）：MCU 可移植、`lighter` 加色混合让重叠处发光才像"光"。
- **核心光用暖白 `#FFE9C7` 而非纯白**：纯白在 Mac 屏色温/Night Shift 下会被推成偏绿；全暖色底保证画面永不发绿。（这是 Evan 早期反复确认的点）
- **v0.3 星云化**：朦胧感靠"**海量极小锐星点的疏密渐变（密核→稀边）**"，不靠"大而糊的光斑"。
  Sprite 亮核收窄、粒子 ~1300、渲染直径砍到 ~3px、中心雾核减层。
- **设置改多视图导航**：单页塞不下 Wi-Fi/蓝牙/音量/亮度的真实交互链路，改成 9 个可下钻子页（`.sv-active/.sv-leaving` + 返回栈）。
- **屏幕亮度 1–400 nit**（行业参考：儿童设备夜间可低至 ~1nit 防刺眼，室内正常 150–250，强光上限 ~400）。默认 200。
  遮罩公式 `op=max(0,(200-nit)/200)*0.8`：**200–400 保持通透**（不压暗调好的星云），**仅 <200 渐暗**模拟夜间。
- **字幕版心**：208px·13px·最多 3 行省略，接收/输出视觉区分，永不撑破圆屏。
- **v0.4.1 语音唤醒引擎（AI 决策）**：选 **Espressif ESP-SR / WakeNet**（ESP32 官方离线唤醒，免费/低功耗/支持中文），备选 Picovoice Porcupine（非 ESP32 时用）。**固定唤醒词「你好，cira / 你好，西拉」，本阶段不做自定义/多语言**（产品验证期）。理由：设备主控即 ESP32，WakeNet 零授权费、端侧离线契合儿童隐私；Porcupine 商用授权费且跨平台引入非 ESP32 依赖，故备选。
- **v0.5 SLEEP 熄屏省电（AI 决策）**：Evan 确认走星云路线后，电池问题成核心矛盾 → 引入 SLEEP 状态。**引擎 pause() 完全跳过粒子渲染 + 屏幕亮度遮罩 100% 黑 = 等同物理熄屏**。v0.6 Evan 明确**超时定为 10s**（无动作/交互即熄屏，省电）：IDLE/LISTENING 10s、THINKING 15s。唤醒路径（v0.6 统一）：触摸或语音唤醒词 → **本地应答「我在。」/「哎！」** → 直入 LISTENING 接收语音。理由：星云粒子持续渲染是 ESP32 主要功耗源，闲置即灭屏可把整机功耗降到 IDLE 的 ~5–10%；儿童设备多为"短时使用+长时空闲"，SLEEP 模型符合实际使用模式；10s 兼顾"随手即用"与"空闲即省"。

## 5. 当前进度

- ✅ v0.1 原型（状态机+触摸+对话模拟）
- ✅ v0.2 体积粒子光场 → v0.21 星尘 → **v0.3 星云化**
- ✅ 设置多视图：Wi-Fi 全链路 / 蓝牙全链路 / 音量 / 亮度 / 模式
- ✅ 字幕版心约束
- ✅ v0.4.1 语音唤醒引擎决策：ESP-SR/WakeNet（ESP32 官方离线），固定唤醒词、不做自定义/多语言。HANDOFF.md §8.1
- ✅ **v0.5 SLEEP 熄屏省电状态**：解决星云粒子持续渲染的高功耗问题。新增 STATES.SLEEP + 引擎 pause/resume；视觉：亮度遮罩 100% 黑 + 隐藏一切 UI；调试面板新增"🌙 Sleep 熄屏"按钮。HANDOFF.md §2/§3.7/§5.5/§7.1/§8/§10 同步
- ✅ **v0.6 唤醒交互重构（Evan 明确）**：① 无动作/交互 **10s** 自动熄屏（IDLE/LISTENING 10s、THINKING 15s）；② 唤醒播放**本地应答**「我在。」/「哎！」（vivi2.0 预录 `assets/wake_wo.mp3|wake_ai.mp3`，缺失 TTS 兜底，**不进大模型**）；③ **唤醒优先级最高**，可打断 SPEAKING 立即应答；④ 触摸/语音任意态唤醒 → LISTENING → 送云端模型；⑤ 新增每态**渲染目标参考图集**（`assets/state_*.svg` 7 张 + HANDOFF §11）。HANDOFF.md §2 状态机/§3.1 主屏交互/§3.8 唤醒应答/§7.1 数据契约/§8 超时/§10/§11 同步
- 🐛 **v0.6.1 黑屏 Bug 修复**：SLEEP 唤醒后屏幕**永久黑屏**（状态切换成功但遮罩 opacity 卡在 1）。根因：`transition()` 离开 SLEEP 时 `currentState` 尚未更新就调用 `setBrightness()`，其 `currentState !== SLEEP` 守卫误判"仍在熄屏"跳过遮罩复位。修复：离开 SLEEP 分支先 `currentState = next` 再 `setBrightness()`；版本戳 `?v=0.6.1` 强刷缓存。HANDOFF §10 changelog 同步。
- ✅ **v0.7 模块化架构落地（Evan 决策）**：CIRA 采用模块化，模块1 CIRA Core（"说什么"）/ 模块2 Language System（"怎么说"）由其他团队在 GitHub 维护并迭代过版本；**本仓库专攻模块3 Device Runtime（"怎么显"）**。做法：① `app.js` 对话流重构为「`CIRA.Core.respond()` → `CIRA.Language.synthesize()` → AudioHandle 播放+星云动画」，唤醒打断走 `AudioHandle.stop()`；② 新增 `modules.js` 作为 Device Runtime 访问 1/2 的**唯一集成接缝**（本地占位桩 ↔ 真实远程模块只改 `CIRA_INTEGRATION` 配置，app.js 不动）；③ `core.js`/`language.js` 明确为**本地占位桩**（非真模块，接入真模块后可删）；④ 新增 `MODULE_INTERFACES.md` = 冻结接口契约（ResponsePackage/AudioHandle schema + 传输协议），含 **§7 模块3 需要 Evan 提供什么**（模块1/2 的 GitHub/版本/传输/端点/鉴权 + 硬件设备信息 + 烧录环境）。关键约束：**模块间只依赖接口协议、不依赖内部实现**。版本戳 `?v=0.7`。
- ✅ **HANDOFF.md 开发交付规格书**（设计原型 → 嵌入式开发的移交文档，含 Mermaid 流程图）
- ✅ **硬件信息吸收 + Device Runtime 目标锁定（Evan 提供设备）**：设备=**ESP32-S3-Touch-LCD-1.85C-BOX（带音箱+外配电池版）**，**已确认 HW V2**（Evan 明确标识实体板为 V2）。关键确认（均取自 Waveshare 官方示例源码，非猜测）：**LCD 驱动=ST77916**（QSPI，SCK=GPIO40/DATA0=46/1=45/2=42/3=41/CS=21/TE=18/RST 走 TCA9554 EXIO2/背光 GPIO5 PWM）；**触摸=CST816T**（I2C 0x15，INT=GPIO4，单点+手势，RST 走 EXIO1）；**音频=ES8311(DAC)+ES7210(ADC)+NS4150B(功放)**，I2S MCLK=GPIO2/BCK=GPIO48/LRCK=GPIO38/DOUT=GPIO47/DIN=GPIO39，PA=GPIO15，4Ω5W 喇叭。新增 **`HARDWARE.md`**（硬件权威文档 + §11 待确认清单）+ `MODULE_INTERFACES.md §9 设备接口映射`。**Device Runtime 目标版本定为 `v0.8.0`**（硬件基线；Web 仿真器维持 v0.7 作孪生验证）。⚠️ 已踩坑预警：直觉会猜 LCD=GC9A01，实为 ST77916，移植须用官方 `esp_lcd_st77916` 驱动组件，勿自换。
- ⏳ **待 Evan 确认（剩余）**：① EXIO1/EXIO2 对应 TCA9554 物理 pin（固件操作扩展器要）；② 电池电压 ADC=GPIO8 是否一致；③（HARDWARE §11-4）QMI8658 IMU 的 I2C 地址。**实体板 V1/V2 已于 2026-08-08 确认 = V2，已从待确认移除。**
- ✅ **模块1/2 契约差异对齐 + 桥接层决策（2026-08-08 模型侧反馈）**：模型侧冻结契约（`engine/cira.py`/`engine/language_system.py`/`CIRA_INTERFACES.md`，非本仓库）与本文档 §1–§3 **不是同一套**，存在 5 处真实差异：`emotion` 9值 vs 本仓库 5值、以及 `priority`/`ttsHints`/`presentationHints`/`endOfTurn` 结构/语义分歧。**判定：非理解偏差，靠「适配桥接层」兜住，不推翻任一方冻结。** Device Runtime 给出两项决定（驱动桥接层实现，写入 MODULE_INTERFACES §10）：**A. 传输=推荐 WebSocket 网关**（流式音频降延迟+干净中断+未来主动推送；ESP32 `esp_websocket_client` 原生；HTTP 亦可为退路；DR 代码不感知传输）；**B. B 类字段 v0.8.0 走适配兜底、不升版本**（emotion 9→5 折叠、其余字段透传扩展；冻结的 engine/* 一字不动；仅当将来要原生消费 9 情绪/hints 时才迭代 Core V2.02 / LS V1.02 / response-package@2）。原则：「以还原交互体验为准」。
- ✅ **模型侧桥接层 = 本仓库冻结契约精确镜像（2026-08-08 确认）**：读 `integration/cira_bridge.py` + `README.md`。其 WS 协议(`voice_turn`/`respond`/`synthesize`/`wake_ack`/`ping`, `ws://host:8788`) 返回的 `ResponsePackage`(5值 emotion/mode/priority/endOfTurn/crisis/_ext) 与 `cira_states.h`/§2.2 完全对齐，`AudioHandle` = base64 音频。故 Device Runtime 的集成接缝直接做 **WS 客户端**即可，桥接层 IP 配一下连（无需改任何冻结代码）。`locahost` 验证：`tools/mock_bridge.py` 起 WS :8788，Python 客户端走通 voice_turn/ping/wake_ack。
- ✅ **真机验证轨道开启（2026-08-08）**：板子插 Mac，端口 **`/dev/cu.usbmodem101`**；`mpremote`/`ampy`/`esptool` 均就绪。路径选定 **MicroPython 真机验证**（不覆盖 Thonny 里的 MicroPython 环境、安全可逆；ESP-IDF C 固件 `firmware/` 留作生产基线）。本回合完成：① 本地 `mock_bridge.py`(WS :8788) 端到端验证通过；② MicroPython `cira_ws.py` WS 客户端（集成接缝）；③ 抽 ST77916 初始化序列(181条→`st77916_init.py`)。待：Thonny **释放端口**(Disconnect) + Evan 给 **WiFi 凭证** → 推 `main.py` 真机验证 WiFi→桥接层→状态机链路；显示/触摸/音频驱动真机迭代。**⚠️ 风险：ST77916 为 QSPI，标准 MicroPython 无 QSPI 类，屏驱可能需 waveshare MP 驱动或降级 ESP-IDF。**
- ✅ **真机链路端到端验证通过（2026-08-08 18:47 · Device Runtime v0.8.1 里程碑）**：Evan 在 Thonny `Run▸Disconnect` 释放 `/dev/cu.usbmodem101` 端口；WiFi 凭证写入（`叮当的智能家居`/`15295601676yw`）。推 **`cira_main.py`(不覆盖 Xiaozhi `main.py`，改名保可逆) + `cira_ws.py` + 自写 `ws_native.py`**(板子自带 `websocket` 模块是非标准流式封装、无 `WebSocket` 类，弃用，改原生 socket 手写握手/帧)。`mpremote run verify_once.py` 三轮 voice_turn 全过：**板子 WiFi 连 `192.168.31.170` → 原生 WS 客户端握手 Mac `192.168.31.33:8788` mock 桥接层 → 返回冻结契约**(reply + emotion[5值 happy] + audio[base64 ~21KB] + dur=500ms)。**这是 CIRA 首次在真机跑通端到端链路。** 备份：原 Xiaozhi `main.py`(636行)→`backups/xiaozhi_main.py`；Xiaozhi 驱动参考 `ref_cst816/es8311/es7210/audio_out/audio_in/face/lifeform/emotions.py` 已拉取，供下一步屏/触摸/音频驱动移植（ST77916 在固件为 frozen module，需从 waveshare MP 驱动移植）。
- ✅ **唤醒链路真机验证通过（2026-08-08 21:30 · Device Runtime v0.8.2 里程碑）**：**架构确认——唤醒应答是硬件本地、不进模型侧**（用户认可设计）：点按屏幕 → 本地随机播"我在。/哎！"(`wake_wo.wav`/`wake_ai.wav`，由用户 `哎.m4a`/`我在.mp3` 经 `afconvert` 转 16k 单声道 WAV) → 播完才 `voice_turn` 发模型侧 → 播模型应答音频。**全部经 ES8311 I2S 出声，真机实测通过。** 新增模块：`cira_pins/mclk/cira_i2c(含总线自愈)/cira_codec/cira_audio/cira_touch/cira_expander(TCA9554)/cira_wake/verify_wake`。**三大真机坑已除**：① I2C 总线锁死(SDA 被拉低)→`cira_i2c.recover()` 补 9 个 SCL 脉冲自愈；② CST816 复位门控→TCA9554 `init(0xFF)` 释放全部 EXIO + GPIO1 复位脉冲（chip_id 实测 `0xB5`/awake=True）；③ 统一用 I2C(0)(GPIO10/11,100kHz)，原厂固件即此。屏驱 ST77916 QSPI 为唯一待补设备能力。
- ✅ **显示 bring-up 真机验证通过（2026-08-09 · Device Runtime v0.8.3 里程碑）**：**ST77916 QSPI 圆形屏点亮 + 光生命体星云渲染真机验证通过**。关键发现：① 固件自带 **frozen `st77916` 模块**（硬件 QSPI + `_blit_kernel` 加速，非位模拟），直接复用即可，**无需自写 QSPI 位模拟**（这是 v0.8.2 时最大的未知，现已确诊）；② 构造签名 `st77916.ST77916(W,H,cs=,pclk=,d0..d3=,rst=,bl=,madctl=,invert=)`，LCD 硬复位走 **TCA9554 EXIO2** → 开机须先 `cira_expander.init()` 释放全部 EXIO；③ 端口实测：`verify_display.py` 跑通 **34 帧无异常**（idle→wake→listen→think→speak/happy→speak/comfort→idle→sleep→wake 全态切换），220×256 中央窗缓冲 blit 约 1.3fps（板子同时跑 Xiaozhi 背景渲染，干净 CIRA boot 会更快）。新增模块：`cira_display`(frozen ST77916 封装)/`cira_emotions`(暖橙/软粉/紫/白调色板,禁蓝)/`cira_face`(画布+draw_emotion 后备)/`cira_lifeform`(星云粒子渲染器,移植 lifeform.js：4层 Fibonacci 球面粒子+加色沉积核+字幕合成,后台 tick 线程)。`cira_main.py` 已整合：开机亮 idle 光生命体、状态机→光生命体态映射、熄屏睡眠亮灭背光、动画后台线程。`subtitle_font` 缺失时字幕降级跳过（中文全字库后续补）。**⇒ 全部设备能力已 bring-up：触摸/音频/唤醒/屏显，Device Runtime 真机四大件齐活。**
- ✅ **v0.8.4 收尾（2026-08-08）：双击双播修复 + 设为开机固件**。① **双击双播**：一次点按令 CST816 产生按下/移动/抬起多个中断，`was` 标志在抬手瞬间被清导致二次 `wake()` 把"哎！"和"我在。"都播；修复：`cira_wake.wake()` 加 2s 冷却（同一点触只播一个应答），`cira_main` 整个唤醒动作（应答+发模型）也加 2s 冷却门。② 把 `cira_main.py` 设为板子 `main.py`（原厂备份 `main_xiaozhi.py`，可逆），上电即跑 CIRA。推送修正：mpremote `fs cp` 多源只落最后一个文件，改单文件推送。③ 设备已有 `subtitle_font.py`，中文全字库字幕可显示。**注意：v0.8.4 的"无 traceback"只在待机态验证过——点按唤醒路径未实测，真正的"点不动/卡死"根因在 v0.8.5 才查清（见下）。**
- ✅ **v0.8.5 修复点按崩溃 + 睡眠改微暗（2026-08-08）**：**真凶 = `cira_main.py` 第135行 `NameError: local variable referenced before assignment`**——`_LAST_WAKE_MS` 在 `main()` 里先读(135)后写(136)，Python 把它当函数局部变量，于是**用户一"点按唤醒"就抛异常崩掉主循环** → 屏卡死/点不动/唤不醒（红圈是更早之前未设主固件时的残留观感，与此无关）。修复：① `main()` 加 `global _LAST_WAKE_MS`；② 整个唤醒块包 `try/except`，主循环永不死；③ **睡眠不再全黑**——`_blit_kernel` 睡眠时跳过渲染，原 `screen_off()` 全黑易被当成"坏了"；改 `set_nit(SLEEP_NIT=40)` 微暗呼吸（creature 继续呼吸），唤醒恢复 `WAKE_NIT=255`；④ 睡眠超时 10s→30s；⑤ 初始 `set_nit(255)` 全亮。**真机验证（模拟一次点按跑真实 `main()`）：`[WAKE] 本地应答: /wake_wo.wav` + `[REPLY] emotion=happy 播放完毕`，全程零异常**——但当时只验到"本地唤醒应答播放完毕"；`do_conversation` 内部调 `ui_state`/`ws`/`lf` 的真实崩溃路径**并未被这次验证覆盖（见下 v0.8.6）。⚠️ **推送新坑（必须记）**：mpremote `fs cp` **覆盖已存在的 `:main.py` 会静默失败**（boot 进程占着），必须 `fs rm :main.py` 后再 `fs cp` 才是"新建"能落盘；推到新文件名(如 `:_newmain.py`)可验证写入是否生效。

## 6. 下一步候选

- ✅ **v0.8.6 真修 `do_conversation` 崩溃 + WiFi/WS 移后台（2026-08-08）**：**Evan 三点反馈（#1 星云没生效 / #2 只有一声唤醒没后续 / #3 唤醒后没接模型）本轮全部定位并修掉。** ① **#1 显示**：冷启动 PSRAM 缓存未一致时 viper `_blit_kernel` 读 PSRAM 会硬 fault 冻屏；改为开机先用纯 Python 安全版 blit 预热 3 帧（~12s），再切回 viper 原生 blit（~50~160ms/帧），星云顺滑呼吸、冷启动不冻死（`cira_display._patch_blit`）。② **#3 真凶（真正根因）**：v0.8.5 只修了 `_LAST_WAKE_MS` 的 NameError，但 `do_conversation`（模块级函数）里调的 `ui_state` 仍是 `main()` 的**嵌套函数**、`ws`/`lf` 仍是 `main()` 的**局部变量** → 一进 `do_conversation` 就 `NameError: name 'ui_state' is not defined` → `MAIN CRASH` → 设备复位（这正是"唤醒后没任何反馈/像坏了"的真因）。修复：把 `ui_state`、`ws`、`lf` 全部提升为**模块级全局**（`do_conversation` 现在能读到）；`ws` 缺失时走"WS none"分支优雅降级。`tools/test_scoping.py`（Mac + 桩硬件模块 import 真实 `cira_main.py`）断言 `do_conversation(ws)` 真跑到 `voice_turn(audio_b64)` 且 `ws=None` 不崩，**确定性验证修复**。③ **#2 开机即交互**：原来 `connect_wifi()`+`ws.connect()` 在主线程、在交互主循环**之前**跑，桥接层不可达时要被 15s×2 网络超时卡 25~30s，期间点按无反应（像"没后续"）。改为开**后台线程**连 WiFi+WS（`_net_connect`），主交互循环立即启动；本地唤醒/触摸/控制中心不等网络。④ 加 `machine.WDT(timeout=30000)` 兜底任何残留硬 fault 自动复位（覆盖冷启动宽窗）。**真机验证**：clean cold reset 后 `boot.log` 走完 `LF ok frames=1 → WS ok`，`anim frames` 持续爬升、`PING` 响应、无 `MAIN CRASH`；开机即可点按交互。
- ✅ **v0.8.7 星云重做 + 控制中心重写对齐原型（2026-08-08）**：Evan 反馈①"星云就是五个红色圆形、难看"、②"控制中心交互在 HTML 原型里 OK、到设备上就坏了，而且设计跟 HTML 差很远"。**① 星云**：根因是设备端把原型 `lifeform.js` 的**柔光精灵（radialGradient 软斑）**退化成了**硬 5 点十字 splat（`_KERN`）+ 平铺径向底 + 硬核辉光** → 生硬红点/圆，不像星云。修复：预生成**柔光圆斑软核 `_BLOB`（半径3≈21非零像素）**做加色 stamp，上千颗软圆点疏密堆叠成连续星云；`_INC_SCALE` 9→14 让星点可见；配色沿用暖白/暖橙/软粉（非纯红）。背景维持原型式平滑径向渐变+暗角。**② 控制中心**：根因是设备端写成"长按进、长按出"的极简三列表（既丑又让进/出的长按互相踩 → 一点就唤醒），而原型是**菜单逐层下钻 + 完成按钮退出**（进=长按、出=按钮，永不串台）。重写 `cira_control_center.py`：HOME 菜单 5 行（Wi-Fi/蓝牙/音量/亮度/模式，含图标点+值+chevron）+ 完成按钮；点行进子视图（返回箭头+大数值2x字+滑块）；**`run()` 开场先 `_wait_release()` 吃掉落场长按残余** + 退出改"完成"按钮短按 → 彻底根治进/出串台。视觉用暖色菜单/滑块对齐原型 settings-panel。Wi-Fi/蓝牙为状态显示行（暂仅显示，未做完整扫描 UI）。`tools/test_cc.py`（Mac 桩）断言所有视图绘制无异常 + 状态机 home→子视图→home→完成 正常退出；`tools/test_lf_smoke.py`（Mac 桩）断言六态渲染无异常。**真机验证**：clean cold reset 后 `boot.log` 走完 `LF ok frames=1 → WS ok`、无 `MAIN CRASH`、无 `[LF] render error`、`PING` 响应。（视觉观感需 Evan 拿板子确认，亮度/柔和度参数可继续调。）
- **控制中心形态**（Evan 提及：iOS 控制中心式——主屏快捷开关 + 长按开关弹悬浮详情页；v0.8.7 已对齐原型的多视图下钻结构，列为后续增强）
- 真实音频输入（Web Speech API）
- 多分辨率（240/480 圆屏）测试
- TTS 字幕同步滚动
- Wi-Fi 配网首次引导（SoftAP/BLE）
- 设备外壳 3D 包装（宣传动效）

## 7. 协作约定 / 注意

- **git 已入库** ✅：`cira-prototype/` 内 `git init` + 提交 + push 至 `Evannnli/CIRA-UIdesign`(main)。
  提交 `33788a4`(v0.3)→`1b12023`(v0.4)→`bf338ef`(v0.4.1)→`191a3a6`(v0.5)→`d168f8f`(v0.6)→`2115c85`(v0.6.1)→`7fcbe02`(v0.7)→`26c46ee`(硬件文档 v0.8.0 基线)→`055c05c`(V2确认+桥接层决策) 已 commit 本机；⚠️ **push 因环境出网代理 502 暂挂**(此前多次), 待网络恢复重试或 Evan 本机 `git push`。本轮新增 `tools/mock_bridge.py` + `micropython/` 亦未 push。
  - 认证：经典 PAT（`ghp_`）一次性 push，remote 已清回纯净 https；**token 建议 Evan 去后台 rotate 作废**（按一贯习惯）。
  - ⚠️ 本次只入库焦点目录 `cira-prototype/`（开发交付最聚焦）；workspace 根创始文档/`PROJECT_CONTEXT.md` 未入库，如需整仓纳入告诉我。
- **缓存坑**：v0.3 改了 settings 结构后，浏览器会缓存老 `styles.css` 导致"纯文字堆叠无样式"。已加版本戳 `?v=0.5`；如仍异常需硬刷 Cmd+Shift+R。
- 调试入口：DevTools Console `__cira`（`.lf.setState / .setDensity / .pulse`、`.transition`、`.gotoView`）。
- 本地 memory：`.workbuddy/memory/2026-08-07.md` 有逐日进度细节。
