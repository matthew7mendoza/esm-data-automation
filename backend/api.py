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
from concurrent.futures import ProcessPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass
from importlib.resources import files
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
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.esm_data.database import (
    async_session_creator,
    get_db_session,
    init_db_tables,
)
from backend.esm_data.db_models import FormTemplate, Task, TemplateQuestion
from backend.esm_data.document import EXTRACTOR_MAP, extract_text
from backend.esm_data.generator import DocumentGenerator
from backend.esm_data.judge import AuditStressTestReport, LLMJudge
from backend.esm_data.models import (
    AgentConfigurationError,
    AgentExecutionError,
    AuditRequest,
    ExtractionReport,
    TaskId,
    TaskReportUpdateRequest,
    TaskStatusResponse,
    TemplateCreateRequest,
)
from backend.esm_data.providers import get_provider
from backend.seed import seed_data_from_yaml

__all__ = ["app"]

PROJECT_ROOT: Final[Path] = Path(str(files("backend"))).parent
RUN_DIR: Final[Path] = PROJECT_ROOT / "data" / "runtime_staging"
logger: Final[logging.Logger] = logging.getLogger(__name__)
cpu_process_pool: Final[ProcessPoolExecutor] = ProcessPoolExecutor(max_workers=2)


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


def _extract_context_cpu_worker(staging_path_str: str) -> str:
    """
    worker function running inside seperate OS process
    byplasses global interpreter lock to completely parse massive files
    """

    worker_path = Path(staging_path_str)

    valid_workspace_files = [
        file
        for file in worker_path.iterdir()
        if file.is_file() and file.suffix.lower() in EXTRACTOR_MAP
    ]

    if not valid_workspace_files:
        raise ValueError("No text could be scanned!")

    return "\n\n".join(
        f"--- SOURCE CONTENT ASSET: {file_path.name} ---\n{extract_text(file_path)}"
        for file_path in valid_workspace_files
    )


async def run_heavy_processing(
    *, task_id: TaskId, target_doc: str, model_provider: str, staging_path: Path
) -> None:
    """Handles the long document reading and AI tasks."""
    async with async_session_creator() as session:
        if not (task := await session.get(Task, task_id)):
            logger.error(
                f"Aborting worker: tracking ticket context {task_id} not found"
            )
            return

        task.status = "PROCESSING"
        await session.commit()

        statement = (
            select(TemplateQuestion)
            .join(FormTemplate)
            .where(FormTemplate.name == target_doc.upper())
            .order_by(col(TemplateQuestion.sort_order))
        )
        result = await session.exec(statement)
        target_questions = [question.text for question in result.all()]

    error_detail: str | None = None
    report: ExtractionReport | None = None
    final_unified_context: str = ""

    try:
        if not target_questions:
            raise ValueError(f"No fields found for data blueprint: '{target_doc}'")

        loop = asyncio.get_running_loop()
        final_unified_context = await loop.run_in_executor(
            cpu_process_pool, _extract_context_cpu_worker, str(staging_path)
        )

        provider_instance = get_provider(name=model_provider)
        generator = DocumentGenerator(provider=provider_instance)

        try:
            report = await asyncio.to_thread(
                generator.execute_extraction, target_questions, final_unified_context
            )
        except Exception as generation_error:
            raise AgentExecutionError(
                f"LLM generation failed: {generation_error}"
            ) from generation_error

    except (
        ValueError,
        OSError,
        AgentConfigurationError,
        AgentExecutionError,
    ) as known_fault:
        error_detail = str(known_fault)
        logger.error(
            f"Processing failed to application domain fault: {error_detail}",
            exc_info=True,
        )

    except Exception as unexpected_fault:
        error_detail = f"Unexpected failure: {unexpected_fault}"
        logger.error(
            "Processing crashed due to unhandled system runtime exception: "
            f"{error_detail}",
            exc_info=True,
        )

    finally:
        if staging_path.exists():
            await asyncio.to_thread(shutil.rmtree, staging_path)

    try:
        async with async_session_creator() as session:
            if not (task := await session.get(Task, task_id)):
                logger.error(
                    "Failed to finalize processing job: "
                    f"tracking ticket {task_id} missing"
                )
                return

            if error_detail:
                task.status = "FAILED"
                task.detail = error_detail
                await session.commit()
                return

            task.status = "COMPLETED"
            task.report_json = json.dumps(report)
            task.source_context = final_unified_context

            await session.commit()

    except SQLAlchemyError as db_error:
        logger.error(
            "Database tracking layer failed to write terminal completion "
            f"status: {db_error}",
            exc_info=True,
        )


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
    """
    Saves input files to disk,
    logs new job in db w/ side-thread,
    fire up background processing
    return tracking JSON reciept
    """

    task_id = TaskId(str(uuid.uuid4()))
    task_staging_path = RUN_DIR / task_id
    task_staging_path.mkdir(parents=True, exist_ok=True)

    for uploaded_file in payload.files:
        if not uploaded_file.filename:
            continue

        file_disk_path = task_staging_path / Path(uploaded_file.filename).name

        try:
            content = await uploaded_file.read()
            await asyncio.to_thread(file_disk_path.write_bytes, content)
        except OSError as io_error:
            if task_staging_path.exists():
                shutil.rmtree(task_staging_path)
            logger.error(
                "Disk write fault encountered during file staging loop", exc_info=True
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Storage IO error while staging files...",
            ) from io_error

    try:
        new_task = Task(
            task_id=task_id, status="PENDING", custom_name=payload.custom_name
        )
        session.add(new_task)
        await session.commit()
    except SQLAlchemyError as db_error:
        if task_staging_path.exists():
            shutil.rmtree(task_staging_path)
        logger.error("Database tracking error while performing task", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal database fail occured while processing task record",
        ) from db_error

    background_tasks.add_task(
        run_heavy_processing,
        task_id=task_id,
        target_doc=payload.target_doc.upper(),
        model_provider=payload.model_provider,
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


@app.post("/api/audit")
async def run_audit(
    payload: AuditRequest, model_provider: str = Query("gemini")
) -> AuditStressTestReport:
    """
    Run stability test w/o blocking primary application
    """

    try:
        provider_instance = get_provider(name=model_provider)
        judge = LLMJudge(provider=provider_instance)

    except (ValueError, AgentConfigurationError) as initialization_error:
        logger.error(
            "Failed to construct evaluator engine configuration mappings", exc_info=True
        )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"LLM Judge Provider Failure: {initialization_error}",
        ) from initialization_error

    answers_as_text = json.dumps(payload.answers, indent=2)

    try:
        metrics = await judge.run_stability_stress_test_async(
            source_content=payload.source_context,
            paste_content=answers_as_text,
            prefix_label="API_EVAL",
            i_iterations=payload.iterations,
        )
        if not metrics:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Stability Audit Failure: empty report generated.",
            )
        return cast(AuditStressTestReport, metrics)

    except HTTPException:
        raise
    except Exception as runtime_execution_error:
        logger.error(
            "Exception intercepted during execution of stability stress test loops",
            exc_info=True,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Stability Audit Failure: {runtime_execution_error!s}",
        ) from runtime_execution_error
