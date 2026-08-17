# CIRA Device Runtime · 手机上机版 冻结文档 v1.0

> 冻结日期：2026-08-17 ｜ 形态：浏览器 Web 原型（非原生 App） ｜ 负责人：模块3 Device Runtime
> 配套权威契约：`../MODULE_INTERFACES.md`（模块间冻结接口）｜ `../PROJECT_CONTEXT.md`（跨会话传承）

---

## 1. 冻结说明

- **版本**：`v1.0`（代码中 `VERSION = '1.0'`，标题「CIRA · 安卓原型 v1.0（冻结版）」）。
- **状态**：UI / 交互逻辑 **封存不再改动**。仅允许：修 bug、外接契约对接、或升版本（升版本 = 新分支，不回头改 v1.0）。
- **形态边界（重要）**：这是**浏览器 Web 原型**，经 `bridge_proxy`(HTTPS) + `cloudflared` 隧道在小米15 上"添加到主屏"当 Web App 用。
  - ✅ 能做的：圆屏星云、状态机、文本/语音输入分离、语音唤醒悬浮面板、本地唤醒音、**真模型对话 + 火山 TTS 播报**（接 8787 时）。
  - ❌ **做不到的（浏览器结构性限制，见 §6）**：程序后台常驻、熄屏 always-on 语音唤醒、系统级悬浮于其他 App 之上。这些需要真·原生 App（下一步）。
- **红线**：模块1(Core) / 模块2(LS) 的代码与契约**一字不改**；v1.0 只动了模块3 自身产物（android-proto 下的 UI/桥接/标注）。

---

## 2. 外接边界清单（哪些不是我的，哪些是我的）

### 2.1 【外接 · 必须来自真模型侧】— 不在本仓库、由 Core(8787)/LS 提供
| 项 | 位置 | 说明 |
|----|------|------|
| 对话推理（"说什么"） | 模块1 CIRA Core @ `http://127.0.0.1:8787` | 收文字 → 返回回复 + 情绪 |
| 语音合成（"怎么说"） | 模块2 Language System，由 Core 内部调用 | 火山 vivi2.0 神经音，经 `/api/tts` 回传音频 |
| 唤醒本地应答音源? | ❌ 不是外接 | 见 2.2，本地预录 |
| 模型/provider/记忆状态 | `/api/status` 返回 | `model`、`provider`、`memories`、`tts_browser_mode`、`asr_ready` |

### 2.2 【本地 · 设备端运行，不依赖模型】— 我的职责（模块3）
| 项 | 实现 |
|----|------|
| 圆屏星云粒子 | `lifeform.js`（LightLifeform，density 1.45） |
| 状态机 / 情绪驱动 | `app.js`（`idle/listening/thinking/speaking` + 5 情绪） |
| 语音识别 ASR | **浏览器 Web Speech API**（设备端捕获文字，送 `/api/chat`） |
| 唤醒本地应答音 | 预录 `ai.m4a`(哎) / `wo.mp3`(我在) — **不进大模型** |
| UI 全部渲染 | 文本/语音输入分离、悬浮唤醒面板、倒计时、回复气泡 |
| 离线兜底 | `/api/*` 不通时仅本地交互，不报错崩溃 |

> 一句话：**模型"想什么/说什么/用什么声音"是外接；"怎么显/怎么播/怎么听"是我的。**

---

## 3. v1.0 实际消费的外部接口（REST / 同源经 bridge_proxy）

> 这是 v1.0 **实际打的接口**。注意：规范的"模块间冻结契约"是 `MODULE_INTERFACES.md` 的 `CIRA.Core.respond` / `CIRA.Language.synthesize`（经 `modules.js`）；android-proto 为快速上机用了直连 `/api/*` 捷径，**上线前建议改走 `modules.js` 接缝**（同契约，Device Runtime 代码不变）。

### 3.1 GET /api/status（探测健康度，失败不影响本地）
响应（节选）：
```json
{ "model":"mimo-v2.5-pro", "provider":"volcano",
  "tts_browser_mode":false, "memories":N, "asr_ready":true }
```
- `tts_browser_mode=false` → 走 `/api/tts` 神经音；`true` → 设备端浏览器朗读兜底。
- `model` / `provider` → 仅展示。

### 3.2 POST /api/chat（对话 · 外接核心）
请求：
```json
{ "text":"用户话语", "age":8, "channel":"voice|text",
  "voice_meta":{"source":"web-speech-api"}, "session_id":"<UUID>" }
```
响应（v1.0 消费字段）：
```json
{ "response":"回复文本", "emotion":"happy",       // 5 值之一(见 §4)
  "ignite":true|false|null, "crisis":true|false } // ignite=脉冲触发; crisis=风险标记
```
- 缺 `response` → 显示用户原话兜底。
- `emotion` 接收 5 值；若模型侧给 9 值，由**桥接层折成 5**（见 §4/§5），Device Runtime 永远只认 5。

### 3.3 POST /api/tts（语音合成 · 外接）
请求：`{ "text":"回复文本" }`
响应：`{ "audio":"<base64 data URI 或 URL，mp3/wav>" }` → 设备端 `playAudio()` 播放。

---

## 4. 冻结契约（权威 · 来自 MODULE_INTERFACES.md）

Device Runtime 经 `modules.js` 只依赖这两个符号，**不感知背后是桩还是真模块**：
- `CIRA.Core.respond(input)` → `ResponsePackage`
- `CIRA.Language.synthesize(pkg)` → `AudioHandle`

`ResponsePackage`（§1.3，节选）：
| 字段 | 类型 | 说明 |
|------|------|------|
| text | string ✓ | 自然语言内容 |
| emotion | enum ✓ | **5 值**：`calm`/`curious`/`thinking`/`happy`/`worried` |
| packageId | string ✓ | 唯一包 ID |
| ignite / crisis / ttsHints / presentationHints / endOfTurn | 可选 | 扩展字段，v1.0 仅消费 ignite/crisis，其余透传忽略 |

`AudioHandle`（§2.2）：`play()` / `stop()` / `onEnd(cb)` / `durationMs?`。

---

## 5. 模型升级时，接口侧（模块1/2）必须提供什么

> 核心原则：**模块1/2 的内部实现怎么升级都行，但对外暴露的契约要保持稳定；若真要变，由桥接层兜住，Device Runtime（v1.0 及后续）代码不动。**

### 5.1 保持兼容（最省事，推荐）
升级后请确保以下**端点 URL 与字段**仍可用（新增字段须向后兼容，不删不改已有字段名）：
1. `GET /api/status` 仍返回 `tts_browser_mode`、`model`、`provider`（至少这三项）。
2. `POST /api/chat` 请求仍接受 `text`(必需) + `age`/`channel`/`session_id`(可选)；响应仍含：
   - **`response`**（string，回复文本，必需）— 设备端播放 + 显示的就是它；
   - **`emotion`**（5 值之一，必需）— 驱动星云；若仍输出 9 值，请在桥接层折成 5，不要改 Device Runtime；
   - `ignite`(bool/trigger，可选)、`crisis`(bool，可选) 保持原语义。
3. `POST /api/tts` 请求仍接受 `text`；响应仍含 **`audio`**（可播放的 mp3/wav，base64 或 URL）。

### 5.2 若必须破坏性变更（换端点 / 换字段名 / 换传输协议）
- **不要直接改 Device Runtime**。在桥接层（§10 定义的适配层）做 marshal：把新输出转成 §4 的 `ResponsePackage` / `AudioHandle` 形状，Device Runtime 无感。
- 若换传输（如 HTTP→WebSocket 流式），桥接层对外仍暴露 `CIRA.Core.respond` / `CIRA.Language.synthesize` 同一接口即可（`modules.js` 已内置 WS 客户端示例，通常无需改 Device Runtime 代码）。
- 破坏性变更前**必须**通知 Device Runtime 负责人（模块3），并连同桥接层变更一起提测；Device Runtime 仅在"要真正消费新字段（如 9 情绪、hints 驱动呈现）"时才升自己的版本。

### 5.3 升级侧自检清单（给模块1/2）
- [ ] `/api/chat` 响应是否仍含 `response`（非空）+ `emotion`（5 值之一）？
- [ ] `emotion` 若为 9 值，桥接层是否已折成 5（calm/curious/thinking/happy/worried）？
- [ ] `/api/tts` 是否仍返回可播放 `audio`？格式仍是 mp3/wav？
- [ ] `/api/status` 是否仍含 `tts_browser_mode`？值为 `false` 时设备端才走神经音。
- [ ] 新增字段是否全为**追加**（旧字段未改名/未删除）？
- [ ] 若改端点/协议，桥接层是否已适配且 Device Runtime 代码未动？

---

## 6. 浏览器形态的能力边界（下一步做真 App 的依据）

| 能力 | 浏览器 Web 原型(v1.0) | 真·原生 App（下一步） |
|------|----------------------|----------------------|
| 程序后台常驻 | ❌ 熄屏/切后台 JS 冻结 | ✅ 原生 Service / 后台进程 |
| 熄屏 always-on 语音唤醒 | ❌ 浏览器挂起即停 | ✅ 唤醒词 SDK（iOS/Android 原生或 ESP-SR） |
| 悬浮于其他 App 顶层 | ❌ 仅在自身页面内 | ✅ 系统级悬浮窗（SYSTEM_ALERT_WINDOW / iOS 画中画/CallKit） |
| 麦克风（亮屏时） | ✅ HTTPS 下 Web Speech | ✅ 原生音频采集 |
| 真模型对话 + TTS | ✅ 接 8787 | ✅ 同（或走云） |

> 结论：**v1.0 的"语音唤醒"是亮屏下的按键/点击触发 + Web Speech 识别，不是熄屏常驻唤醒**。要实现你描述的"后台运行 + 熄屏唤醒 + 顶层悬浮"，必须把 Web 原型移植/封装为原生 App（或 Capacitor 套壳 + 原生插件，或直上 ESP32 硬件）。这是模块3 的下一阶段，契约（§4）不变，变的只是 I/O 适配层。

---

## 7. 部署回顾（防断片 · 当前链路）
- 上机地址：`https://<cloudflared-tunnel>/cira-android.html`（bridge_proxy 从 `android-proto/` 起服务，路径是**根** `/cira-android.html`）。
- 链路：手机 → cloudflared(HTTPS) → bridge_proxy(:8443, 自签 `.tls/`) → 静态页 + `/api/*` 转发 → 本机 Core(8787)。
- ⚠️ 隧道为临时 quick tunnel：Mac 重启 / 任一进程被杀 → 失效。要固定地址请部署云端或命名隧道。
- 红线守住：v1.0 仅改模块3 产物；未碰模块1/2 契约。
