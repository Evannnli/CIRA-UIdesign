// CIRA 本地 mock 桥接服务（零依赖，仅用于联调前端接线）
// 用法：node mock_bridge.js [端口]   默认 8000
// 然后在前端 cira-android.html 把 BRIDGE.BASE 设为 http://<本机局域网IP>:8000
//
// 端点（与 CIRA_APP_INTEGRATION_REQUIREMENTS.md 同名）：
//   GET  /v1/health
//   POST /v1/transcribe   (收裸 16-bit/16k/mono PCM，回 canned 文本)
//   POST /v1/respond      (回 response-package + display_state)
//   POST /v1/speak        (回 base64 wav)
//   GET  /v1/wake_ack      (回唤醒应答音频 + 文案)

const http = require('http');
const PORT = parseInt(process.argv[2] || '8000', 10);

function b64(buf){ return Buffer.from(buf).toString('base64'); }

// 生成一段短促的 16k/16-bit/mono 正弦 wav
function makeWav(seconds = 0.45, freq = 440){
  const sr = 16000, n = Math.floor(sr * seconds);
  const data = Buffer.alloc(n * 2);
  for(let i = 0; i < n; i++){
    const t = i / sr;
    const env = Math.min(1, t * 20) * Math.min(1, (seconds - t) * 20); // 淡入淡出
    const s = Math.sin(2 * Math.PI * freq * t) * 0.5 * env;
    data.writeInt16LE(Math.max(-1, Math.min(1, s)) * 0x7fff, i * 2);
  }
  const buf = Buffer.alloc(44 + data.length);
  buf.write('RIFF', 0); buf.writeUInt32LE(36 + data.length, 4); buf.write('WAVE', 8);
  buf.write('fmt ', 12); buf.writeUInt32LE(16, 16); buf.writeUInt16LE(1, 20);
  buf.writeUInt16LE(1, 22); buf.writeUInt32LE(sr, 24); buf.writeUInt32LE(sr * 2, 28);
  buf.writeUInt16LE(2, 32); buf.writeUInt16LE(16, 34);
  buf.write('data', 36); buf.writeUInt32LE(data.length, 40); data.copy(buf, 44);
  return buf;
}

function sendJSON(res, obj, status = 200){
  const body = JSON.stringify(obj);
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
  });
  res.end(body);
}
function readBody(req){
  return new Promise((resolve) => {
    const chunks = [];
    req.on('data', c => chunks.push(c));
    req.on('end', () => resolve(Buffer.concat(chunks)));
  });
}

const CANNED_TEXT = ['我今天被同学笑了，有点难过', '我想吃冰淇淋', '你叫什么名字呀', '妈妈是不是不喜欢我了'];

const server = http.createServer(async (req, res) => {
  if(req.method === 'OPTIONS'){ res.writeHead(204, {'Access-Control-Allow-Origin':'*','Access-Control-Allow-Methods':'GET,POST,OPTIONS','Access-Control-Allow-Headers':'Content-Type,Authorization'}); return res.end(); }

  const url = new URL(req.url, 'http://x');
  const p = url.pathname;

  if(p === '/v1/health'){
    return sendJSON(res, { asr_available: true, tts_available: true, core_ready: true });
  }

  if(p === '/v1/transcribe'){
    await readBody(req); // 丢弃 PCM 内容，直接回 canned
    return sendJSON(res, { schema: 'asr-result@1', text: CANNED_TEXT[Math.floor(Math.random() * CANNED_TEXT.length)], asr_available: true });
  }

  if(p === '/v1/respond'){
    let body = {};
    try { body = JSON.parse((await readBody(req)).toString('utf8') || '{}'); } catch(e){}
    const text = body.text || '（空）';
    const emotions = ['comfort', 'curious', 'happy', 'thinking', 'excited'];
    const emotion = emotions[Math.floor(Math.random() * emotions.length)];
    return sendJSON(res, {
      schema: 'response-package@1',
      text: '我听到你说：「' + text + '」。我陪你一起想想好不好？',
      emotion, modality: 'language', ignite: false,
      display_state: { schema: 'display-state@1', emotion, status: 'speaking', ignite: false },
    });
  }

  if(p === '/v1/speak'){
    let body = {};
    try { body = JSON.parse((await readBody(req)).toString('utf8') || '{}'); } catch(e){}
    const wav = makeWav(0.6, body.emotion === 'excited' ? 660 : 440);
    return sendJSON(res, { schema: 'audio-output@1', audio: b64(wav), format: 'wav', sample_rate: 16000, text: body.text || '' });
  }

  if(p === '/v1/wake_ack'){
    const which = url.searchParams.get('which') || 'ai';
    const wav = makeWav(0.4, which === 'ai' ? 520 : 392);
    return sendJSON(res, { audio: b64(wav), format: 'wav', text: which === 'ai' ? '哎' : '我在' });
  }

  res.writeHead(404, { 'Access-Control-Allow-Origin': '*' });
  res.end('not found');
});

server.listen(PORT, '0.0.0.0', () => {
  console.log('[CIRA mock bridge] listening on http://0.0.0.0:' + PORT);
  console.log('前端 BRIDGE.BASE 填 http://<本机局域网IP>:' + PORT);
});
