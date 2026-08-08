# CIRA 模块接口冻结规格 (Frozen Module Interfaces)

> 版本：**v0.7** ｜ 日期：2026-08-08 ｜ 阶段：**接口冻结优先**（模块内部可后补，接口不可改）
> 适用：CIRA 圆形屏 AI 陪伴设备（ESP32 + 圆形 LCD/AMOLED）
> 配套：`cira-prototype/`（参考实现：模块 3 Device Runtime 真实逻辑 + 模块 1/2 的**本地占位桩**。`core.js`/`language.js` 仅为离线跑原型用；模块 1/2 的真实实现由其他团队在 GitHub 维护，接入时直接替换占位桩即可，app.js 不变）

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
| 需要 | 说明 | 用途 |
|------|------|------|
| MCU / SoC 型号与规格 | 如 ESP32-S3（是否带 PSRAM、主频、RAM） | 决定星云粒子动画能否实时渲染 |
| 屏幕 | 分辨率（已定 360×360 圆）、面板类型（LCD/AMOLED）、驱动 IC、总线（SPI/QSPI）、色深（RGB565?） | 移植渲染层（Canvas → 帧缓冲 / LVGL） |
| 触摸 | 控制器型号（如 CST816S）、总线、是否支持长按 | 移植触摸唤醒 / 长按进设置 |
| 音频 | 麦克风（数字 I2S? 模拟?）、Codec、功放/喇叭、I2S 配置 | 移植 ASR 采集 + 模块2 音频播放 |
| 连接 | Wi-Fi（配网方式）、BLE？ | 模块1/2 云端通信 + 配网 UI |
| 固件框架 | ESP-IDF 版本？Arduino？LVGL 版本？还是自定义帧缓冲？ | 决定代码形态 |
| 电源 / 唤醒 | 电池电压、休眠电流目标、从 SLEEP 唤醒的硬件源（触摸 GPIO / RTC） | 移植 10s 熄屏省电 |

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
