"""API v1 라우터 집결점 — 도메인 라우터를 /api/v1 프리픽스로 통합."""

from fastapi import APIRouter

from app.domains.auth.router import router as auth_router
from app.domains.budget.router import router as budget_router
from app.domains.mealplan.router import router as mealplan_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router, tags=["auth"])
api_router.include_router(budget_router, tags=["budget"])
api_router.include_router(mealplan_router, tags=["mealplan"])
