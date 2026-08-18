"""
MongoDB Data Access Layer for Repositories and Projects.
"""

from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from services.repository.app.schemas.repository import RepositoryMetadata
from shared.database.mongodb import get_mongodb_database
from shared.logging.logger import logger


class MongoRepositoryMetadataRepository:
    """Data Access Repository for Repository Metadata stored in MongoDB collection 'repositories'."""

    def __init__(self, db: AsyncIOMotorDatabase | None = None) -> None:
        self._custom_db = db

    @property
    def db(self) -> AsyncIOMotorDatabase:
        if self._custom_db is not None:
            return self._custom_db
        return get_mongodb_database()

    @property
    def collection(self):
        return self.db["repositories"]

    async def save_repository(self, meta: RepositoryMetadata) -> RepositoryMetadata:
        """Upsert repository metadata record."""
        data = meta.model_dump()
        await self.collection.update_one(
            {"id": meta.id},
            {"$set": data},
            upsert=True,
        )
        logger.debug(f"Saved repository metadata '{meta.id}' to MongoDB")
        return meta

    async def get_repository(self, repo_id: str) -> RepositoryMetadata | None:
        """Retrieve repository metadata by ID."""
        doc = await self.collection.find_one({"id": repo_id})
        if not doc:
            return None
        doc.pop("_id", None)
        return RepositoryMetadata(**doc)

    async def list_repositories(self, user_id: str | None = None) -> list[RepositoryMetadata]:
        """List all registered repository metadata records."""
        query = {"user_id": user_id} if user_id else {}
        cursor = self.collection.find(query)
        repos: list[RepositoryMetadata] = []
        async for doc in cursor:
            doc.pop("_id", None)
            repos.append(RepositoryMetadata(**doc))
        return repos

    async def delete_repository(self, repo_id: str) -> bool:
        """Delete repository metadata record by ID."""
        res = await self.collection.delete_one({"id": repo_id})
        return res.deleted_count > 0


class MongoProjectRepository:
    """Data Access Repository for Project records stored in MongoDB collection 'projects'."""

    def __init__(self, db: AsyncIOMotorDatabase | None = None) -> None:
        self._custom_db = db

    @property
    def db(self) -> AsyncIOMotorDatabase:
        if self._custom_db is not None:
            return self._custom_db
        return get_mongodb_database()

    @property
    def collection(self):
        return self.db["projects"]

    async def save_project(self, project: dict[str, Any]) -> dict[str, Any]:
        """Upsert project record."""
        project_id = project.get("id")
        if not project_id:
            raise ValueError("Project record must contain 'id'")
        await self.collection.update_one(
            {"id": project_id},
            {"$set": project},
            upsert=True,
        )
        return project

    async def get_project(self, project_id: str) -> dict[str, Any] | None:
        """Retrieve project by ID."""
        doc = await self.collection.find_one({"id": project_id})
        if doc:
            doc.pop("_id", None)
        return doc

    async def list_projects(self) -> list[dict[str, Any]]:
        """List all project records."""
        cursor = self.collection.find()
        projects: list[dict[str, Any]] = []
        async for doc in cursor:
            doc.pop("_id", None)
            projects.append(doc)
        return projects

    async def delete_project(self, project_id: str) -> bool:
        """Delete project record by ID."""
        res = await self.collection.delete_one({"id": project_id})
        return res.deleted_count > 0
