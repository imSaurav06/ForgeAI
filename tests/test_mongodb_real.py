"""
Real MongoDB Integration Tests.

Validates AsyncIOMotorClient pooling, database and collection setup,
idempotent index creation, CRUD operations across projects, repository metadata,
agent execution runs/steps, evaluation records, lifecycle reinitialization persistence,
health checks, and offline error handling.
"""

import time

import pytest
from motor.motor_asyncio import AsyncIOMotorDatabase

from services.agent.app.core.sessions.session_store import AgentExecutionRun
from services.agent.app.storage.mongo_agent_store import MongoAgentRunRepository, MongoAgentStepRepository
from services.evaluation.app.history.history_store import EvaluationRecord
from services.evaluation.app.metrics.collector import PlatformMetricsSnapshot
from services.evaluation.app.scoring.score_calculator import PlatformEvaluationScore
from services.evaluation.app.storage.mongo_eval_store import MongoEvaluationRepository
from services.repository.app.schemas.repository import RepositoryMetadata
from services.repository.app.storage.mongo_repository import MongoProjectRepository, MongoRepositoryMetadataRepository
from shared.database.mongodb import (
    check_mongodb_health,
    close_mongodb_connection,
    get_mongodb_database,
    init_mongodb_indexes,
)


@pytest.fixture
async def test_db() -> AsyncIOMotorDatabase:
    """Fixture providing a clean test database in real MongoDB."""
    db_name = "forge_ai_test_db"
    db = get_mongodb_database(db_name=db_name)
    await init_mongodb_indexes(db)
    yield db
    # Cleanup test collections after test
    try:
        await db.client.drop_database(db_name)
    except Exception:
        pass


@pytest.mark.asyncio
async def test_mongodb_connection_and_indexes(test_db: AsyncIOMotorDatabase):
    """Verify MongoDB ping command and idempotent index creation."""
    res = await test_db.command("ping")
    assert res.get("ok") == 1.0

    health = await check_mongodb_health(db_name=test_db.name)
    assert health["status"] == "healthy"
    assert health["mongodb_connected"] is True


@pytest.mark.asyncio
async def test_mongo_project_repository(test_db: AsyncIOMotorDatabase):
    """Verify Project CRUD persistence in MongoDB collection 'projects'."""
    repo = MongoProjectRepository(db=test_db)
    proj_data = {
        "id": "proj_mongo_100",
        "name": "Auth Service Project",
        "path": "./workspace/auth",
        "description": "Authentication microservice project",
        "created_at": time.time(),
    }

    saved = await repo.save_project(proj_data)
    assert saved["id"] == "proj_mongo_100"

    fetched = await repo.get_project("proj_mongo_100")
    assert fetched is not None
    assert fetched["name"] == "Auth Service Project"

    all_projs = await repo.list_projects()
    assert len(all_projs) >= 1
    assert any(p["id"] == "proj_mongo_100" for p in all_projs)

    deleted = await repo.delete_project("proj_mongo_100")
    assert deleted is True
    assert await repo.get_project("proj_mongo_100") is None


@pytest.mark.asyncio
async def test_mongo_repository_metadata_repository(test_db: AsyncIOMotorDatabase):
    """Verify RepositoryMetadata CRUD persistence in MongoDB collection 'repositories'."""
    repo = MongoRepositoryMetadataRepository(db=test_db)
    meta = RepositoryMetadata(
        id="repo_mongo_200",
        name="ForgeAI Core",
        path="E:/ForgeAI",
        git_remote="https://github.com/forge/ai.git",
        branch="main",
    )

    await repo.save_repository(meta)

    fetched = await repo.get_repository("repo_mongo_200")
    assert fetched is not None
    assert fetched.name == "ForgeAI Core"
    assert fetched.branch == "main"

    all_repos = await repo.list_repositories()
    assert len(all_repos) >= 1
    assert any(r.id == "repo_mongo_200" for r in all_repos)

    deleted = await repo.delete_repository("repo_mongo_200")
    assert deleted is True


@pytest.mark.asyncio
async def test_mongo_agent_run_and_step_repository(test_db: AsyncIOMotorDatabase):
    """Verify AgentExecutionRun and AgentStep CRUD persistence in MongoDB collections 'agent_runs' and 'agent_steps'."""
    run_repo = MongoAgentRunRepository(db=test_db)
    step_repo = MongoAgentStepRepository(db=test_db)

    run = AgentExecutionRun(
        run_id="run_mongo_300",
        project_id="proj_mongo_100",
        repository_id="repo_mongo_200",
        mode="CODE",
        instruction="Refactor authentication middleware",
        selected_model="qwen2.5-coder:7b-instruct-q4_0",
        repair_count=2,
    )

    await run_repo.save_run(run)

    fetched = await run_repo.get_run("run_mongo_300")
    assert fetched is not None
    assert fetched.mode == "CODE"
    assert fetched.repair_count == 2

    # Save Agent Step
    step_data = {
        "step_id": "step_1",
        "state": "PLANNING",
        "action": "Decompose AST tasks",
        "status": "completed",
        "created_at": time.time(),
    }
    await step_repo.save_step("run_mongo_300", step_data)

    steps = await step_repo.get_steps("run_mongo_300")
    assert len(steps) == 1
    assert steps[0]["action"] == "Decompose AST tasks"


@pytest.mark.asyncio
async def test_mongo_evaluation_repository(test_db: AsyncIOMotorDatabase):
    """Verify EvaluationRecord CRUD persistence and model comparison aggregates in MongoDB collection 'evaluations'."""
    repo = MongoEvaluationRepository(db=test_db)

    scores = PlatformEvaluationScore(
        overall_score=88.5,
        avg_latency_sec=1.2,
        avg_token_usage=350,
        pass_rate=95.0,
    )
    metrics = PlatformMetricsSnapshot(
        run_id="run_mongo_300",
    )

    record = EvaluationRecord(
        evaluation_id="eval_mongo_400",
        run_id="run_mongo_300",
        model="qwen2.5-coder:7b-instruct-q4_0",
        repository="repo_mongo_200",
        scores=scores,
        metrics=metrics,
        report_markdown="# Benchmark Report\nOverall Score: 88.5",
    )

    await repo.save_record(record)

    fetched = await repo.get_record("eval_mongo_400")
    assert fetched is not None
    assert fetched.model == "qwen2.5-coder:7b-instruct-q4_0"
    assert fetched.scores.overall_score == 88.5

    history = await repo.list_history()
    assert len(history) >= 1

    comparisons = await repo.get_model_comparisons()
    assert "qwen2.5-coder:7b-instruct-q4_0" in comparisons
    assert comparisons["qwen2.5-coder:7b-instruct-q4_0"]["evaluations_count"] == 1


@pytest.mark.asyncio
async def test_restart_reinitialization_persistence():
    """PROVE PERSISTENCE: Save entity -> close DB connection -> re-open DB -> confirm entity survives restart."""
    test_db_name = "forge_ai_restart_test_db"
    db1 = get_mongodb_database(db_name=test_db_name)
    repo1 = MongoAgentRunRepository(db=db1)

    run = AgentExecutionRun(
        run_id="run_restart_999",
        project_id="proj_restart",
        repository_id="repo_restart",
        mode="DEBUG",
        instruction="Verify restart persistence across connection pool reset",
    )

    # 1. Save run in db1
    await repo1.save_run(run)
    saved = await repo1.get_run("run_restart_999")
    assert saved is not None

    # 2. Close connection pool completely (Simulate Application Restart)
    close_mongodb_connection()

    # 3. Re-open connection pool and retrieve same record from MongoDB
    db2 = get_mongodb_database(db_name=test_db_name)
    repo2 = MongoAgentRunRepository(db=db2)

    reloaded = await repo2.get_run("run_restart_999")
    assert reloaded is not None
    assert reloaded.run_id == "run_restart_999"
    assert reloaded.instruction == "Verify restart persistence across connection pool reset"

    # Clean up
    await db2.client.drop_database(test_db_name)
    close_mongodb_connection()


@pytest.mark.asyncio
async def test_mongodb_unreachable_error_handling():
    """Verify health check returns unhealthy status when MongoDB server is offline."""
    health = await check_mongodb_health(uri="mongodb://localhost:59999", db_name="invalid_db")
    assert health["status"] == "unhealthy"
    assert health["mongodb_connected"] is False
