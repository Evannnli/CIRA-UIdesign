/**
 * CIRA PWA Service Worker — 离线缓存 (network-first, 离线回退 cache)
 * ----------------------------------------------------------------------------
 * 策略: 每次优先走网络(保证 Mac 在线时拿到最新); 离线时回退到首次缓存的壳。
 * 效果: 首次联网加载后, 之后即使 Mac 关机也能在手机上离线打开本地桩版本。
 * 注意: 仅缓存本地桩版 (core.js/language.js 的 Mock), 不缓存任何远程模块。
 */
const CACHE = 'cira-pwa-v1';
const PRECACHE = [
  './', './index.html',
  './styles.css', './lifeform.js', './app.js',
  './modules.js', './core.js', './language.js',
  './manifest.webmanifest', './icon.svg', './icon-maskable.svg',
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(PRECACHE)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  e.respondWith(
    fetch(req)
      .then((resp) => {
        if (resp && resp.status === 200 && (resp.type === 'basic' || resp.type === 'cors')) {
          const copy = resp.clone();
          caches.open(CACHE).then((c) => c.put(req, copy));
        }
        return resp;
      })
      .catch(() => caches.match(req).then((c) => c || caches.match('./index.html')))
  );
});
