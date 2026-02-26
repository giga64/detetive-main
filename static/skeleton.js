/**
 * Skeleton Loading & Progressive Rendering
 * 
 * Cria placeholders enquanto dados carregam via SSE
 */

class SkeletonLoader {
  /**
   * Criar skeleton para resultado
   */
  static createResultSkeleton() {
    const html = `
      <div class="card slide-up">
        <div class="card-header">
          <div class="skeleton skeleton-lg" style="width: 40%"></div>
          <div class="skeleton skeleton-sm" style="width: 20%; margin-top: 8px"></div>
        </div>
        
        <div class="card-body">
          <div class="skeleton" style="width: 100%; height: 100px"></div>
          <div class="skeleton" style="width: 80%; margin-top: 12px"></div>
          <div class="skeleton" style="width: 60%; margin-top: 12px"></div>
        </div>
      </div>
    `;
    
    return html;
  }

  /**
   * Criar skeletons para múltiplos itens
   */
  static createListSkeleton(count = 3) {
    let html = '';
    for (let i = 0; i < count; i++) {
      html += `
        <div class="card" style="margin-bottom: 16px;">
          <div style="display: flex; gap: 12px;">
            <div class="skeleton" style="width: 60px; height: 60px; border-radius: 8px;"></div>
            <div style="flex: 1;">
              <div class="skeleton" style="width: 60%;"></div>
              <div class="skeleton" style="width: 40%; margin-top: 8px;"></div>
              <div class="skeleton" style="width: 50%; margin-top: 8px;"></div>
            </div>
          </div>
        </div>
      `;
    }
    return html;
  }

  /**
   * Substituir skeleton por conteúdo real
   */
  static replaceSkeleton(selector, content) {
    const container = document.querySelector(selector);
    if (!container) return;

    // Adicionar classe de transição
    container.classList.add('fade-in');
    
    // Animate out skeleton
    const skeletons = container.querySelectorAll('.skeleton');
    skeletons.forEach((sk, i) => {
      setTimeout(() => {
        sk.style.opacity = '0';
      }, i * 50);
    });

    // Substituir após animação
    setTimeout(() => {
      container.innerHTML = content;
      container.querySelectorAll('[data-animate]').forEach((el) => {
        el.classList.add('slide-up');
      });
    }, 300);
  }

  /**
   * Render progressivo (tipo stream)
   */
  static renderProgressive(selector, data) {
    const container = document.querySelector(selector);
    if (!container) return;

    // Limpar skeletons existentes
    container.innerHTML = '';

    // Renderizar dados em sequência
    Object.entries(data).forEach(([key, value], index) => {
      setTimeout(() => {
        const el = this.createDataElement(key, value);
        el.classList.add('slide-up');
        container.appendChild(el);
      }, index * 150); // Cada item entra a cada 150ms
    });
  }

  /**
   * Criar elemento para um dado
   */
  static createDataElement(key, value) {
    const div = document.createElement('div');
    div.className = 'data-item card mb-md';
    div.setAttribute('data-animate', '');

    // Formatar chave
    const formattedKey = key
      .replace(/_/g, ' ')
      .replace(/\b\w/g, (l) => l.toUpperCase());

    // Renderizar valor
    let renderedValue = this.renderValue(value);

    div.innerHTML = `
      <div class="flex-between">
        <strong>${formattedKey}</strong>
        <button class="btn btn-secondary" data-copy="${value}" title="Copiar">
          📋
        </button>
      </div>
      <div style="margin-top: 8px; color: var(--color-text-secondary);">
        ${renderedValue}
      </div>
    `;

    return div;
  }

  /**
   * Renderizar valor (pode ser string, array, objeto)
   */
  static renderValue(value) {
    if (Array.isArray(value)) {
      return value
        .map((v) => `<div style="padding: 4px 0;">• ${this.renderValue(v)}</div>`)
        .join('');
    }

    if (typeof value === 'object') {
      return JSON.stringify(value, null, 2);
    }

    return String(value);
  }
}

/**
 * Estilos para skeleton
 * (Adicionar ao design-system.css ou inline)
 */
const SKELETON_CSS = `
  .skeleton {
    height: 16px;
    background: linear-gradient(
      90deg,
      var(--color-bg-tertiary) 25%,
      var(--color-border) 50%,
      var(--color-bg-tertiary) 75%
    );
    background-size: 200% 100%;
    animation: pulse 1.5s infinite;
    border-radius: var(--radius-md);
  }

  .skeleton-sm {
    height: 12px;
  }

  .skeleton-lg {
    height: 24px;
  }

  @keyframes pulse {
    0%, 100% {
      background-position: 200% 0;
    }
    50% {
      background-position: -200% 0;
    }
  }
`;

// Injetar estilos
if (typeof document !== 'undefined') {
  const style = document.createElement('style');
  style.textContent = SKELETON_CSS;
  document.head.appendChild(style);
}

// Exportar
if (typeof module !== 'undefined' && module.exports) {
  module.exports = SkeletonLoader;
}
