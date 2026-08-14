// 本机 HTTPS 代理：解决"手机纯 http 下麦克风被禁 + https 页混跑 http 接口被拦"两个问题。
//  - 用 https 提供 android-proto 静态文件（安全上下文 → getUserMedia 可用，真语音可验）
//  - 把 /v1/* 请求在 Mac 内部转发到真实桥 http://192.168.31.235:8788（同源，无混内容拦截）
// 用法：
//   node bridge_proxy.js            # 默认 https :8443，桥指向 192.168.31.235:8788
//   node bridge_proxy.js 9000       # 自定义端口
// 手机打开：https://192.168.31.33:8443/cira-android.html?bridge=/
//   （?bridge=/ 让页面走同源代理；证书不受信任时点"高级→继续"即可）

const https = require('https');
const http = require('http');
const fs = require('fs');
const path = require('path');
const os = require('os');

const DIR = __dirname;
const PORT = parseInt(process.argv[2] || '8443', 10);
// 桥地址解析优先级：环境变量 CIRA_BRIDGE > 同目录 bridge_target.txt（一行）> 默认局域网真桥
// 换网络/位置时只需改 bridge_target.txt 一行（或设 env），不必改代码
let BRIDGE = process.env.CIRA_BRIDGE || 'http://192.168.31.235:8788';
try {
  const _t = fs.readFileSync(path.join(DIR, 'bridge_target.txt'), 'utf8').trim();
  if(_t && !process.env.CIRA_BRIDGE) BRIDGE = _t;
} catch(e){ /* 文件不存在则用默认真桥 */ }

// 取本机首个非回环 IPv4，换网后自动显示新地址，不用手改
function lanIP(){
  const ifs = os.networkInterfaces();
  for(const k of Object.keys(ifs)){
    for(const a of (ifs[k] || [])){
      if(a.family === 'IPv4' && !a.internal) return a.address;
    }
  }
  return '127.0.0.1';
}
const TLS = {
  key: fs.readFileSync(path.join(DIR, '.tls', 'key.pem')),
  cert: fs.readFileSync(path.join(DIR, '.tls', 'cert.pem')),
};

const MIME = {
  '.html':'text/html; charset=utf-8', '.js':'text/javascript; charset=utf-8',
  '.css':'text/css; charset=utf-8', '.json':'application/json; charset=utf-8',
  '.m4a':'audio/mp4', '.mp3':'audio/mpeg', '.wav':'audio/wav',
  '.png':'image/png', '.svg':'image/svg+xml',
};

function readBody(req){
  return new Promise((res, rej)=>{
    const chunks=[];
    req.on('data', c=>chunks.push(c));
    req.on('end', ()=>res(Buffer.concat(chunks)));
    req.on('error', rej);
  });
}

const server = https.createServer(TLS, async (req, res)=>{
  try{
    const u = new URL(req.url, 'https://x');
    const p = decodeURIComponent(u.pathname);

    // ---- 代理 /v1/* 到真实桥（同源，避混内容） ----
    if(p.startsWith('/v1/')){
      const body = (req.method === 'GET' || req.method === 'HEAD') ? undefined : await readBody(req);
      const headers = {};
      for(const k of ['content-type','authorization']) if(req.headers[k]) headers[k]=req.headers[k];
      const r = await fetch(BRIDGE + p + u.search, {
        method: req.method, headers, body,
      });
      const buf = Buffer.from(await r.arrayBuffer());
      res.writeHead(r.status, { 'content-type': r.headers.get('content-type') || 'application/octet-stream' });
      res.end(buf);
      return;
    }

    // ---- 静态文件 ----
    let f = p === '/' ? '/cira-android.html' : p;
    const fp = path.join(DIR, path.normalize(f).replace(/^(\.\.[/\\])+/, ''));
    if(!fp.startsWith(DIR)){ res.writeHead(403); res.end('forbidden'); return; }
    if(!fs.existsSync(fp) || !fs.statSync(fp).isFile()){
      res.writeHead(404, {'content-type':'text/plain; charset=utf-8'}); res.end('not found'); return;
    }
    const ext = path.extname(fp).toLowerCase();
    res.writeHead(200, { 'content-type': MIME[ext] || 'application/octet-stream' });
    fs.createReadStream(fp).pipe(res);
  }catch(e){
    console.error('[proxy] err', e.message);
    if(!res.headersSent){ res.writeHead(502); }
    res.end('proxy error: ' + e.message);
  }
});

server.listen(PORT, '0.0.0.0', ()=>{
  const ip = lanIP();
  console.log(`[bridge_proxy] https://0.0.0.0:${PORT}  → 桥 ${BRIDGE}`);
  console.log(`[bridge_proxy] 手机打开: https://${ip}:${PORT}/cira-android.html?bridge=/`);
  console.log(`[bridge_proxy] 自签证书不受信任时点"高级→继续"即可（仅本机测试用）`);
});
