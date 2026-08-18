# ForgeAI — Master API Reference & Swagger Matrix

## Overview
ForgeAI provides a unified, production-grade REST and WebSocket API. The **API Gateway** (`forge_gateway`, port `8000`) serves as the single public reverse proxy, enforcing JWT authentication, rate limiting, request validation, distributed tracing, and metrics aggregation across all 8 microservices.

---

## 1. Swagger & OpenAPI Documentation (8/8 Microservices)

Every microservice exposes full interactive OpenAPI specifications:

| Service | Port | Base URL | Swagger UI | ReDoc | OpenAPI JSON |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **API Gateway** | 8000 | `http://localhost:8000` | `/docs` | `/redoc` | `/openapi.json` |
| **Agent Orchestrator** | 8001 | `http://localhost:8001` | `/docs` | `/redoc` | `/openapi.json` |
| **LLM Inference** | 8002 | `http://localhost:8002` | `/docs` | `/redoc` | `/openapi.json` |
| **Repository Intelligence** | 8003 | `http://localhost:8003` | `/docs` | `/redoc` | `/openapi.json` |
| **Code RAG & Retrieval** | 8004 | `http://localhost:8004` | `/docs` | `/redoc` | `/openapi.json` |
| **Tool Execution & Terminal** | 8005 | `http://localhost:8005` | `/docs` | `/redoc` | `/openapi.json` |
| **Git Version Control** | 8006 | `http://localhost:8006` | `/docs` | `/redoc` | `/openapi.json` |
| **Evaluation & Benchmark** | 8007 | `http://localhost:8007` | `/docs` | `/redoc` | `/openapi.json` |

---

## 2. Public API Matrix (Gateway Prefix: `/api/v1`)

### Authentication & Tokens
- `POST /api/v1/auth/login`: Exchange user credentials for signed Bearer JWT token.
- `GET /api/v1/auth/me`: Get current authenticated user profile and roles.

### Projects & Workspaces
- `POST /api/v1/projects`: Create project and register repository directory.
- `GET /api/v1/projects`: List registered projects.
- `GET /api/v1/projects/{id}`: Get project details.
- `DELETE /api/v1/projects/{id}`: Delete project registration and purge vector indexes.

### Repositories & Intelligence
- `POST /api/v1/repositories/open`: Open and inspect a local repository folder.
- `POST /api/v1/repositories/{id}/index`: Trigger AST symbol indexing.
- `GET /api/v1/repositories/{id}/tree`: Get directory tree hierarchy.
- `GET /api/v1/repositories/{id}/status`: Get scan, file count, and language stats.
- `GET /api/v1/repositories/{id}/symbols`: Query parsed AST classes and functions.
- `GET /api/v1/repositories/{id}/dependencies`: Get static dependency graph.

### Chat & Multi-turn Conversations
- `POST /api/v1/conversations`: Create conversation session.
- `GET /api/v1/conversations`: List user conversation threads.
- `GET /api/v1/conversations/{id}`: Get full message history.
- `POST /api/v1/conversations/{id}/messages`: Post user/assistant message to thread.

### Autonomous Agent Runs
- `POST /api/v1/agent/runs`: Initiate autonomous workflow run (ASK, PLAN, CODE, DEBUG, TEST, REVIEW, EXPLAIN).
- `GET /api/v1/agent/runs/{id}`: Get run status, state machine state, and steps.
- `POST /api/v1/agent/runs/{id}/continue`: Provide plan approval or feedback.
- `POST /api/v1/agent/runs/{id}/cancel`: Abort active run.
- `GET /api/v1/agent/runs/{id}/stream`: SSE event stream for live execution logs.

### Search & RAG
- `POST /api/v1/search/code`: Regex and keyword search across repository.
- `POST /api/v1/search/symbol`: AST identifier symbol lookup.
- `POST /api/v1/search/semantic`: Dense vector RAG search in Qdrant.

### Git Version Control
- `GET /api/v1/git/status`: Get branch, uncommitted diffs, and staged changes.
- `GET /api/v1/git/diff`: Get unified diff string.
- `GET /api/v1/git/log`: Get commit history.
- `POST /api/v1/git/branches`: Create and switch branch.
- `POST /api/v1/git/commit`: Stage changes and commit with message.
- `POST /api/v1/git/restore`: Discard or restore uncommitted files.

### Interactive WebSockets
- `WS /api/v1/ws/agent/{run_id}`: Bidirectional agent interaction.
- `WS /api/v1/ws/terminal/{session_id}`: Real-time PTY terminal stream.
