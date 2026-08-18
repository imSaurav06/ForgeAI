"""
MongoDB Data Access Repository for Evaluation Records stored in collection 'evaluations'.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from shared.database.mongodb import get_mongodb_database
from shared.logging.logger import logger

if TYPE_CHECKING:
    from services.evaluation.app.history.history_store import EvaluationRecord


class MongoEvaluationRepository:
    """Data Access Repository for Evaluation execution records stored in MongoDB collection 'evaluations'."""

    def __init__(self, db: AsyncIOMotorDatabase | None = None) -> None:
        self._custom_db = db

    @property
    def db(self) -> AsyncIOMotorDatabase:
        if self._custom_db is not None:
            return self._custom_db
        return get_mongodb_database()

    @property
    def collection(self):
        return self.db["evaluations"]

    async def save_record(self, record: EvaluationRecord) -> EvaluationRecord:
        """Upsert evaluation record."""
        data = record.model_dump()
        await self.collection.update_one(
            {"evaluation_id": record.evaluation_id},
            {"$set": data},
            upsert=True,
        )
        logger.debug(f"Saved evaluation record '{record.evaluation_id}' to MongoDB")
        return record

    async def get_record(self, evaluation_id: str) -> EvaluationRecord | None:
        """Retrieve evaluation record by ID."""
        from services.evaluation.app.history.history_store import EvaluationRecord

        doc = await self.collection.find_one({"evaluation_id": evaluation_id})
        if not doc:
            return None
        doc.pop("_id", None)
        return EvaluationRecord(**doc)

    async def list_history(self) -> list[EvaluationRecord]:
        """List all historical evaluation records."""
        from services.evaluation.app.history.history_store import EvaluationRecord

        cursor = self.collection.find().sort("timestamp", -1)
        records: list[EvaluationRecord] = []
        async for doc in cursor:
            doc.pop("_id", None)
            records.append(EvaluationRecord(**doc))
        return records

    async def get_model_comparisons(self) -> dict[str, dict[str, Any]]:
        """Compute performance comparisons grouped by model name from MongoDB."""
        records = await self.list_history()
        grouped: dict[str, list[EvaluationRecord]] = {}
        for rec in records:
            model = rec.model
            if model not in grouped:
                grouped[model] = []
            grouped[model].append(rec)

        comparisons: dict[str, dict[str, Any]] = {}
        for model, recs in grouped.items():
            avg_score = sum(r.scores.overall_score for r in recs) / len(recs)
            avg_latency = sum(r.scores.avg_latency_sec for r in recs) / len(recs)
            avg_tokens = sum(r.scores.avg_token_usage for r in recs) / len(recs)

            comparisons[model] = {
                "model_name": model,
                "evaluations_count": len(recs),
                "avg_overall_score": round(avg_score, 2),
                "avg_latency_sec": round(avg_latency, 3),
                "avg_token_usage": int(avg_tokens),
            }

        return comparisons
