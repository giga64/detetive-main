/**
 * Dark/Light Mode Toggle
 * 
 * Suporta preferências do sistema e escolha manual do usuário
 */

class ThemeToggle {
  constructor(options = {}) {
    this.storageKey = options.storageKey || 'detetive-theme';
    this.buttonSelector = options.buttonSelector || '[data-theme-toggle]';
    this.htmlElement = document.documentElement;

    this.init();
  }

  /**
   * Inicializar
   */
  init() {
    // 1. Obter tema salvo ou preferência do sistema
    const savedTheme = localStorage.getItem(this.storageKey);
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const initialTheme = savedTheme || (prefersDark ? 'dark' : 'light');

    // 2. Aplicar tema
    this.setTheme(initialTheme);

    // 3. Listeners
    const button = document.querySelector(this.buttonSelector);
    if (button) {
      button.addEventListener('click', () => this.toggle());
      this.updateButtonIcon(initialTheme);
    }

    // 4. Monitorar mudança de preferência do sistema
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
      if (!localStorage.getItem(this.storageKey)) {
        this.setTheme(e.matches ? 'dark' : 'light');
      }
    });
  }

  /**
   * Definir tema
   */
  setTheme(theme) {
    const isValid = theme === 'dark' || theme === 'light';
    if (!isValid) return;

    // Atualizar HTML
    this.htmlElement.setAttribute('data-theme', theme);

    // Salvar preferência
    localStorage.setItem(this.storageKey, theme);

    // Atualizar ícone do botão
    this.updateButtonIcon(theme);

    // Disparar evento
    window.dispatchEvent(new CustomEvent('theme-changed', { detail: { theme } }));
  }

  /**
   * Toggle tema
   */
  toggle() {
    const current = this.htmlElement.getAttribute('data-theme') || 'light';
    const next = current === 'dark' ? 'light' : 'dark';
    this.setTheme(next);
  }

  /**
   * Atualizar ícone do botão
   */
  updateButtonIcon(theme) {
    const button = document.querySelector(this.buttonSelector);
    if (!button) return;

    if (theme === 'dark') {
      button.innerHTML = '☀️'; // Sol para mudar pra light
      button.title = 'Mudar para Modo Claro';
    } else {
      button.innerHTML = '🌙'; // Lua para mudar pra dark
      button.title = 'Mudar para Modo Escuro';
    }
  }

  /**
   * Obter tema atual
   */
  getCurrentTheme() {
    return this.htmlElement.getAttribute('data-theme') || 'light';
  }

  /**
   * Verificar se está em dark mode
   */
  isDarkMode() {
    return this.getCurrentTheme() === 'dark';
  }
}

// Inicializar automaticamente ao carregar
if (typeof document !== 'undefined') {
  document.addEventListener('DOMContentLoaded', () => {
    window.themeToggle = new ThemeToggle({
      storageKey: 'detetive-theme',
      buttonSelector: '[data-theme-toggle]'
    });
  });
}

// Permitir acesso manual também
if (typeof window !== 'undefined') {
  window.ThemeToggle = ThemeToggle;
}

// Exportar
if (typeof module !== 'undefined' && module.exports) {
  module.exports = ThemeToggle;
}
