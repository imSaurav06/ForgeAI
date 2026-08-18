from services.retrieval.app.api.routers.retrieval import router as retrieval_router
from services.retrieval.app.embeddings.vector_encoder import get_code_vector_encoder
from services.retrieval.app.qdrant.qdrant_client import get_qdrant_client
from shared.config.settings import get_settings
from shared.utils.app_factory import create_app

settings = get_settings()


def health_details_provider() -> dict:
    qdrant = get_qdrant_client()
    encoder = get_code_vector_encoder()
    return {
        "qdrant": qdrant.check_health(),
        "embedding_model": encoder.check_health(),
    }


app = create_app(
    service_name="retrieval-service",
    service_version="0.1.0",
    description="Code RAG & Retrieval Service providing dense vector embeddings, Qdrant vector search, hybrid RRF reranking, and context building with token budgeting.",
    routers=[retrieval_router],
    health_details_provider=health_details_provider,
    enforce_internal_auth=True,
)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "services.retrieval.app.main:app",
        host=settings.retrieval_service_host,
        port=settings.retrieval_service_port,
        reload=True,
    )
