from fastapi import APIRouter

from app.api.v1 import (
    api_keys,
    auth,
    otp,
    wallet,
    webhooks,
    applications,
    logs,
    team,
    billing,
    notifications,
    integrations,
    monitoring,
)

api_v1_router = APIRouter(prefix="/v1")

api_v1_router.include_router(auth.router)
api_v1_router.include_router(api_keys.router)
api_v1_router.include_router(otp.router)
api_v1_router.include_router(webhooks.router)
api_v1_router.include_router(wallet.router)
api_v1_router.include_router(applications.router)
api_v1_router.include_router(logs.router)
api_v1_router.include_router(team.router)
api_v1_router.include_router(billing.router)
api_v1_router.include_router(notifications.router)
api_v1_router.include_router(integrations.router)
api_v1_router.include_router(monitoring.router)

