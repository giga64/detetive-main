/**
 * Metrics & Conversions Tracking
 * 
 * Rastreia eventos de conversão e comportamento do usuário
 * Rauch mindset: "Se não mede, não existe"
 */

class MetricsTracker {
  constructor() {
    this.sessionId = this.generateSessionId();
    this.events = [];
    this.conversionFunnel = {
      visit: false,
      consulta_iniciada: false,
      resultado_obtido: false,
      download_realizado: false,
      compartilhado: false
    };

    this.init();
  }

  generateSessionId() {
    return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }

  init() {
    // Rastrear visita
    this.recordEvent('page_visit', {
      url: window.location.href,
      referrer: document.referrer,
      userAgent: navigator.userAgent
    });
    this.conversionFunnel.visit = true;

    // Rastrear interações importantes
    this.trackFormSubmit();
    this.trackDownloads();
    this.trackSharing();
    this.trackSearchQueries();

    // Auto-submit a cada 60s
    setInterval(() => this.submit(), 60000);
  }

  /**
   * Rastrear envio de formulário (consulta)
   */
  trackFormSubmit() {
    document.addEventListener('submit', (e) => {
      const form = e.target;

      // Se for formulário de consulta
      if (form.querySelector('input[name="identificador"]')) {
        const query = form.querySelector('input[name="identificador"]').value;
        const type = form.querySelector('input[name="tipo"]')?.value || 'auto';

        this.recordEvent('consulta_iniciada', {
          query: query,
          type: type,
          timestamp: Date.now()
        });

        this.conversionFunnel.consulta_iniciada = true;

        // Rastrear tempo até resultado
        const startTime = Date.now();
        const observer = new MutationObserver(() => {
          if (document.querySelector('#resultado')) {
            const loadTime = Date.now() - startTime;

            this.recordEvent('resultado_obtido', {
              loadTime: loadTime,
              query: query,
              timestamp: Date.now()
            });

            this.conversionFunnel.resultado_obtido = true;
            observer.disconnect();
          }
        });

        observer.observe(document.body, {
          childList: true,
          subtree: true
        });
      }
    });
  }

  /**
   * Rastrear downloads
   */
  trackDownloads() {
    document.addEventListener('click', (e) => {
      if (
        e.target.matches('[download]') ||
        e.target.matches('.btn-download') ||
        e.target.matches('a[href*=".pdf"]') ||
        e.target.matches('a[href*=".xlsx"]')
      ) {
        const filename = e.target.getAttribute('download') || e.target.href.split('/').pop();

        this.recordEvent('download_realizado', {
          filename: filename,
          timestamp: Date.now()
        });

        this.conversionFunnel.download_realizado = true;
      }
    });
  }

  /**
   * Rastrear compartilhamentos
   */
  trackSharing() {
    document.addEventListener('click', (e) => {
      if (e.target.matches('[data-share]') || e.target.matches('.btn-share')) {
        const shareType = e.target.getAttribute('data-share') || 'unknown';

        this.recordEvent('compartilhado', {
          type: shareType,
          url: window.location.href,
          timestamp: Date.now()
        });

        this.conversionFunnel.compartilhado = true;
      }
    });

    // Web Share API
    if (navigator.share) {
      document.addEventListener('click', (e) => {
        if (e.target.matches('[data-native-share]')) {
          navigator.share({
            title: 'Detetive',
            text: document.title,
            url: window.location.href
          });
        }
      });
    }
  }

  /**
   * Rastrear buscas
   */
  trackSearchQueries() {
    const searchInput = document.querySelector('input[name="identificador"]');
    if (!searchInput) return;

    let searchTimeout;
    searchInput.addEventListener('input', (e) => {
      clearTimeout(searchTimeout);

      searchTimeout = setTimeout(() => {
        const query = e.target.value.trim();
        if (query.length > 0) {
          this.recordEvent('search_query', {
            query: query,
            length: query.length,
            timestamp: Date.now()
          });
        }
      }, 1000); // Debounce 1s
    });
  }

  /**
   * Registrar evento
   */
  recordEvent(eventName, data = {}) {
    this.events.push({
      name: eventName,
      data: data,
      timestamp: Date.now(),
      sessionId: this.sessionId
    });

    console.log(`📊 Evento: ${eventName}`, data);

    // Se foi conversão importante, enviar imediatamente
    if (['resultado_obtido', 'download_realizado', 'compartilhado'].includes(eventName)) {
      this.submit();
    }
  }

  /**
   * Enviar métricas para backend
   */
  async submit() {
    if (this.events.length === 0) return;

    const payload = {
      sessionId: this.sessionId,
      events: this.events,
      funnel: this.conversionFunnel,
      timestamp: Date.now()
    };

    try {
      const response = await fetch('/api/metrics/events', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (response.ok) {
        console.log('✅ Métricas enviadas');
        this.events = []; // Limpar eventos enviados
      }
    } catch (e) {
      console.warn('⚠️ Erro ao enviar métricas:', e);
    }
  }

  /**
   * Obter status da conversão
   */
  getConversionStatus() {
    const completed = Object.values(this.conversionFunnel).filter(Boolean).length;
    const total = Object.keys(this.conversionFunnel).length;

    return {
      completed: completed,
      total: total,
      percentage: Math.round((completed / total) * 100),
      funnel: this.conversionFunnel
    };
  }

  /**
   * Debug: Log status completo
   */
  debug() {
    console.group('📊 Métricas');
    console.log('Session ID:', this.sessionId);
    console.log('Eventos:', this.events);
    console.log('Conversão:', this.getConversionStatus());
    console.groupEnd();
  }
}

// Inicializar globalmente
if (typeof document !== 'undefined') {
  document.addEventListener('DOMContentLoaded', () => {
    window.metricsTracker = new MetricsTracker();
  });
}

// Exportar
if (typeof module !== 'undefined' && module.exports) {
  module.exports = MetricsTracker;
}
