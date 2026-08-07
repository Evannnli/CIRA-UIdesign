/**
 * CIRA Web 交互原型 — 主控制器  (v0.3)
 *
 * 职责:
 *   - 状态机 (Idle / Listening / Thinking / Speaking / Settings / Offline)
 *   - 触摸交互 (点按唤醒, 长按 1.2s 进 Settings)
 *   - Settings 多视图导航 (home / wifi / wifi-pwd / wifi-detail /
 *       bluetooth / bt-detail / volume / brightness / mode)
 *   - Wi-Fi 完整链路: 开关 / 自动搜索 + 重新搜索 / 点击连接 / 屏内键盘输入密码 / 忘掉此网络
 *   - 蓝牙完整链路: 开关 / 扫描 / 配对连接 / 已配对设备 / 忽略此设备
 *   - 音量滑杆 (0–100) / 屏幕亮度滑杆 (1–400 nit, 实时遮罩)
 *   - 模拟对话脚本 (Listening 接收字幕 → Thinking → Speaking 输出字幕 → 回 Idle)
 *   - 控制面板: 状态切换 / 情绪切换 / 输入字幕 / 模拟异常 / 视觉调参
 */

(function () {
  'use strict';

  // ============================================================
  //  引用
  // ============================================================
  const canvas      = document.getElementById('lifeform');
  const stateBadge  = document.getElementById('state-badge');
  const stateDot    = stateBadge.querySelector('.dot');
  const stateLabel  = document.getElementById('state-label');
  const subtitle    = document.getElementById('subtitle');
  const settings    = document.getElementById('settings-panel');
  const offline     = document.getElementById('offline-banner');
  const brightnessOverlay = document.getElementById('brightness-overlay');

  // 启动光生命体
  const lf = new LightLifeform(canvas);
  lf.setState('idle');
  lf.setEmotion('calm');

  // ============================================================
  //  状态机
  // ============================================================
  const STATES = {
    IDLE: 'idle',
    LISTENING: 'listening',
    THINKING: 'thinking',
    SPEAKING: 'speaking',
    SETTINGS: 'settings',
    OFFLINE: 'offline',
  };
  let currentState = STATES.IDLE;

  const STATE_EMOTION = {
    idle: 'calm', listening: 'curious', thinking: 'thinking',
    speaking: 'happy', offline: 'worried', settings: 'calm',
  };
  const STATE_COLOR = {
    idle: '#FF8A3D', listening: '#FF8A3D', thinking: '#A98CE0',
    speaking: '#FF8A3D', offline: '#FF9EB5', settings: '#FFFFFF',
  };

  function transition(next, opts = {}) {
    currentState = next;

    // 设置浮层: 进入显示并回到主菜单 / 退出隐藏
    if (next === STATES.SETTINGS) {
      settings.classList.add('show');
      resetSettingsToHome();
    } else {
      settings.classList.remove('show');
    }

    lf.setState(next);
    lf.setEmotion(opts.emotion || STATE_EMOTION[next]);

    stateLabel.textContent = next;
    stateDot.style.background = STATE_COLOR[next];
    stateDot.style.boxShadow = `0 0 8px ${STATE_COLOR[next]}`;
    stateBadge.style.borderColor = hexToRGBA(STATE_COLOR[next], 0.25);

    // 字幕: 仅 Listening(接收) / Speaking(输出) 显示
    if (next !== STATES.SPEAKING && next !== STATES.LISTENING) {
      subtitle.classList.remove('show', 'listening');
    }

    offline.classList.toggle('show', next === STATES.OFFLINE);

    document.querySelectorAll('[data-state]').forEach(b => {
      b.classList.toggle('active', b.dataset.state === next);
    });
  }

  function hexToRGBA(hex, a) {
    const h = hex.replace('#', '');
    return `rgba(${parseInt(h.substr(0,2),16)},${parseInt(h.substr(2,2),16)},${parseInt(h.substr(4,2),16)},${a})`;
  }

  // ============================================================
  //  Settings 多视图导航
  // ============================================================
  const svStack = document.getElementById('sv-stack');
  const views = {};
  svStack.querySelectorAll('.sv').forEach(s => { views[s.dataset.view] = s; });
  let currentView = 'home';
  let viewHistory = ['home'];

  function showView(name) {
    const from = views[currentView];
    const to = views[name];
    if (!to || name === currentView) return;
    if (from) {
      from.classList.remove('sv-active');
      from.classList.add('sv-leaving');
      setTimeout(() => from.classList.remove('sv-leaving'), 240);
    }
    to.classList.add('sv-active');
    currentView = name;

    // 各视图进入钩子
    if (name === 'wifi')       onEnterWifi();
    if (name === 'bluetooth')  onEnterBt();
    if (name === 'volume')     setVolume(volume);
    if (name === 'brightness') setBrightness(brightnessNit);
  }

  function gotoView(name) {
    viewHistory.push(name);
    showView(name);
  }

  function backView() {
    if (viewHistory.length <= 1) return;
    viewHistory.pop();
    showView(viewHistory[viewHistory.length - 1]);
  }

  function resetSettingsToHome() {
    Object.values(views).forEach(v => v.classList.remove('sv-active', 'sv-leaving'));
    views.home.classList.add('sv-active');
    currentView = 'home';
    viewHistory = ['home'];
  }

  // 主菜单跳转
  document.querySelectorAll('[data-goto]').forEach(btn => {
    btn.addEventListener('click', () => gotoView(btn.dataset.goto));
  });
  // 返回按钮
  document.querySelectorAll('[data-back]').forEach(btn => {
    btn.addEventListener('click', backView);
  });

  // ============================================================
  //  Wi-Fi 交互链路
  // ============================================================
  const WIFI_NETWORKS = [
    { ssid: 'CIRA_Home',      sec: 'WPA2', signal: 3, saved: true },
    { ssid: 'TP-LINK_5G',     sec: 'WPA2', signal: 3, saved: false },
    { ssid: 'Xiaomi_A18',     sec: 'WPA2', signal: 2, saved: false },
    { ssid: 'ChinaNet-2.4G',  sec: 'WPA',  signal: 2, saved: false },
    { ssid: 'CoffeeHouse',    sec: 'open', signal: 1, saved: false },
    { ssid: 'Room-1502',      sec: 'WPA2', signal: 1, saved: false },
  ];
  let wifiOn = true;
  let wifiConnectedSSID = 'CIRA_Home';
  let wifiScanTimer = null;
  let pendingNet = null;
  let detailNet = null;

  const wifiSwitch  = document.getElementById('wifi-switch');
  const wifiScanRow = document.getElementById('wifi-scan-row');
  const netList     = document.getElementById('net-list');
  const miWifi      = document.getElementById('mi-wifi');

  function sigDots(n) {
    let s = '';
    for (let i = 1; i <= 3; i++) s += (i <= n ? '●' : '○');
    return `<span class="ni-sig">${s}</span>`;
  }

  function updateWifiLabel() {
    miWifi.textContent = !wifiOn ? '关闭' : (wifiConnectedSSID || '未连接');
  }

  function renderNetList() {
    netList.innerHTML = '';
    const nets = WIFI_NETWORKS.slice().sort((a, b) => {
      if (a.ssid === wifiConnectedSSID) return -1;
      if (b.ssid === wifiConnectedSSID) return 1;
      return b.signal - a.signal;
    });
    nets.forEach(net => {
      const item = document.createElement('button');
      item.className = 'net-item' + (net.ssid === wifiConnectedSSID ? ' connected' : '');
      item.innerHTML =
        `<span class="ni-name">${net.ssid}</span>` +
        (net.ssid === wifiConnectedSSID ? '<span class="badge-conn">已连接</span>' : '') +
        (net.sec !== 'open' ? '<span class="ni-lock">🔒</span>' : '') +
        sigDots(net.signal);
      item.addEventListener('click', () => onClickNet(net));
      netList.appendChild(item);
    });
  }

  function scanWifi() {
    if (!wifiOn) return;
    wifiScanRow.style.display = 'flex';
    netList.innerHTML = '';
    clearTimeout(wifiScanTimer);
    wifiScanTimer = setTimeout(() => {
      wifiScanRow.style.display = 'none';
      renderNetList();
    }, 1600);
  }

  function onEnterWifi() {
    views.wifi.classList.toggle('off', !wifiOn);
    wifiSwitch.checked = wifiOn;
    updateWifiLabel();
    if (wifiOn && !netList.children.length) scanWifi();
  }

  function onClickNet(net) {
    if (net.ssid === wifiConnectedSSID) {   // 已连接 → 详情
      detailNet = net;
      fillWifiDetail(net);
      gotoView('wifi-detail');
      return;
    }
    if (net.saved || net.sec === 'open') {  // 已保存 / 开放网络 → 直接连
      connectWifi(net.ssid);
      return;
    }
    // 加密且未保存 → 输入密码
    pendingNet = net;
    pwdValue = '';
    pwdMasked = true;
    document.getElementById('pwd-ssid-label').textContent = net.ssid;
    renderPwd();
    gotoView('wifi-pwd');
  }

  function connectWifi(ssid) {
    wifiConnectedSSID = ssid;
    const net = WIFI_NETWORKS.find(n => n.ssid === ssid);
    if (net) net.saved = true;
    updateWifiLabel();
    renderNetList();
  }

  function fillWifiDetail(net) {
    document.getElementById('detail-ssid').textContent   = net.ssid;
    document.getElementById('detail-status').textContent = '已连接';
    document.getElementById('detail-signal').textContent =
      net.signal >= 3 ? '强' : (net.signal === 2 ? '中' : '弱');
    document.getElementById('detail-sec').textContent =
      net.sec === 'open' ? '无 (开放)' : net.sec;
  }

  wifiSwitch.addEventListener('change', () => {
    wifiOn = wifiSwitch.checked;
    views.wifi.classList.toggle('off', !wifiOn);
    updateWifiLabel();
    if (wifiOn) scanWifi();
    else { netList.innerHTML = ''; clearTimeout(wifiScanTimer); wifiScanRow.style.display = 'none'; }
  });

  document.getElementById('wifi-rescan').addEventListener('click', scanWifi);

  document.getElementById('wifi-forget').addEventListener('click', () => {
    if (detailNet) {
      detailNet.saved = false;
      if (wifiConnectedSSID === detailNet.ssid) wifiConnectedSSID = null;
      updateWifiLabel();
      renderNetList();
    }
    viewHistory = ['home', 'wifi'];
    showView('wifi');
  });

  // ---- Wi-Fi 密码: 屏内键盘 ----
  let pwdValue = '';
  let pwdMasked = true;
  let shiftOn = false;
  const pwdDisplay = document.getElementById('pwd-display');
  const keypad     = document.getElementById('keypad');

  const KP_ROWS = [
    ['1','2','3','4','5','6','7','8','9','0'],
    ['q','w','e','r','t','y','u','i','o','p'],
    ['a','s','d','f','g','h','j','k','l'],
    ['⇧','z','x','c','v','b','n','m','⌫'],
  ];

  function buildKeypad() {
    keypad.innerHTML = '';
    KP_ROWS.forEach(row => {
      const r = document.createElement('div');
      r.className = 'kp-row';
      row.forEach(k => {
        const key = document.createElement('button');
        const special = (k === '⇧' || k === '⌫');
        key.className = 'kp-key' + (special ? ' wide' : '');
        key.textContent = (k.length === 1 && /[a-z]/.test(k) && shiftOn) ? k.toUpperCase() : k;
        key.addEventListener('click', () => onKey(k));
        r.appendChild(key);
      });
      keypad.appendChild(r);
    });
  }

  function onKey(k) {
    if (k === '⌫') { pwdValue = pwdValue.slice(0, -1); }
    else if (k === '⇧') { shiftOn = !shiftOn; buildKeypad(); }
    else {
      let ch = k;
      if (/[a-z]/.test(k) && shiftOn) ch = k.toUpperCase();
      if (pwdValue.length < 32) pwdValue += ch;
    }
    renderPwd();
  }

  function renderPwd() {
    pwdDisplay.textContent = pwdMasked ? '•'.repeat(pwdValue.length) : pwdValue;
  }

  document.getElementById('pwd-eye').addEventListener('click', () => {
    pwdMasked = !pwdMasked;
    renderPwd();
  });

  document.getElementById('pwd-connect').addEventListener('click', () => {
    if (!pendingNet) return;
    // 模拟连接: 短暂 "连接中" 后成功
    const btn = document.getElementById('pwd-connect');
    btn.textContent = '连接中…';
    setTimeout(() => {
      btn.textContent = '连接';
      connectWifi(pendingNet.ssid);
      pendingNet = null;
      pwdValue = '';
      viewHistory = ['home', 'wifi'];
      showView('wifi');
    }, 900);
  });

  // ============================================================
  //  蓝牙 交互链路
  // ============================================================
  const BT_POOL = [
    { name: '小爱音箱 Pro', type: '音频设备' },
    { name: 'AirPods',      type: '耳机' },
    { name: '客厅电视',      type: '显示设备' },
    { name: '小米手环 8',    type: '穿戴设备' },
    { name: 'JBL Go 3',     type: '音频设备' },
  ];
  let btOn = false;
  let btPaired = [];        // { name, type, connected }
  let btScanTimer = null;
  let btDetail = null;

  const btSwitch     = document.getElementById('bt-switch');
  const btPairedEl   = document.getElementById('bt-paired');
  const btAvailEl    = document.getElementById('bt-available');
  const btScanInline = document.getElementById('bt-scan-inline');
  const miBt         = document.getElementById('mi-bt');

  function updateBtLabel() {
    if (!btOn) { miBt.textContent = '关闭'; return; }
    const conn = btPaired.find(d => d.connected);
    miBt.textContent = conn ? conn.name : '开启';
  }

  function renderBtLists() {
    // 已配对
    btPairedEl.innerHTML = '';
    if (!btPaired.length) {
      btPairedEl.innerHTML = '<div class="grp-empty">暂无已配对设备</div>';
    } else {
      btPaired.forEach(dev => {
        const item = document.createElement('button');
        item.className = 'dev-item' + (dev.connected ? ' connected' : '');
        item.innerHTML =
          `<span class="di-name">${dev.name}</span>` +
          (dev.connected ? '<span class="badge-conn">已连接</span>' : '<span class="di-tag">已保存</span>');
        item.addEventListener('click', () => { btDetail = dev; fillBtDetail(dev); gotoView('bt-detail'); });
        btPairedEl.appendChild(item);
      });
    }
    // 可用 (排除已配对)
    btAvailEl.innerHTML = '';
    BT_POOL.filter(d => !btPaired.some(p => p.name === d.name)).forEach(dev => {
      const item = document.createElement('button');
      item.className = 'dev-item';
      item.innerHTML = `<span class="di-name">${dev.name}</span><span class="di-tag">${dev.type}</span>`;
      item.addEventListener('click', () => pairBt(dev, item));
      btAvailEl.appendChild(item);
    });
  }

  function scanBt() {
    if (!btOn) return;
    btScanInline.style.display = 'inline-flex';
    clearTimeout(btScanTimer);
    btScanTimer = setTimeout(() => {
      btScanInline.style.display = 'none';
      renderBtLists();
    }, 1600);
  }

  function onEnterBt() {
    views.bluetooth.classList.toggle('off', !btOn);
    btSwitch.checked = btOn;
    updateBtLabel();
    if (btOn) { renderBtLists(); scanBt(); }
  }

  function pairBt(dev, itemEl) {
    itemEl.innerHTML = `<span class="di-name">${dev.name}</span><span class="di-tag">配对中…</span>`;
    setTimeout(() => {
      // 断开其它已连接, 新设备设为已连接
      btPaired.forEach(d => d.connected = false);
      btPaired.unshift({ name: dev.name, type: dev.type, connected: true });
      updateBtLabel();
      renderBtLists();
      btDetail = btPaired[0];
      fillBtDetail(btDetail);
      gotoView('bt-detail');
    }, 1000);
  }

  function fillBtDetail(dev) {
    document.getElementById('bt-detail-name').textContent   = dev.name;
    document.getElementById('bt-detail-status').textContent = dev.connected ? '已连接' : '已配对 (未连接)';
    document.getElementById('bt-detail-type').textContent   = dev.type;
  }

  btSwitch.addEventListener('change', () => {
    btOn = btSwitch.checked;
    views.bluetooth.classList.toggle('off', !btOn);
    updateBtLabel();
    if (btOn) { renderBtLists(); scanBt(); }
    else { btScanInline.style.display = 'none'; clearTimeout(btScanTimer); }
  });

  document.getElementById('bt-rescan').addEventListener('click', scanBt);

  document.getElementById('bt-forget').addEventListener('click', () => {
    if (btDetail) btPaired = btPaired.filter(d => d.name !== btDetail.name);
    updateBtLabel();
    renderBtLists();
    viewHistory = ['home', 'bluetooth'];
    showView('bluetooth');
  });

  // ============================================================
  //  通用滑杆 (音量 / 亮度)
  // ============================================================
  function setSliderUI(fill, thumb, min, max, val) {
    const ratio = (val - min) / (max - min);
    const pct = (ratio * 100).toFixed(2) + '%';
    fill.style.width = pct;
    thumb.style.left = pct;
  }

  function attachSlider(slider, min, max, onChange) {
    let dragging = false;
    const update = (clientX) => {
      const rect = slider.getBoundingClientRect();
      let ratio = (clientX - rect.left) / rect.width;
      ratio = Math.max(0, Math.min(1, ratio));
      onChange(Math.round(min + ratio * (max - min)));
    };
    slider.addEventListener('pointerdown', e => {
      dragging = true;
      try { slider.setPointerCapture(e.pointerId); } catch (_) {}
      update(e.clientX);
    });
    slider.addEventListener('pointermove', e => { if (dragging) update(e.clientX); });
    slider.addEventListener('pointerup', e => {
      dragging = false;
      try { slider.releasePointerCapture(e.pointerId); } catch (_) {}
    });
    slider.addEventListener('pointercancel', () => { dragging = false; });
  }

  // ---- 音量 (0–100) ----
  let volume = 60;
  const volumeSlider = document.getElementById('volume-slider'); // 调试面板全局
  const volumeValue  = document.getElementById('volume-value');
  const volNum   = document.getElementById('vol-num');
  const volFill  = document.getElementById('vol-fill');
  const volThumb = document.getElementById('vol-thumb');
  const miVol    = document.getElementById('mi-vol');

  function setVolume(v) {
    volume = Math.max(0, Math.min(100, Math.round(v)));
    if (volumeSlider) volumeSlider.value = volume;
    if (volumeValue)  volumeValue.textContent = volume + '%';
    volNum.textContent = volume;
    setSliderUI(volFill, volThumb, 0, 100, volume);
    miVol.textContent = volume + '%';
  }
  attachSlider(document.getElementById('vol-slider'), 0, 100, setVolume);
  if (volumeSlider) volumeSlider.addEventListener('input', e => setVolume(+e.target.value));

  // ---- 屏幕亮度 (1–400 nit) ----
  // 行业参考: 儿童设备夜间最低 ~1 nit, 室内正常 150–250 nit, 强光下 ~400 nit
  let brightnessNit = 200;
  const briNum   = document.getElementById('bri-num');
  const briFill  = document.getElementById('bri-fill');
  const briThumb = document.getElementById('bri-thumb');
  const miBri    = document.getElementById('mi-bri');

  function setBrightness(nit) {
    brightnessNit = Math.max(1, Math.min(400, Math.round(nit)));
    briNum.textContent = brightnessNit;
    setSliderUI(briFill, briThumb, 1, 400, brightnessNit);
    // 遮罩不透明度: 200–400 nit 保持屏幕通透(不压暗默认星云效果),
    // 低于 200 nit 才逐渐变暗以模拟夜间, 最暗保留 ~0.8 不至全黑
    const COMFORT = 200;
    const op = Math.max(0, (COMFORT - brightnessNit) / COMFORT) * 0.8;
    brightnessOverlay.style.opacity = op.toFixed(3);
    miBri.textContent = brightnessNit + ' nit';
  }
  attachSlider(document.getElementById('bri-slider'), 1, 400, setBrightness);

  // ============================================================
  //  模式选择
  // ============================================================
  const MODE_LABEL = { normal: '正常', quiet: '安静', story: '故事' };
  document.querySelectorAll('.opt-item[data-mode]').forEach(opt => {
    opt.addEventListener('click', () => {
      document.querySelectorAll('.opt-item[data-mode]').forEach(o => o.classList.remove('active'));
      opt.classList.add('active');
      document.getElementById('mi-mode').textContent = MODE_LABEL[opt.dataset.mode] || '正常';
    });
  });

  // ============================================================
  //  触摸交互 (点按唤醒 / 长按 1.2s Settings)
  // ============================================================
  let pressTimer = null;
  let pressed = false;
  const LONG_PRESS_MS = 1200;

  canvas.addEventListener('pointerdown', (e) => {
    pressed = true;
    try { canvas.setPointerCapture(e.pointerId); } catch (_) {}
    pressTimer = setTimeout(() => {
      if (pressed) transition(STATES.SETTINGS);
    }, LONG_PRESS_MS);
  });

  canvas.addEventListener('pointerup', () => {
    if (!pressed) return;
    pressed = false;
    clearTimeout(pressTimer);
    pressTimer = null;
    if (currentState === STATES.IDLE) startConversation();
    else if (currentState === STATES.OFFLINE) transition(STATES.IDLE);
  });

  canvas.addEventListener('pointercancel', () => {
    pressed = false;
    clearTimeout(pressTimer);
    pressTimer = null;
  });

  canvas.addEventListener('contextmenu', e => e.preventDefault());

  // ============================================================
  //  模拟对话流  (Listening → Thinking → Speaking → Idle)
  // ============================================================
  let conversationTimer = null;
  let audioLevelAnim = null;

  const LISTEN_PHRASES = [
    '妈妈，我们来玩游戏好不好',
    '你看那只蝴蝶好漂亮呀',
    '我今天有一点点不开心…',
    '给我讲一个小兔子的故事吧',
    '天上的星星为什么会眨眼睛呢',
  ];

  function startConversation(customText) {
    if (conversationTimer) clearTimeout(conversationTimer);
    transition(STATES.LISTENING);

    // 接收语音: 逐字 "识别" 出现 (listening 字幕)
    const heard = LISTEN_PHRASES[Math.floor(Math.random() * LISTEN_PHRASES.length)];
    subtitle.classList.add('listening', 'show');
    subtitle.textContent = '';

    const recordMs = 1600;
    const start = performance.now();
    if (audioLevelAnim) cancelAnimationFrame(audioLevelAnim);
    const tick = () => {
      const dt = (performance.now() - start) / recordMs;
      if (dt > 1) { subtitle.textContent = heard; onAsrDone(customText); return; }
      const shown = Math.floor(heard.length * Math.min(1, dt * 1.15));
      subtitle.textContent = heard.slice(0, shown);
      const t = performance.now() / 200;
      const lvl = 0.4 + 0.3 * Math.sin(t) + 0.15 * Math.sin(t * 2.7);
      lf.setAudioLevel(Math.max(0, Math.min(1, lvl)));
      audioLevelAnim = requestAnimationFrame(tick);
    };
    audioLevelAnim = requestAnimationFrame(tick);
  }

  function onAsrDone(text) {
    transition(STATES.THINKING, { emotion: 'thinking' });
    conversationTimer = setTimeout(() => {
      speakScript(text || pickRandomScript());
    }, 1200);
  }

  function speakScript(text) {
    transition(STATES.SPEAKING, { emotion: 'happy' });
    subtitle.classList.remove('listening');
    subtitle.textContent = text;
    subtitle.classList.add('show');

    const speakMs = Math.max(1400, text.length * 180);
    const startSpeak = performance.now();
    const tickSpeak = () => {
      const dt = (performance.now() - startSpeak) / speakMs;
      if (dt > 1) {
        cancelAnimationFrame(audioLevelAnim);
        lf.setAudioLevel(0);
        lf.setTtsProgress(0.5);
        conversationTimer = setTimeout(() => transition(STATES.IDLE), 1500);
        return;
      }
      lf.setTtsProgress(dt);
      lf.setAudioLevel(0.3 + 0.25 * Math.sin(performance.now() / 100));
      audioLevelAnim = requestAnimationFrame(tickSpeak);
    };
    audioLevelAnim = requestAnimationFrame(tickSpeak);
  }

  function pickRandomScript() {
    const scripts = [
      '蝴蝶花真的很漂亮呢',
      '今天有什么想跟我聊聊的吗?',
      '我在听你说, 慢慢来.',
      '嗯嗯, 你是这样想的呀.',
      '我想了一下, 你说得有道理.',
      '要不要一起画一只小兔子?',
      '别担心, 我一直都在.',
    ];
    return scripts[Math.floor(Math.random() * scripts.length)];
  }

  // ============================================================
  //  控制面板 (调试)
  // ============================================================
  document.querySelectorAll('[data-state]').forEach(btn => {
    btn.addEventListener('click', () => transition(btn.dataset.state));
  });

  document.querySelectorAll('[data-emotion]').forEach(chip => {
    chip.addEventListener('click', () => {
      const emo = chip.dataset.emotion;
      lf.setEmotion(emo);
      document.querySelectorAll('[data-emotion]').forEach(c => {
        c.classList.toggle('active', c.dataset.emotion === emo);
      });
    });
  });

  document.getElementById('btn-talk').addEventListener('click', () => {
    if (currentState === STATES.SETTINGS || currentState === STATES.OFFLINE) return;
    const text = document.getElementById('script-text').value.trim();
    startConversation(text);
  });

  document.getElementById('btn-mute').addEventListener('click', () => setVolume(0));

  const btnReset = document.getElementById('btn-reset');
  if (btnReset) btnReset.addEventListener('click', () => alert('已重置配网信息, 重启设备进入配网模式'));

  document.getElementById('btn-offline').addEventListener('click', () => {
    transition(STATES.OFFLINE, { emotion: 'worried' });
  });
  document.getElementById('btn-back-online').addEventListener('click', () => {
    transition(STATES.IDLE, { emotion: 'calm' });
  });

  document.getElementById('btn-close-settings').addEventListener('click', () => {
    transition(STATES.IDLE);
  });

  const densitySlider = document.getElementById('density-slider');
  const densityValue = document.getElementById('density-value');
  if (densitySlider) {
    densitySlider.addEventListener('input', (e) => {
      const v = parseInt(e.target.value, 10);
      densityValue.textContent = `粒子 ${v}%`;
      lf.setDensity(v / 100);
    });
  }

  const btnPulse = document.getElementById('btn-pulse');
  if (btnPulse) btnPulse.addEventListener('click', () => lf.pulse());

  const btnWake = document.getElementById('btn-wake');
  if (btnWake) {
    btnWake.addEventListener('click', () => {
      const back = currentState;
      lf.setState('wake');
      lf.pulse();
      setTimeout(() => lf.setState(back), 900);
    });
  }

  // ============================================================
  //  初始化
  // ============================================================
  buildKeypad();
  transition(STATES.IDLE);
  setVolume(60);
  setBrightness(200);
  updateWifiLabel();
  updateBtLabel();

  window.__cira = { lf, transition, STATES, gotoView, backView };
})();
