/**
 * Language System — 模块 2「How to say」  (LOCAL DEV STUB · 接口已冻结 v0.7)
 * ============================================================================
 * 本文件是【本地占位桩】: 用浏览器 Web Speech API 本地合成, 仅为了让原型离线跑起来。
 *
 * 真实模块 2 由其他团队在 GitHub 维护(接入 vivi2.0 等音色 TTS)并替换。
 * Device Runtime(app.js) 不依赖本文件内部, 只经 modules.js 暴露的
 * CIRA.Language.synthesize() 接口访问 (见 MODULE_INTERFACES.md)。接入真实模块时本文件可直接删除。
 *
 * ── AudioHandle schema (冻结) ────────────────────────────────────────────
 * {
 *   play(): void,                 // 开始播放
 *   stop(): void,                 // 立即停止 (用于唤醒打断当前播报)
 *   onEnd(cb: ()=>void): void,    // 播放结束 / 被打断时回调
 *   durationMs?: number,          // 预估时长(ms), 可选
 * }
 * ============================================================================
 */
(function () {
  'use strict';

  // 注册为本地桩 (modules.js 解析为 CIRA.Language)
  window.__CIRA_LANG_MOCK = {
    async synthesize(pkg) {
      const text = (pkg && pkg.text) || '';
      const hints = (pkg && pkg.ttsHints) || {};
      const rate = (hints.rate != null) ? hints.rate : 1.0;
      const pitch = (hints.pitch != null) ? hints.pitch : 1.12;

      let ended = false;
      const endCbs = [];

      const handle = {
        durationMs: Math.max(1400, text.length * 180),
        play() {
          try {
            const s = window.speechSynthesis;
            if (!s) {  // 无 TTS 环境: 用计时模拟结束
              setTimeout(() => { if (!ended) { ended = true; endCbs.forEach(cb => cb()); } }, handle.durationMs);
              return;
            }
            const u = new SpeechSynthesisUtterance(text);
            u.lang = 'zh-CN'; u.rate = rate; u.pitch = pitch; u.volume = 1.0;
            u.onend = () => { if (!ended) { ended = true; endCbs.forEach(cb => cb()); } };
            u.onerror = () => { if (!ended) { ended = true; endCbs.forEach(cb => cb()); } };
            s.cancel(); s.speak(u);
          } catch (_) {
            setTimeout(() => { if (!ended) { ended = true; endCbs.forEach(cb => cb()); } }, handle.durationMs);
          }
        },
        stop() {
          try { if (window.speechSynthesis) window.speechSynthesis.cancel(); } catch (_) {}
          if (!ended) { ended = true; endCbs.forEach(cb => cb()); }
        },
        onEnd(cb) { endCbs.push(cb); },
      };
      return handle;
    },
  };
})();
