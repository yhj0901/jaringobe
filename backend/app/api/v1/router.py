"""API v1 라우터 집결점 — 도메인 라우터를 /api/v1 프리픽스로 통합."""

from fastapi import APIRouter

from app.domains.auth.router import router as auth_router
from app.domains.budget.router import router as budget_router
from app.domains.fridge.router import router as fridge_router
from app.domains.household.router import router as household_router
from app.domains.mealplan.router import router as mealplan_router
from app.domains.notification.router import router as notification_router
from app.domains.store.connection_router import router as store_connection_router
from app.domains.store.router import router as store_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router, tags=["auth"])
api_router.include_router(budget_router, tags=["budget"])
api_router.include_router(household_router, tags=["household"])
api_router.include_router(mealplan_router, tags=["mealplan"])
api_router.include_router(notification_router, tags=["notification"])
api_router.include_router(store_router, tags=["store"])
api_router.include_router(store_connection_router, tags=["store"])
api_router.include_router(fridge_router, tags=["fridge"])
