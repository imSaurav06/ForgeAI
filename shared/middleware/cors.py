from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def setup_cors(
    app: FastAPI,
    allow_origins: list[str] | None = None,
    allow_methods: list[str] | None = None,
    allow_headers: list[str] | None = None,
) -> None:
    """Configure CORS middleware for a FastAPI service."""
    origins = allow_origins or ["*"]
    methods = allow_methods or ["*"]
    headers = allow_headers or ["*"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=methods,
        allow_headers=headers,
    )
