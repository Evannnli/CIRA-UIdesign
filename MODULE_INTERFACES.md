# CIRA 模块接口冻结规格 (Frozen Module Interfaces)

> 版本：**v0.7** ｜ 日期：2026-08-08 ｜ 阶段：**接口冻结优先**（模块内部可后补，接口不可改）
> 适用：CIRA 圆形屏 AI 陪伴设备 — 硬件目标 **ESP32-S3-Touch-LCD-1.85C-BOX**（360×360 圆 LCD，ESP32-S3R8 + 8MB PSRAM）｜ **Device Runtime 目标版本 `v0.8.0`**（硬件基线，见 `HARDWARE.md`）
> 配套：`cira-prototype/`（参考实现：模块 3 Device Runtime 真实逻辑 + 模块 1/2 的**本地占位桩**。`core.js`/`language.js` 仅为离线跑原型用；模块 1/2 的真实实现由其他团队在 GitHub 维护，接入时直接替换占位桩即可，app.js 不变）；`HARDWARE.md`（**硬件权威文档**：型号/引脚/接口协议/烧录/待确认项）

---

## 0. 架构与冻结标准

```
┌─────────────┐      ResponsePackage       ┌────────────────┐     AudioHandle     ┌────────────────┐
│  CIRA Core  │ ────────────────────────▶ │ Language System│ ───────────────────▶ │ Device Runtime │
│ 「What to   │   (模块1, 云端/端侧)        │ 「How to say」  │  (模块2, 云端/端侧)   │ 「How to show」 │
│   say」     │                            │                │                     │  (模块3, 设备)  │
└─────────────┘                            └────────────────┘                     └────────────────┘
      ▲                                       ▲                                       │
      │  UserInput(transcript)                │  ResponsePackage                      │ 状态/音频/情绪 → 硬件表现
      └───────────────────────────────────────┴───────────────────────────────────────┘
                                          Device Runtime 作为编排层, 调用 1 与 2
```

- **CIRA Core**：负责"说什么"——对话/人设/推理，输出 **Response Package**。
- **Language System**：负责"怎么说"——输入 Response Package，输出 **Audio**（音频句柄/流）。
- **Device Runtime**：负责"怎么显"——输入状态、音频、情绪参数，实现硬件表现（星云渲染、亮度、音频播放、触摸/语音唤醒）。**本模块当前由本仓库负责开发（含硬件装机）。**
- **依赖规则**：任何模块**只依赖接口协议**，不得依赖其他模块内部实现。
- **冻结标准**：当某模块能通过稳定的输入/输出协议被其他模块调用，即认为该模块达到可集成状态。模块 1、2 的**接口**已冻结（schema 见 §1.3 / §2.2）；本仓库用本地占位桩满足「可调用」标准，真实实现由其他团队在 GitHub 维护并替换占位桩即可。模块 3（Device Runtime）的"被调用契约"即下方三套接口。

---

## 1. 模块 1 — CIRA Core（接口已冻结）

**职责**：接收用户话语（ASR 文本）→ 产出 `ResponsePackage`。

### 1.1 调用接口（冻结）
```
CIRACore.respond(input: UserInput) -> Promise<ResponsePackage>
```

### 1.2 UserInput schema（冻结）
| 字段 | 类型 | 说明 |
|------|------|------|
| transcript | string | ASR 识别出的用户话语文本（由设备端 ASR 或模块外提供） |
| sessionId | string? | 会话 ID，用于多轮上下文 |
| locale | string? | 语言区域，默认 `zh-CN` |

### 1.3 ResponsePackage schema（冻结 · 跨模块唯一契约对象）
| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| packageId | string | ✓ | 唯一包 ID |
| text | string | ✓ | 要表达的自然语言内容 |
| emotion | enum | ✓ | `calm`/`curious`/`thinking`/`happy`/`worried` |
| mode | enum? | | `normal`/`quiet`/`story` |
| priority | enum? | | `normal`/`interrupt`（唤醒打断语义） |
| ttsHints | object? | | 给模块 2 的发声建议：`rate`/`pitch`/`voice`/`style` |
| presentationHints | object? | | 给模块 3 的呈现提示，如 `{pulse:true}` |
| endOfTurn | bool? | | 是否本轮最后一句 |

> 唤醒本地应答「我在。」/「哎！」**不属本模块**（不进大模型），由 Device Runtime 本地播放。

---

## 2. 模块 2 — Language System（接口已冻结）

**职责**：输入 `ResponsePackage` → 输出 `AudioHandle`。

### 2.1 调用接口（冻结）
```
LanguageSystem.synthesize(pkg: ResponsePackage) -> Promise<AudioHandle>
```

### 2.2 AudioHandle schema（冻结）
| 方法 | 签名 | 说明 |
|------|------|------|
| play | `() => void` | 开始播放 |
| stop | `() => void` | 立即停止（用于唤醒打断当前播报） |
| onEnd | `(cb: () => void) => void` | 播放结束或被打断时回调 |
| durationMs | `number?` | 预估时长（ms），可选 |

---

## 3. 模块 3 — Device Runtime（本仓库负责 · 输入契约）

**职责**：状态机编排 + 星云渲染 + 亮度 + 音频播放协调 + 触摸/语音唤醒。
**它消费（仅依赖接口，不依赖实现）**：
- `CIRACore.respond(input)` → `ResponsePackage`
- `LanguageSystem.synthesize(pkg)` → `AudioHandle`

**它对外暴露的"被调用契约"（即硬件表现层输入）**：
| 输入 | 类型 | 来源 | 说明 |
|------|------|------|------|
| 状态 | enum | 内部状态机 | `idle`/`listening`/`thinking`/`speaking`/`settings`/`offline`/`sleep` |
| 情绪 | enum | 来自 `ResponsePackage.emotion` | 驱动星云形态 |
| 音频 | AudioHandle | 来自 `LanguageSystem` | 播放 + 同步口型/音频电平动画 |
| 唤醒 | 事件 | 触摸/唤醒词 | 本地应答（不进大模型）→ LISTENING |

---

## 4. 传输协议（Transport · 冻结建议）

接口在**逻辑层**已冻结（上述函数签名 + schema）。为达到"跨进程/跨机器可集成"，推荐传输绑定为：

- **进程内（原型期）**：JS 模块直接调用 `window.CIRACore` / `window.LanguageSystem`（本仓库 `core.js`/`language.js` 即为 Mock 适配器）。
- **分布式（生产期）**：WebSocket + JSON 消息，消息类型：
  - `Device → Core`：`{type:"user_input", transcript, sessionId, locale}`
  - `Core → Device`：`{type:"response_package", ...ResponsePackage}`
  - `Device → Language`：`{type:"synthesize", pkg: ResponsePackage}`
  - `Language → Device`：`{type:"audio_handle", durationMs, streamRef}`（音频流或句柄引用）
  - 打断：`{type:"interrupt"}` → Device 调 `AudioHandle.stop()`
- **替换规则**：模块 1/2 的真实实现只需提供同签名接口（或同消息处理），Device Runtime **无需改动**。

---

## 5. 冻结状态

| 模块 | 接口 | 状态 | 当前实现 |
|------|------|------|----------|
| 1 CIRA Core | `respond → ResponsePackage` | ✅ 冻结/可集成 | Mock（`core.js`） |
| 2 Language System | `synthesize → AudioHandle` | ✅ 冻结/可集成 | Mock（`language.js`，Web Speech） |
| 3 Device Runtime | 状态/情绪/音频/唤醒输入契约 | 🚧 开发中（本仓库） | 真实逻辑（`app.js`/`lifeform.js`）+ 待硬件装机 |

---

## 6. 给其他模块开发者的接入说明

1. 取本文件作为契约权威来源（schema 不可改，新增字段向后兼容）。
2. 实现模块 1：提供一个 `respond(input)` 返回符合 §1.3 的 `ResponsePackage`。
3. 实现模块 2：提供一个 `synthesize(pkg)` 返回符合 §2.2 的 `AudioHandle`。
4. 替换本仓库 `core.js` / `language.js` 中的本地占位桩即可，`app.js`（Device Runtime）保持不变。
5. 分布式部署时按 §4 实现 WebSocket 消息处理；本仓库 `modules.js` 已内置 WS 客户端示例，通常无需改动。

---

## 7. Device Runtime（模块3）需要你提供什么

模块 3 由本仓库负责（交互原型 + 硬件装机）。要真正把 Device Runtime 烧进开发板并接上模块 1/2，需要你提供以下信息（可先口头/文档给，不强制马上齐全）：

### 7.1 模块 1 / 2 的接入信息（来自你的 GitHub）
| 需要 | 说明 | 用途 |
|------|------|------|
| 仓库地址 + 当前版本（commit/tag） | 模块1（CIRA Core）与模块2（Language System）在 GitHub 的位置 | 对接 & 版本对齐 |
| 传输方式 | `ws` / `http` / 进程内？ | 决定 `modules.js` 的 `CIRA_INTEGRATION` 配置 |
| 端点 URL | 如 `wss://host/core`、`wss://host/lang` | Device Runtime 连接用 |
| 鉴权方式 | 无 / token / 签名？ | 接入时的鉴权头 |
| 接口是否符合 §1.3 / §2.2 | 是 / 需微调 | 不一致则双方对齐 schema |

> 提供后，只需把 `modules.js` 里的 `CIRA_INTEGRATION.core/language` 从 `'local'` 改成 `{type:'ws', url:'…'}`，`app.js` 一行不用改即可接入真实模块。

### 7.2 硬件设备信息（用于把 Device Runtime 移植到开发板）

> **已汇总为权威文档 `HARDWARE.md`**（型号/引脚/接口协议/烧录/待确认项均来自 Waveshare 官方 wiki + 示例源码）。下方为"曾需你提供"的清单，现已基本由官方资料填实；仅 §11（待确认项，尤其是 **HW V1/V2 判定**）仍需你判断。

| 项 | 已确认（权威来源） | 用途 |
|------|------|------|
| MCU / SoC | ESP32-S3R8，双核 240MHz，8MB PSRAM，16MB Flash | 决定星云粒子动画能否实时渲染 |
| 屏幕 | 360×360 圆 LCD，驱动 **ST77916**，QSPI，RGB565 | 移植渲染层（Canvas → 帧缓冲） |
| 触摸 | **CST816T**，I2C 0x15，INT=GPIO4，单点+手势 | 移植触摸唤醒 / 长按进设置 |
| 音频 | **ES8311**(DAC)+**ES7210**(ADC)+**NS4150B**(功放)，I2S MCLK=GPIO2/BCK=GPIO48/LRCK=GPIO38/DOUT=GPIO47/DIN=GPIO39，PA=GPIO15 | 移植 ASR 采集 + 模块2 音频播放 |
| 连接 | Wi-Fi 802.11b/g/n + BLE5 | 模块1/2 云端通信 + 配网 UI |
| 固件框架 | Arduino(esp32 3.2.0/LVGL9.3.0) 或 ESP-IDF(≥5.5.1) | 决定代码形态 |
| 电源 / 唤醒 | 3.7V 锂电(MX1.25)，唤醒源=触摸 INT(GPIO4)/语音唤醒词 | 移植 10s 熄屏省电 |

### 7.3 烧录环境（「直接开发进开发板」的前提）
- 开发板需**物理连接到本机**（USB 串口 / 或网络），且本机具备对应工具链（如 ESP-IDF）。
- 当前本机为 macOS，尚未确认装有 ESP-IDF；届时若未装，我会先安装/配置工具链，再构建并烧录。
- 若板子不在本机旁，我会产出**可烧录的固件镜像 + 烧录步骤**，由你在设备端执行。

---

## 8. 集成接缝（Integration Seam）

Device Runtime 访问模块 1/2 的唯一入口是 `modules.js` 暴露的：

- `CIRA.Core.respond(input)`      → 对应 §1（模块1）
- `CIRA.Language.synthesize(pkg)`  → 对应 §2（模块2）

`app.js` 只调用这两个符号，**不知道也不关心**背后是本地占位桩还是云端真模块。切换只需改 `CIRA_INTEGRATION` 配置：

```js
const CIRA_INTEGRATION = {
  core:     'local',                                    // → 本地占位桩(core.js)
  // core:   { type:'ws', url:'wss://你的模块1端点' },   // → 真实模块1
  language: 'local',
  // language:{ type:'ws', url:'wss://你的模块2端点' },
};
```

分布式消息协议见 §4；`modules.js` 已内置 WebSocket 客户端示例，通常**无需改动**即可接入。

---

## 9. 设备接口映射（模块协议 → 硬件落点）

> 模块接口（§1–§3）如何落到 ESP32-S3-Touch-LCD-1.85C-BOX 真实硬件。硬件引脚/驱动以 `HARDWARE.md` 为准（**V2 已确认**）。

| Device Runtime 输入/契约 | 硬件落点（V2） | 说明 |
|--------------------------|----------------|------|
| 状态 `idle/listening/thinking/speaking/settings/sleep/offline` | 星云渲染 → **ST77916** 帧缓冲；`sleep` → 背光 **GPIO5** 占空比 0 + 停粒子渲染（`lf.pause()`） | SLEEP 视觉=黑屏省电 |
| 情绪 `emotion`（calm/curious/thinking/happy/worried） | 星云形态参数（`lifeform.js` 的 density/pulse/color）→ 帧缓冲 | 暖白 `#FFE9C7` 光团 |
| 音频 `AudioHandle`（play/stop/onEnd） | **ES8311** I2S 播放：DOUT=GPIO47 / DIN=GPIO39；PA 使能 **GPIO15**；MCLK=GPIO2/BCK=GPIO48/LRCK=GPIO38 | `stop()` 即唤醒打断当前播报 |
| 唤醒（触摸 / 语音唤醒词） | 触摸 INT **GPIO4**（CST816）/ **ESP-SR** 唤醒词「你好，cira/西拉」 | 本地应答不进大模型 |
| 亮度 1–400 nit | 背光 PWM **GPIO5**（占空比映射） | `setBrightness()` → 占空比 |
| 长按进设置（≥1.2s） | 触摸按下计时（软件），非依赖 CST816 长按手势 | CST816 单点，故 UI 限单点 |

**移植要点（与 Web 仿真器差异）**：
- 渲染后端：浏览器 Canvas 2D → ESP32 帧缓冲（LVGL `lv_canvas` 或直接写 ST77916 framebuffer）。
- 音频后端：Web Speech TTS（占位桩）→ ES8311 I2S 真实播放（模块2 输出 PCM）。
- 状态机/触摸/唤醒逻辑（`app.js`/`lifeform.js` 抽象）**可复用**，仅 I/O 适配层替换。
- ⚠️ 详见 `HARDWARE.md`：实体板**已确认 V2**，音频栈按 ES8311+ES7210 锁定；V1 差异仅作历史参考，换 V1 板时再整体切换。

---

## 10. 双契约对齐与桥接层（与模型侧 CIRA_INTERFACES.md 的差异处理）

> 背景（2026-08-08 模型侧反馈）：模块 1/2 的冻结契约在 `engine/cira.py` / `engine/language_system.py` / `CIRA_INTERFACES.md`（由模型团队维护，**非本仓库**），与本文档 §1–§3 的冻结契约**不是同一套文本**，存在真实字段/枚举差异。**这不是理解偏差，无需推翻任一方冻结**——靠新增「适配桥接层」兜住即可。

### 10.1 差异矩阵（已对齐，仅 5 处）
除以下 5 处外，其余字段（`packageId` / `text` 等）两契约一致，无需桥接处理。

| 字段 | 模型侧（CIRA_INTERFACES） | 本仓库（§1.3 / §2.2） | 桥接处理 |
|------|--------------------------|----------------------|----------|
| `emotion` | **9 值**枚举 | **5 值**：`calm`/`curious`/`thinking`/`happy`/`worried` | 桥接映射 **9→5**（就近折叠）；Device Runtime 仅识别 5 态 |
| `priority` | 见 CIRA_INTERFACES（粒度可能更细） | `normal`/`interrupt` | 唤醒打断语义由 Device Runtime **本地硬编码「唤醒优先级最高」**（Evan 明确），桥接可忽略模型侧 priority 或默认 wake 始终胜出 |
| `ttsHints` | 结构见 CIRA_INTERFACES | `{rate,pitch,voice,style}` | 桥接 marshal 为本仓库 shape；v0.8.0 Device Runtime **暂不消费**，作扩展字段透传 |
| `presentationHints` | 结构见 CIRA_INTERFACES | `{pulse:bool}` 等 | 同上，透传 + 忽略未知 |
| `endOfTurn` | bool | bool? | 桥接透传；v0.8.0 默认 `true`（单轮），后续可在不破冻结前提下消费 |

### 10.2 Device Runtime 对桥接层的两项决定（驱动桥接层实现）
**A. 传输方式：推荐 WebSocket 网关**
- Device Runtime 只依赖本文档冻结的异步接口 `CIRA.Core.respond` / `CIRA.Language.synthesize`；**传输是桥接层内部事务**，`app.js` 不感知。
- 推荐 WS 理由：对话设备需**流式音频（边合成边播）**以降低儿童陪伴场景的感知延迟；WS 长连接便于中断在播音频、以及未来 Core 主动推送。ESP32 `esp_websocket_client` 原生支持。
- 退路：若模型侧基础设施仅 HTTP，HTTP(+chunked/streaming) 亦可——桥接层对外仍暴露同一冻结接口即可。**Device Runtime 代码不变**。

**B. B 类字段（priority/ttsHints/presentationHints/endOfTurn + emotion 5vs9）：v0.8.0 走适配兜底，不升版本**
- 依据：「**以还原交互体验为准**」。v0.8.0 目标是复刻当前原型体验（5 情绪 + 无 hints 消费），无需原生无损。
- 兜底策略：桥接层把模型侧契约 **marshal 为本仓库 §1.3/§2.2 形状**（emotion 9→5 折叠；其余字段透传为扩展字段，Device Runtime 忽略未知）。
- 冻结不动：模块 1/2 的 `engine/cira.py` / `engine/language_system.py` / `CIRA_INTERFACES.md` **一字不改**。
- 升级触发条件（后续，非 v0.8.0）：当我们要在仿真器/固件里**真正消费 9 情绪或 hints 驱动呈现**时，再迭代 Core V2.02 / LS V1.01→V1.02 / `response-package@2`，并同步扩展 §1.3。届时属**新增字段（向后兼容）**，不破坏现有冻结。

### 10.3 桥接层职责边界
- **输入** = 模型侧 CIRA_INTERFACES 契约；**输出** = 本仓库 §1.3/§2.2 契约。
- 仅做协议 marshal + 枚举映射 + 传输封装，**不含任何业务逻辑**（对话/发声/渲染分别在模块 1/2/3）。
- Device Runtime 经 `modules.js` 的 `CIRA.Core` / `CIRA.Language` 调用桥接层暴露的**同一接口**，不感知桥接存在。
