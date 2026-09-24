from fastapi import APIRouter
from app.api.v1.endpoints import usuarios, conversas, gerenciacao

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(usuarios.router)
api_router.include_router(conversas.router)
api_router.include_router(gerenciacao.router)
