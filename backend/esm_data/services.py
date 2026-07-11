import asyncio
import json
import logging
import shutil
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Final

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.esm_data.config import settings_engine
from backend.esm_data.database import async_session_creator
from backend.esm_data.db_models import FormTemplate, Task, TemplateQuestion
from backend.esm_data.document import EXTRACTOR_MAP, extract_text
from backend.esm_data.generator import DocumentGenerator
from backend.esm_data.providers import get_provider
from shared.models import (
    AgentConfigurationError,
    AgentExecutionError,
    ExtractionReport,
    TaskId,
)

logger: Final[logging.Logger] = logging.getLogger(__name__)
cpu_process_pool: Final[ProcessPoolExecutor] = ProcessPoolExecutor(max_workers=2)


def _extract_context_cpu_worker(staging_path_str: str) -> str:
    """
    Worker function running inside a separate OS process
    Bypasses the Global Interpreter Lock (GIL) to completely parse massive files
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


async def _initialize_task_and_questions_in_session(
    session: AsyncSession, task_id: TaskId, target_doc: str
) -> list[str] | None:
    task = await session.get(Task, task_id)
    if not task:
        logger.error(f"Aborting worker: tracking ticket context {task_id} not found")
        return None

    task.status = "PROCESSING"
    await session.commit()

    statement = (
        select(TemplateQuestion)
        .join(FormTemplate)
        .where(FormTemplate.name == target_doc.upper())
        .order_by(col(TemplateQuestion.sort_order))
    )
    result = await session.exec(statement)
    return [question.text for question in result.all()]


async def _initialize_task_and_questions(
    task_id: TaskId, target_doc: str
) -> list[str] | None:
    async with async_session_creator() as session:
        return await _initialize_task_and_questions_in_session(
            session, task_id, target_doc
        )


async def _run_extraction_thread(
    generator: DocumentGenerator, target_questions: list[str], context: str
) -> ExtractionReport:
    try:
        return await asyncio.to_thread(
            generator.execute_extraction, target_questions, context
        )
    except Exception as generation_error:
        raise AgentExecutionError(
            f"LLM generation failed: {generation_error}"
        ) from generation_error


async def _perform_document_extraction(  # noqa: C901
    target_questions: list[str], model_provider: str, staging_path: Path
) -> tuple[ExtractionReport | None, str, str | None]:
    error_detail: str | None = None
    report: ExtractionReport | None = None
    final_unified_context: str = ""

    if not target_questions:
        error_detail = "No fields found for data blueprint"
        logger.error(
            f"Processing failed to application domain fault: {error_detail}",
            exc_info=True,
        )
        return None, "", error_detail

    try:
        loop = asyncio.get_running_loop()
        final_unified_context = await loop.run_in_executor(
            cpu_process_pool, _extract_context_cpu_worker, str(staging_path)
        )

        active_config = settings_engine.get_current()
        provider_instance = get_provider(name=model_provider)

        instruction_blocks: list[str] = []
        if active_config.generator_system_prompt:
            instruction_blocks.append(active_config.generator_system_prompt)

        # Guard clause check for automated parsed data
        yaml_files = [
            staging_file
            for staging_file in staging_path.iterdir()
            if staging_file.is_file()
            and staging_file.suffix.lower() in {".yaml", ".yml"}
        ]
        if yaml_files and active_config.yaml_system_prompt:
            logger.info(
                "Detected automated YAML payload. Appending strict YAML instructions."
            )
            instruction_blocks.append(f"\n\n{active_config.yaml_system_prompt}")

        # Guard clause check for scientist-provided custom overrides
        custom_prompt_file = staging_path / "custom_instructions.txt"
        if custom_prompt_file.exists():
            logger.info(
                "Detected custom_instructions.txt override. Appending to system prompt."
            )
            try:
                custom_prompt_text = custom_prompt_file.read_text(
                    encoding="utf-8"
                ).strip()
                instruction_blocks.append(
                    f"\n\nUSER OVERRIDE INSTRUCTIONS:\n{custom_prompt_text}"
                )
            except OSError as read_error:
                logger.warning(f"Could not read custom_instructions.txt: {read_error}")

        final_instructions = "".join(instruction_blocks) if instruction_blocks else None

        logger.info(
            f"Initializing AI DocumentGenerator using provider: {model_provider}"
        )
        generator = DocumentGenerator(
            provider=provider_instance, instructions=final_instructions
        )
        report = await _run_extraction_thread(
            generator, target_questions, final_unified_context
        )

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
    return report, final_unified_context, error_detail


async def _write_final_task_status(
    session: AsyncSession,
    task_id: TaskId,
    report: ExtractionReport | None,
    final_unified_context: str,
    error_detail: str | None,
) -> None:
    task = await session.get(Task, task_id)
    if not task:
        logger.error(
            f"Failed to finalize processing job: tracking ticket {task_id} missing"
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


async def _finalize_heavy_processing(
    task_id: TaskId,
    report: ExtractionReport | None,
    final_unified_context: str,
    error_detail: str | None,
) -> None:
    try:
        async with async_session_creator() as session:
            await _write_final_task_status(
                session, task_id, report, final_unified_context, error_detail
            )
    except SQLAlchemyError as db_error:
        logger.error(
            "Database tracking layer failed to write terminal completion "
            f"status: {db_error}",
            exc_info=True,
        )


async def run_heavy_processing(
    *, task_id: TaskId, target_doc: str, model_provider: str, staging_path: Path
) -> None:
    """Handles the long document reading and AI tasks."""
    target_questions = await _initialize_task_and_questions(task_id, target_doc)
    if target_questions is None:
        return

    report: ExtractionReport | None = None
    final_unified_context: str = ""
    error_detail: str | None = None

    try:
        (
            report,
            final_unified_context,
            error_detail,
        ) = await _perform_document_extraction(
            target_questions, model_provider, staging_path
        )
    finally:
        if staging_path.exists():
            await asyncio.to_thread(shutil.rmtree, staging_path)

    await _finalize_heavy_processing(
        task_id, report, final_unified_context, error_detail
    )


async def _stage_single_file(uploaded_file: UploadFile, staging_path: Path) -> None:
    if not uploaded_file.filename:
        return
    file_disk_path = staging_path / Path(uploaded_file.filename).name
    try:
        content = await uploaded_file.read()
        await asyncio.to_thread(file_disk_path.write_bytes, content)
    except OSError as io_error:
        if staging_path.exists():
            shutil.rmtree(staging_path)
        logger.error(
            "Disk write fault encountered during file staging loop", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Storage IO error while staging files...",
        ) from io_error


async def _register_new_task(
    session: AsyncSession, task_id: TaskId, custom_name: str | None, staging_path: Path
) -> None:
    try:
        new_task = Task(task_id=task_id, status="PENDING", custom_name=custom_name)
        session.add(new_task)
        await session.commit()
    except SQLAlchemyError as db_error:
        if staging_path.exists():
            shutil.rmtree(staging_path)
        logger.error("Database tracking error while performing task", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal database failure occurred while processing task record.",
        ) from db_error


async def stage_incoming_files_and_register_task(
    session: AsyncSession,
    task_id: TaskId,
    files: list[UploadFile],
    custom_name: str | None,
    staging_path: Path,
    is_update_boolean: bool = False,
) -> None:
    if is_update_boolean:
        existing_versions_count: int = (
            len([item for item in staging_path.iterdir() if item.is_dir()])
            if staging_path.exists()
            else 0
        )
        next_version_integer: int = existing_versions_count + 1
        version_directory_path: Path = staging_path / f"v{next_version_integer}"
        version_directory_path.mkdir(parents=True, exist_ok=True)

        for uploaded_file in files:
            await _stage_single_file(uploaded_file, version_directory_path)

        task_record = await session.get(Task, task_id)
        if task_record:
            task_record.status = "PENDING_REVIEW"
            session.add(task_record)
            await session.commit()
        return

    for uploaded_file in files:
        await _stage_single_file(uploaded_file, staging_path)
    await _register_new_task(session, task_id, custom_name, staging_path)
