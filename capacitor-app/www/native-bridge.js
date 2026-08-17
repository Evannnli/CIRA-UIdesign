/* CIRA 原生桥（Native Bridge）
 * 仅在 Capacitor 原生壳内运行（window.Capacitor 存在时生效）。
 * 职责：
 *  1. 把原生层能力（唤醒词、浮窗、前台保活、权限）暴露给 Web（window.CiraNative）。
 *  2. 把原生唤醒词事件转成 Web 的 triggerWake()，让同一套星云 UI 直接进入聆听。
 *  3. 把 Web 的生命状态（listening/thinking/speaking/wake/idle）回传原生，便于原生侧联动。
 * 注意：本文件与 android-proto 的 cira-android.html 解耦——它只通过 window.CIRA 钩子通信，
 *       不直接依赖任何内部变量名，新增/改名都能向后兼容。
 */
(function () {
  'use strict';

  var hasCap = !!(window.Capacitor && window.Capacitor.Plugins && window.Capacitor.Plugins.CiraRuntime);
  var plugin = hasCap ? window.Capacitor.Plugins.CiraRuntime : null;

  // ---- Web → 原生 的调用封装 ----
  var CiraNative = {
    available: hasCap,

    // 请求所有需要的权限（麦克风 / 悬浮窗 / 通知）。返回 Promise<{mic,overlay,notification}>
    requestPermissions: function () {
      return plugin ? plugin.requestPermissions() : Promise.resolve({ mic: false, overlay: false, notification: false });
    },

    // 轻量申请麦克风+通知（不跳悬浮窗设置），App 启动时预申请
    requestMicPermission: function () {
      return plugin ? plugin.requestMicPermission() : Promise.resolve({ mic: false, notification: false });
    },

    // 启动原生唤醒词引擎（前台 Service 内常驻）。返回 Promise
    startWakeword: function (opts) {
      return plugin ? plugin.startWakeword(opts || {}) : Promise.resolve();
    },

    // 停止原生唤醒词引擎
    stopWakeword: function () {
      return plugin ? plugin.stopWakeword() : Promise.resolve();
    },

    // 启动原生离线语音识别（Vosk），识别结果通过 asrPartial/asrFinal 事件回传
    startAsr: function () {
      return plugin ? plugin.startAsr() : Promise.resolve();
    },

    // 停止原生语音识别
    stopAsr: function () {
      return plugin ? plugin.stopAsr() : Promise.resolve();
    },

    // 原生 HTTP 代理：绕过 WebView 的 CORS，所有 /api/* 改走原生层（Core 地址由 BuildConfig 注入）
    apiFetch: function (req) {
      return plugin ? plugin.apiFetch(req || {}) : Promise.reject(new Error('no plugin'));
    },

    // 显示系统级浮窗（顶层悬浮星云）
    showOverlay: function () {
      return plugin ? plugin.showOverlay() : Promise.resolve();
    },

    // 隐藏浮窗
    hideOverlay: function () {
      return plugin ? plugin.hideOverlay() : Promise.resolve();
    },

    // 从浮窗回到完整 App 主界面（原生会把主 Activity 带到前台）
    openMain: function () {
      return plugin ? plugin.openMain() : Promise.resolve();
    },

    // 读取原生侧配置（Core 地址、唤醒词等），由 MainActivity 注入
    getConfig: function () {
      return plugin ? plugin.getConfig() : Promise.resolve({ coreUrl: '' });
    },

    // 订阅原生事件（wakeword / overlayState）。返回取消订阅函数
    on: function (event, cb) {
      if (!plugin || !plugin.addListener) return function () {};
      var h = plugin.addListener(event, cb);
      // Capacitor 的 addListener 返回 { remove }
      return function () { if (h && h.remove) h.remove(); };
    }
  };

  window.CiraNative = CiraNative;

  if (!hasCap) {
    // 在非原生环境（纯浏览器调试）静默降级，不影响原 Web 原型功能
    console.log('[CIRA] 非原生环境，原生桥已禁用（降级为纯 Web 原型）');
    return;
  }

  // ---- 原生 → Web：唤醒词命中 ----
  // 原生唤醒词引擎在后台/熄屏检测到关键词后，会 emit 'wakeword' 事件。
  // 这里转成 Web 已存在的 triggerWake()，让星云直接进入唤醒聆听流程。
  CiraNative.on('wakeword', function (payload) {
    try {
      if (window.CIRA && typeof window.CIRA.triggerWake === 'function') {
        window.CIRA.triggerWake(payload && payload.phrase);
      }
    } catch (e) {
      console.warn('[CIRA] 唤醒回调失败', e);
    }
  });

  // ---- 原生 → Web：离线识别结果 ----
  // asrPartial：实时中间结果（用于"正在听…「xxx」"的即时反馈）
  // asrFinal：一句完整识别（送入对话流程，等同说了一句话）
  CiraNative.on('asrPartial', function (payload) {
    try {
      if (window.CIRA && typeof window.CIRA.onNativeInterim === 'function') {
        window.CIRA.onNativeInterim(payload && payload.text);
      }
    } catch (e) {}
  });
  CiraNative.on('asrFinal', function (payload) {
    try {
      if (window.CIRA && typeof window.CIRA.onNativeTranscript === 'function') {
        window.CIRA.onNativeTranscript(payload && payload.text);
      }
    } catch (e) {}
  });
  CiraNative.on('asrError', function (payload) {
    try {
      if (window.CIRA && typeof window.CIRA.onNativeError === 'function') {
        window.CIRA.onNativeError(payload && payload.text);
      }
    } catch (e) {}
  });

  // ---- Web → 原生：状态回传 ----
  // Web 在状态切换时调用 CiraNative.reportState，原生据此联动浮窗/保活。
  CiraNative.reportState = function (state, detail) {
    if (!plugin) return;
    try { plugin.reportState({ state: state, detail: detail || null }); } catch (e) {}
  };

  // 启动时把 Core 地址写回 Web（setCoreUrl 在 Web 主脚本内定义）
  CiraNative.getConfig().then(function (cfg) {
    if (cfg && cfg.coreUrl) {
      window.CIRA_CONFIG = window.CIRA_CONFIG || {};
      window.CIRA_CONFIG.coreUrl = cfg.coreUrl;
      // 回填到 Web 的 API_BASE（window.CIRA.setCoreUrl 由主脚本暴露；window.CIRA_SET_CORE_URL 为顶层兜底）
      try { if (window.CIRA && window.CIRA.setCoreUrl) window.CIRA.setCoreUrl(cfg.coreUrl); } catch (e) {}
      try { if (window.CIRA_SET_CORE_URL) window.CIRA_SET_CORE_URL(cfg.coreUrl); } catch (e) {}
    }
    // 主动预申请麦克风+通知权限，避免首次按住说话卡在权限弹窗
    try { CiraNative.requestMicPermission().catch(function () {}); } catch (e) {}
    window.dispatchEvent(new CustomEvent('ciranative:ready', { detail: cfg || {} }));
  }).catch(function () {});

  console.log('[CIRA] 原生桥已挂载（Capacitor 环境）');
})();
