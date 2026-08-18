"""
MongoDB Data Access Repositories for Agent Execution Runs and Steps.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from shared.database.mongodb import get_mongodb_database
from shared.logging.logger import logger

if TYPE_CHECKING:
    from services.agent.app.core.sessions.session_store import AgentExecutionRun


class MongoAgentRunRepository:
    """Data Access Repository for Agent Execution Runs stored in MongoDB collection 'agent_runs'."""

    def __init__(self, db: AsyncIOMotorDatabase | None = None) -> None:
        self._custom_db = db

    @property
    def db(self) -> AsyncIOMotorDatabase:
        if self._custom_db is not None:
            return self._custom_db
        return get_mongodb_database()

    @property
    def collection(self):
        return self.db["agent_runs"]

    async def save_run(self, run: AgentExecutionRun) -> AgentExecutionRun:
        """Upsert agent execution run."""
        data = run.model_dump()
        await self.collection.update_one(
            {"run_id": run.run_id},
            {"$set": data},
            upsert=True,
        )
        logger.debug(f"Saved agent run '{run.run_id}' to MongoDB collection 'agent_runs'")
        return run

    async def get_run(self, run_id: str) -> AgentExecutionRun | None:
        """Retrieve agent run by ID."""
        from services.agent.app.core.sessions.session_store import AgentExecutionRun

        doc = await self.collection.find_one({"run_id": run_id})
        if not doc:
            return None
        doc.pop("_id", None)
        return AgentExecutionRun(**doc)

    async def list_runs(
        self,
        project_id: str | None = None,
        repository_id: str | None = None,
        limit: int = 50,
    ) -> list[AgentExecutionRun]:
        """List agent runs with optional filtering."""
        from services.agent.app.core.sessions.session_store import AgentExecutionRun

        filter_dict: dict[str, Any] = {}
        if project_id:
            filter_dict["project_id"] = project_id
        if repository_id:
            filter_dict["repository_id"] = repository_id

        cursor = self.collection.find(filter_dict).sort("created_at", -1).limit(limit)
        runs: list[AgentExecutionRun] = []
        async for doc in cursor:
            doc.pop("_id", None)
            runs.append(AgentExecutionRun(**doc))
        return runs

    async def delete_run(self, run_id: str) -> bool:
        """Delete agent run by ID."""
        res = await self.collection.delete_one({"run_id": run_id})
        return res.deleted_count > 0


class MongoAgentStepRepository:
    """Data Access Repository for Agent Execution Steps stored in MongoDB collection 'agent_steps'."""

    def __init__(self, db: AsyncIOMotorDatabase | None = None) -> None:
        self._custom_db = db

    @property
    def db(self) -> AsyncIOMotorDatabase:
        if self._custom_db is not None:
            return self._custom_db
        return get_mongodb_database()

    @property
    def collection(self):
        return self.db["agent_steps"]

    async def save_step(self, run_id: str, step_data: dict[str, Any]) -> dict[str, Any]:
        """Save an execution step for an agent run."""
        doc = dict(step_data)
        doc["run_id"] = run_id
        step_id = doc.get("step_id") or f"{run_id}_{len(doc)}"
        doc["step_id"] = step_id

        await self.collection.update_one(
            {"run_id": run_id, "step_id": step_id},
            {"$set": doc},
            upsert=True,
        )
        return doc

    async def get_steps(self, run_id: str) -> list[dict[str, Any]]:
        """Retrieve execution steps for an agent run."""
        cursor = self.collection.find({"run_id": run_id}).sort("created_at", 1)
        steps: list[dict[str, Any]] = []
        async for doc in cursor:
            doc.pop("_id", None)
            steps.append(doc)
        return steps
