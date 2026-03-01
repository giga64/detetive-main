/**
 * Loading Narrative - OneSeek
 * Animações de loading com narrativa detetivesca
 */

(function() {
  'use strict';

  const loadingMessages = [
    '🔍 Rastreando pistas...',
    '📡 Conectando ao servidor secreto...',
    '🔐 Criptografando dados...',
    '📊 Analisando padrões...',
    '🎯 Triangulando coordenadas...',
    '⚡ Acelerando processamento...',
    '🕵️ Investigando...',
    '💾 Salvando evidências...',
    '🔔 Notificando agentes...',
    '✅ Quase lá...',
  ];

  let messageIndex = 0;

  /**
   * Criar overlay de loading
   */
  class LoadingOverlay {
    constructor() {
      this.overlay = null;
      this.progressBar = null;
      this.messageEl = null;
      this.progress = 0;
    }

    show(title = 'Carregando...') {
      if (this.overlay) return;

      this.overlay = document.createElement('div');
      this.overlay.id = 'loading-overlay';
      this.overlay.innerHTML = `
        <div class="loading-container">
          <div class="loading-content">
            <h2>${title}</h2>
            <div class="loading-spinner">
              <div class="spinner-ring"></div>
              <div class="spinner-ring"></div>
              <div class="spinner-ring"></div>
            </div>
            <p class="loading-message">${loadingMessages[0]}</p>
            <div class="progress-bar">
              <div class="progress-fill"></div>
            </div>
            <p class="loading-percent">0%</p>
          </div>
        </div>
      `;

      document.body.appendChild(this.overlay);
      this.progressBar = this.overlay.querySelector('.progress-fill');
      this.messageEl = this.overlay.querySelector('.loading-message');

      // CSS
      this.injectStyles();

      // Iniciar animação de progresso
      this.startProgressAnimation();
    }

    hide() {
      if (this.overlay) {
        this.overlay.style.opacity = '0';
        setTimeout(() => {
          this.overlay?.remove();
          this.overlay = null;
          this.progress = 0;
        }, 300);
      }
    }

    setProgress(percent) {
      this.progress = Math.min(percent, 90); // Máximo 90% automático
      if (this.progressBar) {
        this.progressBar.style.width = this.progress + '%';
      }
      if (this.overlay) {
        const percentEl = this.overlay.querySelector('.loading-percent');
        if (percentEl) percentEl.textContent = Math.round(this.progress) + '%';
      }
    }

    setMessage(message) {
      if (this.messageEl) {
        this.messageEl.textContent = message;
      }
    }

    startProgressAnimation() {
      messageIndex = 0;
      const messageInterval = setInterval(() => {
        if (!this.overlay) {
          clearInterval(messageInterval);
          return;
        }

        messageIndex = (messageIndex + 1) % loadingMessages.length;
        this.setMessage(loadingMessages[messageIndex]);

        // Aumentar progresso lentamente
        if (this.progress < 85) {
          this.setProgress(this.progress + Math.random() * 15);
        }
      }, 1500);
    }

    injectStyles() {
      if (!document.getElementById('loading-styles')) {
        const style = document.createElement('style');
        style.id = 'loading-styles';
        style.textContent = `
          #loading-overlay {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: linear-gradient(135deg, rgba(15, 23, 42, 0.95) 0%, rgba(30, 41, 59, 0.95) 100%);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 10000;
            animation: fadeIn 0.3s ease-in;
            backdrop-filter: blur(4px);
          }

          #loading-overlay.hidden {
            animation: fadeOut 0.3s ease-out;
            opacity: 0;
            pointer-events: none;
          }

          .loading-container {
            text-align: center;
            color: var(--color-text-primary);
          }

          .loading-content {
            max-width: 400px;
          }

          .loading-content h2 {
            font-size: 1.5rem;
            margin-bottom: 2rem;
            color: var(--color-accent);
            text-shadow: 0 0 10px rgba(14, 165, 233, 0.3);
            animation: pulse 2s ease-in-out infinite;
          }

          .loading-spinner {
            position: relative;
            width: 120px;
            height: 120px;
            margin: 0 auto 2rem;
          }

          .spinner-ring {
            position: absolute;
            top: 50%;
            left: 50%;
            width: 100%;
            height: 100%;
            border: 3px solid transparent;
            border-top-color: var(--color-accent);
            border-radius: 50%;
            transform: translate(-50%, -50%);
            animation: spin 1.5s linear infinite;
          }

          .spinner-ring:nth-child(2) {
            width: 70%;
            height: 70%;
            animation: spin 2s linear infinite reverse;
            border-top-color: var(--color-accent-dark);
          }

          .spinner-ring:nth-child(3) {
            width: 40%;
            height: 40%;
            animation: spin 1s linear infinite;
            border-top-color: rgba(14, 165, 233, 0.5);
          }

          .loading-message {
            font-size: 1rem;
            color: var(--color-text-secondary);
            margin: 1rem 0;
            min-height: 1.5rem;
            animation: fadeInOut 1.5s ease-in-out infinite;
          }

          .progress-bar {
            width: 100%;
            height: 4px;
            background: var(--color-gray-700);
            border-radius: 2px;
            margin: 1.5rem 0;
            overflow: hidden;
          }

          .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, var(--color-accent) 0%, var(--color-accent-dark) 100%);
            width: 0%;
            transition: width 0.3s ease-out;
            box-shadow: 0 0 10px var(--color-accent);
          }

          .loading-percent {
            font-size: 0.9rem;
            color: var(--color-text-muted);
          }

          @keyframes spin {
            to { transform: translate(-50%, -50%) rotate(360deg); }
          }

          @keyframes fadeInOut {
            0%, 100% { opacity: 0.5; }
            50% { opacity: 1; }
          }

          @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
          }

          @keyframes fadeOut {
            from { opacity: 1; }
            to { opacity: 0; }
          }

          @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.8; }
          }
        `;
        document.head.appendChild(style);
      }
    }
  }

  // Instância global
  window.LoadingOverlay = LoadingOverlay;
  window.loadingOverlay = new LoadingOverlay();

  /**
   * Integração automática com Fetch API
   */
  const originalFetch = window.fetch;
  window.fetch = function(...args) {
    const isLongRequest = args[0]?.toString().includes('consulta');
    
    if (isLongRequest) {
      window.loadingOverlay.show('Consultando...');
    }

    return originalFetch.apply(this, args)
      .then(response => {
        if (isLongRequest) {
          window.loadingOverlay.hide();
        }
        return response;
      })
      .catch(error => {
        if (isLongRequest) {
          window.loadingOverlay.hide();
        }
        throw error;
      });
  };

  /**
   * Inicialização
   */
  function init() {
    // Mostrar loading na navegação de página
    let isNavigating = false;

    document.addEventListener('click', (e) => {
      const link = e.target.closest('a[href^="/"]');
      if (!link || isNavigating) return;

      const href = link.getAttribute('href');
      if (href === window.location.pathname) return;

      isNavigating = true;
      window.loadingOverlay.show('Redirecionando...');
    });

    // Restaurar ao carregar página
    window.addEventListener('load', () => {
      window.loadingOverlay.hide();
      isNavigating = false;
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
