"""
FastAPI backend
uvicorn api:app --reload --port 8000
"""

import asyncio
import json
import logging
import shutil
import tempfile
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

import yaml
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

from backend.auth import generate_secure_token_string, verify_api_token
from backend.esm_data.config import PipelineSettings, settings_engine
from backend.esm_data.database import (
    async_session_creator,
    get_db_session,
    init_db_tables,
)
from backend.esm_data.db_models import ApiToken, FormTemplate, Task, TemplateQuestion
from backend.esm_data.document import EXTRACTOR_MAP, extract_text
from backend.esm_data.judge import AuditStressTestReport, LLMJudge
from backend.esm_data.providers import get_provider
from backend.esm_data.services import (
    cpu_process_pool,
    run_heavy_processing,
    stage_incoming_files_and_register_task,
)
from backend.seed import seed_data_from_yaml
from shared.models import (
    AuditRequest,
    TaskId,
    TaskRenameRequest,
    TaskReportUpdateRequest,
    TaskStatusResponse,
    TemplateCreateRequest,
    TemplateQuestionsExtraction,
)

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


def _convert_task_database_record_to_response_model(
    task_record: Task,
) -> TaskStatusResponse:
    report_dictionary = None
    if task_record.report_json:
        report_dictionary = json.loads(task_record.report_json)

    return TaskStatusResponse(
        task_id=task_record.task_id,
        status=task_record.status,
        custom_name=task_record.custom_name,
        report=report_dictionary,
        detail=task_record.detail,
        source_context=task_record.source_context,
    )


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


@app.post("/api/auth/token", status_code=status.HTTP_201_CREATED)
async def create_api_token(
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    """
    Generates a secure API token, saves it to the database, and returns it.
    This is used by Streamlit to display the single copy-pastable CLI command.
    """
    new_token_string: str = generate_secure_token_string()
    new_token: ApiToken = ApiToken(token_string=new_token_string)

    session.add(new_token)
    await session.commit()

    logger.info("Successfully generated and registered a new API token.")
    return {"token": new_token_string}


@app.post("/api/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_document(
    *,
    background_tasks: BackgroundTasks,
    payload: GenerationPayload = Depends(),
    session: AsyncSession = Depends(get_db_session),
    _token: ApiToken = Depends(verify_api_token),
) -> JSONResponse:
    project_identifier_string: str = str(uuid.uuid4())
    is_force_update_boolean: bool = False

    for uploaded_file in payload.files:
        if uploaded_file.filename and uploaded_file.filename.endswith(".yaml"):
            file_bytes_content: bytes = await uploaded_file.read()
            await uploaded_file.seek(0)
            parsed_yaml_dictionary: dict[str, object] = yaml.safe_load(
                file_bytes_content
            )
            project_identifier_string = str(
                parsed_yaml_dictionary.get(
                    "project_unique_identifier", project_identifier_string
                )
            )
            is_force_update_boolean = bool(
                parsed_yaml_dictionary.get("is_force_update_boolean", False)
            )
            break

    task_id = TaskId(project_identifier_string)
    existing_task_record = await session.get(Task, task_id)

    task_root_path = RUN_DIR / task_id
    task_root_path.mkdir(parents=True, exist_ok=True)
    config_dict = {
        "target_doc": payload.target_doc,
        "model_provider": payload.model_provider,
    }
    (task_root_path / "run_config.json").write_text(json.dumps(config_dict))

    if existing_task_record and is_force_update_boolean:
        task_staging_path: Path = task_root_path / "versions"
        task_staging_path.mkdir(parents=True, exist_ok=True)

        await stage_incoming_files_and_register_task(
            session=session,
            task_id=task_id,
            files=payload.files,
            custom_name=payload.custom_name,
            staging_path=task_staging_path,
            is_update_boolean=True,
        )
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"task_id": task_id, "status": "PENDING_REVIEW"},
        )

    task_staging_path = RUN_DIR / task_id
    task_staging_path.mkdir(parents=True, exist_ok=True)

    await stage_incoming_files_and_register_task(
        session=session,
        task_id=task_id,
        files=payload.files,
        custom_name=payload.custom_name,
        staging_path=task_staging_path,
        is_update_boolean=False,
    )

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

    return _convert_task_database_record_to_response_model(task_record=task)


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


@app.patch("/api/tasks/{task_id}/rename", status_code=status.HTTP_200_OK)
async def rename_task(
    *,
    task_id: TaskId,
    payload: TaskRenameRequest,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    """
    Rename an existing task.
    """
    if not (task := await session.get(Task, task_id)):
        raise HTTPException(status_code=404, detail="The requested job does not exist.")

    task.custom_name = payload.custom_name
    session.add(task)
    await session.commit()
    return {"status": "SUCCESS", "message": "Task renamed successfully."}


@app.post("/api/templates", status_code=status.HTTP_201_CREATED)
async def create_custom_template(
    payload: TemplateCreateRequest, session: AsyncSession = Depends(get_db_session)
) -> dict[str, str]:
    """
    Saves a brand new form template into the database
    making it instantly available. Overwrites if it exists.
    """

    template_name_upper = payload.name.upper()
    existing = (
        await session.exec(
            select(FormTemplate).where(FormTemplate.name == template_name_upper)
        )
    ).one_or_none()

    if existing:
        await session.delete(existing)
        await session.commit()

    database_questions = [
        TemplateQuestion(text=question_text, sort_order=index)
        for index, question_text in enumerate(payload.questions)
    ]

    new_template = FormTemplate(
        name=template_name_upper,
        description=payload.description,
        questions=database_questions,
    )

    session.add(new_template)
    await session.commit()
    return {
        "status": "SUCCESS",
        "message": f"Template '{template_name_upper}' successfully registered!",
    }


async def _extract_text_from_upload(file: UploadFile) -> str:
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded.")

    with tempfile.NamedTemporaryFile(
        delete=False, suffix=Path(file.filename).suffix
    ) as temporary_file:
        temporary_file.write(await file.read())
        temporary_file_path = Path(temporary_file.name)

    try:
        return extract_text(temporary_file_path)
    except OSError as io_error:
        raise HTTPException(
            status_code=400, detail=f"Failed to read document IO error: {io_error}"
        ) from io_error
    except ValueError as value_error:
        raise HTTPException(
            status_code=400, detail=f"Failed to extract document text: {value_error}"
        ) from value_error
    finally:
        temporary_file_path.unlink(missing_ok=True)


@app.post("/api/templates/extract", status_code=status.HTTP_200_OK)
async def extract_template_questions(
    *, file: UploadFile = File(...), model_provider: str = Form("gemini")
) -> list[str]:
    """
    Extracts form questions from an unstructured document using an LLM.
    """
    source_text_content = await _extract_text_from_upload(file)
    provider_instance = get_provider(name=model_provider)

    prompt_text = (
        "Please extract all form fields or questions from the following document. "
        "Format the output strictly as a list of strings representing the "
        "questions.\n\n"
        f"DOCUMENT:\n{source_text_content}"
    )

    try:
        validated_schema_data = provider_instance.generate_structured(
            prompt=prompt_text,
            system_instruction=(
                "You are a strict data assistant. "
                "Extract the questions from the provided template document."
            ),
            response_schema=TemplateQuestionsExtraction,
        )
    except ValueError as value_error:
        logger.error(
            f"Failed to extract questions formatting: {value_error}", exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="LLM failed to extract correctly formatted questions.",
        ) from value_error
    except RuntimeError as runtime_error:
        logger.error(
            f"Failed to extract questions runtime: {runtime_error}", exc_info=True
        )
        raise HTTPException(
            status_code=500, detail="LLM failed to generate extraction."
        ) from runtime_error

    return validated_schema_data.questions


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
        _convert_task_database_record_to_response_model(task_record=task_record)
        for task_record in result.all()
    ]


@app.post("/api/audit")
async def run_audit(
    payload: AuditRequest, *, model_provider: str = Query("gemini")
) -> AuditStressTestReport:
    active_config = settings_engine.get_current()
    engine_client = get_provider(name=model_provider)

    judge = LLMJudge(
        provider=engine_client,
        instructions=(
            active_config.judge_system_prompt
            if active_config.judge_system_prompt
            else None
        ),
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


@app.get("/api/settings")
async def get_system_settings() -> dict[str, object]:
    """Retrieves active global execution guidelines and hyperparameters."""
    return settings_engine.get_current().model_dump(
        exclude={"api_key_input", "custom_api_keys"}
    )


@app.patch("/api/settings", status_code=status.HTTP_200_OK)
async def update_system_settings(payload: PipelineSettings) -> dict[str, str]:
    """Overrides active system execution variables cleanly in a single window."""
    settings_engine.update_runtime(payload.model_dump())
    return {"status": "SUCCESS", "message": "System parameters updated."}


@app.post("/api/settings/reset", status_code=status.HTTP_200_OK)
async def reset_system_settings(
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    """Wipes out active user overrides and restores factory instructions."""
    settings_engine.reset_to_factory_defaults()

    # Re-seed the database form templates
    templates = await session.exec(select(FormTemplate))
    for template in templates.all():
        await session.delete(template)
    await session.commit()
    await seed_data_from_yaml()

    return {"status": "SUCCESS", "message": "Factory settings restored."}


def _build_pending_context_string(latest_dir: Path) -> str:
    valid_files_list = [
        file_path_item
        for file_path_item in latest_dir.iterdir()
        if file_path_item.is_file() and file_path_item.suffix.lower() in EXTRACTOR_MAP
    ]
    return "\n\n".join(
        f"--- SOURCE CONTENT ASSET: {file_path_item.name} ---\n"
        f"{extract_text(file_path_item)}"
        for file_path_item in valid_files_list
    )


def _get_latest_task_version_directory(task_id: TaskId) -> Path | None:
    versions_dir = RUN_DIR / task_id / "versions"
    if not versions_dir.exists():
        logger.warning(f"No versions directory found for task {task_id}.")
        return None

    version_dirs = [
        directory for directory in versions_dir.iterdir() if directory.is_dir()
    ]
    if not version_dirs:
        logger.warning(
            f"Versions directory exists but contains no version folders "
            f"for task {task_id}."
        )
        return None

    return sorted(version_dirs, key=lambda directory: directory.name)[-1]


@app.get("/api/tasks/{task_id}/pending-context")
async def get_pending_context(
    task_id: TaskId, session: AsyncSession = Depends(get_db_session)
) -> dict[str, str]:
    task = await session.get(Task, task_id)
    if not task:
        logger.error(
            f"Cannot fetch pending context: Task {task_id} not found in database."
        )
        raise HTTPException(status_code=404, detail="Task not found in the database.")

    latest_dir = _get_latest_task_version_directory(task_id=task_id)
    if not latest_dir:
        return {"original": task.source_context or "", "pending": ""}

    try:
        new_context = _build_pending_context_string(latest_dir)
    except OSError as operating_system_error:
        logger.error(f"Failed to extract pending context: {operating_system_error}")
        new_context = f"Error extracting files: {operating_system_error}"
    except ValueError as value_error:
        logger.error(f"Failed to extract pending context: {value_error}")
        new_context = f"Error extracting files: {value_error}"

    return {"original": task.source_context or "", "pending": new_context}


@app.post("/api/tasks/{task_id}/approve", status_code=status.HTTP_202_ACCEPTED)
async def approve_pending_update(
    *,
    task_id: TaskId,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str]:
    task = await session.get(Task, task_id)
    if not task or task.status != "PENDING_REVIEW":
        logger.error(
            f"Cannot approve update: Task {task_id} is missing or not "
            "in PENDING_REVIEW state."
        )
        raise HTTPException(
            status_code=400, detail="Cannot approve: Invalid task state or missing."
        )

    versions_dir = RUN_DIR / task_id / "versions"
    if not versions_dir.exists():
        logger.error(
            f"Cannot approve update: Versions directory missing for task {task_id}."
        )
        raise HTTPException(
            status_code=404, detail="No pending files directory found for approval."
        )

    version_dirs = [
        directory for directory in versions_dir.iterdir() if directory.is_dir()
    ]
    if not version_dirs:
        logger.error(
            f"Cannot approve update: No version folders found inside "
            f"versions directory for task {task_id}."
        )
        raise HTTPException(
            status_code=404, detail="No pending version folders found for approval."
        )

    latest_dir = sorted(version_dirs, key=lambda directory: directory.name)[-1]

    task.status = "PENDING"
    session.add(task)
    await session.commit()
    logger.info(f"Task {task_id} approved and state updated to PENDING.")

    config_path = RUN_DIR / task_id / "run_config.json"
    target_doc = "DMP"
    model_provider = "gemini"

    try:
        config_data = (
            json.loads(config_path.read_text()) if config_path.exists() else {}
        )
        target_doc = config_data.get("target_doc", target_doc)
        model_provider = config_data.get("model_provider", model_provider)
    except json.JSONDecodeError as decode_error:
        logger.warning(
            f"Failed to decode run config JSON for task {task_id}: "
            f"{decode_error}. Using defaults."
        )

    logger.info(
        f"Dispatching AI processing for task {task_id} with model "
        f"{model_provider} for {target_doc}."
    )
    background_tasks.add_task(
        run_heavy_processing,
        task_id=task_id,
        target_doc=target_doc.upper(),
        model_provider=model_provider,
        staging_path=latest_dir,
    )

    return {"status": "SUCCESS", "message": "Job dispatched successfully."}
