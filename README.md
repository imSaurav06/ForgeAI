# ForgeAI - Local AI Software Engineering Platform

ForgeAI is an enterprise-grade local AI software engineering platform featuring Repository Intelligence, Code RAG, Agent Orchestration, Safe Tool Execution, Automated Testing with Self-Correction, Git Integration, and Evaluation Benchmarking.

## Monorepo Layout

```
forge-ai/
├── services/             # FastAPI Microservices
│   ├── gateway/          # API Gateway (:8000)
│   ├── agent/            # Agent Orchestration Service (:8001)
│   ├── llm/              # Ollama LLM Service (:8002)
│   ├── repository/       # Repository Intelligence Service (:8003)
│   ├── retrieval/        # RAG / Qdrant Retrieval Service (:8004)
│   ├── tools/            # Safe Tool Execution Service (:8005)
│   ├── git/              # Git Operations Service (:8006)
│   └── evaluation/       # Benchmark & Metrics Service (:8007)
├── shared/               # Reusable Core Infrastructure
│   ├── config/           # Pydantic environment configuration
│   ├── logging/          # Loguru structured logging
│   ├── middleware/       # Correlation ID, Logging, CORS
│   ├── exceptions/       # Custom domain exceptions & handlers
│   ├── schemas/          # Standard response and paginated models
│   └── utils/            # App factory & shared helpers
├── infrastructure/       # Docker & Deployment configuration
├── tests/                # Global test suite
└── docs/                 # Platform documentation
```

## Shared Infrastructure Features

- **Environment-Driven Configuration**: Typed `pydantic-settings` with default environment overrides.
- **Structured Logging**: `loguru` with contextual Request-IDs and JSON formatting support.
- **Standardized API Schema**: Every response follows `SuccessResponse[T]`, `ErrorResponse`, `HealthResponse`, or `PaginatedResponse[T]`.
- **Global Exception Tracing**: Standardized handling for Pydantic validation errors, Starlette HTTP exceptions, and domain `ForgeException` subclasses.
- **Reusable FastAPI App Factory**: `create_app()` bootstraps routers, OpenAPI Swagger (`/docs`), `/health` endpoint, middleware, and lifecycle hooks consistently across all 8 microservices.

## Getting Started

1. **Install Dependencies**:
   ```bash
   pip install -e .
   ```

2. **Environment Configuration**:
   ```bash
   cp .env.example .env
   ```

3. **Run Tests**:
   ```bash
   pytest
   ```
# ForgeAI
