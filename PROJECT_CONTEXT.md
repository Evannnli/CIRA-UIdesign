# CIRA 项目传承文档（PROJECT_CONTEXT）

> **最后更新**：2026-08-17（真 App 安卓壳 `app-debug.apk` 已在本机 macOS arm64 成功编译出包） · 星云交互定版 `git tag nebula-1.0`
> 本文件随代码走，换电脑/换模型/换协作者都能满血接手。改动重大里程碑后必须更新此处并 commit。

---

## 一、项目是什么

**CIRA** = 面向儿童的 AI 陪伴生命体，视觉载体是一个"会呼吸、会被吸引、有情绪"的**暖色星云**。
核心体验：孩子戳它/对它说话，星云有"生命感"回应；待机时喊它名字，它在手机底部以半透明悬浮生命体出现。

当前两条产品线：
- **星云交互（安卓 App 首要）**：全屏自适应星云主界面 + 待机悬浮唤醒。✅ **v1.0 已定稿**（本回合）。
- **硬件嵌入式（ESP32-S3 圆屏，暂停）**：因 Mac USB CDC 驱动崩溃反复，自 2026-08-12 起暂停 2 天，未废弃。

---

## 二、核心哲学 / 产品定义

1. **"生命感"优先**：交互的"活"比功能重要。引力汇聚、呼吸、情绪 morph 都是为"它像活的"。
2. **暖色体积光场基调不可动**：橙/粉/紫/暖白，无青蓝绿（用户强偏好，见 NEBULA_V1_SPEC §1）。
3. **状态是同一套动效词汇的变体**：待机/聆听/思考/回应/唤醒/休眠 用统一的呼吸-旋转-收束-声波语言，构成一个系列。
4. **CIRA 的"心情"由 Core 权威**：接模型后情绪(emotion/ignite)以 Core 为准，App 不自己编（防脱节）。

---

## 三、技术分工与关键决策（理由已验证，勿走弯路）

| 决策 | 结论 | 理由 |
|---|---|---|
| 首要平台 | **安卓（小米15）** | 用户手机；iOS 第三方 App 无法真悬浮（系统限制） |
| 悬浮+唤醒 | **必须原生** Capacitor（前台 Service + SYSTEM_ALERT_WINDOW + Porcupine/Vosk + Silero VAD） | Web/PWA 做不到"悬浮于所有应用" |
| 桌面 Tauri | 降级为副产物（已出 CIRA.app + dmg） | 非首要目标 |
| 模型侧 status 归属 | **App 自管** listening/thinking/speaking/wake/idle | status 是调用生命周期副产品，Core 不参与 listening/thinking（零冻结、最干净） |
| 模型侧 emotion/ignite | **Core 权威**，随 `/v1/respond` 的 `display_state` 返回 | 回复内容属性，App 据此驱动配色点亮 |
| 硬件调试 | 暂停，等 Windows 笔记本或 USB-TTL 适配器 | Mac 原生 USB CDC 驱动 panic 累计 4 次 |

---

## 四、当前进度（里程碑）

- ✅ **星云交互 v1.0 定稿**（2026-08-12）：触碰"万有引力式汇聚"手感验收通过；6 种状态动效重做；唤醒 VAD 流转（说一句才进思考、不说静静等）。
  - 源：`android-proto/cira-android.html` + `android-proto/lifeform.js`
  - 规格：`android-proto/NEBULA_V1_SPEC.md`（参数全冻结）
- 🟡 **模型集成前端已接通（2026-08-12 晚）**：`android-proto/cira-android.html` 占位逻辑已替换为真实桥接调用 —— `transcribe`(16k PCM)/`respond`(取 display_state.emotion 驱动星云)/`speak`(base64 播放)/`wake_ack`(唤醒音频)/`health`(启动自检) 全通；含双降级（BASE 为空=离线占位；桥不可达=文字输入/系统 TTS）。附 `android-proto/mock_bridge.js`（零依赖本地桥，自测全绿）供联调。
  - **真模型就在本机 Mac（非远程桥）**：调的是冻结 Core V2.01 / LS V1.01（`engine/cira.CIRA`，即 `2026-07-28-21-39-04/engine/server.py` 那套），不是后来那套 `/v1/*` 桥接层。启动方式：在 `2026-07-28-21-39-04/` 跑 `bash .start.sh`（读同目录 `.env` 的 MiMo key，用隔离 venv python），监听 `0.0.0.0:8787`。实测：`provider=openai`(mimo-v2.5-pro + 快模型)、`tts=volcano`(vivi2.0 神经音 mp3)、`asr=volcano` 就绪、**80 条长期记忆已加载**。`/api/*` 契约：`GET /api/status`、`POST /api/chat`{text,age,channel,voice_meta,session_id}→{response,emotion(英文字符串),ignite,crisis,debug}、`POST /api/tts`{text}→{provider,format,audio:base64 mp3}、`POST /api/reset`。前端 `android-proto/cira-android.html` 现已**直接对接本机 8787 的 `/api/*`**（默认 `API_BASE=''` 经代理同源），不再走 235 桥 / `/v1/*` / mock。
  - **空壳问题已修（2026-08-12 深夜）**：原场景A「按住说话」按钮是**无模型的空心状态动画**（固定 思考1s→回应1.8s），被用户识破。已改为：该按钮触发真实对话轮（文字降级）→ 真实 `transcribe→respond→speak`；并在流转中回显 **「我听到：<你说的话>」** + 模型回复文字，证明真的听进去了、有实际回应。状态切换改为由真实模型延迟驱动，不再用固定 setTimeout 假动画。
  - **真语音测试通道（https 代理）**：纯 http 下手机浏览器禁 `getUserMedia`（需安全上下文），故小米上只能打字、验不到真 ASR。已加 `android-proto/bridge_proxy.js`——本机 https(:8443) 提供页面 + 把 `/api/*`（及兼容 `/v1/*`）在 Mac 内部转发到 `127.0.0.1:8787`（同源、避开混内容拦截）。手机打开 `https://<本机LAN IP>:8443/cira-android.html?bridge=/`（启动日志自动打印该地址），接受自签证书后即解锁麦克风，可验 **说话(Web Speech ASR)→/api/chat→星云变色(emotion)→/api/tts 语音回应** 全链路。ASR 在浏览器端做（Web Speech API zh-CN），后端只收文字。自签证书在 `.tls/`（已 gitignore，需用时本地 openssl 重生成）。
- 🟡 **联调可移植性 / 桥地址解析（2026-08-14）**：`bridge_proxy.js` 桥地址解析优先级 = 环境变量 `CIRA_BRIDGE` > 同目录 `bridge_target.txt`（一行 URL）> 默认 `http://127.0.0.1:8787`（本机真模型）。启动日志用 `lanIP()` 动态打印本机新 LAN IP，换网络不用手改。**2026-08-14 实测跑通**：真模型就在本机 8787，无需内网穿透/远程桥，默认真桥即可。先前规划的"家里桥机 Cloudflare Tunnel"方案已不再需要（模型与本机同源）。`mock_bridge.js`(:8000/现 8123) 仅作离线演示保留，勿与真模型混淆。
- 🟢 **UX 升级 v0.1（2026-08-14 晚）**：纯前端、手机硬刷新即生效。① 首屏 onboarding 脉冲提示（#welcomeHint，首次交互后自动隐藏+记 localStorage）；② 开场星云问候脉冲；③ 模型思考 ~15–23s 等待期状态栏持续显示「我听到：「…」思考…」动画点，避免像卡死。后续 UX 方向待定（情绪↔星云映射审计 / 唤醒悬浮面板打磨 / 危机呈现 / 延迟体感）。
- 🟢 **真 App 安卓壳已在本机出包（2026-08-17）**：`capacitor-app/`（Capacitor 8 安卓壳）把 v1.0 Web 星云封装为原生 App，
  含前台保活服务 / Porcupine 离线唤醒词 / SYSTEM_ALERT_WINDOW 顶层浮窗 / JS↔原生桥 / **Vosk 离线语音识别**。**本机（macOS arm64）已成功编译 `app-debug.apk`（~89MB，含中文识别模型，compileSdk 36）**。
  ⚠️ **关键架构坑（用户反馈"装好但调不动硬件"已定位修复）**：Android **WebView 不实现 Web Speech API**，原 Web 原型靠浏览器端 `SpeechRecognition` 做 ASR，在 App 的 WebView 里是 `undefined` → 代码把"按住说话"按钮直接隐藏。修复：新增 `asr/VoskAsrEngine.java`（离线 Vosk，中文模型 `vosk-model-small-cn-0.22` 打进 `assets/models/`），经 `CiraRuntimePlugin.startAsr/stopAsr` + `asrPartial/asrFinal` 事件回传文字给 Web 对话流程；纯浏览器调试仍走 Web Speech 回退。
  ⚠️ 关键环境坑已写入 `capacitor-app/README_BUILD.md` §3.5：**必须 JDK 21**（非17）+ **Gradle 必须显式走代理**（Gradle 不读 `HTTPS_PROXY` 环境变量，否则 `dl.google.com` 握手被掐；多代理端口时挑快的 7897）。工具链装在 `/Users/evanli/cira-sdk/`。
  构建与小米15/HyperOS 授权清单见 `capacitor-app/README_BUILD.md`。
- ⏸️ **硬件**：ST77916 黑屏根因已定位（QPI→标准 SPI 8-bit），修复已 commit 未 push；Mac 崩溃阻断验证。

---

## 五、关键技术决策细节（避免重踩）

- **引力模型演进结论**（已验证定稿）：不可用硬半径 cutoff（进圈即死）→ 无硬边界软化井；不可"到点=目标位移归零"（星飘走）→ 绝对点钉死；不可匀速缓动 → 加速度积分实现远慢近快。详见 NEBULA_V1_SPEC §2。
- **Mac USB CDC 崩溃**：`/dev/cu.usbmodem101` 在 macOS 26.x 内核 `usb.cdc.acm` 有 NULL 解引用 bug，被 DTR/RTS 复位信令触发。避坑：烧录 `--before no_reset`、避免 `mpremote reset`、换好线直插 USB-A。
- **构建铁律**：`USER_C_MODULES` 必须 `-DUSER_C_MODULES=<path>/micropython.cmake` 显式传给 `idf.py`（非 env 变量），否则 st77916.c 被静默丢弃→黑屏。
- **代理坑**：git/cargo 全局代理 57213 失效；cargo 用 `~/.cargo/config.toml` 强制 7897 + `GIT_CONFIG_GLOBAL=/dev/null`。

---

## 六、下一步

1. ✅ **真模型联调实测跑通（2026-08-14）**：本机 `8787` 冻结 Core 已由 `.start.sh` 拉起，`android-proto/cira-android.html` 经 `bridge_proxy.js`(:8443) 直接调 `/api/chat`+`/api/tts` 真链路。手机实测地址 `https://<本机LAN IP>:8443/cira-android.html?bridge=/`（麦克风/语音需 https，iPhone Safari 仅支持朗读不支持语音输入）。本机 playground 直开 `http://localhost:8787`。
2. **（进行中）交互/UX 升级**：模型联调已通，焦点回到用户真实诉求——升级交互与用户体验。待 Evan 指定优先打磨的 UX 方向（如：唤醒/聆听/回应动效手感、儿童话术与情绪映射、危机与安全协议呈现、首屏引导、延迟体感优化等）。
3. **封 Capacitor（真 App · 进行中）**：2026-08-17 已立工程脚手架 `capacitor-app/`（Capacitor 8 + 自带安卓模板），
   把冻结版 Web 星云（v1.0）封装为原生安卓 App，补浏览器三短板：
   - 前台 `CiraForegroundService`（PARTIAL_WAKE_LOCK + 常驻通知）解决**后台保活/熄屏常驻**；
   - `PorcupineWakewordEngine`（离线唤醒词，-v 3.0.1）解决**熄屏语音唤醒**；
   - `CiraOverlayService`（`SYSTEM_ALERT_WINDOW` 顶层浮窗，复用 `?overlay=1` 小星云）解决**顶层悬浮**；
   - `CiraRuntimePlugin` 暴露 JS↔原生桥（`window.CiraNative`/`window.CIRA`），唤醒命中经 `wakeword` 事件转 Web 的 `triggerWake()`。
   - ✅ **已在本机（macOS arm64）成功编译出 `app-debug.apk`（~89MB，含 Vosk 中文模型）**：需 JDK 21 + Gradle 显式走代理（见 `capacitor-app/README_BUILD.md` §3.5，多代理端口挑快的 7897）。工具链 `/Users/evanli/cira-sdk/`。
   - 🔧 **2026-08-17 晚补：原生离线 ASR（Vosk）替代 Web Speech**：Web 原型在 App 的 WebView 里 `SpeechRecognition` 为 undefined，导致"按住说话"按钮被隐藏、麦克风调不动。已加 `asr/VoskAsrEngine.java` + 插件 `startAsr/stopAsr` + Web 桥 `asrPartial/asrFinal`，Web 在 Capacitor 下自动改用原生识别。复装新版 APK 即可真听清说话。
   - 路线对照：浏览器 Web 原型 = `android-proto/cira-android.html`（v1.0 冻结）；原生封装版 = `capacitor-app/`（Web 层是同一套星云 UI 的副本，改 `www/` 后 `npx cap sync android`）。
4. **硬件恢复**（可选）：Windows 笔记本或 USB-TTL 适配器到位后，续烧录验证。

---

## 七、协作约定

- **仓库**：`cira-prototype/`，remote = `Evannnli/CIRA-UIdesign`（main，用户指定唯一远端）。
- **提交**：每次里程碑自动 commit（并尽量 push）；敏感 token 只在对话里给、不落盘、不写 `.git/config`。
- **push**：`git -c http.proxy= -c https.proxy= push`（当前代理 57213 失效，需用户给新 token 才能推）。
- **记忆**：长期笔记在 `.workbuddy/memory/MEMORY.md`；本文件为项目级传承。
- **决策人**：Evan（用户）。

---

*变更记录：2026-08-12 新增本项目传承文档；冻结星云交互 v1.0（NEBULA_V1_SPEC.md + git tag nebula-1.0）；集成需求 status 归属改为 App 自管（采纳用户建议）。2026-08-12 深夜 `BRIDGE.BASE` 填入真实桥 `http://192.168.31.235:8788`，并修「按住说话」空心演示→真实模型链路 + 回显「我听到」+ 新增 `bridge_proxy.js` 解锁手机真语音。2026-08-13 凌晨修复交互逻辑串路 bug：把「按住说话」(场景A 主动对话) 与「语音唤醒」(场景B 说"哎/我在"+连续听) 彻底拆成两条独立路径（`convMode`/`recording` 标志 + `runTurn(mode)`/`endPushTurn()`），按住说话不再误触发唤醒词招呼、按下即录音松手才发模型。2026-08-14 联调可移植性改造：`bridge_proxy.js` 桥地址改由 `CIRA_BRIDGE` 环境变量 / `bridge_target.txt`（一行）覆盖，默认回退本机真桥 `127.0.0.1:8787`；启动日志动态打印本机新局域网 IP，并附 `bridge_target.txt.example`。**2026-08-14 实测跑通真模型联调**：澄清"真模型一直在本机 Mac 8787 冻结 Core（非 235 桥 / 非 /v1/* 层）"，由 `2026-07-28-21-39-04/.start.sh` 拉起 `engine.server`；前端 `cira-android.html` 模型层由"235 桥 /v1/*"重写为直接对接本机 8787 的 `/api/chat`+`/api/tts`+`/api/status`（Web Speech 浏览器端 ASR + volcano 神经 TTS），emotion 驱动星云、ignite 触发 pulse、crisis 弹横幅；`bridge_proxy.js`(:8443) 转发 `/api/*` 到 8787 供手机 https 真语音验。原"家里桥机 Cloudflare 内网穿透"方案因模型本机同源而作废；UX v0.1（首屏引导提示 + 思考期活动指示）已 commit 5d40cd2。*

🔧 **2026-08-17 续：修两处真机 bug（commit 445ef3f）**：① 对话空转 = WebView 跨域 CORS（Core 不回 ACAO，POST+JSON 触发预检被静默拦截）；改为所有 `/api/*` 走**原生 `HttpURLConnection` 代理**（插件 `apiFetch`），不动 Core。② 按住说话不转文字 = `startAsr` 只查不申请麦克风权限、Web 从未调 `requestPermissions` → 识别永不启动；改为 `startAsr` **自动申请权限** + App 启动预申请 + UI 线程回传事件 + 松手无结果兜底提示。已重建 `app-debug.apk`(84.6MB) 并 push。复装即两处都好。

🔧 **2026-08-17 续2：挖出真正两个硬 bug（commit 8531929，终版）**：用户复装后仍"文字无反馈 + 按住说话一直听不转文字 + 浮窗收不到话"，且 HyperOS 无独立"联网权限"选项（INTERNET 声明即默认授权，联网非阻塞点）。① **真因A（文字无反馈）= 原生 `apiFetch` 在后台线程 `call.resolve`**：Capacitor 要求 PluginCall 结果在主线程回传，子线程 resolve 会让 JS `await` 永不 resolve、连输入都回显不出；改为 `deliverApiResult` 用 `runOnUiThread` 回传（Mac 侧 Core:8787 + Funnel 实测在线，反证非 Mac 端问题）。② **真因B（按住说话卡死）= talkBtn `pointerdown` 的 `preventDefault` 吞掉 `pointerup`**：Android WebView 上此写法会让 `endTalk` 永不触发、Vosk 永续；改为去 preventDefault + CSS `touch-action:none` + `setPointerCapture` + `window` 级 pointerup/cancel 兜底。附带：Vosk 模型拷贝加完整性校验（防损坏缓存）、屏幕底部 `__ciraDbg` 诊断黑条（免 adb 看 API/识别实时状态）、浮窗 `?overlay` 不再隐藏显示元素。重建 `app-debug.apk`(88.7MB) 并 push。**方法论：真机 bug 要在代码里找硬证据，不能凭"推测没授权/没联网"下结论。**
