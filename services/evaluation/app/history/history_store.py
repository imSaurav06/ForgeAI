import time
from typing import Any

from pydantic import BaseModel, Field

from services.evaluation.app.metrics.collector import PlatformMetricsSnapshot
from services.evaluation.app.scoring.score_calculator import PlatformEvaluationScore
from services.evaluation.app.storage.mongo_eval_store import MongoEvaluationRepository
from shared.exceptions.handlers import NotFoundException
from shared.logging.logger import logger


class EvaluationRecord(BaseModel):
    """Model holding persistent evaluation execution record."""

    evaluation_id: str = Field(..., description="Unique evaluation ID")
    run_id: str = Field(..., description="Target agent run ID")
    model: str = Field(..., description="LLM model name")
    repository: str = Field(..., description="Target repository ID")
    timestamp: float = Field(default_factory=time.time, description="Evaluation timestamp")
    scores: PlatformEvaluationScore = Field(..., description="Scores breakdown")
    metrics: PlatformMetricsSnapshot = Field(..., description="Raw metrics snapshot")
    report_markdown: str = Field(..., description="Markdown report text")


class EvaluationHistoryStore:
    """Evaluation History Store backed by MongoDB collection 'evaluations' and local in-memory cache."""

    def __init__(self) -> None:
        self._records: dict[str, EvaluationRecord] = {}
        self.mongo_repo = MongoEvaluationRepository()

    def save_record(self, record: EvaluationRecord) -> EvaluationRecord:
        """Save evaluation record in memory and MongoDB."""
        self._records[record.evaluation_id] = record
        self._persist_record_bg(record)
        return record

    def get_record(self, evaluation_id: str) -> EvaluationRecord:
        """Retrieve record by ID or raise NotFoundException."""
        record = self._records.get(evaluation_id)
        if not record:
            raise NotFoundException(message=f"Evaluation record '{evaluation_id}' not found")
        return record

    async def get_record_async(self, evaluation_id: str) -> EvaluationRecord:
        """Retrieve record by ID from memory or MongoDB."""
        record = self._records.get(evaluation_id)
        if not record:
            record = await self.mongo_repo.get_record(evaluation_id)
            if record:
                self._records[record.evaluation_id] = record
        if not record:
            raise NotFoundException(message=f"Evaluation record '{evaluation_id}' not found")
        return record

    def list_history(self) -> list[EvaluationRecord]:
        """List all historical evaluation records."""
        return list(self._records.values())

    async def list_history_async(self) -> list[EvaluationRecord]:
        """List all historical evaluation records from MongoDB."""
        records = await self.mongo_repo.list_history()
        for r in records:
            self._records[r.evaluation_id] = r
        return records

    def get_model_comparisons(self) -> dict[str, dict[str, Any]]:
        """Compute performance comparisons grouped by model name."""
        grouped: dict[str, list[EvaluationRecord]] = {}
        for rec in self._records.values():
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

    def _persist_record_bg(self, record: EvaluationRecord) -> None:
        """Schedule asynchronous save of EvaluationRecord to MongoDB."""
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self.mongo_repo.save_record(record))
        except Exception as err:
            logger.debug(f"Could not schedule background save to MongoDB: {err}")


_history_store_instance: EvaluationHistoryStore | None = None


def get_evaluation_history_store() -> EvaluationHistoryStore:
    """Accessor for global EvaluationHistoryStore."""
    global _history_store_instance
    if _history_store_instance is None:
        _history_store_instance = EvaluationHistoryStore()
    return _history_store_instance
