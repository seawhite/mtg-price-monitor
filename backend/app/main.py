import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.routers import monitors
from app.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting MTG Price Monitor...")
    init_db()
    start_scheduler()
    yield
    logger.info("Shutting down MTG Price Monitor...")
    stop_scheduler()


app = FastAPI(
    title="MTG Price Monitor",
    description="Monitor Magic: The Gathering card prices across TCGPlayer, eBay, and Manapool",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(monitors.router, prefix="/api")
