"""FastAPI 应用装配。"""
from __future__ import annotations

import logging

from fastapi import FastAPI

from api.routes import tasks, shops, ops


def create_app() -> FastAPI:
    app = FastAPI(
        title="EcListingAgent API",
        version="0.2.0",
        description="电商商品上下架智能 Agent 接口层",
    )
    app.include_router(tasks.router, prefix="/api", tags=["tasks"])
    app.include_router(shops.router, prefix="/api", tags=["shops"])
    app.include_router(ops.router, prefix="/api", tags=["ops"])

    @app.get("/health", tags=["health"])
    def health():
        return {"ok": True}

    return app


app = create_app()


def run():
    """pyproject entrypoint: ec-agent-api"""
    import uvicorn
    logging.basicConfig(level=logging.INFO)
    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=False)
