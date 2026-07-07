"""
FastAPI backend
uvicorn api:app --reload --port 8000
"""

import asyncio
import json
import logging
import shutil
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.esm_data.config import PipelineSettings, settings_engine
from backend.esm_data.database import (
    async_session_creator,
    get_db_session,
    init_db_tables,
)
from backend.esm_data.db_models import FormTemplate, Task, TemplateQuestion
from backend.esm_data.judge import AuditStressTestReport, LLMJudge
from backend.esm_data.models import (
    AuditRequest,
    TaskId,
    TaskReportUpdateRequest,
    TaskStatusResponse,
    TemplateCreateRequest,
)
from backend.esm_data.providers import get_provider
from backend.esm_data.services import (
    cpu_process_pool,
    run_heavy_processing,
    stage_incoming_files_and_register_task,
)
from backend.seed import seed_data_from_yaml

__all__ = ["app"]

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
RUN_DIR: Final[Path] = PROJECT_ROOT / "data" / "runtime_staging"
logger: Final[logging.Logger] = logging.getLogger(__name__)


@dataclass(frozen=True)
class GenerationPayload:
    target_doc: str = Form(...)
    model_provider: str = Form("gemini")
    custom_name: str | None = Form(None)
    files: list[UploadFile] = File(...)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """
    Manages action when sever boots up and handles when server boots down
    """

    PROJECT_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    RUN_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    await init_db_tables()

    async with async_session_creator() as session:
        result = await session.exec(select(FormTemplate))
        if not result.all():
            logger.info("DB is empty... seeding default layouts")
            await seed_data_from_yaml()

    yield

    cpu_process_pool.shutdown(wait=True)
    # add server cleanup commands here later


app = FastAPI(title="ESM Data Automation API", description="backend", lifespan=lifespan)


@app.get("/api/templates")
async def get_templates(
    *, session: AsyncSession = Depends(get_db_session)
) -> list[str]:
    """
    Gets availabble template keys from database
    """

    result = await session.exec(select(FormTemplate))
    return [template.name for template in result.all()]


@app.post("/api/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_document(
    *,
    background_tasks: BackgroundTasks,
    payload: GenerationPayload = Depends(),
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    task_id = TaskId(str(uuid.uuid4()))
    task_staging_path = RUN_DIR / task_id
    task_staging_path.mkdir(parents=True, exist_ok=True)

    # Abstracted structural implementation details to service layer
    await stage_incoming_files_and_register_task(
        session, task_id, payload.files, payload.custom_name, task_staging_path
    )

    background_tasks.add_task(
        run_heavy_processing,
        task_id=task_id,
        target_doc=payload.target_doc.upper(),
        model_provider=_sanitize_provider_token(payload.model_provider),
        staging_path=task_staging_path,
    )
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={"task_id": task_id, "status": "PENDING"},
    )


@app.get("/api/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: TaskId, session: AsyncSession = Depends(get_db_session)
) -> TaskStatusResponse:
    """
    Look up a specific tracking code inside db,
    checks if AI is still writing, finished, or crashed
    """

    if not (task := await session.get(Task, task_id)):
        raise HTTPException(status_code=404, detail="The request job does not exist.")

    return TaskStatusResponse(
        task_id=task.task_id,
        status=task.status,
        custom_name=task.custom_name,
        report=json.loads(task.report_json) if task.report_json else None,
        detail=task.detail,
        source_context=task.source_context,
    )


@app.delete("/api/tasks/{task_id}")
async def delete_task(
    task_id: TaskId,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    """
    Remove a task/run from history.
    Also deletes its staged files if they exist.
    """
    task = await session.get(Task, task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The request job does not exist.",
        )

    await session.delete(task)
    await session.commit()

    staging_path = RUN_DIR / task_id
    if staging_path.exists():
        await asyncio.to_thread(shutil.rmtree, staging_path)

    return {"status": "DELETED", "task_id": task_id}


@app.patch("/api/tasks/{task_id}/report", status_code=status.HTTP_200_OK)
async def update_task_report(
    *,
    task_id: TaskId,
    payload: TaskReportUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    """
    Update the extraction report for an existing task.
    Allows scientists to save manual edits back to the DB.
    """
    if not (task := await session.get(Task, task_id)):
        raise HTTPException(status_code=404, detail="The requested job does not exist.")

    # Serialize incoming report structure and save to task
    task.report_json = json.dumps(
        {
            "extracted_answers": payload.extracted_answers,
            "missing_information": payload.missing_information,
        }
    )
    session.add(task)
    await session.commit()
    return {"status": "SUCCESS", "message": "Task report successfully updated."}


@app.post("/api/templates", status_code=status.HTTP_201_CREATED)
async def create_custom_template(
    payload: TemplateCreateRequest, session: AsyncSession = Depends(get_db_session)
) -> dict[str, str]:
    """
    Saves a brand new form template into the database
    making it instantly available
    """

    template_name_upper = payload.name.upper()
    if (
        await session.exec(
            select(FormTemplate).where(FormTemplate.name == template_name_upper)
        )
    ).one_or_none():
        raise HTTPException(
            status_code=400, detail=f"Template '{template_name_upper}' already exists!"
        )

    db_questions = [
        TemplateQuestion(text=question_text, sort_order=index)
        for index, question_text in enumerate(payload.questions)
    ]

    new_template = FormTemplate(
        name=template_name_upper,
        description=payload.description,
        questions=db_questions,
    )

    session.add(new_template)
    await session.commit()
    return {
        "status": "SUCCESS",
        "message": f"Template '{template_name_upper}' successfully registered!",
    }


@app.get("/api/tasks", response_model=list[TaskStatusResponse])
async def list_all_tasks(
    session: AsyncSession = Depends(get_db_session),
) -> list[TaskStatusResponse]:
    """
    Gets every tracking ticket stored in db,
    allows scientists to look at their history of generated documents
    """

    result = await session.exec(select(Task).order_by(Task.task_id))

    return [
        TaskStatusResponse(
            task_id=task.task_id,
            status=task.status,
            custom_name=task.custom_name,
            report=json.loads(task.report_json) if task.report_json else None,
            detail=task.detail,
            source_context=task.source_context,
        )
        for task in result.all()
    ]


def _sanitize_provider_token(raw_token: str, /) -> str:
    """
    Transforms frontend UI presentation tags into core factory routing string literals.
    """
    clean = raw_token.lower()

    if "gemini" in clean:
        return "gemini"
    if "openai" in clean:
        return "openai"
    if "nvidia" in clean or "nemotron" in clean:
        return "nemotron"

    active_config = settings_engine.get_current()
    if active_config.custom_key_name and active_config.custom_key_name.lower() == clean:
        return active_config.recognized_provider

    return clean

@app.post("/api/audit")
async def run_audit(
    payload: AuditRequest,
    *,
    model_provider: str = Query("gemini")
) -> AuditStressTestReport:
    active_config = settings_engine.get_current()
    target_engine = _sanitize_provider_token(model_provider)

    engine_client = get_provider(
        name=target_engine,
        api_key=active_config.api_key_input if active_config.api_key_input else None
    )

    judge = LLMJudge(
        provider=engine_client,
        instructions=(
            active_config.judge_system_prompt
            if active_config.judge_system_prompt
            else None
        )
    )
    answers_text = json.dumps(payload.answers, indent=2)

    metrics = await judge.run_stability_stress_test_async(
        source_content=payload.source_context,
        paste_content=answers_text,
        prefix_label="API_EVAL",
        i_iterations=payload.iterations,
    )

    if not metrics:
        raise ValueError(
            "Audit lifecycle execution produced empty validation sequence."
        )

    return cast(AuditStressTestReport, metrics)


@app.get("/api/settings", response_model=PipelineSettings)
async def get_system_settings() -> PipelineSettings:
    """Retrieves active global execution guidelines and hyperparameters."""
    return settings_engine.get_current()


@app.patch("/api/settings", status_code=status.HTTP_200_OK)
async def update_system_settings(payload: PipelineSettings) -> dict[str, str]:
    """Overrides active system execution variables cleanly in a single window."""
    settings_engine.update_runtime(payload.model_dump())
    return {"status": "SUCCESS", "message": "System parameters updated."}


@app.post("/api/settings/reset", status_code=status.HTTP_200_OK)
async def reset_system_settings() -> dict[str, str]:
    """Wipes out active user overrides and restores factory instructions."""
    settings_engine.reset_to_factory_defaults()
    return {"status": "SUCCESS", "message": "Factory settings restored."}

