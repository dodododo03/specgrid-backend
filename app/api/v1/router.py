from fastapi import APIRouter

from app.api.v1.endpoints import auth, chat, health, product_images, products, trades, users

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(products.router)
api_router.include_router(product_images.router)
api_router.include_router(chat.router)
api_router.include_router(trades.router)
