/**
 * CIRA 模块集成适配层 (Integration Adapter) — 模块3 (Device Runtime) 的唯一对外接缝
 * ============================================================================
 * Device Runtime (app.js) 只通过本文件访问模块 1 / 2, 绝不直接 import 具体实现。
 * 切换「本地 Mock ↔ 真实远程模块」只改下方 CIRA_INTEGRATION 配置, app.js 一行不用动。
 *
 * 真实模块 1 / 2 由其他团队在 GitHub 维护; 这里只定义「怎么连上它们」。
 * 接入真实模块时你需要提供给 Device Runtime 的信息见 MODULE_INTERFACES.md §7:
 *   - 模块 1 / 2 的仓库地址与版本
 *   - 传输方式 (ws / http) 与端点 URL / 鉴权
 *
 * 协议 (分布式): 见 MODULE_INTERFACES.md §4 —— WebSocket + JSON 消息。
 * ============================================================================
 */
(function () {
  'use strict';

  // ── 集成配置: 切换点 (Device Runtime 接模块 1/2 的唯一开关) ───────────────
  // 'local' = 用 core.js / language.js 的本地占位桩 (原型演示, 离线可跑)
  // 接真模块时改成: { type:'ws', url:'wss://你的模块端点' }
  //   · 模块1 (CIRA Core) 端点 → CIRA_INTEGRATION.core
  //   · 模块2 (Language System) 端点 → CIRA_INTEGRATION.language
  const CIRA_INTEGRATION = {
    core:     'local',
    language: 'local',
  };
  window.CIRA_INTEGRATION = CIRA_INTEGRATION;

  // ---- 进程内本地 Mock (默认) ----
  function localCore() { return window.__CIRA_CORE_MOCK; }
  function localLang() { return window.__CIRA_LANG_MOCK; }

  // ---- 远程 WebSocket 客户端 (真实模块 1/2 示例实现, 协议见 MODULE_INTERFACES.md §4) ----
  function makeWsClient(url, role) {
    let ws = null, openProm = null, seq = 0;
    const pending = new Map();
    function ensureOpen() {
      if (ws && ws.readyState === 1) return openProm || Promise.resolve(ws);
      openProm = new Promise((resolve, reject) => {
        try {
          ws = new WebSocket(url);
          ws.onopen = () => resolve(ws);
          ws.onerror = (e) => reject(e);
          ws.onmessage = (ev) => {
            let m; try { m = JSON.parse(ev.data); } catch (_) { return; }
            if (m.seq != null && pending.has(m.seq)) {
              const cb = pending.get(m.seq); pending.delete(m.seq); cb(m);
            }
          };
        } catch (e) { reject(e); }
      });
      return openProm;
    }
    if (role === 'core') {
      return {
        async respond(input) {
          const s = await ensureOpen();
          const mySeq = ++seq;
          return new Promise((resolve) => {
            pending.set(mySeq, (m) => resolve(m.package || m));
            s.send(JSON.stringify(Object.assign({ type: 'user_input', seq: mySeq }, input)));
          });
        },
      };
    }
    // role === 'lang'
    return {
      async synthesize(pkg) {
        const s = await ensureOpen();
        const mySeq = ++seq;
        return new Promise((resolve) => {
          pending.set(mySeq, (m) => resolve(remoteHandle(s, mySeq, m)));
          s.send(JSON.stringify({ type: 'synthesize', seq: mySeq, pkg }));
        });
      },
    };
  }

  function remoteHandle(ws, seq, meta) {
    let ended = false; const cbs = [];
    return {
      durationMs: meta && meta.durationMs,
      play() { try { ws.send(JSON.stringify({ type: 'audio_play', seq })); } catch (_) {} },
      stop() {
        if (!ended) { ended = true; cbs.forEach(c => c()); }
        try { ws.send(JSON.stringify({ type: 'interrupt', seq })); } catch (_) {}
      },
      onEnd(cb) { cbs.push(cb); },
    };
  }

  function resolve(cfg, role) {
    if (cfg === 'local') return role === 'core' ? localCore() : localLang();
    if (cfg && cfg.type === 'ws') return makeWsClient(cfg.url, role);
    throw new Error('未支持的集成配置: ' + JSON.stringify(cfg));
  }

  // ── 暴露给 app.js: 仅这两个入口, 内部实现可替换 ──────────────────────────
  window.CIRA = {
    Core:     resolve(CIRA_INTEGRATION.core, 'core'),
    Language: resolve(CIRA_INTEGRATION.language, 'lang'),
  };
})();
