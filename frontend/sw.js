// Makes RetroManager installable as an app, which is what puts it in the
// phone's share menu (see manifest.webmanifest). Browsers only allow this on
// HTTPS. Nothing is cached: every request goes to the server as usual.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));
self.addEventListener('fetch', () => {});
