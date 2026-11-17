/* 550W·知识库助手 · Service Worker
 *
 * 目标是「装到手机桌面 + 断网也能打开」，不是「离线用完整功能」。
 *
 * 策略：
 *   · 静态资源（本文件同目录下的 html/css/js/图标）：cache-first，装完就能离线开
 *   · /api/*：network-only，**绝不缓存**。数据依赖本机知识库与导师索引，
 *     缓存下来只会让人看到过期数字，比报错更糟
 *
 * 为什么不做「离线可用的完整版」：这个站的接口全部由本机 Python 服务提供，
 * 手机离线时后端根本不在，缓存 JSON 只会给出假的老数据。
 */
const VER = "kb-v1";
const SHELL = [
  "/",
  "/index.html",
  "/style.css",
  "/app.js",
  "/manifest.webmanifest",
  "/icon-192.png",
  "/icon-512.png",
];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(VER).then((c) =>
      // 单个资源失败不该让整个安装失败（比如某个图标还没生成）
      Promise.all(SHELL.map((u) => c.add(u).catch(() => null)))
    ).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== VER).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);

  // 只接管同源 GET
  if (e.request.method !== "GET" || url.origin !== location.origin) return;

  // 接口一律走网络，不缓存
  if (url.pathname.startsWith("/api/")) return;

  e.respondWith(
    caches.match(e.request).then((hit) => {
      if (hit) {
        // 后台顺手更新，下次打开就是新的
        fetch(e.request)
          .then((r) => {
            if (r && r.ok) caches.open(VER).then((c) => c.put(e.request, r.clone()));
          })
          .catch(() => null);
        return hit;
      }
      return fetch(e.request)
        .then((r) => {
          if (r && r.ok && r.type === "basic") {
            const copy = r.clone();
            caches.open(VER).then((c) => c.put(e.request, copy));
          }
          return r;
        })
        .catch(() =>
          // 页面导航请求失败时退回首页壳子
          e.request.mode === "navigate"
            ? caches.match("/index.html")
            : new Response("离线且未缓存", { status: 503 })
        );
    })
  );
});