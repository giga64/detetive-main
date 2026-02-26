/**
 * Service Worker - PWA Minimalista
 * 
 * Funcionalidades:
 * - Cache de arquivos estáticos
 * - Histórico offline
 * - Sincronização em background
 */

const CACHE_NAME = 'detetive-v1';
const STATIC_ASSETS = [
  '/',
  '/static/design-system.css',
  '/static/observability.js',
  '/static/theme-toggle.js',
  '/static/skeleton.js',
  '/static/metrics.js',
  '/favicon.png'
];

/**
 * Install: Cache arquivos estáticos
 */
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS);
    })
  );
  self.skipWaiting();
});

/**
 * Activate: Limpar caches antigos
 */
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          if (cacheName !== CACHE_NAME) {
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
  self.clients.claim();
});

/**
 * Fetch: Estratégia Cache-First para estáticos, Network-First para dados
 */
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // API routes: Network-First (tentar rede, fallback para cache)
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirst(request));
    return;
  }

  // Assets estáticos: Cache-First
  if (isStaticAsset(url.pathname)) {
    event.respondWith(cacheFirst(request));
    return;
  }

  // Páginas HTML: Network-First
  if (request.mode === 'navigate') {
    event.respondWith(networkFirst(request));
    return;
  }

  // Default: Network-First
  event.respondWith(networkFirst(request));
});

/**
 * Cache-First Strategy
 */
async function cacheFirst(request) {
  const cache = await caches.open(CACHE_NAME);
  const cached = await cache.match(request);

  if (cached) {
    // Atualizar cache em background (não espera resposta)
    fetch(request)
      .then((response) => {
        if (response.ok) {
          cache.put(request, response);
        }
      })
      .catch(() => {});

    return cached;
  }

  try {
    const response = await fetch(request);
    if (response.ok) {
      cache.put(request, response.clone());
    }
    return response;
  } catch (error) {
    return new Response('Offline - recurso não disponível', {
      status: 503,
      statusText: 'Service Unavailable'
    });
  }
}

/**
 * Network-First Strategy
 */
async function networkFirst(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, response.clone());
    }
    return response;
  } catch (error) {
    // Fallback para cache
    const cached = await caches.match(request);
    if (cached) {
      return cached;
    }

    // Se é API e não tem cache, retornar erro
    if (request.url.includes('/api/')) {
      return new Response(
        JSON.stringify({
          error: 'Offline - não foi possível consultar',
          cached: false
        }),
        {
          status: 503,
          statusText: 'Service Unavailable',
          headers: { 'Content-Type': 'application/json' }
        }
      );
    }

    // Para HTML, retornar página offline
    return new Response('Você está offline. Verifique sua conexão.', {
      status: 503,
      statusText: 'Service Unavailable'
    });
  }
}

/**
 * Verificar se é asset estático
 */
function isStaticAsset(pathname) {
  return (
    pathname.startsWith('/static/') ||
    pathname.endsWith('.css') ||
    pathname.endsWith('.js') ||
    pathname.endsWith('.png') ||
    pathname.endsWith('.jpg') ||
    pathname.endsWith('.svg') ||
    pathname.endsWith('.woff') ||
    pathname.endsWith('.woff2')
  );
}

/**
 * Sincronização em Background (quando voltar online)
 */
self.addEventListener('sync', (event) => {
  if (event.tag === 'sync-consultas') {
    event.waitUntil(syncConsultas());
  }
});

async function syncConsultas() {
  try {
    const cache = await caches.open(CACHE_NAME);
    const requests = await cache.keys();

    for (const request of requests) {
      if (request.url.includes('/api/consulta')) {
        try {
          const response = await fetch(request.clone());
          if (response.ok) {
            cache.put(request, response);
          }
        } catch (e) {
          // Continuar se falhar
        }
      }
    }
  } catch (e) {
    console.error('Erro ao sincronizar:', e);
  }
}

/**
 * Push Notifications (opcional)
 */
self.addEventListener('push', (event) => {
  const data = event.data?.json?.() || {
    title: 'Detetive - Notificação',
    body: 'Você tem uma nova notificação'
  };

  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: '/static/favicon.png',
      badge: '/static/favicon.png',
      tag: 'detetive-notification'
    })
  );
});

/**
 * Notfication Click
 */
self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  event.waitUntil(
    clients.matchAll({ type: 'window' }).then((windows) => {
      if (windows.length > 0) {
        windows[0].focus();
      } else {
        clients.openWindow('/');
      }
    })
  );
});
