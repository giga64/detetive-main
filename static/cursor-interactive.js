/**
 * Cursor Interactive - OneSeek
 * Cursor customizado com efeitos interativos
 */

(function() {
  'use strict';

  let mouseX = 0;
  let mouseY = 0;
  let cursorX = 0;
  let cursorY = 0;
  const speed = 0.2;

  /**
   * Criar cursor customizado
   */
  function initCustomCursor() {
    const cursor = document.createElement('div');
    cursor.id = 'custom-cursor';
    cursor.className = 'custom-cursor';

    const trail = document.createElement('div');
    trail.className = 'cursor-trail';

    document.body.appendChild(cursor);
    document.body.appendChild(trail);

    // CSS
    if (!document.getElementById('cursor-styles')) {
      const style = document.createElement('style');
      style.id = 'cursor-styles';
      style.textContent = `
        .custom-cursor {
          position: fixed;
          width: 12px;
          height: 12px;
          border: 2px solid var(--color-accent);
          border-radius: 50%;
          pointer-events: none;
          z-index: 9998;
          mix-blend-mode: lighten;
          box-shadow: 0 0 10px var(--color-accent);
          display: none;
        }

        .custom-cursor.active {
          display: block;
        }

        .cursor-trail {
          position: fixed;
          width: 6px;
          height: 6px;
          background: var(--color-accent);
          border-radius: 50%;
          pointer-events: none;
          z-index: 9997;
          opacity: 0.3;
          display: none;
          box-shadow: 0 0 5px var(--color-accent);
        }

        .cursor-trail.active {
          display: block;
        }

        /* Cursor padrão do navegador fica invisível */
        body.custom-cursor-active {
          cursor: none !important;
        }

        body.custom-cursor-active * {
          cursor: none !important;
        }

        /* Exceto em inputs */
        body.custom-cursor-active input,
        body.custom-cursor-active textarea,
        body.custom-cursor-active select {
          cursor: text !important;
        }

        /* Hover em botões */
        .custom-cursor.hitting {
          width: 20px;
          height: 20px;
          margin-left: -10px;
          margin-top: -10px;
          border-width: 3px;
          box-shadow: 0 0 20px var(--color-accent), inset 0 0 10px var(--color-accent);
        }
      `;
      document.head.appendChild(style);
    }

    // Ativar cursor customizado
    const cursor_el = document.getElementById('custom-cursor');
    cursor_el?.classList.add('active');
    document.getElementById('custom-cursor')?.parentElement.classList.add('custom-cursor-active');
    document.body.classList.add('custom-cursor-active');

    // Rastrear movimento do mouse
    document.addEventListener('mousemove', (e) => {
      mouseX = e.clientX;
      mouseY = e.clientY;

      const cursor = document.getElementById('custom-cursor');
      if (!cursor) return;

      cursor.style.left = mouseX + 'px';
      cursor.style.top = mouseY + 'px';
      cursor.style.transform = 'translate(-50%, -50%)';

      // Efeito de seguimento suave
      cursorX += (mouseX - cursorX) * speed;
      cursorY += (mouseY - cursorY) * speed;

      // Criar trail
      const trail = document.querySelector('.cursor-trail');
      if (trail && Math.random() > 0.7) {
        const trailClone = trail.cloneNode();
        trailClone.style.left = cursorX + 'px';
        trailClone.style.top = cursorY + 'px';
        trailClone.classList.add('active');
        document.body.appendChild(trailClone);

        setTimeout(() => {
          trailClone.style.opacity = '0';
          trailClone.style.transition = 'opacity 0.5s ease-out';
        }, 10);

        setTimeout(() => trailClone.remove(), 500);
      }
    });

    // Hover em elementos interativos
    document.addEventListener('mouseover', (e) => {
      const cursor = document.getElementById('custom-cursor');
      if (!cursor) return;

      const isInteractive = e.target.closest('button, a, input, textarea, select, [data-interactive]');
      
      if (isInteractive) {
        cursor.classList.add('hitting');
      } else {
        cursor.classList.remove('hitting');
      }
    });

    document.addEventListener('mouseout', (e) => {
      const cursor = document.getElementById('custom-cursor');
      if (cursor) cursor.classList.remove('hitting');
    });

    // Esconder cursor ao sair da janela
    document.addEventListener('mouseleave', () => {
      const cursor = document.getElementById('custom-cursor');
      if (cursor) cursor.style.opacity = '0';
    });

    document.addEventListener('mouseenter', () => {
      const cursor = document.getElementById('custom-cursor');
      if (cursor) cursor.style.opacity = '1';
    });
  }

  /**
   * Inicialização
   */
  function init() {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', initCustomCursor);
    } else {
      initCustomCursor();
    }
  }

  init();
})();
