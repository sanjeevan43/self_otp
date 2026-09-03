from fastapi import APIRouter

from app.api.v1.api_keys import router as api_keys_router
from app.api.v1.auth import router as auth_router
from app.api.v1.otp import router as otp_router
from app.api.v1.wallet import router as wallet_router
from app.api.v1.webhooks import router as webhooks_router

api_v1_router = APIRouter(prefix="/v1")
api_v1_router.include_router(auth_router)
api_v1_router.include_router(api_keys_router)
api_v1_router.include_router(otp_router)
api_v1_router.include_router(wallet_router)
api_v1_router.include_router(webhooks_router)
