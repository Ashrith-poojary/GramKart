const CACHE_NAME = 'gramkart-cache-v1';
const ASSETS_TO_CACHE = [
  '/',
  '/static/css/custom.css',
  '/static/manifest.json',
  'https://cdn.tailwindcss.com',
  'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css',
  'https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Poppins:wght@300;400;500;600;700;800;900&display=swap'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('Opened cache and caching static assets');
        return cache.addAll(ASSETS_TO_CACHE);
      })
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cache => {
          if (cache !== CACHE_NAME) {
            console.log('Clearing old cache:', cache);
            return caches.delete(cache);
          }
        })
      );
    })
  );
});

self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET' || event.request.url.includes('/admin') || event.request.url.includes('/payment')) {
    return;
  }
  
  event.respondWith(
    caches.match(event.request)
      .then(response => {
        if (response) {
          return response;
        }
        return fetch(event.request).then(fetchResponse => {
          if (fetchResponse.status === 200 && (event.request.url.includes('/product/') || event.request.url.includes('/static/'))) {
            const responseClone = fetchResponse.clone();
            caches.open(CACHE_NAME).then(cache => cache.put(event.request, responseClone));
          }
          return fetchResponse;
        });
      }).catch(() => {
        return caches.match('/');
      })
  );
});
