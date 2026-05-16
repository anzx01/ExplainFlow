from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import settings
from src.core.logging import setup_logging
from src.explain.router import router as explain_router
from src.imagegen.router import router as imagegen_router
from src.narration.router import router as narration_router
from src.planner.router import router as planner_router
from src.render.router import router as render_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(settings.log_level)
    yield


app = FastAPI(
    title="ExplainFlow API",
    description="AI-powered whiteboard animation video generator for AI/ML concepts",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(explain_router)
app.include_router(imagegen_router)
app.include_router(planner_router)
app.include_router(narration_router)
app.include_router(render_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}
