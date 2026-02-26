#!/bin/bash
# Setup script para instalar e configurar as features de performance

set -e

echo "🚀 Configurando Features de Performance..."
echo ""

# Detectar OS
OS="$(uname -s)"

# Função para instalar Redis
install_redis() {
    if command -v redis-server &> /dev/null; then
        echo "✅ Redis já está instalado"
        return 0
    fi
    
    echo "📦 Instalando Redis..."
    
    case "$OS" in
        Linux*)
            if [ -f /etc/os-release ]; then
                . /etc/os-release
                case "$ID" in
                    ubuntu|debian)
                        sudo apt-get update
                        sudo apt-get install -y redis-server
                        ;;
                    centos|fedora|rhel)
                        sudo yum install -y redis
                        ;;
                esac
            fi
            ;;
        Darwin*)
            # macOS
            if ! command -v brew &> /dev/null; then
                echo "❌ Homebrew não instalado. Instale em: https://brew.sh"
                exit 1
            fi
            brew install redis
            ;;
        *)
            echo "❌ OS não suportado. Instale Redis manualmente."
            exit 1
            ;;
    esac
}

# Função para iniciar Redis
start_redis() {
    echo ""
    echo "🔄 Iniciando Redis..."
    
    case "$OS" in
        Linux*)
            sudo systemctl start redis-server
            echo "✅ Redis iniciado (systemctl)"
            ;;
        Darwin*)
            brew services start redis
            echo "✅ Redis iniciado (brew services)"
            ;;
    esac
    
    # Verificar conexão
    sleep 2
    if redis-cli ping | grep -q "PONG"; then
        echo "✅ Redis respondendo corretamente"
    else
        echo "❌ Redis não está respondendo"
        exit 1
    fi
}

# Função para instalar dependências Python
install_python_deps() {
    echo ""
    echo "📦 Instalando dependências Python..."
    pip install -r requirements.txt -q
    echo "✅ Dependências instaladas"
}

# Função para verificar Docker
check_docker() {
    echo ""
    if command -v docker &> /dev/null; then
        echo "✅ Docker detectado"
        
        if command -v docker-compose &> /dev/null; then
            echo "✅ Docker Compose detectado"
            
            read -p "Deseja usar Docker para Redis/Celery? (s/n): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Ss]$ ]]; then
                echo ""
                echo "🐳 Iniciando containers Docker..."
                docker-compose up -d
                echo "✅ Containers iniciados!"
                echo ""
                echo "Verificar status:"
                docker-compose ps
                return 0
            fi
        fi
    fi
    
    return 1
}

# Menu principal
main() {
    echo "╔════════════════════════════════════════════════════════╗"
    echo "║   Setup - Features de Performance                      ║"
    echo "║   1. Circuit Breaker                                   ║"
    echo "║   2. Redis Cache                                       ║"
    echo "║   3. SSE Streaming                                     ║"
    echo "║   4. Celery Job Queue                                  ║"
    echo "╚════════════════════════════════════════════════════════╝"
    echo ""
    
    # Instalar dependências Python
    install_python_deps
    
    # Tentar usar Docker primeiro
    if check_docker; then
        echo "✅ Setup com Docker concluído!"
        echo ""
        echo "Próximos passos:"
        echo "1. Inicie a aplicação: python app.py"
        echo "2. Acesse: http://localhost:8000"
        echo ""
        exit 0
    fi
    
    echo "📦 Configuração Manual (sem Docker)..."
    echo ""
    
    # Instalar Redis manualmente
    install_redis
    start_redis
    
    echo ""
    echo "📝 Configuração da Aplicação..."
    echo ""
    echo "O arquivo .env foi atualizado com:"
    echo "  - REDIS_URL=redis://localhost:6379/0"
    echo "  - CELERY_BROKER_URL=redis://localhost:6379/1"
    echo "  - CELERY_RESULT_BACKEND=redis://localhost:6379/2"
    echo ""
    
    echo "✅ Setup concluído!"
    echo ""
    echo "╔════════════════════════════════════════════════════════╗"
    echo "║  PRÓXIMOS PASSOS                                       ║"
    echo "╚════════════════════════════════════════════════════════╝"
    echo ""
    echo "1️⃣  Terminal 1 - Iniciar Celery Worker:"
    echo "    celery -A job_queue worker --loglevel=info"
    echo ""
    echo "2️⃣  Terminal 2 - Iniciar Celery Beat (tarefas agendadas):"
    echo "    celery -A job_queue beat --loglevel=info"
    echo ""
    echo "3️⃣  Terminal 3 - Iniciar Aplicação FastAPI:"
    echo "    python app.py"
    echo ""
    echo "4️⃣  Acessar:"
    echo "    http://localhost:8000"
    echo ""
    echo "📊 Monitorar:"
    echo "    redis-cli INFO stats"
    echo "    celery -A job_queue inspect active"
    echo ""
}

main
