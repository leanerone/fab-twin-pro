"""路由模块包"""
from .machines import router as machines_router
from .events import router as events_router
from .lots import router as lots_router
from .alarms import router as alarms_router
from .ai import router as ai_router
from .oht import router as oht_router
from .recipes import router as recipes_router

__all__ = [
    "machines_router",
    "events_router",
    "lots_router",
    "alarms_router",
    "ai_router",
    "oht_router",
    "recipes_router",
]
