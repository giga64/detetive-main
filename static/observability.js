/**
 * Observabilidade Frontend
 * Web Vitals + Error Tracking + User Journey
 * 
 * Tudo é enviado pra /api/metrics
 */

class Observability {
  constructor() {
    this.sessionId = this.generateSessionId();
    this.pageLoadTime = performance.now();
    this.metrics = {};
    this.errors = [];
    this.journey = [];
    
    this.init();
  }

  generateSessionId() {
    return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }

  init() {
    // Rastrear Web Vitals (Largest Contentful Paint, First Input Delay, Cumulative Layout Shift)
    this.trackWebVitals();
    
    // Rastrear erros
    this.trackErrors();
    
    // Rastrear jornada do usuário
    this.trackJourney();
    
    // Enviar métricas periodicamente
    setInterval(() => this.sendMetrics(), 30000); // A cada 30s
    
    // Enviar ao descarregar página
    window.addEventListener('beforeunload', () => this.sendMetrics());
  }

  /**
   * Web Vitals: LCP, FID, CLS
   */
  trackWebVitals() {
    // Largest Contentful Paint (LCP) - tempo até maior elemento
    if ('PerformanceObserver' in window) {
      try {
        const lcpObserver = new PerformanceObserver((entryList) => {
          const entries = entryList.getEntries();
          const lastEntry = entries[entries.length - 1];
          
          this.metrics.lcp = {
            value: Math.round(lastEntry.renderTime || lastEntry.loadTime),
            timestamp: Date.now(),
            status: lastEntry.renderTime || lastEntry.loadTime < 2500 ? 'good' : 'poor'
          };
        });
        lcpObserver.observe({ entryTypes: ['largest-contentful-paint'] });
      } catch (e) {
        console.warn('⚠️ LCP não suportado', e);
      }

      // First Input Delay (FID)
      try {
        const fidObserver = new PerformanceObserver((entryList) => {
          const entries = entryList.getEntries();
          const entry = entries[0];
          
          this.metrics.fid = {
            value: Math.round(entry.processingDuration),
            timestamp: Date.now(),
            status: entry.processingDuration < 100 ? 'good' : 'poor'
          };
        });
        fidObserver.observe({ entryTypes: ['first-input'] });
      } catch (e) {
        console.warn('⚠️ FID não suportado', e);
      }

      // Cumulative Layout Shift (CLS)
      try {
        let clsValue = 0;
        const clsObserver = new PerformanceObserver((entryList) => {
          for (const entry of entryList.getEntries()) {
            if (!entry.hadRecentInput) {
              clsValue += entry.value;
            }
          }
          
          this.metrics.cls = {
            value: Math.round(clsValue * 1000) / 1000,
            timestamp: Date.now(),
            status: clsValue < 0.1 ? 'good' : 'poor'
          };
        });
        clsObserver.observe({ entryTypes: ['layout-shift'] });
      } catch (e) {
        console.warn('⚠️ CLS não suportado', e);
      }
    }

    // TTL (Time to Interactive) - tempo até página interativa
    if ('PerformanceObserver' in window) {
      try {
        const perfObserver = new PerformanceObserver((list) => {
          const entries = list.getEntries();
          const navigationEntry = entries[0];
          
          this.metrics.ttl = {
            value: Math.round(navigationEntry.domInteractive - navigationEntry.fetchStart),
            timestamp: Date.now()
          };
        });
        perfObserver.observe({ entryTypes: ['navigation'] });
      } catch (e) {
        console.warn('⚠️ TTL não suportado', e);
      }
    }
  }

  /**
   * Rastrear erros JavaScript
   */
  trackErrors() {
    window.addEventListener('error', (event) => {
      this.errors.push({
        type: 'js_error',
        message: event.message,
        filename: event.filename,
        lineno: event.lineno,
        colno: event.colno,
        stack: event.error?.stack,
        timestamp: Date.now()
      });

      // Se muitos erros, enviar imediatamente
      if (this.errors.length > 5) {
        this.sendMetrics();
      }
    });

    // Unhandled Promise Rejections
    window.addEventListener('unhandledrejection', (event) => {
      this.errors.push({
        type: 'unhandled_promise',
        reason: event.reason?.message || String(event.reason),
        stack: event.reason?.stack,
        timestamp: Date.now()
      });
    });
  }

  /**
   * Rastrear jornada do usuário (clicks, navegação, etc)
   */
  trackJourney() {
    // Rastrear clicks em elementos importantes
    document.addEventListener('click', (event) => {
      const target = event.target;
      
      if (target.matches('[data-track]')) {
        this.journey.push({
          event: 'click',
          element: target.getAttribute('data-track'),
          timestamp: Date.now()
        });
      }

      // Rastrear cliques em botões de consulta
      if (target.closest('button[type="submit"]') || target.closest('.btn-success')) {
        this.journey.push({
          event: 'consulta_iniciada',
          timestamp: Date.now()
        });
      }
    });

    // Rastrear quando resultado é visível
    if ('IntersectionObserver' in window) {
      const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          if (entry.target.id === 'resultado' && entry.isIntersecting) {
            this.journey.push({
              event: 'resultado_visivel',
              timestamp: Date.now()
            });
          }
        });
      });

      const resultado = document.getElementById('resultado');
      if (resultado) observer.observe(resultado);
    }
  }

  /**
   * Enviar métricas para backend
   */
  async sendMetrics() {
    if (Object.keys(this.metrics).length === 0 && this.errors.length === 0 && this.journey.length === 0) {
      return; // Nada pra enviar
    }

    const payload = {
      sessionId: this.sessionId,
      userAgent: navigator.userAgent,
      url: window.location.href,
      timestamp: Date.now(),
      metrics: this.metrics,
      errors: this.errors.slice(-10), // Últimos 10 erros
      journey: this.journey.slice(-20), // Últimas 20 ações
      vitals: {
        navigationTiming: this.getNavigationTiming()
      }
    };

    try {
      await fetch('/api/metrics', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      // Limpar depois de enviar
      this.errors = [];
    } catch (e) {
      console.warn('⚠️ Erro ao enviar métricas:', e);
    }
  }

  /**
   * Obter timing de navegação
   */
  getNavigationTiming() {
    if (!window.performance.timing) return {};

    const timing = performance.timing;
    return {
      dns: timing.domainLookupEnd - timing.domainLookupStart,
      tcp: timing.connectEnd - timing.connectStart,
      request: timing.responseStart - timing.requestStart,
      response: timing.responseEnd - timing.responseStart,
      dom: timing.domInteractive - timing.domLoading,
      load: timing.loadEventEnd - timing.loadEventStart,
      total: timing.loadEventEnd - timing.navigationStart
    };
  }

  /**
   * Log customizado (útil para debugging)
   */
  log(evento, dados = {}) {
    this.journey.push({
      event: evento,
      data: dados,
      timestamp: Date.now()
    });
  }

  /**
   * Rastrear conversão (usuário completou ação)
   */
  trackConversion(tipo, valor = 1) {
    fetch('/api/metrics/conversion', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sessionId: this.sessionId,
        type: tipo,
        value: valor,
        timestamp: Date.now()
      })
    }).catch(e => console.warn('⚠️ Erro ao rastrear conversão:', e));
  }
}

// Inicializar globalmente
window.observability = new Observability();

// Exportar para uso em outros scripts
if (typeof module !== 'undefined' && module.exports) {
  module.exports = Observability;
}
