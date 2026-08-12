/**
 * CIRA Web 交互原型 — 主控制器 / Device Runtime (模块3)  (v0.7)
 *
 * 职责:
 *   - 状态机 (Idle / Listening / Thinking / Speaking / Settings / Offline / Sleep)
 *   - 唤醒 (统一入口 wake): 触摸或唤醒词触发; 优先级最高, 可打断 SPEAKING
 *       · 播放本地应答 "我在。"/"哎！" (vivi2.0 预录, 缺失则 TTS 兜底) — 不进大模型
 *       · 之后进入 LISTENING 正式接收语音 → 送云端模型
 *   - 无动作/交互 10s 自动熄屏 SLEEP 省电; 被点击或唤醒时亮屏
 *   - 触摸交互 (点按唤醒, 长按 1.2s 进 Settings)
 *   - 语音唤醒 (唤醒方式之二): "你好，cira" / "你好，西拉" 唤醒词, 待机时被动聆听
 *   - Settings 多视图导航 (home / wifi / wifi-pwd / wifi-detail /
 *       bluetooth / bt-detail / volume / brightness / mode)
 *   - Wi-Fi 完整链路: 开关 / 自动搜索 + 重新搜索 / 点击连接 / 屏内键盘输入密码 / 忘掉此网络
 *   - 蓝牙完整链路: 开关 / 扫描 / 配对连接 / 已配对设备 / 忽略此设备
 *   - 音量滑杆 (0–100) / 屏幕亮度滑杆 (1–400 nit, 实时遮罩)
 *   - 通过冻结接口编排模块1/2 (Listening → 模块1 respond → 模块2 synthesize → 回 Idle)
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
    SLEEP: 'sleep',           // v0.5 新增: 熄屏省电
  };
  let currentState = STATES.IDLE;

  const STATE_EMOTION = {
    idle: 'calm', listening: 'curious', thinking: 'thinking',
    speaking: 'happy', offline: 'worried', settings: 'calm', sleep: 'calm',
  };
  const STATE_COLOR = {
    idle: '#FF8A3D', listening: '#FF8A3D', thinking: '#A98CE0',
    speaking: '#FF8A3D', offline: '#FF9EB5', settings: '#FFFFFF', sleep: '#000000',
  };

  // ---- SLEEP 超时参数 (ms) — 无动作/交互 10s 自动熄屏省电 (v0.6 产品决定) ----
  const SLEEP_TIMEOUTS = {
    fromIdle:      10000,    // IDLE 空闲 10s → SLEEP
    fromListening: 10000,    // LISTENING 静默(无语音输入) 10s → SLEEP
    fromThinking:  15000,    // THINKING 模型思考超时 15s → SLEEP (防模型卡死)
    fromSpeaking:  10000,    // (预留) SPEAKING 兜底, 正常由 IDLE 路径接管
  };
  let sleepTimer = null;
  function clearSleepTimer() { if (sleepTimer) { clearTimeout(sleepTimer); sleepTimer = null; } }
  function armSleepTimer(ms) { clearSleepTimer(); sleepTimer = setTimeout(() => {
    transition(STATES.SLEEP);
  }, ms); }

  function transition(next, opts = {}) {
    clearSleepTimer();
    const prev = currentState;

    // SLEEP: 引擎暂停 + 全黑遮罩; 非 SLEEP: 恢复引擎 + 还原遮罩
    if (next === STATES.SLEEP) {
      lf.pause();
      brightnessOverlay.style.opacity = '1';
      brightnessOverlay.style.transition = 'opacity 0.35s ease';
      document.body.classList.add('sleep-mode');
    } else {
      if (prev === STATES.SLEEP) {
        // 离开 SLEEP: 必须先更新 currentState 再还原遮罩 —— 否则 setBrightness 里的
        // `currentState !== STATES.SLEEP` 守卫会判定"仍在熄屏"而跳过复位, 导致全黑遮罩
        // 残留、屏幕永远亮不起来 (v0.6.1 修正)
        lf.resume();
        brightnessOverlay.style.transition = 'opacity 0.35s ease';
        currentState = next;                 // 提前更新, 让 setBrightness 守卫放行
        setBrightness(brightnessNit);        // 还原用户设定的不透明度 (覆盖 SLEEP 期间的 1.0)
        document.body.classList.remove('sleep-mode');
      } else {
        document.body.classList.remove('sleep-mode');
      }
    }

    currentState = next;

    // 设置浮层: 进入显示并回到主菜单 / 退出隐藏
    if (next === STATES.SETTINGS) {
      settings.classList.add('show');
      resetSettingsToHome();
    } else {
      settings.classList.remove('show');
    }

    if (next !== STATES.SLEEP) {
      lf.setState(next);
      lf.setEmotion(opts.emotion || STATE_EMOTION[next]);
    }

    stateLabel.textContent = next;
    stateDot.style.background = STATE_COLOR[next];
    stateDot.style.boxShadow = `0 0 8px ${STATE_COLOR[next]}`;
    stateBadge.style.borderColor = hexToRGBA(STATE_COLOR[next], 0.25);

    // 字幕: 仅 Listening(接收) / Speaking(输出) 显示; SLEEP 也强制隐藏
    if (next !== STATES.SPEAKING && next !== STATES.LISTENING) {
      subtitle.classList.remove('show', 'listening');
    }

    // 各状态进入时启动对应 SLEEP 计时器 (无动作/交互则熄屏省电)
    if (next === STATES.IDLE) {
      vwWoke = false;
      armSleepTimer(SLEEP_TIMEOUTS.fromIdle);
    } else if (next === STATES.LISTENING) {
      armSleepTimer(SLEEP_TIMEOUTS.fromListening);
    } else if (next === STATES.THINKING) {
      armSleepTimer(SLEEP_TIMEOUTS.fromThinking);
    }
    // SPEAKING 为活跃输出, 不挂 SLEEP 计时; 结束后由 IDLE 路径接管

    // 语音唤醒: IDLE + SLEEP 时都允许被动聆听 (SLEEP 时跳 IDLE 直入 LISTENING)
    syncVoiceWake();

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
    // SLEEP 期间保持全黑 (transition() 控制); 退出 SLEEP 后由本函数恢复
    if (currentState !== STATES.SLEEP) brightnessOverlay.style.opacity = op.toFixed(3);
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
  let longPressed = false;
  const LONG_PRESS_MS = 1200;

  canvas.addEventListener('pointerdown', (e) => {
    pressed = true;
    longPressed = false;
    try { canvas.setPointerCapture(e.pointerId); } catch (_) {}
    pressTimer = setTimeout(() => {
      if (pressed) { longPressed = true; transition(STATES.SETTINGS); }
    }, LONG_PRESS_MS);
  });

  canvas.addEventListener('pointerup', () => {
    if (!pressed) return;
    pressed = false;
    clearTimeout(pressTimer);
    pressTimer = null;
    if (longPressed) return;                              // 长按已进入设置, 不再唤醒
    if (currentState === STATES.OFFLINE) { transition(STATES.IDLE); return; }
    // 任何可交互态(含 IDLE/SLEEP/LISTENING/THINKING/SPEAKING)触摸 → 唤醒:
    // 播放本地应答(我在。/哎！) → 进入 LISTENING 接收语音 → 送云端模型
    wake('touch');
  });

  canvas.addEventListener('pointercancel', () => {
    pressed = false;
    longPressed = false;
    clearTimeout(pressTimer);
    pressTimer = null;
  });

  canvas.addEventListener('contextmenu', e => e.preventDefault());

  // ============================================================
  //  唤醒 (统一入口) — 优先级最高
  //  - 任何活跃态(含 SPEAKING 播报中)被触摸/唤醒词触发, 立即打断当前输出
  //  - 播放本地应答 "我在。"/"哎！" (vivi2.0 预录 assets/wake_wo.mp3|wake_ai.mp3;
  //    缺失则用 Web Speech TTS 兜底) — 此应答不进大模型
  //  - 应答播完后进入 LISTENING 正式接收语音, 之后才送云端模型
  // ============================================================
  function stopAllOutput() {
    try { if (window.speechSynthesis) window.speechSynthesis.cancel(); } catch (_) {}
    if (currentAudioHandle) { try { currentAudioHandle.stop(); } catch (_) {} currentAudioHandle = null; }
    if (conversationTimer) { clearTimeout(conversationTimer); conversationTimer = null; }
    if (audioLevelAnim) { cancelAnimationFrame(audioLevelAnim); audioLevelAnim = null; }
    lf.setAudioLevel(0);
    lf.setTtsProgress(0);
    subtitle.classList.remove('show', 'listening');
  }

  function ttsSpeak(text) {
    try {
      const s = window.speechSynthesis;
      if (!s) return;
      const u = new SpeechSynthesisUtterance(text);
      u.lang = 'zh-CN'; u.rate = 1.0; u.pitch = 1.12; u.volume = 1.0;
      s.cancel(); s.speak(u);
    } catch (_) {}
  }

  // 播放本地唤醒应答; 返回所用应答词(供字幕展示)
  function playWakeResponse() {
    stopAllOutput();                         // 先打断一切进行中的输出(含模型回复)
    const opts = ['我在。', '哎！'];
    const phrase = opts[Math.floor(Math.random() * opts.length)];
    const file = phrase === '我在。' ? 'assets/wake_wo.mp3' : 'assets/wake_ai.mp3';
    const audio = new Audio(file);
    let fell = false;
    const fallback = () => { if (!fell) { fell = true; ttsSpeak(phrase); } };
    audio.addEventListener('error', fallback);
    const p = audio.play();
    if (p && p.catch) p.catch(fallback);
    return phrase;
  }

  function estimateAckMs(phrase) {
    return phrase.length * 300 + 500;        // 估算本地应答时长, 之后转 LISTENING
  }

  function wake(reason) {
    if (currentState === STATES.SETTINGS || currentState === STATES.OFFLINE) return;
    vwWoke = true;                           // 防同一次唤醒词尾音重复触发
    const phrase = playWakeResponse();       // 本地应答(不进大模型)
    transition(STATES.LISTENING, { emotion: 'curious' });
    subtitle.classList.add('listening', 'show');
    subtitle.textContent = phrase;           // 视觉呈现应答
    const ackMs = estimateAckMs(phrase);
    setTimeout(() => {
      // 应答结束后正式接收语音 → 送云端模型 (非 SLEEP 才继续, 避免期间被熄屏打断)
      if (currentState === STATES.LISTENING) beginListen();
    }, ackMs);
  }

  // ============================================================
  //  对话流编排 (模块3 = Device Runtime 编排 模块1 → 模块2 → 自身表现)
  //  - 模块1 CIRA Core:      respond(transcript)   → ResponsePackage   ("说什么")
  //  - 模块2 Language System: synthesize(pkg)        → AudioHandle      ("怎么说")
  //  - 模块3 自身: 状态机 + 星云渲染 + 音频电平动画 + 唤醒打断
  //  依赖方式: 仅经 modules.js 暴露的 CIRA.Core / CIRA.Language 接口,
  //            绝不依赖模块1/2 内部实现 (满足冻结标准)
  // ============================================================
  let conversationTimer = null;
  let audioLevelAnim = null;
  let currentAudioHandle = null;   // 模块2 返回的 AudioHandle, 供唤醒打断时 stop()

  const LISTEN_PHRASES = [
    '妈妈，我们来玩游戏好不好',
    '你看那只蝴蝶好漂亮呀',
    '我今天有一点点不开心…',
    '给我讲一个小兔子的故事吧',
    '天上的星星为什么会眨眼睛呢',
  ];

  function beginListen(customText) {
    vwWoke = false;            // 新一轮接收, 允许再次语音唤醒打断
    if (conversationTimer) clearTimeout(conversationTimer);
    transition(STATES.LISTENING);

    // 接收语音 (原型用脚本模拟 ASR; 真机由设备端 ASR 产出 transcript 后调 onAsrDone)
    const heard = customText || LISTEN_PHRASES[Math.floor(Math.random() * LISTEN_PHRASES.length)];
    subtitle.classList.add('listening', 'show');
    subtitle.textContent = '';

    const recordMs = 1600;
    const start = performance.now();
    if (audioLevelAnim) cancelAnimationFrame(audioLevelAnim);
    const tick = () => {
      const dt = (performance.now() - start) / recordMs;
      if (dt > 1) { subtitle.textContent = heard; onAsrDone(heard); return; }
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
    // ① 进入思考态, 调用冻结接口 CIRA.Core.respond()
    transition(STATES.THINKING, { emotion: 'thinking' });
    conversationTimer = setTimeout(async () => {
      let pkg;
      try {
        pkg = await CIRA.Core.respond({ transcript: text || '', sessionId: 'local', locale: 'zh-CN' });
      } catch (err) {
        console.warn('[DeviceRuntime] 模块1 CIRA Core 调用失败:', err);
        transition(STATES.OFFLINE, { emotion: 'worried' });
        return;
      }
      await playResponsePackage(pkg);
    }, 1200);
  }

  async function playResponsePackage(pkg) {
    if (!pkg) return;
    const emotion = pkg.emotion || 'calm';
    lf.setEmotion(emotion);
    transition(STATES.SPEAKING, { emotion });

    subtitle.classList.remove('listening');
    subtitle.textContent = pkg.text || '';
    subtitle.classList.add('show');

    // ② 调用冻结接口 CIRA.Language.synthesize() → AudioHandle
    let handle;
    try {
      handle = await CIRA.Language.synthesize(pkg);
    } catch (err) {
      console.warn('[DeviceRuntime] 模块2 Language System 调用失败:', err);
      scheduleReturnToIdle(1500);
      return;
    }
    currentAudioHandle = handle;

    // 音频电平动画: 真机由模块2音频流驱动; 原型用 durationMs 估算
    const dur = (handle && handle.durationMs) || Math.max(1400, (pkg.text || '').length * 180);
    const startSpeak = performance.now();
    let finished = false;
    const finishSpeak = () => {
      if (finished) return; finished = true;
      if (audioLevelAnim) cancelAnimationFrame(audioLevelAnim);
      lf.setAudioLevel(0);
      lf.setTtsProgress(0.5);
      currentAudioHandle = null;
      scheduleReturnToIdle(1500);
    };
    const tickSpeak = () => {
      const dt = (performance.now() - startSpeak) / dur;
      if (dt > 1) { finishSpeak(); return; }
      lf.setTtsProgress(dt);
      lf.setAudioLevel(0.3 + 0.25 * Math.sin(performance.now() / 100));
      audioLevelAnim = requestAnimationFrame(tickSpeak);
    };
    audioLevelAnim = requestAnimationFrame(tickSpeak);

    if (handle && handle.onEnd) handle.onEnd(finishSpeak);
    if (handle && handle.play) handle.play();
  }

  function scheduleReturnToIdle(ms) {
    if (conversationTimer) clearTimeout(conversationTimer);
    conversationTimer = setTimeout(() => transition(STATES.IDLE), ms);
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
    beginListen(text);
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
    // 演示唤醒(含本地应答 + 进入接收); 也可用来演示 "播报中打断"
    btnWake.addEventListener('click', () => wake('button'));
  }

  // ============================================================
  //  语音唤醒 (唤醒方式之二)
  //  唤醒词: "你好，cira"(英文发音) / "你好，西拉"(中文发音)
  //  待机(IDLE)时被动聆听; 命中 → 与"点按唤醒"同路径进入 LISTENING
  //  真机用端侧唤醒词引擎(Porcupine/WeNet 等); 本原型用 Web Speech API(zh-CN) 最佳实践
  // ============================================================
  const micBtn = document.getElementById('mic-btn');
  const vwPill = document.getElementById('vw-pill');
  const vwText = vwPill.querySelector('.vw-text');
  let voiceWakeOn = true;        // 默认开启
  let vwSupported = false;
  let vwRecognition = null;
  let vwWoke = false;            // 防一次说话重复触发
  let vwGesture = false;         // 首个用户手势后才真正 start (避免加载即弹麦克风权限)

  // 唤醒词 (小写匹配): cira / 西拉(中文发音) / 西啦(同音) / 带 hi/hey 前缀
  const VW_KEYWORDS = ['cira', '西拉', '西啦', 'ci ra', 'hey cira', 'hi cira', 'hello cira'];

  function initVoiceWake() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      vwSupported = false;
      vwText.textContent = '本浏览器不支持语音识别 · 点话筒模拟唤醒';
      updateMicUI();
      return;
    }
    vwSupported = true;
    vwRecognition = new SR();
    vwRecognition.lang = 'zh-CN';
    vwRecognition.continuous = true;
    vwRecognition.interimResults = true;

    vwRecognition.onresult = (ev) => {
      if (!voiceWakeOn) return;
      if (currentState === STATES.SETTINGS || currentState === STATES.OFFLINE) return;
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        const txt = (ev.results[i][0].transcript || '').toLowerCase();
        if (VW_KEYWORDS.some(k => txt.includes(k))) { wakeByVoice(); break; }
      }
    };
    // 浏览器在无语音一段时间后会自动 onend, 在 IDLE/SLEEP/LISTENING+开启 时拉起维持待命
    vwRecognition.onend = () => {
      if (voiceWakeOn && (currentState === STATES.IDLE || currentState === STATES.SLEEP || currentState === STATES.LISTENING) && vwGesture) startVWRecognition();
    };
    vwRecognition.onerror = () => { /* 权限拒绝/无网络: 静默, 等待下次手势 */ };
    updateMicUI();
  }

  function wakeByVoice() {
    // 语音唤醒优先级同触摸: 任何活跃态均可触发(含 SPEAKING 播报中打断)
    wake('voice');
  }

  function startVWRecognition() {
    if (!vwSupported || !voiceWakeOn || !vwGesture) return;
    try { vwRecognition.start(); } catch (_) { /* 已在运行 */ }
  }
  function stopVWRecognition() {
    if (vwRecognition) { try { vwRecognition.stop(); } catch (_) {} }
  }

  function syncVoiceWake() {
    // IDLE + SLEEP + LISTENING 期间都允许被动监听唤醒词 (LISTENING 用于语音打断)
    if ((currentState === STATES.IDLE || currentState === STATES.SLEEP || currentState === STATES.LISTENING) && voiceWakeOn && vwSupported) {
      document.body.classList.add('vw-active');
      startVWRecognition();
    } else {
      document.body.classList.remove('vw-active');
      stopVWRecognition();
    }
    updateMicUI();
  }

  function updateMicUI() {
    micBtn.classList.toggle('on', voiceWakeOn);
    vwPill.classList.toggle('show', voiceWakeOn);
  }

  // 首个用户手势后, 才真正拉起语音识别 (规避加载即弹麦克风权限)
  document.addEventListener('pointerdown', () => {
    if (!vwGesture) { vwGesture = true; if (currentState === STATES.IDLE) startVWRecognition(); }
  }, { once: false });

  micBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    if (!vwSupported) {
      // 演示模式(无 SpeechRecognition): 点话筒直接模拟一次唤醒(含本地应答)
      wake('touch');
      return;
    }
    vwGesture = true;
    voiceWakeOn = !voiceWakeOn;
    if (voiceWakeOn && (currentState === STATES.IDLE || currentState === STATES.SLEEP || currentState === STATES.LISTENING)) startVWRecognition();
    else stopVWRecognition();
    syncVoiceWake();
  });

  // 演示模式: 待命气泡也可点击触发, 便于无麦克风环境下演示交互
  vwPill.addEventListener('click', (e) => {
    e.stopPropagation();
    if (!vwSupported) wake('touch');
  });

  // ============================================================
  //  初始化
  // ============================================================
  buildKeypad();
  initVoiceWake();
  transition(STATES.IDLE);
  setVolume(60);
  setBrightness(200);
  updateWifiLabel();
  updateBtLabel();

  window.__cira = { lf, transition, STATES, gotoView, backView };
})();
