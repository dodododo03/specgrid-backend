from fastapi import APIRouter

from app.api.v1.endpoints import auth, chat, client_config, favorites, health, product_images, products, rankings, trades, users

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(client_config.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(products.router)
api_router.include_router(product_images.router)
api_router.include_router(chat.router)
api_router.include_router(trades.router)
api_router.include_router(rankings.router)
api_router.include_router(favorites.router)
