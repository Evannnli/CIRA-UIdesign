# CIRA 真 App（Capacitor 安卓壳）· 构建与部署说明

> 目标：把"Web 星云原型（v1.0 冻结版）"封装成**真正的安卓 App**，解决浏览器做不到的三件事——
> **① 后台常驻运行　② 熄屏/后台语音唤醒　③ 系统级悬浮于其它 App 顶层**。
> 路线依据：`PROJECT_CONTEXT.md` §三 / §六（Capacitor 原生壳，ESP32 硬件路线暂停）。

---

## 0. 工程结构（本目录 = `capacitor-app/`）

```
capacitor-app/
├── www/                         # 【Web 层源码，改这里】
│   ├── index.html              # = 冻结版 cira-android.html 的副本 + 原生桥注入
│   ├── lifeform.js             # 星云粒子
│   ├── native-bridge.js        # Web ↔ 原生 桥（window.CiraNative / window.CIRA）
│   └── wake_src/               # 本地唤醒应答音（哎 / 我在）
├── native-bridge.js 引用说明： Capacitor 环境才激活，纯浏览器调试自动降级
├── capacitor.config.json       # Capacitor 配置（webDir=www）
├── android/                    # 【原生层，Capacitor CLI 生成的工程 + 自写插件】
│   └── app/src/main/
│       ├── java/com/cira/runtime/
│       │   ├── MainActivity.java          # 注册插件 + 允许 WebView 混合内容
│       │   ├── CiraRuntimePlugin.java      # JS↔原生 桥（唤醒/浮窗/保活/权限/配置）
│       │   ├── CiraForegroundService.java   # 前台服务 + WakeLock + 跑唤醒词
│       │   ├── CiraOverlayService.java      # SYSTEM_ALERT_WINDOW 顶层浮窗（小星云）
│       │   ├── BootReceiver.java            # 开机重启后台唤醒
│       │   └── wake/PorcupineWakewordEngine.java  # 离线唤醒词（Picovoice）
│       ├── res/layout/overlay_window.xml   # 浮窗布局
│       ├── res/drawable/ic_stat_notify.xml # 前台通知图标
│       └── AndroidManifest.xml             # 权限 / 服务 / 接收器
└── README_BUILD.md             # 本文件
```

> ⚠️ `android/app/src/main/assets/public/` 是 **`www/` 的自动拷贝**，由 `npx cap sync android` 生成。
> **改 Web 请改 `www/`，再 `npx cap sync android`**，不要直接改 assets。

---

## 1. 前置条件

- **Node ≥ 18** + 已装依赖（本工程已 `npm i` 过 `@capacitor/core` `@capacitor/cli` `@capacitor/android`）。
- **JDK 21**（⚠️ 非 17）。Capacitor 8.13 的 `:capacitor-android` 库以**源码级 Java 21** 编译，用 JDK 17 会直接报 `无效的源发行版：21`。本机实测 Amazon Corretto 21 通过。
- **Android SDK**：`platform-tools`、`build-tools`（最新）、`platforms;android-36`。
  - 最简：装 **Android Studio**，打开 `capacitor-app/android` 让它自动拉 SDK。
  - 或仅命令行：`sdkmanager "platform-tools" "build-tools;36.0.0" "platforms;android-36"`，并设 `ANDROID_HOME`。
- **小米15 一台**（HyperOS），USB 调试或无线调试已开。

> ✅ **本工程已于 2026-08-17 在本机（macOS arm64）成功编译出 `app-debug.apk`（6.1 MB）**。
> 工具链装在 `/Users/evanli/cira-sdk/`：`amazon-corretto-21.jdk`（JDK21）、`android-sdk`（cmdline-tools + platform-36 + build-tools;36.0.0 + platform-tools）。
> 本机出包命令见 §3.5。换机器只需重装同版本 JDK21 + SDK 并设好代理即可。

---

## 2. 填两处配置（编译前必做）

打开 `android/app/build.gradle` 的 `defaultConfig`，填入：

```gradle
buildConfigField "String", "CIRA_CORE_URL", "\"http://<你的Core地址>:8787\""
buildConfigField "String", "PORCUPINE_ACCESS_KEY", "\"<Picovoice免费key>\""
```

- `CIRA_CORE_URL`：CIRA Core（8787）的地址。本机/局域网就填 `http://192.168.x.x:8787`；上云后填云端 HTTPS 地址。
  - 也可不填编译期值，改在 App 内用 `CiraNative` 的 `setConfig({coreUrl})` 运行时写入（SharedPreferences 持久化）。
- `PORCUPINE_ACCESS_KEY`：Picovoice 唤醒词 key。**留空 = 不启用离线唤醒**，App 仍可经"模拟唤醒 FAB / 点击"触发对话（仅后台保活，无熄屏唤醒）。

---

## 3. 构建 APK

```bash
cd capacitor-app
npm install                 # 若换机器，先装依赖
npx cap sync android       # 把 www/ 拷贝进 assets + 同步插件
cd android
./gradlew assembleDebug    # 需要 ANDROID_HOME 指向 Android SDK
# 产物：app/build/outputs/apk/debug/app-debug.apk
```

或用 Android Studio 图形界面：`npx cap open android` → 点 ▶ Run（连上小米15 直接装）。

### 3.5 ⚠️ 本机（含公司/校园网）出包必读：Gradle 必须显式走代理

**最坑的一点**：Gradle **不读** `HTTPS_PROXY` 这类环境变量。本机上网实际走 `http://127.0.0.1:52190`（WorkBuddy 会话代理，来自系统设置）。
若直接 `./gradlew assembleDebug`，JVM 会直连 `dl.google.com` 被代理端掐断，报
`Remote host terminated the handshake` / `server may not support TLSv1.2/TLSv1.3`。
（curl、sdkmanager 能下是因为它们认系统代理；Gradle 不认。）

**修法**：把代理以 JVM 参数传给 Gradle（不要写进仓库 `gradle.properties`，它是会话/机器相关的）：

```bash
export JAVA_HOME=/Users/evanli/cira-sdk/amazon-corretto-21.jdk/Contents/Home
export ANDROID_SDK_ROOT=/Users/evanli/cira-sdk/android-sdk
export ANDROID_HOME=$ANDROID_SDK_ROOT
export GRADLE_OPTS="-Xmx2048m \
  -Dhttp.proxyHost=127.0.0.1 -Dhttp.proxyPort=52190 \
  -Dhttps.proxyHost=127.0.0.1 -Dhttps.proxyPort=52190 \
  -Dhttp.nonProxyHosts=localhost|127.0.0.1"
cd capacitor-app/android
./gradlew clean assembleDebug --no-daemon
# 产物：app/build/outputs/apk/debug/app-debug.apk
```

> 代理端口会变（会话级），以 `echo $HTTPS_PROXY` 当前值替换 `52190` 即可。
> 若换到无代理的纯净网络，删掉 `GRADLE_OPTS` 里的 `-D*proxy*` 段即可直连。

---

## 4. 装到小米15

```bash
adb install -r app/build/outputs/apk/debug/app-debug.apk
# 或把 apk 传到手机，文件管理器里点安装
```

首次打开会请求：麦克风、通知。按系统提示允许。

---

## 5. 小米15 / HyperOS 必做手动授权（否则"真 App"能力不生效）

HyperOS 对后台/浮窗限制极严，**光在 App 里点"允许"不够**，必须去系统设置逐一开：

1. **悬浮窗（顶层浮窗前提）**
   设置 → 应用设置 → 授权管理 → 应用权限管理 → CIRA → 悬浮窗 → **允许**
2. **自启动（后台不被杀的前提）**
   设置 → 应用设置 → 自启动管理 → 找到 CIRA → **允许自启动**
3. **后台电池无限制**
   设置 → 电池 → 应用智能省电 → CIRA → 无限制
4. **后台弹出界面 / 后台运行（锁屏也能拉起主界面）**
   设置 → 应用设置 → 授权管理 → 应用权限管理 → CIRA → 后台弹出界面 → **允许**
5. **麦克风 / 通知**：首次打开按系统弹窗授予即可。

> 只有 1+2+3 都开，才能做到"熄屏/切到别的应用后，喊一声唤醒、并在其它 App 上看到浮窗星云"。

---

## 6. 唤醒词（离线、熄屏常驻）

- 去 <https://console.picovoice.ai> 免费注册，建一个唤醒词（建议「哎」或「CIRA」），下载 `.ppn` 模型。
- 放到 `android/app/src/main/res/raw/cira_wake.ppn`。
- 把 access key 填进 `PORCUPINE_ACCESS_KEY`（见 §2）。
- 引擎优先级：有 `.ppn` 用自定义词，否则退回内置 `COMPUTER`。没 key 则只保活不检测。
- 想换开源方案（如 Vosk）可替换 `wake/PorcupineWakewordEngine.java`，对外接口不变。

---

## 7. 已知限制 / 待验证

- [x] 本工程**已于 2026-08-17 在本机（macOS arm64）成功编译出 `app-debug.apk`**（6.1 MB，compileSdk 36）。
  - Porcupine `3.0.1` 解析正常；其 `setKeywordPath` 仅接受 `String` 文件路径（已用"拷贝 raw→文件"实现，见 `wake/PorcupineWakewordEngine.java`）。
  - AGP 8.13 + Gradle 8.14.3 自洽；**需 JDK 21**、且 **Gradle 必须显式走代理**（见 §3.5）。
- [ ] 浮窗 WebView 加载的是 `file:///android_asset/public/index.html`（`?overlay=1`），与 Capacitor 主 WebView 是两套实例，状态不共享（符合设计：浮窗只显示小星云 + 点击回主界面）。
- [ ] `?overlay=1` 模式下目前只显示星云 + 点击回主界面；如需在浮窗里直接对话，需在 `index.html` 的 overlay 分支补迷你对话 UI。
- [ ] 熄屏唤醒的"真·always-on"依赖厂商不杀后台 + 自启动授权，HyperOS 上需用户手动开（见 §5）。

---

## 8. 与冻结版 v1.0 的边界

- **契约不变**：Core(8787) `/api/chat` `/api/tts` `/api/status` 契约、9→5 情绪折叠、模块1/2 代码一律不改（红线）。
- **变的只是 I/O 适配层**：WebSocket/麦克风/渲染 从"浏览器"换成"原生 WebView + 原生插件"。
- 冻结版 `android-proto/cira-android.html` 仍是浏览器上机版；本 `capacitor-app/` 是它的**原生封装版**，Web 层是同一套星云 UI 的副本。
