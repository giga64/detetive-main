/**
 * CURSOR INTERATIVO
 * Cursor customizado que responde a elementos interativos
 * Inspirado em: Bruno Simon
 * Apenas para desktop (min-width: 1024px)
 */

class InteractiveCursor {
    constructor() {
        // DESABILITADO - cursor customizado removido temporariamente
        // Uncomment código abaixo para reativar
        console.log('⚠️ Cursor customizado desabilitado');
        return;
        
        // Código original comentado abaixo:
        /*
        this.cursorDot = null;
        this.cursorRing = null;
        this.mouseX = 0;
        this.mouseY = 0;
        this.currentX = 0;
        this.currentY = 0;
        this.ringX = 0;
        this.ringY = 0;
        
        // Desabilitar em mobile/tablet
        if (window.innerWidth < 1024) {
            return;
        }
        
        this.init();
    }

    init() {
        // Criar elementos do cursor
        this.createCursorElements();
        
        // Event listeners
        this.addEventListeners();
        
        // Iniciar animação
        this.animate();
        
        // Adicionar classe ao body
        document.body.classList.add('custom-cursor');
    }

    createCursorElements() {
        // Cursor dot (ponto pequeno)
        this.cursorDot = document.createElement('div');
        this.cursorDot.className = 'cursor-dot';
        document.body.appendChild(this.cursorDot);

        // Cursor ring (círculo maior)
        this.cursorRing = document.createElement('div');
        this.cursorRing.className = 'cursor-ring';
        document.body.appendChild(this.cursorRing);
    }

    addEventListeners() {
        // Seguir mouse
        document.addEventListener('mousemove', (e) => {
            this.mouseX = e.clientX;
            this.mouseY = e.clientY;
        });

        // Hover em elementos interativos
        const interactiveElements = 'a, button, .btn, .copyable, input, [role="button"]';
        
        document.addEventListener('mouseover', (e) => {
            if (e.target.matches(interactiveElements)) {
                this.cursorRing.style.width = '48px';
                this.cursorRing.style.height = '48px';
                this.cursorRing.style.borderColor = 'var(--color-success)';
                this.cursorDot.style.transform = 'scale(1.5)';
            }
        });

        document.addEventListener('mouseout', (e) => {
            if (e.target.matches(interactiveElements)) {
                this.cursorRing.style.width = '32px';
                this.cursorRing.style.height = '32px';
                this.cursorRing.style.borderColor = 'var(--color-primary)';
                this.cursorDot.style.transform = 'scale(1)';
            }
        });

        // Click feedback
        document.addEventListener('mousedown', () => {
            this.cursorRing.style.transform = 'scale(0.8)';
            this.cursorDot.style.transform = 'scale(1.2)';
        });

        document.addEventListener('mouseup', () => {
            this.cursorRing.style.transform = 'scale(1)';
            this.cursorDot.style.transform = 'scale(1)';
        });

        // Esconder quando sair da janela
        document.addEventListener('mouseleave', () => {
            this.cursorDot.style.opacity = '0';
            this.cursorRing.style.opacity = '0';
        });

        document.addEventListener('mouseenter', () => {
            this.cursorDot.style.opacity = '1';
            this.cursorRing.style.opacity = '1';
        });
    }

    animate() {
        // Smooth following com easing
        const ease = 0.15;
        const ringEase = 0.08;

        // Dot segue o mouse mais rápido
        this.currentX += (this.mouseX - this.currentX) * ease;
        this.currentY += (this.mouseY - this.currentY) * ease;

        // Ring segue com delay (efeito lag suave)
        this.ringX += (this.mouseX - this.ringX) * ringEase;
        this.ringY += (this.mouseY - this.ringY) * ringEase;

        // Aplicar posições
        if (this.cursorDot) {
            this.cursorDot.style.left = `${this.currentX}px`;
            this.cursorDot.style.top = `${this.currentY}px`;
        }

        if (this.cursorRing) {
            this.cursorRing.style.left = `${this.ringX}px`;
            this.cursorRing.style.top = `${this.ringY}px`;
        }

        // Loop
        requestAnimationFrame(() => this.animate());
    }
}

// Inicializar quando DOM estiver pronto
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        new InteractiveCursor();
    });
} else {
    new InteractiveCursor();
}

// Exportar
window.InteractiveCursor = InteractiveCursor;
