/**
 * LOADING NARRATIVE
 * Loading states com narrativa e progresso visual
 * Integrado com SSE streaming
 * Inspirado em: Charles Bruyerre, Adham Dannaway
 */

class LoadingNarrative {
    constructor(container) {
        this.container = typeof container === 'string' 
            ? document.querySelector(container) 
            : container;
        
        if (!this.container) {
            console.error('Container não encontrado para LoadingNarrative');
            return;
        }

        this.etapas = [];
        this.currentProgress = 0;
        this.ui = null;
    }

    /**
     * Iniciar loading com etapas definidas
     */
    start(etapas = []) {
        this.etapas = etapas.length > 0 ? etapas : [
            { id: 'telegram', nome: 'Telegram', tempo: 200 },
            { id: 'enrichment', nome: 'Enriquecimento', tempo: 800 },
            { id: 'analysis', nome: 'Análise', tempo: 500 },
        ];

        this.render();
    }

    /**
     * Renderizar UI de loading
     */
    render() {
        this.ui = document.createElement('div');
        this.ui.className = 'loading-narrative animate-materialize';
        this.ui.innerHTML = `
            <div class="loading-narrative-header">
                <div class="loading-icon">
                    ${SVGIcons.loading}
                </div>
                <h3 class="loading-title">Consultando em ${this.getTotalBases()} bases</h3>
            </div>
            
            <div class="loading-progress">
                <div class="loading-progress-bar">
                    <div class="loading-progress-fill" style="width: 0%"></div>
                </div>
                <span class="loading-progress-text">0%</span>
            </div>
            
            <div class="loading-steps">
                ${this.etapas.map(etapa => this.renderStep(etapa)).join('')}
            </div>
        `;

        this.container.innerHTML = '';
        this.container.appendChild(this.ui);
        
        this.addStyles();
    }

    /**
     * Renderizar uma etapa individual
     */
    renderStep(etapa) {
        return `
            <div class="loading-step" data-step-id="${etapa.id}">
                <div class="loading-step-icon">
                    <div class="loading-step-spinner"></div>
                </div>
                <div class="loading-step-content">
                    <span class="loading-step-name">${etapa.nome}</span>
                    <span class="loading-step-status">aguardando...</span>
                </div>
                <div class="loading-step-time"></div>
            </div>
        `;
    }

    /**
     * Atualizar status de uma etapa
     */
    updateStep(stepId, status, time = null) {
        const stepEl = this.ui?.querySelector(`[data-step-id="${stepId}"]`);
        if (!stepEl) return;

        const iconEl = stepEl.querySelector('.loading-step-icon');
        const statusEl = stepEl.querySelector('.loading-step-status');
        const timeEl = stepEl.querySelector('.loading-step-time');

        // Remover classes anteriores
        stepEl.classList.remove('loading', 'success', 'error');

        switch (status) {
            case 'loading':
                stepEl.classList.add('loading');
                iconEl.innerHTML = `<div class="loading-step-spinner"></div>`;
                statusEl.textContent = 'processando...';
                statusEl.style.color = 'var(--color-primary)';
                break;

            case 'success':
                stepEl.classList.add('success');
                iconEl.innerHTML = SVGIcons.check;
                iconEl.style.color = 'var(--color-success)';
                statusEl.textContent = 'concluído';
                statusEl.style.color = 'var(--color-success)';
                if (time) {
                    timeEl.textContent = `${time}ms`;
                    timeEl.style.color = 'var(--color-text-tertiary)';
                }
                this.incrementProgress();
                break;

            case 'error':
                stepEl.classList.add('error');
                iconEl.innerHTML = SVGIcons.alert;
                iconEl.style.color = 'var(--color-danger)';
                statusEl.textContent = 'falhou';
                statusEl.style.color = 'var(--color-danger)';
                break;
        }
    }

    /**
     * Atualizar progresso geral
     */
    incrementProgress() {
        this.currentProgress++;
        const percent = Math.round((this.currentProgress / this.etapas.length) * 100);
        
        const fillEl = this.ui?.querySelector('.loading-progress-fill');
        const textEl = this.ui?.querySelector('.loading-progress-text');
        
        if (fillEl) {
            fillEl.style.width = `${percent}%`;
        }
        
        if (textEl) {
            textEl.textContent = `${percent}%`;
        }
    }

    /**
     * Finalizar loading
     */
    finish(message = 'Consulta concluída!', success = true) {
        setTimeout(() => {
            if (!this.ui) return;

            const headerEl = this.ui.querySelector('.loading-narrative-header');
            if (headerEl) {
                headerEl.innerHTML = `
                    <div class="loading-icon" style="color: ${success ? 'var(--color-success)' : 'var(--color-danger)'}">
                        ${success ? SVGIcons.check : SVGIcons.alert}
                    </div>
                    <h3 class="loading-title">${message}</h3>
                `;
            }

            // Fade out após 1.5s
            setTimeout(() => {
                if (this.ui) {
                    this.ui.style.animation = 'fade-out 0.3s ease-out forwards';
                    setTimeout(() => {
                        this.ui?.remove();
                    }, 300);
                }
            }, 1500);
        }, 500);
    }

    /**
     * Obter total de bases (fictício para demo)
     */
    getTotalBases() {
        return Math.floor(Math.random() * 20) + 30; // 30-50
    }

    /**
     * Adicionar estilos inline
     */
    addStyles() {
        if (document.querySelector('#loading-narrative-styles')) return;

        const styles = document.createElement('style');
        styles.id = 'loading-narrative-styles';
        styles.textContent = `
            .loading-narrative {
                background: rgba(15, 23, 42, 0.8);
                backdrop-filter: blur(20px);
                border: 1px solid var(--color-border);
                border-radius: var(--radius-xl);
                padding: var(--space-6);
                box-shadow: var(--shadow-xl);
            }

            .loading-narrative-header {
                display: flex;
                align-items: center;
                gap: var(--space-4);
                margin-bottom: var(--space-5);
            }

            .loading-icon {
                display: flex;
                align-items: center;
                color: var(--color-primary);
            }

            .loading-title {
                font-size: var(--text-xl);
                font-weight: var(--font-semibold);
                color: var(--color-text-primary);
            }

            .loading-progress {
                margin-bottom: var(--space-6);
            }

            .loading-progress-bar {
                position: relative;
                width: 100%;
                height: 8px;
                background: var(--color-bg-elevated);
                border-radius: var(--radius-full);
                overflow: hidden;
                margin-bottom: var(--space-2);
            }

            .loading-progress-fill {
                height: 100%;
                background: linear-gradient(90deg, var(--color-primary), var(--color-success));
                border-radius: var(--radius-full);
                transition: width 0.4s cubic-bezier(0.4, 0, 0.2, 1);
            }

            .loading-progress-text {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--color-text-secondary);
            }

            .loading-steps {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }

            .loading-step {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-3);
                background: rgba(30, 41, 59, 0.5);
                border-radius: var(--radius-md);
                transition: all 0.3s ease;
            }

            .loading-step.loading {
                background: rgba(6, 182, 212, 0.1);
                border-left: 3px solid var(--color-primary);
            }

            .loading-step.success {
                background: rgba(16, 185, 129, 0.1);
                border-left: 3px solid var(--color-success);
            }

            .loading-step.error {
                background: rgba(239, 68, 68, 0.1);
                border-left: 3px solid var(--color-danger);
            }

            .loading-step-icon {
                flex-shrink: 0;
                width: 20px;
                height: 20px;
                display: flex;
                align-items: center;
                justify-content: center;
                color: var(--color-text-tertiary);
            }

            .loading-step-spinner {
                width: 16px;
                height: 16px;
                border: 2px solid var(--color-border);
                border-top-color: var(--color-primary);
                border-radius: 50%;
                animation: spin 0.8s linear infinite;
            }

            .loading-step-content {
                flex: 1;
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
            }

            .loading-step-name {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--color-text-primary);
            }

            .loading-step-status {
                font-size: var(--text-xs);
                color: var(--color-text-tertiary);
            }

            .loading-step-time {
                font-size: var(--text-xs);
                font-family: var(--font-mono);
                color: var(--color-text-tertiary);
            }

            @keyframes fade-out {
                to {
                    opacity: 0;
                    transform: translateY(-10px);
                }
            }
        `;
        document.head.appendChild(styles);
    }
}

// Exportar
window.LoadingNarrative = LoadingNarrative;
