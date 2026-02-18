# Re-export da aplicação FastAPI
# Este arquivo é necessário para compatibilidade com containers e deploys
# que procuram por um módulo chamado 'main'

from app import app

__all__ = ["app"]
