"""
MongoDB Infrastructure Layer — managing connection pooling, database access,
index initialization, health checking, and graceful shutdown via Motor.
"""

from __future__ import annotations

import asyncio
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, IndexModel
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

from shared.config.settings import get_settings
from shared.logging.logger import logger

_client_instance: AsyncIOMotorClient | None = None
_client_loop: asyncio.AbstractEventLoop | None = None


def get_mongodb_client(uri: str | None = None) -> AsyncIOMotorClient:
    """Retrieve or create the global AsyncIOMotorClient instance."""
    global _client_instance, _client_loop
    current_loop = None
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        pass

    if (
        _client_instance is None
        or uri is not None
        or (_client_loop is not None and current_loop is not None and _client_loop != current_loop)
        or (current_loop is not None and current_loop.is_closed())
    ):
        settings = get_settings()
        target_uri = uri or settings.mongodb_uri
        logger.info(f"Initializing AsyncIOMotorClient with uri='{target_uri}'")
        _client_instance = AsyncIOMotorClient(
            target_uri,
            serverSelectionTimeoutMS=3000,
            maxPoolSize=50,
            minPoolSize=5,
        )
        _client_loop = current_loop
    return _client_instance


def get_mongodb_database(uri: str | None = None, db_name: str | None = None) -> AsyncIOMotorDatabase:
    """Retrieve or create the global AsyncIOMotorDatabase instance."""
    settings = get_settings()
    target_db_name = db_name or settings.mongodb_database
    client = get_mongodb_client(uri=uri)
    return client[target_db_name]


async def init_mongodb_indexes(db: AsyncIOMotorDatabase | None = None) -> None:
    """Create MongoDB indexes idempotently for all core collections."""
    if db is None:
        db = get_mongodb_database()

    try:
        # Users Collection
        await db["users"].create_indexes([
            IndexModel([("email", ASCENDING)], unique=True, name="idx_users_email"),
        ])

        # Projects Collection
        await db["projects"].create_indexes([
            IndexModel([("id", ASCENDING)], unique=True, name="idx_projects_id"),
            IndexModel([("created_at", ASCENDING)], name="idx_projects_created_at"),
        ])

        # Repositories Collection
        await db["repositories"].create_indexes([
            IndexModel([("id", ASCENDING)], unique=True, name="idx_repositories_id"),
            IndexModel([("name", ASCENDING)], name="idx_repositories_name"),
            IndexModel([("created_at", ASCENDING)], name="idx_repositories_created_at"),
        ])

        # Agent Runs Collection
        await db["agent_runs"].create_indexes([
            IndexModel([("run_id", ASCENDING)], unique=True, name="idx_agent_runs_id"),
            IndexModel([("project_id", ASCENDING)], name="idx_agent_runs_project_id"),
            IndexModel([("repository_id", ASCENDING)], name="idx_agent_runs_repo_id"),
            IndexModel([("state", ASCENDING)], name="idx_agent_runs_state"),
            IndexModel([("created_at", ASCENDING)], name="idx_agent_runs_created_at"),
        ])

        # Agent Steps Collection
        await db["agent_steps"].create_indexes([
            IndexModel([("run_id", ASCENDING)], name="idx_agent_steps_run_id"),
            IndexModel([("step_id", ASCENDING)], name="idx_agent_steps_step_id"),
            IndexModel([("created_at", ASCENDING)], name="idx_agent_steps_created_at"),
        ])

        # Conversations & Messages
        await db["conversations"].create_indexes([
            IndexModel([("conversation_id", ASCENDING)], unique=True, name="idx_conversations_id"),
            IndexModel([("created_at", ASCENDING)], name="idx_conversations_created_at"),
        ])
        await db["messages"].create_indexes([
            IndexModel([("conversation_id", ASCENDING)], name="idx_messages_conv_id"),
            IndexModel([("created_at", ASCENDING)], name="idx_messages_created_at"),
        ])

        # Evaluations Collection
        await db["evaluations"].create_indexes([
            IndexModel([("evaluation_id", ASCENDING)], unique=True, name="idx_evaluations_id"),
            IndexModel([("run_id", ASCENDING)], name="idx_evaluations_run_id"),
            IndexModel([("model", ASCENDING)], name="idx_evaluations_model"),
            IndexModel([("timestamp", ASCENDING)], name="idx_evaluations_timestamp"),
        ])

        logger.info(f"MongoDB indexes successfully created for database '{db.name}'")
    except Exception as err:
        logger.warning(f"Error creating MongoDB indexes: {err}")


async def check_mongodb_health(uri: str | None = None, db_name: str | None = None) -> dict[str, Any]:
    """Check MongoDB server connectivity by executing a ping command."""
    settings = get_settings()
    target_db_name = db_name or settings.mongodb_database
    try:
        db = get_mongodb_database(uri=uri, db_name=target_db_name)
        res = await db.command("ping")
        is_ok = bool(res.get("ok") == 1.0)
        return {
            "status": "healthy" if is_ok else "degraded",
            "mongodb_connected": is_ok,
            "database_name": target_db_name,
        }
    except (ConnectionFailure, ServerSelectionTimeoutError, Exception) as err:
        logger.warning(f"MongoDB health check failed: {err}")
        return {
            "status": "unhealthy",
            "mongodb_connected": False,
            "database_name": target_db_name,
            "error": str(err),
        }


def close_mongodb_connection() -> None:
    """Close active AsyncIOMotorClient connection pool."""
    global _client_instance, _client_loop
    if _client_instance is not None:
        _client_instance.close()
        _client_instance = None
        _client_loop = None
        logger.info("Closed MongoDB client connection pool")
