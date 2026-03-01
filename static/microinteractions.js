/**
 * Microinteractions - OneSeek
 * Feedback visual para interações do usuário
 */

(function() {
  'use strict';

  /**
   * Ripple effect ao clicar em elementos
   */
  function addRippleEffect() {
    document.addEventListener('click', function(e) {
      const target = e.target.closest('[data-ripple], .btn, .btn-primary, .btn-secondary, .btn-danger');
      if (!target) return;

      const rect = target.getBoundingClientRect();
      const size = Math.max(rect.width, rect.height);
      const x = e.clientX - rect.left - size / 2;
      const y = e.clientY - rect.top - size / 2;

      const ripple = document.createElement('span');
      ripple.classList.add('ripple');
      ripple.style.width = ripple.style.height = size + 'px';
      ripple.style.left = x + 'px';
      ripple.style.top = y + 'px';

      target.style.position = target.style.position || 'relative';
      target.style.overflow = 'hidden';
      target.appendChild(ripple);

      setTimeout(() => ripple.remove(), 600);
    });

    // CSS para o ripple
    if (!document.getElementById('ripple-styles')) {
      const style = document.createElement('style');
      style.id = 'ripple-styles';
      style.textContent = `
        .ripple {
          position: absolute;
          pointer-events: none;
          border-radius: 50%;
          background-color: rgba(255, 255, 255, 0.5);
          transform: scale(0);
          animation: rippleAnimation 0.6s ease-out;
        }
        @keyframes rippleAnimation {
          to {
            transform: scale(4);
            opacity: 0;
          }
        }
      `;
      document.head.appendChild(style);
    }
  }

  /**
   * Feedback de hover com glow
   */
  function addHoverGlow() {
    document.addEventListener('mouseover', function(e) {
      const target = e.target.closest('[data-glow]');
      if (!target) return;

      target.style.boxShadow = '0 0 20px rgba(14, 165, 233, 0.3)';
    });

    document.addEventListener('mouseout', function(e) {
      const target = e.target.closest('[data-glow]');
      if (!target) return;

      target.style.boxShadow = '';
    });
  }

  /**
   * Tolltip customizado
   */
  function initTooltips() {
    document.addEventListener('mouseover', function(e) {
      const target = e.target.closest('[data-tooltip]');
      if (!target) return;

      const tooltip = document.createElement('div');
      tooltip.className = 'custom-tooltip';
      tooltip.textContent = target.getAttribute('data-tooltip');
      document.body.appendChild(tooltip);

      const rect = target.getBoundingClientRect();
      tooltip.style.left = (rect.left + rect.width / 2 - tooltip.offsetWidth / 2) + 'px';
      tooltip.style.top = (rect.top - tooltip.offsetHeight - 8) + 'px';

      setTimeout(() => tooltip.remove(), 3000);
    });

    // CSS para o tooltip
    if (!document.getElementById('tooltip-styles')) {
      const style = document.createElement('style');
      style.id = 'tooltip-styles';
      style.textContent = `
        .custom-tooltip {
          position: fixed;
          background-color: var(--color-dark);
          color: var(--color-text-primary);
          padding: 0.5rem 0.75rem;
          border-radius: 0.375rem;
          font-size: 0.85rem;
          border: 1px solid var(--color-gray-600);
          box-shadow: 0 10px 15px rgba(0, 0, 0, 0.1);
          z-index: var(--z-tooltip);
          pointer-events: none;
          animation: tooltipFade 0.3s ease-in;
        }
        @keyframes tooltipFade {
          from { opacity: 0; transform: translateY(8px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `;
      document.head.appendChild(style);
    }
  }

  /**
   * Feedback ao submeter formulário
   */
  function addFormFeedback() {
    document.addEventListener('submit', function(e) {
      const form = e.target;
      const submitBtn = form.querySelector('button[type="submit"]');

      if (submitBtn && !submitBtn.disabled) {
        submitBtn.disabled = true;
        submitBtn.classList.add('submitting');
        submitBtn.innerHTML = '<span class="spinner"></span> Enviando...';

        // Restaurar após sucesso (será restaurado pelo servidor se houver erro)
        form.addEventListener('submit', function() {
          setTimeout(() => {
            submitBtn.disabled = false;
            submitBtn.classList.remove('submitting');
            submitBtn.innerHTML = submitBtn.getAttribute('data-original-text') || 'Enviar';
          }, 2000);
        }, { once: true });
      }
    });
  }

  /**
   * Feedback ao copiar para clipboard
   */
  function addCopyFeedback() {
    document.addEventListener('click', function(e) {
      const target = e.target.closest('[data-copy]');
      if (!target) return;

      const text = target.getAttribute('data-copy');
      navigator.clipboard.writeText(text).then(() => {
        const originalText = target.textContent;
        target.textContent = '✓ Copiado!';
        target.style.color = 'var(--color-success)';

        setTimeout(() => {
          target.textContent = originalText;
          target.style.color = '';
        }, 2000);
      });
    });
  }

  /**
   * Transição de página ao navegar
   */
  function addPageTransitions() {
    document.addEventListener('click', function(e) {
      const link = e.target.closest('a[href^="/"]');
      if (!link) return;

      const href = link.getAttribute('href');
      if (href === window.location.pathname) return;

      const overlay = document.createElement('div');
      overlay.className = 'page-transition';
      document.body.appendChild(overlay);

      setTimeout(() => {
        window.location.href = href;
      }, 300);
    });

    // CSS para a transição
    if (!document.getElementById('transition-styles')) {
      const style = document.createElement('style');
      style.id = 'transition-styles';
      style.textContent = `
        .page-transition {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: linear-gradient(135deg, var(--color-accent) 0%, var(--color-accent-dark) 100%);
          z-index: 9999;
          animation: pageTransitionFade 0.3s ease-out;
        }
        @keyframes pageTransitionFade {
          from { opacity: 0; }
          to { opacity: 1; }
        }
      `;
      document.head.appendChild(style);
    }
  }

  /**
   * Controle de visibilidade de senhas
   */
  function addPasswordToggle() {
    document.addEventListener('click', function(e) {
      const target = e.target.closest('[data-toggle-password]');
      if (!target) return;

      const inputId = target.getAttribute('data-toggle-password');
      const input = document.getElementById(inputId);
      
      if (!input) return;

      const isPassword = input.type === 'password';
      input.type = isPassword ? 'text' : 'password';
      target.textContent = isPassword ? '🙈 Ocultar' : '👁️ Mostrar';
    });
  }

  /**
   * Inicialização
   */
  function init() {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', init);
    } else {
      addRippleEffect();
      addHoverGlow();
      initTooltips();
      addFormFeedback();
      addCopyFeedback();
      addPageTransitions();
      addPasswordToggle();
    }
  }

  init();
})();
