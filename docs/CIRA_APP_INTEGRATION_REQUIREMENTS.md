# CIRA 安卓 App 集成需求（给 Core / Language System 侧准备）

> 这份是 **App 端（JS / WebView）对 CIRA-Core、CIRA-Language-System 的接入需求清单**。
> 契约层 `CIRA_INTERFACES.md` 已冻结，模块边界清晰；本文只补「App 是 JS、Core/LS 是 Python」之间
> **必须存在的一层网络契约**，以及几个端到端跑通前要定的行为。
> 让那边照此准备一个桥接服务即可，App 端不改任何内部、只按端点收发。

---

## 0. 背景与调用链

App 是 **Capacitor（WebView + JS）**，Core/LS 是 **Python**。两者不在同一进程，必须有一个网络桥。

完整一轮对话（App 视角）：

```
孩子说话 ──麦克风──▶ 16k mono PCM
   └─ POST /transcribe ─────────────▶ Language System.ASR ──▶ text
   └─ POST /respond (child-input@1) ─▶ Core.respond_to ───▶ response-package@1
   └─ POST /speak (response-package) ─▶ Language System.TTS ─▶ audio-output@1
   ▶ 播放音频 + 按 display_state 驱动星云表情/状态
```

唤醒词（Porcupine，离线）在**原生层**检测，不在桥里；唤醒后 App 调 `GET /wake_ack` 取应答音频。

---

## 1. [必做] HTTP 桥接服务：把冻结函数包成 REST 端点

建议用 FastAPI。以下端点 App 端会直接调用，请严格对齐字段名（与 `CIRA_INTERFACES.md` 协议同名）。

### 1.1 `POST /v1/transcribe` — 语音→文字（ASR）
- 请求体：`application/octet-stream`，**原始 16-bit / 16000Hz / 单声道 / little-endian PCM 字节**（App 直采，不含 wav 头；若只吃 wav 容器请说明，App 改成封 wav 头）。
- 响应（JSON）：
  ```json
  { "schema": "asr-result@1", "text": "我今天被同学笑了", "asr_available": true }
  ```
- ASR 不可用时：`{ "text": null, "asr_available": false }`（App 据此切到屏幕文字输入）。

### 1.2 `POST /v1/respond` — 文字→回应（Core）
- 请求（JSON）：`child-input@1` 全部字段 + 一个 `session_id`（字符串，可选，见 §3）。
  ```json
  { "schema":"child-input@1", "text":"...", "speaker":"child", "child_age":0,
    "channel":"voice", "history":"", "voice_meta":null, "session_id":"sess_abc" }
  ```
- 响应（JSON）：`response-package@1` 全部字段 + 一个 `display_state`（见 §4）。
  ```json
  { "schema":"response-package@1", "text":"...", "emotion":"comfort",
    "modality":"language", "ignite":null,
    "display_state": { "schema":"display-state@1", "emotion":"comfort", "status":"speaking", "ignite":null } }
  ```

### 1.3 `POST /v1/speak` — 回应→音频（TTS）
- 请求（JSON）：`response-package@1`（或直接 `{ "text":"...", "emotion":"..." }`）。
- 响应（JSON）：`audio-output@1`，音频用 **base64** 内嵌（WebView 最省事）。
  ```json
  { "schema":"audio-output@1", "audio":"<base64>", "format":"wav",
    "sample_rate":16000, "text":"..." }
  ```
- **TTS 不可合成时**（对应 `speak` 返回 `(None,None)`）：`{ "audio":null, "text":"...", "fallback":"web_tts" }`，App 用浏览器/系统 TTS 兜底朗读 `text`。

### 1.4 `GET /v1/wake_ack?which=ai|wo` — 唤醒应答音频
- 响应：`{ "audio":"<base64>", "format":"mp3", "text":"哎" }` 或 `"我在"`。
- 唤醒检测不在桥里，桥只产出这段应答音频。

### 1.5 `GET /v1/health`
- 响应：`{ "asr_available":true, "tts_available":true, "core_ready":true }`，供 App 启动自检与降级判断。

---

## 2. [必做] CORS / 可被 WebView 调用
- 开发期：响应头 `Access-Control-Allow-Origin: *`（含 `OPTIONS` 预检放行）。
- 或：App 走 Capacitor 原生 HTTP 插件直连、彻底免 CORS（推荐生产用，避免暴露）。
- 明确告诉 App 端：服务监听地址 + 端口（局域网可达，如 `http://192.168.x.x:8000`）。

---

## 3. [必做] 会话 / 多轮回话（session_id）
- `POST /v1/respond` 接受 `session_id`；服务端按 `session_id` **维护最近 N 轮 history**（N≥20 轮，超出滚动丢弃）。
- App 每轮带同一个 `session_id` 即可，无需自己拼 `history` 长字符串。
- 首次对话 `session_id` 由 App 生成（UUID），可持久化在手机上（同一孩子长期连续记忆）。
- 服务端重启后 history 是否留存请告知（影响"记忆连续性"预期）。

---

## 4. [必做] display-state 归属：以 Core 为准
- 星云的**表情/配色/状态必须由 Core 的 `emotion` 与 `status` 驱动**，不能 App 自己编。
- 因此 `/v1/respond` 响应必须带回 `display_state`（`emotion` + `status`）。
- `status` 取值：`idle|listening|thinking|speaking|sleeping|alert`。App 映射：
  - `listening` → 星云"开放接收"态（已在原型实现 VAD 聆听）
  - `thinking` → 内向漩涡态
  - `speaking` → 向外辐射波 + 播放音频
  - `emotion` → 决定星云主色调（happy/excited/curious/comfort… 同原型 STATE_PROFILE 调色板）
- 这样"CIRA 此刻什么心情"与"星云怎么演"是同一份数据，不会脱节。

---

## 5. [必做] 降级契约（让 App 不崩）
| 场景 | 桥应返回 | App 行为 |
|---|---|---|
| ASR 不可用 | `transcribe` → `{text:null, asr_available:false}` | 切屏幕文字输入 |
| TTS 不可用 | `speak` → `{audio:null, fallback:"web_tts"}` | 用系统/浏览器 TTS 朗读 text |
| Core 超时/5xx | HTTP 错误 | App 保持"思考"态、重试 1 次；仍失败播一句本地兜底"我刚才走神了" |
| 网络不可达 | 连接失败 | App 显示"离线"态，交互降级为本地戳星 |

请明确：单次 `respond` / `speak` 的**建议超时秒数**（App 据此设超时与动画节奏）。

---

## 6. [推荐] 流式 `respond_stream`（降低延迟）
- 对话陪伴对延迟敏感，建议加 `POST /v1/respond_stream`（SSE 或 chunked）。
- 流式顺序：`display_state(listening)` → `thinking` → `response-package` 文本分片 → `audio` 分片（边生成边播）。
- 冻结与否不影响首版联调；**但首版若只给非流式 `/respond`，App 的"思考"动画需等整句生成完才切"说话"，会有可感知停顿**——请评估首版是否就要流式。

---

## 7. [推荐] 唤醒词边界确认
- 明确：**唤醒检测（Porcupine/Vosk 离线）在 App 原生层，不在桥里**。
- 桥只负责 `GET /wake_ack` 产出应答音频；唤醒→应答→进聆听 的编排在 App。
- 若那边其实把唤醒也放在 Python 侧，请告知，App 改调用方式。

---

## 8. [推荐] 鉴权与部署
- 开发/局域网联调：**免鉴权**，App 直连 `http://<LAN_IP>:<port>`。
- 生产：支持可选 `Authorization: Bearer <token>` 请求头（默认关，dev 直接调）。
- 部署形态请告知：是长期跑在某某 LAN 服务器 / 还是临时本机 / 还是将来上云——决定 App 里服务地址怎么配（硬编码调试地址 vs 可配置）。

---

## 9. [推荐] 延迟预算（用于调星云动画节奏）
请给出各调用在典型网络下的 P50 延迟，App 用它们校准动画时长，避免"思考太久显得卡"或"说话没播完就切走"：
- `transcribe`：___ ms
- `respond`（首字）：___ ms
- `speak`（首音）：___ ms
- 整体一轮（听到→回应播完）：___ ms

---

## 10. App 端会做的对应改造（让那边知道契约闭环）
1. 麦克风采集改 16k mono PCM → `POST /transcribe`。
2. "按住说话"/VAD 句尾 → `POST /v1/respond`（带 session_id）→ 取 `response-package` + `display_state`。
3. 按 `display_state.status/emotion` 切星云状态与配色；`thinking` 期间播"思考"动画。
4. `POST /v1/speak` → base64 解码播放，`speaking` 态同步。
5. 唤醒（原生 Porcupine）→ `GET /wake_ack` 播"哎/我在" → 进聆听。
6. 所有调用失败按 §5 降级；服务地址走可配置常量（先填调试 LAN 地址）。

---
*状态：需求方（App 端）已冻结上述契约，待 Core/LS 侧准备桥接服务后做端到端联调。*
