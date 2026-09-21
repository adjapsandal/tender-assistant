import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

from common.config import config
from web.dependencies import shutdown_db, startup_db
from web.routers import auth, company, documents, references, search, tenders, won_tenders

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Падаем на старте, а не на первом логине: приложение без SECRET_KEY
# выдаёт токены, которые может подписать кто угодно.
_config_errors = config.validate_web()
if _config_errors:
    raise RuntimeError("Invalid configuration: " + "; ".join(_config_errors))


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Tender Assistant API...")
    await startup_db()
    logger.info("Database connected")
    yield
    logger.info("Shutting down...")
    await shutdown_db()


app = FastAPI(title="Tender Assistant API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(company.router, prefix="/api", tags=["company"])
app.include_router(search.router, prefix="/api", tags=["search"])
app.include_router(tenders.router, prefix="/api", tags=["tenders"])
app.include_router(documents.router, prefix="/api", tags=["documents"])
app.include_router(won_tenders.router, prefix="/api", tags=["won-tenders"])
app.include_router(references.router, prefix="/api", tags=["references"])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("web_main:app", host="0.0.0.0", port=8000, reload=True)
