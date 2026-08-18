# ForgeAI — Security Architecture & Threat Model

## Overview
ForgeAI is engineered with a **Defense-in-Depth** security model. Every layer of the platform—from public API ingress down to operating system process execution and PTY terminal interactions—enforces strict authentication, path traversal containment, command sandboxing, and data sanitization.

---

## 1. Authentication & Identity Boundaries

### A. Public API Layer (JWT Authentication)
- All public gateway routes under `/api/v1/` require an `Authorization: Bearer <token>` header.
- Tokens are signed with HMAC-SHA256 (`HS256`) and validate subject (`sub`), issuer (`iss`), expiration (`exp`), and user role.
- Unauthenticated requests are rejected immediately with `HTTP 401 Unauthorized`.

### B. Internal Service-to-Service Layer (HMAC Signature Verification)
- Internal microservice communication is secured via the `X-Internal-Service-Token` header.
- Token format: `<service_name>:<unix_timestamp>:<hmac_sha256_hex_digest>`
- **Replay Protection**: Timestamps exceeding a 300-second window are rejected with `HTTP 401/403`.
- Direct unauthenticated requests to internal microservice ports (e.g. 8001–8007) are blocked.

---

## 2. Sandbox & Path Traversal Containment (`SecuritySandbox`)

The `SecuritySandbox` in `services/tools/app/sandbox/security_sandbox.py` protects the host system:
1. **Canonical Path Resolution**: All target file paths are resolved to absolute, symlink-dereferenced paths.
2. **Boundary Enforcement**: Target paths are strictly verified to reside within the allowed `repository_root` or `workspace_root`.
3. **Traversal Prevention**: Relative escape vectors (`../`, `..\\`, null bytes, drive switching) raise `UnauthorizedException`.
4. **Forbidden Target Protection**: Critical system paths (`/etc`, `/proc`, `/sys`, `C:\Windows`, `C:\Program Files`, `.git/hooks`) are strictly blocked.

---

## 3. Terminal & Command Execution Isolation

- **Command Whitelisting & Normalization**: Malicious shell injection sequences (`rm -rf /`, `curl | sh`, `:(){ :|:& };:`) are intercepted before execution.
- **PTY Terminal Dimension & Signal Isolation**: Terminal instances are bounded by strict dimensions and allow only safe posix signals (`SIGINT`, `SIGTERM`).
- **Resource Constraints**: Subprocess execution is capped with strict timeouts (default 30 seconds) to prevent infinite loops or fork bombs.

---

## 4. Credential Redaction Protocol

- All logs, error traces, diffs, and benchmark reports enforce a mandatory redaction filter.
- Any pattern resembling GitHub tokens (`ghp_...`), JWT secrets, API keys, or private keys is transformed to `[REDACTED]`.
- No raw credentials are ever persisted to disk or emitted in API responses.
