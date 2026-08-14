/**
 * cira-phone.js — 手机 / 独立窗口(app) 适配 (Device Runtime 形态层, 不影响冻结逻辑)
 * ----------------------------------------------------------------------------
 * 1) 注册 Service Worker (仅在安全上下文/支持时; 失败静默忽略, 不影响渲染)
 * 2) 把 360×360 圆屏按视口缩放填满 (真机像素不变)
 * 3) 提供浮起调试面板开关 (上机测试时仍能驱动状态/情绪/对话流)
 */
(function () {
  'use strict';

  // ── 1. Service Worker (离线壳) ──
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () {
      navigator.serviceWorker.register('./sw.js').catch(function () {
        /* 非安全上下文(LAN http)不注册, 页面照常渲染 */
      });
    });
  }

  // ── 2/3. 手机形态 ──
  function isPhone() {
    return (
      window.matchMedia('(max-width: 560px)').matches ||
      window.matchMedia('(display-mode: standalone)').matches ||
      ('standalone' in window.navigator && window.navigator.standalone === true)
    );
  }

  function fit() {
    if (!isPhone()) return;
    var shell = document.getElementById('device-shell');
    if (!shell) return;
    var m = Math.min(window.innerWidth, window.innerHeight) * 0.92;
    var scale = m / 360;
    shell.style.setProperty('--cira-scale', scale.toFixed(3));
  }

  function setupDebugToggle() {
    if (!isPhone()) return;
    if (document.getElementById('cira-debug-toggle')) return;
    var btn = document.createElement('button');
    btn.id = 'cira-debug-toggle';
    btn.textContent = '⚙';
    btn.setAttribute('aria-label', '调试面板');
    document.body.appendChild(btn);
    var panel = document.querySelector('.control-panel');
    btn.addEventListener('click', function () {
      if (panel) panel.classList.toggle('open');
    });
  }

  window.addEventListener('resize', fit);
  window.addEventListener('orientationchange', fit);

  function init() { fit(); setupDebugToggle(); }
  if (document.readyState !== 'loading') init();
  else document.addEventListener('DOMContentLoaded', init);
})();
