/**
 * CIRA Light Lifeform Engine  v0.2.1 "Ethereal"  (安卓原型适配版)
 * 光生命体渲染器 — 体积粒子光场
 *
 * 与桌面 v0.7 同源 (cira-prototype/lifeform.js)，区别：
 *   - 支持 fullscreen 模式：铺满手机屏 (非 360 圆)，去掉 circle clip，靠暖色背景+暗角聚焦中心。
 *   - 复用同一套配色 / 三层球状粒子 / 加色混合 / 拖尾 / FBM 噪声形变 —— 外观与 v0.7 一致。
 *
 * 用法：
 *   new LightLifeform(canvas, { fullscreen: true })   // 铺满
 *   new LightLifeform(canvas)                          // 正方形圆 (场景B 小星云)
 *   .setState('idle'|'listening'|'thinking'|'speaking'|'offline'|'wake')
 *   .setEmotion('calm'|'curious'|'happy'|'thinking'|'comfort'|'worried'|'sleepy')
 *   .pulse()   // 戳一下 / 唤醒时的弹性脉冲
 */

(function (global) {
  'use strict';

  // ---- 配色 (与 emotions.py / UX规范一致, 全暖色系, 永不出现绿/蓝) ----
  const PALETTE = {
    core:     '#FFE3BC',  // 核心光: 暖白 (偏橙)
    warm:     '#FF8A3D',  // 暖橙
    pink:     '#FF9EB5',  // 软粉
    purple:   '#A98CE0',  // 紫
    dimWhite: '#D8C0A8',  // 暖白弱化
    faint:    '#9A8270',  // 暖白很暗
  };

  const EMOTION_COLOR = {
    calm:     PALETTE.core,
    curious:  PALETTE.warm,
    happy:    PALETTE.warm,
    thinking: PALETTE.purple,
    comfort:  PALETTE.pink,
    worried:  PALETTE.dimWhite,
    sleepy:   PALETTE.faint,
  };

  const STATE_PROFILE = {
    idle:      { breath:.040, spread:1.00, coreGlow:.55, swirl:.055, flow:.42, ripple:0,   morph:'sphere',  trailFade:7.5,  gain:1.00, sag:0  },
    listening: { breath:.060, spread:1.20, coreGlow:.72, swirl:.16,  flow:.78, ripple:1,   morph:'scatter', trailFade:9.5,  gain:1.12, sag:0  },
    thinking:  { breath:.028, spread:0.88, coreGlow:.88, swirl:.62,  flow:.98, ripple:0,   morph:'vortex',  trailFade:5.5,  gain:1.05, sag:0  },
    speaking:  { breath:.070, spread:1.06, coreGlow:.76, swirl:.10,  flow:.66, ripple:.45, morph:'wave',    trailFade:8.5,  gain:1.10, sag:0  },
    offline:   { breath:.030, spread:0.78, coreGlow:.20, swirl:.018, flow:.20, ripple:0,   morph:'droop',   trailFade:6.0,  gain:0.38, sag:22 },
    wake:      { breath:.100, spread:1.34, coreGlow:.98, swirl:.34,  flow:1.15,ripple:0,   morph:'burst',   trailFade:4.5,  gain:1.30, sag:0  },
  };

  const TAU = Math.PI * 2;
  const GOLDEN = Math.PI * (3 - Math.sqrt(5));

  function fbm3(x, y, z, t) {
    return (
      Math.sin(x * 1.7 + t * 0.62) * Math.cos(y * 1.31 - t * 0.44) * 0.50 +
      Math.sin(y * 2.93 - t * 0.51) * Math.cos(z * 2.11 + t * 0.33) * 0.30 +
      Math.sin(z * 4.37 + t * 0.73) * Math.cos(x * 3.67 - t * 0.27) * 0.20
    );
  }

  function makeSprite(r, g, b, kind) {
    const S = 64;
    const c = document.createElement('canvas');
    c.width = S; c.height = S;
    const x = c.getContext('2d');
    const gr = x.createRadialGradient(S / 2, S / 2, 0, S / 2, S / 2, S / 2);

    if (kind === 'fog') {
      gr.addColorStop(0.00, `rgba(${r},${g},${b},0.42)`);
      gr.addColorStop(0.22, `rgba(${r},${g},${b},0.20)`);
      gr.addColorStop(0.50, `rgba(${r},${g},${b},0.062)`);
      gr.addColorStop(0.78, `rgba(${r},${g},${b},0.014)`);
      gr.addColorStop(1.00, `rgba(${r},${g},${b},0)`);
    } else {
      gr.addColorStop(0.00, `rgba(${r},${g},${b},1)`);
      gr.addColorStop(0.10, `rgba(${r},${g},${b},0.95)`);
      gr.addColorStop(0.24, `rgba(${r},${g},${b},0.42)`);
      gr.addColorStop(0.42, `rgba(${r},${g},${b},0.11)`);
      gr.addColorStop(0.66, `rgba(${r},${g},${b},0.018)`);
      gr.addColorStop(1.00, `rgba(${r},${g},${b},0)`);
    }
    x.fillStyle = gr;
    x.fillRect(0, 0, S, S);
    return c;
  }

  function hexToRgb(hex) {
    const h = hex.replace('#', '');
    return {
      r: parseInt(h.substr(0, 2), 16),
      g: parseInt(h.substr(2, 2), 16),
      b: parseInt(h.substr(4, 2), 16),
    };
  }

  class LightLifeform {
    constructor(canvas, opts) {
      opts = opts || {};
      this.fullscreen = !!opts.fullscreen;
      this.canvas = canvas;
      this.ctx = canvas.getContext('2d');
      this.dpr = Math.min(2.5, Math.max(1, window.devicePixelRatio || 1));

      this.state = 'idle';
      this.emotion = 'calm';
      this.audioLevel = 0.3;
      this.ttsProgress = 0.5;
      this.pulseEnergy = 0;
      this.density = 1.0;

      this.colorTarget = hexToRgb(EMOTION_COLOR.calm);
      this.colorCurrent = { ...this.colorTarget };
      this._spriteKey = '';

      this.pf = { ...STATE_PROFILE.idle };

      // 触碰引力：手指处成为引力点，星云向其汇聚
      this.attract = 0;        // 当前影响强度 0..1 (平滑)
      this.attractTarget = 0;  // 手指按下=1，松开=0
      this.attractor = { x: 0, y: 0 };

      this._resize();
      this._buildParticles();
      this._rebuildSprites(true);

      this._t0 = performance.now();
      this._lastFrame = this._t0;
      this._running = true;
      this._loop = this._loop.bind(this);
      requestAnimationFrame(this._loop);

      this._onResize = () => { this._resize(); this._buildParticles(); };
      window.addEventListener('resize', this._onResize);
    }

    _buildParticles() {
      const d = this.density;
      const layers = [
        { n: Math.round(420 * d), r0: 0.030, r1: 0.130, s0: 0.45, s1: 1.15, flow: 1.35, spin: 1.55, id: 0 },
        { n: Math.round(560 * d), r0: 0.130, r1: 0.270, s0: 0.40, s1: 1.00, flow: 0.85, spin: 1.00, id: 1 },
        { n: Math.round(280 * d), r0: 0.270, r1: 0.420, s0: 0.34, s1: 0.85, flow: 0.45, spin: 0.55, id: 2 },
        { n: Math.round(140 * d), r0: 0.420, r1: 0.500, s0: 0.30, s1: 0.70, flow: 0.30, spin: 0.35, id: 3 },
        { n: Math.round(340 * d), r0: 0.006, r1: 0.055, s0: 0.70, s1: 1.70, flow: 1.70, spin: 2.30, id: 4 }, // 中心聚集小星群 (亮、密、紧)
      ];

      this.particles = [];
      for (const L of layers) {
        for (let i = 0; i < L.n; i++) {
          const yy = 1 - (i / Math.max(1, L.n - 1)) * 2;
          const rr = Math.sqrt(Math.max(0, 1 - yy * yy));
          const th = GOLDEN * i;

          const jitter = 0.16;
          const ux = Math.cos(th) * rr + (Math.random() - 0.5) * jitter;
          const uy = yy + (Math.random() - 0.5) * jitter;
          const uz = Math.sin(th) * rr + (Math.random() - 0.5) * jitter;
          const len = Math.hypot(ux, uy, uz) || 1;

          const roll = Math.random();
          const tint = roll < 0.70 ? 0 : (roll < 0.88 ? 1 : 2);

          this.particles.push({
            ux: ux / len, uy: uy / len, uz: uz / len,
            r0: L.r0 + Math.random() * (L.r1 - L.r0),
            size: L.s0 + Math.random() * (L.s1 - L.s0),
            flowRate: L.flow * (0.7 + Math.random() * 0.6),
            spin: L.spin * (0.75 + Math.random() * 0.5),
            layer: L.id,
            tint,
            seed: Math.random() * 100,
            twPhase: Math.random() * TAU,
            twRate: 0.35 + Math.random() * 1.3,
            ax: 0, ay: 0,   // 触碰吸力的缓动位移量 (相对原轨道)
          });
        }
      }
    }

    _rebuildSprites(force) {
      const c = this.colorCurrent;
      const key = `${(c.r / 12) | 0}_${(c.g / 12) | 0}_${(c.b / 12) | 0}`;
      if (!force && key === this._spriteKey) return;
      this._spriteKey = key;

      const w = hexToRgb(PALETTE.warm);
      const p = hexToRgb(PALETTE.pink);
      const core = hexToRgb(PALETTE.core);

      this.spr = [
        makeSprite(c.r | 0, c.g | 0, c.b | 0, 'dot'),
        makeSprite(w.r, w.g, w.b, 'dot'),
        makeSprite(p.r, p.g, p.b, 'dot'),
      ];
      this.sprFog  = makeSprite(c.r | 0, c.g | 0, c.b | 0, 'fog');
      this.sprCore = makeSprite(core.r, core.g, core.b, 'fog');
    }

    setState(s) {
      if (!STATE_PROFILE[s]) s = 'idle';
      if (this.state === 'idle' && s !== 'idle') this.pulse();
      this.state = s;
    }
    setEmotion(e) {
      this.emotion = e || 'calm';
      this.colorTarget = hexToRgb(EMOTION_COLOR[this.emotion] || EMOTION_COLOR.calm);
    }
    setAudioLevel(v) { this.audioLevel = Math.max(0, Math.min(1, v)); }
    setTtsProgress(v) { this.ttsProgress = Math.max(0, Math.min(1, v)); }
    pulse() { this.pulseEnergy = 1.0; }
    // 触碰引力：手指落点成为引力中心，星云向其汇聚
    setAttractor(x, y) { this.attractor.x = x; this.attractor.y = y; this.attractTarget = 1; }
    clearAttractor() { this.attractTarget = 0; }
    setDensity(v) {
      this.density = Math.max(0.3, Math.min(2.0, v));
      this._buildParticles();
    }
    destroy() {
      this._running = false;
      window.removeEventListener('resize', this._onResize);
    }
    pause() {
      this._running = false;
      try {
        this.tctx.clearRect(0, 0, this.trail.width, this.trail.height);
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        this.ctx.fillStyle = '#000';
        this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
      } catch (e) {}
    }
    resume() {
      if (this._running) return;
      this._running = true;
      this._lastFrame = performance.now();
      this._t0 = performance.now();
      requestAnimationFrame(this._loop);
    }

    _resize() {
      const rect = this.canvas.getBoundingClientRect();
      const w = Math.round(rect.width) || this.canvas.width || 360;
      const h = Math.round(rect.height) || this.canvas.height || 360;
      this.W = w; this.H = h;
      this.cx = w / 2; this.cy = h / 2;
      this.base = Math.min(w, h);

      this.canvas.width = w * this.dpr;
      this.canvas.height = h * this.dpr;
      this.canvas.style.width = w + 'px';
      this.canvas.style.height = h + 'px';
      this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);

      if (!this.trail) {
        this.trail = document.createElement('canvas');
        this.tctx = this.trail.getContext('2d');
      }
      this.trail.width = w * this.dpr;
      this.trail.height = h * this.dpr;
      this.tctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
      this.tctx.clearRect(0, 0, w, h);

      this._buildBackdrop(w, h);
    }

    _buildBackdrop(w, h) {
      const cx = w / 2, cy = h / 2, base = Math.min(w, h);

      if (!this.bgLayer) {
        this.bgLayer = document.createElement('canvas');
        this.vgLayer = document.createElement('canvas');
      }
      for (const c of [this.bgLayer, this.vgLayer]) {
        c.width = w * this.dpr; c.height = h * this.dpr;
        c.getContext('2d').setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
      }

      // 极暗暖底 — 让光团有"空间"
      const b = this.bgLayer.getContext('2d');
      const bg = b.createRadialGradient(cx, cy, 0, cx, cy, base * 0.52);
      bg.addColorStop(0.00, 'rgba(26,13,8,0.62)');
      bg.addColorStop(0.55, 'rgba(10,5,4,0.86)');
      bg.addColorStop(1.00, 'rgba(0,0,0,1)');
      b.fillStyle = bg;
      b.fillRect(0, 0, w, h);

      // 边缘暗角 — 增强"体积"
      const v = this.vgLayer.getContext('2d');
      v.clearRect(0, 0, w, h);
      const vg = v.createRadialGradient(cx, cy, base * 0.34, cx, cy, base * 0.50);
      vg.addColorStop(0.0, 'rgba(0,0,0,0)');
      vg.addColorStop(0.7, 'rgba(0,0,0,0.20)');
      vg.addColorStop(1.0, 'rgba(0,0,0,0.62)');
      v.fillStyle = vg;
      v.fillRect(0, 0, w, h);
    }

    _loop(now) {
      if (!this._running) return;
      const dt = Math.min(0.05, (now - this._lastFrame) / 1000);
      this._lastFrame = now;
      const t = (now - this._t0) / 1000;

      const k = 1 - Math.exp(-dt * 3.2);
      this.colorCurrent.r += (this.colorTarget.r - this.colorCurrent.r) * k;
      this.colorCurrent.g += (this.colorTarget.g - this.colorCurrent.g) * k;
      this.colorCurrent.b += (this.colorTarget.b - this.colorCurrent.b) * k;
      this._rebuildSprites(false);

      const tgt = STATE_PROFILE[this.state] || STATE_PROFILE.idle;
      const km = 1 - Math.exp(-dt * 2.6);
      for (const key in this.pf) {
        if (typeof tgt[key] === 'number') this.pf[key] += (tgt[key] - this.pf[key]) * km;
      }
      this.pf.morph = tgt.morph;

      this.pulseEnergy *= Math.exp(-dt * 2.0);

      // 触碰引力包络：手指按下=1，松开=0 (整体强度). 逐粒"缓慢汇入"由下方缓动实现
      const aRate = this.attractTarget > this.attract ? 5.0 : 2.2;
      this.attract += (this.attractTarget - this.attract) * (1 - Math.exp(-dt * aRate));

      this._render(t, dt);
      requestAnimationFrame(this._loop);
    }

    _render(t, dt) {
      const W = this.W, H = this.H, cx = this.cx, cy = this.cy, base = this.base;
      const P = this.pf;
      const tctx = this.tctx;
      const pulse = this.pulseEnergy;
      const at = this.attract;   // 触碰引力强度 0..1

      // === A. 拖尾层衰减 ===
      const fade = 1 - Math.exp(-dt * P.trailFade);
      tctx.globalCompositeOperation = 'destination-out';
      tctx.globalAlpha = 1;
      tctx.fillStyle = `rgba(0,0,0,${fade})`;
      tctx.fillRect(0, 0, W, H);

      tctx.globalCompositeOperation = 'lighter';

      const breathScale = 1
        + Math.sin(t * 0.72) * P.breath
        + Math.sin(t * 1.63 + 1.3) * P.breath * 0.35
        + pulse * 0.26;

      const spread = P.spread * breathScale * (1 + pulse * 0.22);
      const gain = P.gain * (1 + pulse * 0.35) + at * 0.18;
      const audio = this.audioLevel;

      // === B. 中心雾核 ===
      const coreN = 2;
      for (let i = 0; i < coreN; i++) {
        const ph = i * 1.7;
        const dx = fbm3(2.1 + ph, 0.3, 1.1, t * 0.5) * base * 0.026;
        const dy = fbm3(0.7, 3.3 + ph, 2.2, t * 0.44) * base * 0.026;
        const rl = base * (0.050 + i * 0.045) * breathScale * (1 + audio * 0.10);
        const flick = 0.78 + 0.14 * Math.sin(t * 1.1 + ph) + 0.10 * fbm3(ph, 2.4, 0.9, t * 0.8);
        const al = P.coreGlow * gain * (0.11 - i * 0.035) * flick;
        if (al <= 0) continue;
        tctx.globalAlpha = Math.max(0, Math.min(1, al));
        tctx.drawImage(this.sprFog, cx + dx - rl, cy + dy - rl + P.sag * 0.5, rl * 2, rl * 2);
      }
      {
        const rl = base * (0.022 + 0.004 * Math.sin(t * 1.9)) * breathScale;
        const jx = fbm3(5.1, 1.7, 0.4, t * 0.7) * base * 0.010;
        const jy = fbm3(1.3, 4.9, 2.8, t * 0.63) * base * 0.010;
        tctx.globalAlpha = Math.min(1, P.coreGlow * gain * 0.30);
        tctx.drawImage(this.sprCore, cx + jx - rl, cy + jy - rl + P.sag * 0.5, rl * 2, rl * 2);
      }

      // === C. 粒子场 (3D 球面 + 噪声形变 + 透视) ===
      const swirl = t * P.swirl;
      const flowAmt = P.flow;

      for (let i = 0; i < this.particles.length; i++) {
        const p = this.particles[i];

        const nq = fbm3(p.ux * 2.3, p.uy * 2.3, p.uz * 2.3, t * p.flowRate * 0.6);
        let rad = p.r0 * spread * (1 + nq * 0.26 * flowAmt);

        let extraSpin = 0, sagP = P.sag, alphaMul = 1;
        switch (P.morph) {
          case 'scatter':
            rad *= 1 + audio * 0.28 + 0.08 * Math.sin(t * 3.4 + p.seed);
            break;
          case 'vortex':
            rad *= 0.82 + 0.18 * Math.sin(t * 1.1 + p.seed * 0.3);
            extraSpin = (1.0 - p.r0 * 2.2) * t * 0.85;
            break;
          case 'wave':
            rad *= 1 + 0.13 * Math.sin(t * 4.2 + p.uy * 5.0 + this.ttsProgress * TAU);
            break;
          case 'droop':
            rad *= 0.92;
            sagP = P.sag * (0.5 + (p.uy + 1) * 0.5);
            alphaMul = 0.55;
            break;
          case 'burst':
            rad *= 1 + pulse * 0.45;
            break;
        }

        const a = swirl * p.spin + extraSpin;
        const cs = Math.cos(a), sn = Math.sin(a);
        const x = p.ux * cs - p.uz * sn;
        const z = p.ux * sn + p.uz * cs;
        const y = p.uy;

        const persp = 1 / (1 - z * 0.36);
        const bx = cx + x * rad * base * persp;       // 原轨道位置 (自转仍在)
        const by = cy + y * rad * base * persp + sagP;

        // 触碰引力 = "宇宙中多了一个引力点"：无硬边界，整片星云都感受吸引，
        // 随距离自然衰减但永不为零 → 近处猛、远处缓，随自转源源不断汇入手指处的点；
        // 松手 at→0，偏移缓动回原轨道(宇宙复原)。中心小星群(层4)几乎不被吸。
        let tox = 0, toy = 0;
        if (at > 0.001) {
          const gx = this.attractor.x, gy = this.attractor.y;
          const ddx = gx - bx, ddy = gy - by;
          const dist = Math.hypot(ddx, ddy) || 1;
          const Rs = base * 0.26;                     // 引力井尺度(非硬边界，只控制衰减快慢)
          const eff = 1 / (1 + Math.pow(dist / Rs, 1.8)); // 随距离自然衰减，dist→∞ 时→0 但永不为0=持续吸引
          const layerDamp = p.layer === 4 ? 0.05 : (p.layer === 0 ? 0.72 : 1.0);
          const coreR = base * 0.028;                 // 汇聚成的"点"半径(不大，不变)
          const close = Math.min(1, at * eff * layerDamp * 1.40); // 0..1：收拢比例(中心增益)
          const targetDist = coreR + (dist - coreR) * (1 - close);
          const pull = dist - targetDist;             // 朝点收拢的位移量(随收拢→0)
          const ux = ddx / dist, uy = ddy / dist;
          tox = ux * pull - uy * pull * 0.18;         // 径向吸引 + 轻微切向旋吸(近点即归零)
          toy = uy * pull + ux * pull * 0.18;
        }
        // 每颗粒子缓动逼近目标位移：吸引时渐进汇入，松手时缓慢落回原轨道
        const offMag2 = p.ax * p.ax + p.ay * p.ay;
        const tgtMag2 = tox * tox + toy * toy;
        const approaching = tgtMag2 > offMag2;
        const erate = approaching ? (1 - Math.exp(-dt * 2.3)) : (1 - Math.exp(-dt * 0.85));
        p.ax += (tox - p.ax) * erate;
        p.ay += (toy - p.ay) * erate;

        const px = bx + p.ax;
        const py = by + p.ay;

        const depth = (z + 1) * 0.5;
        const tw = 0.55 + 0.45 * Math.sin(t * p.twRate + p.twPhase);

        let a2 = (0.075 + depth * 0.40) * tw * gain * alphaMul;
        if (p.layer === 3) a2 *= 0.40;
        if (p.layer === 2) a2 *= 0.60;
        if (p.layer === 0) a2 *= 0.52;
        if (p.layer === 4) a2 *= 0.95;   // 中心小星群：保持明亮
        if (a2 <= 0.004) continue;

        const d = Math.max(1.3, p.size * persp * (0.6 + depth * 0.8) * 3.1);
        tctx.globalAlpha = Math.min(1, a2);
        tctx.drawImage(this.spr[p.tint], px - d / 2, py - d / 2, d, d);
      }

      // === D. 声波环 ===
      if (P.ripple > 0.02) {
        const c = this.colorCurrent;
        const rings = 3;
        tctx.globalAlpha = 1;
        for (let i = 0; i < rings; i++) {
          const ph = (t * (0.42 + audio * 0.55) + i / rings) % 1;
          const rr = base * (0.11 + ph * 0.36);
          const ra = (1 - ph) * (1 - ph) * 0.30 * P.ripple * (0.35 + audio * 0.85);
          tctx.beginPath();
          tctx.arc(cx, cy, rr, 0, TAU);
          tctx.strokeStyle = `rgba(${c.r | 0},${c.g | 0},${c.b | 0},${ra})`;
          tctx.lineWidth = 1.1 + audio * 1.4;
          tctx.stroke();
        }
      }

      tctx.globalAlpha = 1;
      tctx.globalCompositeOperation = 'source-over';

      // === E. 合成到主画布 ===
      const ctx = this.ctx;
      ctx.globalCompositeOperation = 'source-over';
      ctx.globalAlpha = 1;
      ctx.clearRect(0, 0, W, H);

      if (!this.fullscreen) {
        ctx.save();
        ctx.beginPath();
        ctx.arc(cx, cy, base / 2, 0, TAU);
        ctx.clip();
      }

      ctx.drawImage(this.bgLayer, 0, 0, W, H);
      ctx.globalCompositeOperation = 'lighter';
      ctx.drawImage(this.trail, 0, 0, W, H);
      ctx.globalCompositeOperation = 'source-over';
      ctx.drawImage(this.vgLayer, 0, 0, W, H);

      if (!this.fullscreen) ctx.restore();
    }
  }

  global.LightLifeform = LightLifeform;
})(window);
