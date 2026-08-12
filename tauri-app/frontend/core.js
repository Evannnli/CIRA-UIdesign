/**
 * CIRA Core — 模块 1「What to say」  (LOCAL DEV STUB · 接口已冻结 v0.7)
 * ============================================================================
 * 本文件是【本地占位桩】: 仅为了让原型在脱离真实后端时也能离线跑起来。
 *
 * 真实模块 1 由其他团队在 GitHub 维护并替换。Device Runtime(app.js) 不依赖
 * 本文件内部实现, 只经 modules.js 暴露的 CIRA.Core.respond() 接口访问
 * (见 MODULE_INTERFACES.md)。接入真实模块时本文件可直接删除。
 *
 * ── ResponsePackage schema (冻结, 跨模块唯一契约对象) ──────────────────────
 * {
 *   packageId: string,                       // 唯一包 ID
 *   text: string,                            // 要表达的自然语言内容
 *   emotion: 'calm'|'curious'|'thinking'|'happy'|'worried',
 *   mode?:  'normal'|'quiet'|'story',
 *   priority?: 'normal'|'interrupt',
 *   ttsHints?: { rate?, pitch?, voice?, style? },   // 给模块 2 的发声建议
 *   presentationHints?: { pulse?: boolean },         // 给模块 3 的呈现提示
 *   endOfTurn?: boolean,
 * }
 * 注意: 唤醒本地应答「我在。」/「哎！」不属本模块(不进大模型), 由 Device Runtime 本地播放。
 * ============================================================================
 */
(function () {
  'use strict';

  const SCRIPTS = [
    '蝴蝶花真的很漂亮呢',
    '今天有什么想跟我聊聊的吗?',
    '我在听你说, 慢慢来.',
    '嗯嗯, 你是这样想的呀.',
    '我想了一下, 你说得有道理.',
    '要不要一起画一只小兔子?',
    '别担心, 我一直都在.',
    '那我们一起来想想办法吧.',
    '你刚刚说的, 我记住啦.',
  ];

  function makePackage(p) {
    return Object.assign({
      packageId: 'pkg_' + Math.random().toString(36).slice(2, 10),
      mode: 'normal',
      priority: 'normal',
      ttsHints: { rate: 1.0, pitch: 1.12, voice: 'vivi2.0' },
      presentationHints: {},
      endOfTurn: true,
    }, p);
  }

  function pickScript() {
    return SCRIPTS[Math.floor(Math.random() * SCRIPTS.length)];
  }

  function pickEmotion(heard) {
    if (/担心|不开心|怕|难过|哭/.test(heard)) return 'worried';
    if (/故事|讲|画|玩|游戏|猜/.test(heard)) return 'happy';
    return 'calm';
  }

  // ── 冻结接口: respond(input) -> Promise<ResponsePackage> ────────────────
  // 注册为本地桩 (modules.js 解析为 CIRA.Core)
  window.__CIRA_CORE_MOCK = {
    async respond(input) {
      const heard = (input && input.transcript) || '';
      const text = pickScript();
      const emotion = pickEmotion(heard);
      return makePackage({ text, emotion });
    },
  };

  // 调试/自检导出
  window.__ciraCore = { makePackage, SCRIPTS };
})();
