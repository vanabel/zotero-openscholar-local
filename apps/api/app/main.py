from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import init_db
from app.pipeline_logging import plog_info, setup_logging
from app.routers import chat, chunks, health, papers, review, scan, settings_route, stats


def _log_openscholar_startup() -> None:
    want = settings.openscholar_retriever_enabled or settings.openscholar_reranker_enabled
    if not want:
        return
    from app.services.openscholar_retrieval import (
        _IMPORT_ERROR,
        openscholar_deps_available,
        openscholar_reranker_enabled,
        openscholar_retriever_enabled,
    )

    if openscholar_deps_available():
        plog_info(
            "retrieve",
            "OpenScholar 已启用 retriever=%s reranker=%s device=%s",
            openscholar_retriever_enabled(),
            openscholar_reranker_enabled(),
            settings.openscholar_device,
        )
        return
    plog_info(
        "retrieve",
        "OpenScholar 已在 .env 开启但未安装依赖（%s），检索将回退 FTS+Ollama 嵌入；"
        "请执行: cd apps/api && pip install -e \".[openscholar]\"",
        _IMPORT_ERROR or "unknown",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    init_db()
    _log_openscholar_startup()
    yield


app = FastAPI(
    title="Zotero OpenScholar Local API",
    description=(
        "本地 Zotero PDF 的带引用问答与综述。RAG 与提示范式参考 OpenScholar（"
        "https://arxiv.org/abs/2411.14199 ）；非官方 OpenScholar 托管，亦不内置其论文库或官方权重。"
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(scan.router)
app.include_router(papers.router)
app.include_router(chunks.router)
app.include_router(chat.router)
app.include_router(review.router)
app.include_router(settings_route.router)
app.include_router(stats.router)
