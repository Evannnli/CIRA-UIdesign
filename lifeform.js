/**
 * CIRA Light Lifeform Engine  v0.2 "Ethereal"
 * 光生命体渲染器 — 体积粒子光场
 *
 * v0.2 相对 v0.1 的核心改变 (解决"扁平化"问题):
 *   1. 三维球面粒子分布 + 透视投影  → 有前后景深, 不再是平面圆环
 *   2. 加色混合 (lighter)           → 粒子重叠处自然变亮, 这才是"光"而不是"贴纸"
 *   3. 运动拖尾层 (motion trail)     → 粒子留下光轨, 产生"飘渺""流动"感
 *   4. FBM 噪声场驱动形态             → 轮廓永远不规则, 有机呼吸, 不是完美圆
 *   5. 核心光由粒子聚集形成            → 去掉硬边实心圆, 中心是"雾核"不是"圆点"
 *   6. 三层粒子 (核心尘 / 主体云 / 游离星尘) + 色散 → 层次感
 *   7. Sprite 预渲染 + drawImage     → 250 粒子稳定 60fps
 *
 * 设计依据:
 *   - 《CIRA UX 设计规范 v0.1》§4 光生命体(核心光 + 粒子场 + 柔性形态)
 *   - 《交互需求文档》§5 动效基线
 *   - emotions.py 颜色映射 (暖橙/软粉/紫/暖白) — 全暖色, 无绿
 *
 * 导出:
 *   const lf = new LightLifeform(canvas)
 *   lf.setState('idle'|'listening'|'thinking'|'speaking'|'offline'|'wake')
 *   lf.setEmotion('calm'|'curious'|'happy'|'thinking'|'comfort'|'worried'|'sleepy')
 *   lf.setAudioLevel(0..1)
 *   lf.setTtsProgress(0..1)
 *   lf.pulse()
 *   lf.setDensity(0.4..1.6)   // 粒子密度倍率, 调试用
 *   lf.destroy()
 */

(function (global) {
  'use strict';

  // ---- 配色 (与 emotions.py / UX规范一致, 全暖色系, 永不出现绿) ----
  const PALETTE = {
    core:    '#FFE3BC',  // 核心光: 暖白 (偏橙, 避免屏幕色温推成绿)
    warm:    '#FF8A3D',  // 暖橙
    pink:    '#FF9EB5',  // 软粉
    purple:  '#A98CE0',  // 紫
    dimWhite:'#D8C0A8',  // 暖白弱化
    faint:   '#9A8270',  // 暖白很暗
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

  /**
   * 状态形态参数
   *  breath    呼吸幅度
   *  spread    整体扩散倍率
   *  coreGlow  中心雾核强度
   *  swirl     绕轴旋流速度 (rad/s)
   *  flow      噪声流动强度 (形变剧烈程度)
   *  ripple    声波环强度
   *  morph     形态模式
   *  trailFade 拖尾衰减速度 (越小拖尾越长)
   *  gain      整体亮度增益
   *  sag       整体下沉像素 (offline)
   */
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

  // ---- 轻量 FBM 噪声 (三角函数堆叠, 比 simplex 便宜, 视觉上足够有机) ----
  function fbm3(x, y, z, t) {
    return (
      Math.sin(x * 1.7 + t * 0.62) * Math.cos(y * 1.31 - t * 0.44) * 0.50 +
      Math.sin(y * 2.93 - t * 0.51) * Math.cos(z * 2.11 + t * 0.33) * 0.30 +
      Math.sin(z * 4.37 + t * 0.73) * Math.cos(x * 3.67 - t * 0.27) * 0.20
    );
  }

  // ---- 预渲染粒子精灵 (核心提速手段) ----
  function makeSprite(r, g, b, kind) {
    const S = 64;
    const c = document.createElement('canvas');
    c.width = S; c.height = S;
    const x = c.getContext('2d');
    const gr = x.createRadialGradient(S / 2, S / 2, 0, S / 2, S / 2, S / 2);

    if (kind === 'fog') {
      // 体积雾: 极柔, 无亮核
      gr.addColorStop(0.00, `rgba(${r},${g},${b},0.42)`);
      gr.addColorStop(0.22, `rgba(${r},${g},${b},0.20)`);
      gr.addColorStop(0.50, `rgba(${r},${g},${b},0.062)`);
      gr.addColorStop(0.78, `rgba(${r},${g},${b},0.014)`);
      gr.addColorStop(1.00, `rgba(${r},${g},${b},0)`);
    } else {
      // 粒子: 锐利的"星点" — 极小亮核 + 极短光晕
      // 星云的质感 = 成千上万个清晰小星点靠疏密堆叠, 不是大范围柔光
      // 亮核收到 0.10 内即接近实心, 0.34 后基本熄灭 → 单颗就是一个"点", 不糊
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
    constructor(canvas) {
      this.canvas = canvas;
      this.ctx = canvas.getContext('2d');
      this.dpr = Math.min(2, Math.max(1, window.devicePixelRatio || 1));

      this.state = 'idle';
      this.emotion = 'calm';
      this.audioLevel = 0.3;
      this.ttsProgress = 0.5;
      this.pulseEnergy = 0;
      this.density = 1.0;

      // 颜色: 平滑过渡
      this.colorTarget = hexToRgb(EMOTION_COLOR.calm);
      this.colorCurrent = { ...this.colorTarget };
      this._spriteKey = '';

      // 形态参数平滑插值 (状态切换不跳变)
      this.pf = { ...STATE_PROFILE.idle };

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

    // ---------- 粒子构建: 三层 3D 球面分布 ----------
    _buildParticles() {
      const d = this.density;
      // 注意 r0 从 0.045 起 — 最中心留"空腔", 让光从内部雾核透出来,
      // 而不是一坨颗粒糊在中间 (这是"扁平感"的主要来源)
      const layers = [
        // n, rMin, rMax, sizeMin, sizeMax, flowRate, spinMul, layerId
        // 星云化: 数量 ~3x, 单颗尺寸 ~½ → 极细密星点, 密度梯度(密核→疏边)造星云
        { n: Math.round(420 * d), r0: 0.030, r1: 0.130, s0: 0.45, s1: 1.15, flow: 1.35, spin: 1.55, id: 0 }, // 核心尘 (最密, 堆出中心亮)
        { n: Math.round(560 * d), r0: 0.130, r1: 0.270, s0: 0.40, s1: 1.00, flow: 0.85, spin: 1.00, id: 1 }, // 主体星云
        { n: Math.round(280 * d), r0: 0.270, r1: 0.420, s0: 0.34, s1: 0.85, flow: 0.45, spin: 0.55, id: 2 }, // 游离星尘
        { n: Math.round(140 * d), r0: 0.420, r1: 0.500, s0: 0.30, s1: 0.70, flow: 0.30, spin: 0.35, id: 3 }, // 外场散星 (极稀疏, 星云边缘)
      ];

      this.particles = [];
      for (const L of layers) {
        for (let i = 0; i < L.n; i++) {
          // Fibonacci 球面采样 → 方向均匀, 不会结块
          const yy = 1 - (i / Math.max(1, L.n - 1)) * 2;
          const rr = Math.sqrt(Math.max(0, 1 - yy * yy));
          const th = GOLDEN * i;

          const jitter = 0.16;
          const ux = Math.cos(th) * rr + (Math.random() - 0.5) * jitter;
          const uy = yy + (Math.random() - 0.5) * jitter;
          const uz = Math.sin(th) * rr + (Math.random() - 0.5) * jitter;
          const len = Math.hypot(ux, uy, uz) || 1;

          // 色散: 70% 主色, 18% 暖橙, 12% 软粉 → 光团内部有色彩层次
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
          });
        }
      }
    }

    _rebuildSprites(force) {
      const c = this.colorCurrent;
      // 量化到 12 级, 避免每帧重建
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

    // ---------- 公共 API ----------
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
    setDensity(v) {
      this.density = Math.max(0.3, Math.min(2.0, v));
      this._buildParticles();
    }
    destroy() {
      this._running = false;
      window.removeEventListener('resize', this._onResize);
    }

    // ---------- SLEEP 状态: 熄屏省电 ----------
    pause() {
      this._running = false;
      // 清屏 = 等同物理熄屏 (开发在设备上对应 LCD backlight off / OLED pixel off)
      try {
        this.tctx.clearRect(0, 0, this.trail.width, this.trail.height);
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        // 黑底矩形兜底, 防止某些浏览器不立即 commit clear
        this.ctx.fillStyle = '#000';
        this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
      } catch(e) {}
    }
    resume() {
      if (this._running) return;
      this._running = true;
      this._lastFrame = performance.now();
      this._t0 = performance.now();
      requestAnimationFrame(this._loop);
    }

    // ---------- 尺寸 / 图层 ----------
    _resize() {
      const rect = this.canvas.getBoundingClientRect();
      const w = Math.round(rect.width) || this.canvas.width || 360;
      this.size = w;
      this.canvas.width = w * this.dpr;
      this.canvas.height = w * this.dpr;
      this.canvas.style.width = w + 'px';
      this.canvas.style.height = w + 'px';
      this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);

      // 拖尾层 (离屏): 粒子全部画在这层, 每帧只擦掉一部分 → 形成光轨
      if (!this.trail) {
        this.trail = document.createElement('canvas');
        this.tctx = this.trail.getContext('2d');
      }
      this.trail.width = w * this.dpr;
      this.trail.height = w * this.dpr;
      this.tctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
      this.tctx.clearRect(0, 0, w, w);

      this._buildBackdrop(w);
    }

    /** 背景底色 + 暗角: 静态图层, 只在 resize 时重建 (省掉每帧两次 createRadialGradient) */
    _buildBackdrop(w) {
      const cx = w / 2, cy = w / 2;

      if (!this.bgLayer) {
        this.bgLayer = document.createElement('canvas');
        this.vgLayer = document.createElement('canvas');
      }
      for (const c of [this.bgLayer, this.vgLayer]) {
        c.width = w * this.dpr; c.height = w * this.dpr;
        c.getContext('2d').setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
      }

      // 极暗暖底 — 让光团有"空间", 不是浮在纸上
      const b = this.bgLayer.getContext('2d');
      const bg = b.createRadialGradient(cx, cy, 0, cx, cy, w * 0.52);
      bg.addColorStop(0.00, 'rgba(26,13,8,0.62)');
      bg.addColorStop(0.55, 'rgba(10,5,4,0.86)');
      bg.addColorStop(1.00, 'rgba(0,0,0,1)');
      b.fillStyle = bg;
      b.fillRect(0, 0, w, w);

      // 边缘暗角 — 增强"体积"错觉, 但不要压掉外层星尘
      const v = this.vgLayer.getContext('2d');
      v.clearRect(0, 0, w, w);
      const vg = v.createRadialGradient(cx, cy, w * 0.34, cx, cy, w * 0.50);
      vg.addColorStop(0.0, 'rgba(0,0,0,0)');
      vg.addColorStop(0.7, 'rgba(0,0,0,0.20)');
      vg.addColorStop(1.0, 'rgba(0,0,0,0.62)');
      v.fillStyle = vg;
      v.fillRect(0, 0, w, w);
    }

    // ---------- 主循环 ----------
    _loop(now) {
      if (!this._running) return;
      const dt = Math.min(0.05, (now - this._lastFrame) / 1000);
      this._lastFrame = now;
      const t = (now - this._t0) / 1000;

      // 颜色平滑
      const k = 1 - Math.exp(-dt * 3.2);
      this.colorCurrent.r += (this.colorTarget.r - this.colorCurrent.r) * k;
      this.colorCurrent.g += (this.colorTarget.g - this.colorCurrent.g) * k;
      this.colorCurrent.b += (this.colorTarget.b - this.colorCurrent.b) * k;
      this._rebuildSprites(false);

      // 形态参数平滑 (状态切换是"化"过去的, 不是"跳"过去的)
      const tgt = STATE_PROFILE[this.state] || STATE_PROFILE.idle;
      const km = 1 - Math.exp(-dt * 2.6);
      for (const key in this.pf) {
        if (typeof tgt[key] === 'number') this.pf[key] += (tgt[key] - this.pf[key]) * km;
      }
      this.pf.morph = tgt.morph;

      this.pulseEnergy *= Math.exp(-dt * 2.0);

      this._render(t, dt);
      requestAnimationFrame(this._loop);
    }

    // ---------- 渲染 ----------
    _render(t, dt) {
      const w = this.size;
      const cx = w / 2, cy = w / 2;
      const P = this.pf;
      const tctx = this.tctx;
      const pulse = this.pulseEnergy;

      // === A. 拖尾层: 先衰减旧帧 (帧率无关) ===
      const fade = 1 - Math.exp(-dt * P.trailFade);
      tctx.globalCompositeOperation = 'destination-out';
      tctx.globalAlpha = 1;
      tctx.fillStyle = `rgba(0,0,0,${fade})`;
      tctx.fillRect(0, 0, w, w);

      // 之后全部加色混合 → 光的叠加
      tctx.globalCompositeOperation = 'lighter';

      // 全局呼吸
      const breathScale = 1
        + Math.sin(t * 0.72) * P.breath
        + Math.sin(t * 1.63 + 1.3) * P.breath * 0.35
        + pulse * 0.26;

      const spread = P.spread * breathScale * (1 + pulse * 0.22);
      const gain = P.gain * (1 + pulse * 0.35);
      const audio = this.audioLevel;

      // === B. 中心雾核 (削弱: 从 5 层大雾砍到 3 层小淡辉) ===
      // 只保留极淡的底辉让中心不发黑; 中心真正的"亮"由密集核心尘粒子堆叠形成,
      // 不再靠一大团柔光糊出来 → 去掉"大模糊"的主要来源
      const coreN = 2;
      for (let i = 0; i < coreN; i++) {
        const ph = i * 1.7;
        // 每层雾核自身缓慢漂移 → 中心不是死的
        const dx = fbm3(2.1 + ph, 0.3, 1.1, t * 0.5) * w * 0.026;
        const dy = fbm3(0.7, 3.3 + ph, 2.2, t * 0.44) * w * 0.026;
        const rl = w * (0.050 + i * 0.045) * breathScale * (1 + audio * 0.10);
        // 亮度不规则起伏 (sin + 噪声): 中心也在"活动", 不是一块死光
        const flick = 0.78 + 0.14 * Math.sin(t * 1.1 + ph) + 0.10 * fbm3(ph, 2.4, 0.9, t * 0.8);
        const al = P.coreGlow * gain * (0.11 - i * 0.035) * flick;
        if (al <= 0) continue;
        tctx.globalAlpha = Math.max(0, Math.min(1, al));
        tctx.drawImage(this.sprFog, cx + dx - rl, cy + dy - rl + P.sag * 0.5, rl * 2, rl * 2);
      }
      // 最内层亮核: 极小极淡 → 只是"光源暗示", 中心真正的亮靠密集核心尘星点
      {
        const rl = w * (0.022 + 0.004 * Math.sin(t * 1.9)) * breathScale;
        const jx = fbm3(5.1, 1.7, 0.4, t * 0.7) * w * 0.010;
        const jy = fbm3(1.3, 4.9, 2.8, t * 0.63) * w * 0.010;
        tctx.globalAlpha = Math.min(1, P.coreGlow * gain * 0.30);
        tctx.drawImage(this.sprCore, cx + jx - rl, cy + jy - rl + P.sag * 0.5, rl * 2, rl * 2);
      }

      // === C. 粒子场 (3D 球面 + 噪声形变 + 透视) ===
      const swirl = t * P.swirl;
      const flowAmt = P.flow;

      for (let i = 0; i < this.particles.length; i++) {
        const p = this.particles[i];

        // 1) 噪声形变: 半径随 3D 噪声场起伏 → 轮廓永远不规则
        const nq = fbm3(p.ux * 2.3, p.uy * 2.3, p.uz * 2.3, t * p.flowRate * 0.6);
        let rad = p.r0 * spread * (1 + nq * 0.26 * flowAmt);

        // 2) 形态调制
        let extraSpin = 0, sagP = P.sag, alphaMul = 1;
        switch (P.morph) {
          case 'scatter': // 聆听: 外扩 + 随音量脉动
            rad *= 1 + audio * 0.28 + 0.08 * Math.sin(t * 3.4 + p.seed);
            break;
          case 'vortex':  // 思考: 内聚成漩涡, 越靠内转得越快
            rad *= 0.82 + 0.18 * Math.sin(t * 1.1 + p.seed * 0.3);
            extraSpin = (1.0 - p.r0 * 2.2) * t * 0.85;
            break;
          case 'wave':    // 说话: 沿纵向声波起伏
            rad *= 1 + 0.13 * Math.sin(t * 4.2 + p.uy * 5.0 + this.ttsProgress * TAU);
            break;
          case 'droop':   // 断网: 下沉 + 暗淡
            rad *= 0.92;
            sagP = P.sag * (0.5 + (p.uy + 1) * 0.5);
            alphaMul = 0.55;
            break;
          case 'burst':   // 唤醒: 猛然扩散
            rad *= 1 + pulse * 0.45;
            break;
          default:        // idle: 只有噪声 + 呼吸
            break;
        }

        // 3) 绕 Y 轴旋流 (立体旋转, 不是平面转圈)
        const a = swirl * p.spin + extraSpin;
        const cs = Math.cos(a), sn = Math.sin(a);
        const x = p.ux * cs - p.uz * sn;
        const z = p.ux * sn + p.uz * cs;
        const y = p.uy;

        // 4) 透视投影: z 越靠前, 越大越亮
        const persp = 1 / (1 - z * 0.36);
        const px = cx + x * rad * w * persp;
        const py = cy + y * rad * w * persp + sagP;

        const depth = (z + 1) * 0.5;              // 0=最远 1=最近
        const tw = 0.55 + 0.45 * Math.sin(t * p.twRate + p.twPhase); // 明灭

        let a2 = (0.075 + depth * 0.40) * tw * gain * alphaMul;
        if (p.layer === 3) a2 *= 0.40;            // 外场散星最淡
        if (p.layer === 2) a2 *= 0.60;            // 游离星尘更淡
        if (p.layer === 0) a2 *= 0.52;            // 核心尘压低, 防密集堆叠过曝成死白块
        if (a2 <= 0.004) continue;

        // 渲染直径大幅缩小 (5.2→3.1) + 最小 1.3px → 每颗是真正的"星点"而非光斑
        // 星云的朦胧完全交给"成千上万小点的疏密堆叠", 单颗不许糊
        const d = Math.max(1.3, p.size * persp * (0.6 + depth * 0.8) * 3.1);
        tctx.globalAlpha = Math.min(1, a2);
        tctx.drawImage(this.spr[p.tint], px - d / 2, py - d / 2, d, d);
      }

      // === D. 声波环 (聆听时, 画进拖尾层 → 环也会拖出残影) ===
      if (P.ripple > 0.02) {
        const c = this.colorCurrent;
        const rings = 3;
        tctx.globalAlpha = 1;
        for (let i = 0; i < rings; i++) {
          const ph = (t * (0.42 + audio * 0.55) + i / rings) % 1;
          const rr = w * (0.11 + ph * 0.36);
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
      ctx.clearRect(0, 0, w, w);

      // 圆屏裁切
      ctx.save();
      ctx.beginPath();
      ctx.arc(cx, cy, w / 2, 0, TAU);
      ctx.clip();

      ctx.drawImage(this.bgLayer, 0, 0, w, w);

      // 拖尾层加色合成 → 真正的光
      ctx.globalCompositeOperation = 'lighter';
      ctx.drawImage(this.trail, 0, 0, w, w);

      // 边缘暗角: 让光团聚焦在中心, 增强"体积"错觉
      ctx.globalCompositeOperation = 'source-over';
      ctx.drawImage(this.vgLayer, 0, 0, w, w);

      ctx.restore();
    }
  }

  global.LightLifeform = LightLifeform;
})(window);
