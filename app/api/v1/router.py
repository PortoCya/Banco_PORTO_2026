from fastapi import APIRouter

from app.api.v1.endpoints import auditoria, auth, ia, pesquisas, publico, usuarios

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router)
api_router.include_router(usuarios.router)
api_router.include_router(pesquisas.router)
api_router.include_router(publico.router)
api_router.include_router(ia.router)
api_router.include_router(auditoria.router)
