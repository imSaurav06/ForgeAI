# ForgeAI System Architecture - Shared Infrastructure

## Overview

ForgeAI is structured as a Python 3.12+ monorepo of 8 independent FastAPI microservices, relying on shared infrastructure modules to ensure consistent logging, request context tracing, exception handling, configuration management, and OpenAPI standards.

```
                    ┌──────────────────────────┐
                    │       API GATEWAY        │
                    │         (:8000)          │
                    └────────────┬─────────────┘
                                 │
          ┌──────────────────────┼──────────────────────┐
          │                      │                      │
          ▼                      ▼                      ▼

   Agent Service          Repository Service       LLM Service
      (:8001)                (:8003)                 (:8002)

          │                      │                      │
          ▼                      ▼                      ▼

   Tool Service            Retrieval Service       Ollama Host
      (:8005)                (:8004)                 (:11434)

          │                      │
          ▼                      ▼

     Git Service              Qdrant
      (:8006)                 (:6333)

          │
          ▼

  Evaluation Service
      (:8007)

          │
          ▼

       MongoDB
       (:27017)
```

## Shared Core Components

### 1. Central Configuration (`shared.config`)
- Powered by `pydantic-settings`.
- Reads `.env` and system environment variables.
- Configures default host/ports for all 8 microservices and external databases (MongoDB, Qdrant, Ollama).

### 2. Structured Logging (`shared.logging`)
- Loguru integration with contextual `X-Request-ID` propagation via Python `ContextVar`.
- Enriched log output formatting timestamp, level, service name, file/line context, and request trace.

### 3. Response Schemas (`shared.schemas`)
- Unified Pydantic models: `SuccessResponse[T]`, `ErrorResponse`, `HealthResponse`, `PaginatedResponse[T]`.

### 4. Exceptions & Handlers (`shared.exceptions`)
- Subclasses of `ForgeException` (`NotFoundException`, `ValidationException`, `ServiceUnavailableException`, `UnauthorizedException`).
- Global exception handlers formatting output as standard `ErrorResponse`.

### 5. Application Factory (`shared.utils.app_factory`)
- `create_app()` bootstraps routers, OpenAPI docs (`/docs`, `/redoc`), standard `/health` endpoint, middleware stack (`RequestIDMiddleware`, `RequestLoggingMiddleware`, CORS), and lifespan hooks.
