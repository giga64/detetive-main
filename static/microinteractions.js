/**
 * MICROINTERACTIONS
 * Sistema de interações subtis e inteligentes
 * Inspirado em: Bruno Simon, Adham Dannaway
 */

class MicroInteractions {
    constructor() {
        this.init();
    }

    init() {
        this.initCopyable();
        this.initCardHover();
        this.initButtonFeedback();
        this.initFormFeedback();
        this.initTooltips();
    }

    /**
     * Copyable Elements - Copy com feedback visual
     */
    initCopyable() {
        document.querySelectorAll('.copyable').forEach(elem => {
            elem.addEventListener('click', async (e) => {
                const text = elem.textContent.trim();
                
                try {
                    await navigator.clipboard.writeText(text);
                    
                    // Feedback visual
                    elem.classList.add('copied');
                    
                    // Vibração (mobile)
                    if ('vibrate' in navigator) {
                        navigator.vibrate(50);
                    }
                    
                    // Remove estado após 2s
                    setTimeout(() => {
                        elem.classList.remove('copied');
                    }, 2000);
                    
                } catch (err) {
                    console.error('Erro ao copiar:', err);
                }
            });
        });
    }

    /**
     * Card Hover Effect - Materialize com delay
     */
    initCardHover() {
        document.querySelectorAll('.card').forEach(card => {
            card.addEventListener('mouseenter', (e) => {
                // Pequeno pulse no hover
                card.style.animation = 'none';
                setTimeout(() => {
                    card.style.animation = '';
                }, 10);
            });
        });
    }

    /**
     * Button Feedback - Ripple effect
     */
    initButtonFeedback() {
        document.querySelectorAll('.btn').forEach(btn => {
            btn.addEventListener('click', function(e) {
                const ripple = document.createElement('span');
                const rect = this.getBoundingClientRect();
                const size = Math.max(rect.width, rect.height);
                const x = e.clientX - rect.left - size / 2;
                const y = e.clientY - rect.top - size / 2;
                
                ripple.style.cssText = `
                    position: absolute;
                    width: ${size}px;
                    height: ${size}px;
                    left: ${x}px;
                    top: ${y}px;
                    background: rgba(255, 255, 255, 0.5);
                    border-radius: 50%;
                    transform: scale(0);
                    animation: ripple 0.6s ease-out;
                    pointer-events: none;
                `;
                
                this.style.position = 'relative';
                this.style.overflow = 'hidden';
                this.appendChild(ripple);
                
                setTimeout(() => ripple.remove(), 600);
            });
        });

        // Adicionar keyframe se não existir
        if (!document.querySelector('#ripple-keyframes')) {
            const style = document.createElement('style');
            style.id = 'ripple-keyframes';
            style.textContent = `
                @keyframes ripple {
                    to {
                        transform: scale(2);
                        opacity: 0;
                    }
                }
            `;
            document.head.appendChild(style);
        }
    }

    /**
     * Form Feedback - Input validation visual
     */
    initFormFeedback() {
        document.querySelectorAll('.input').forEach(input => {
            input.addEventListener('focus', function() {
                this.parentElement?.classList.add('focused');
            });

            input.addEventListener('blur', function() {
                this.parentElement?.classList.remove('focused');
                
                // Validação visual
                if (this.value && this.checkValidity()) {
                    this.classList.add('valid');
                    this.classList.remove('invalid');
                } else if (this.value) {
                    this.classList.add('invalid');
                    this.classList.remove('valid');
                }
            });
        });
    }

    /**
     * Tooltips - Hover com delay inteligente
     */
    initTooltips() {
        document.querySelectorAll('[data-tooltip]').forEach(elem => {
            let tooltip = null;
            let timeout = null;

            elem.addEventListener('mouseenter', function() {
                timeout = setTimeout(() => {
                    tooltip = document.createElement('div');
                    tooltip.className = 'tooltip';
                    tooltip.textContent = this.dataset.tooltip;
                    
                    const rect = this.getBoundingClientRect();
                    tooltip.style.cssText = `
                        position: fixed;
                        top: ${rect.bottom + 8}px;
                        left: ${rect.left + rect.width / 2}px;
                        transform: translateX(-50%) translateY(-10px);
                        background: rgba(15, 23, 42, 0.95);
                        backdrop-filter: blur(10px);
                        color: #f1f5f9;
                        padding: 0.5rem 0.75rem;
                        border-radius: 6px;
                        font-size: 0.875rem;
                        z-index: 10000;
                        pointer-events: none;
                        opacity: 0;
                        animation: tooltip-appear 0.2s ease-out forwards;
                        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
                    `;
                    
                    document.body.appendChild(tooltip);
                }, 500); // Delay de 500ms
            });

            elem.addEventListener('mouseleave', function() {
                clearTimeout(timeout);
                if (tooltip) {
                    tooltip.style.animation = 'tooltip-disappear 0.15s ease-out forwards';
                    setTimeout(() => tooltip?.remove(), 150);
                }
            });
        });

        // Keyframes tooltip
        if (!document.querySelector('#tooltip-keyframes')) {
            const style = document.createElement('style');
            style.id = 'tooltip-keyframes';
            style.textContent = `
                @keyframes tooltip-appear {
                    from {
                        opacity: 0;
                        transform: translateX(-50%) translateY(-10px);
                    }
                    to {
                        opacity: 1;
                        transform: translateX(-50%) translateY(0);
                    }
                }
                @keyframes tooltip-disappear {
                    to {
                        opacity: 0;
                        transform: translateX(-50%) translateY(-5px);
                    }
                }
            `;
            document.head.appendChild(style);
        }
    }
}

/**
 * SVG ICONS
 * Biblioteca de ícones SVG inline
 */
const SVGIcons = {
    search: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><path d="m21 21-4.35-4.35"></path></svg>`,
    
    check: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>`,
    
    copy: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>`,
    
    user: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>`,
    
    building: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="2" width="16" height="20" rx="2" ry="2"></rect><path d="M9 22v-4h6v4M8 6h.01M16 6h.01M12 6h.01M12 10h.01M12 14h.01M16 10h.01M16 14h.01M8 10h.01M8 14h.01"></path></svg>`,
    
    mapPin: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path><circle cx="12" cy="10" r="3"></circle></svg>`,
    
    phone: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"></path></svg>`,
    
    mail: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="4" width="20" height="16" rx="2"></rect><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"></path></svg>`,
    
    alert: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>`,
    
    clock: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>`,
    
    loading: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="animate-spin"><line x1="12" y1="2" x2="12" y2="6"></line><line x1="12" y1="18" x2="12" y2="22"></line><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"></line><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"></line><line x1="2" y1="12" x2="6" y2="12"></line><line x1="18" y1="12" x2="22" y2="12"></line><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"></line><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"></line></svg>`,
    
    file: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>`,
    
    download: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>`,
};

// Inicializar automaticamente quando DOM estiver pronto
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        new MicroInteractions();
    });
} else {
    new MicroInteractions();
}

// Exportar para uso global
window.MicroInteractions = MicroInteractions;
window.SVGIcons = SVGIcons;
