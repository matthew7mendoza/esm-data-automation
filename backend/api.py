"""
FastAPI backend
uvicorn api:app --reload --port 8000
"""

import asyncio
from concurrent.futures import ProcessPoolExecutor
from contextlib import asynccontextmanager
from importlib.resources import files
import json
import logging
from pathlib import Path
import shutil
from typing import Never
import uuid

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

from backend.esm_data.database import async_session_creator, get_db_session, init_db_tables
from backend.esm_data.db_models import FormTemplate, Task, TemplateQuestion
from backend.esm_data.document import EXTRACTOR_MAP, extract_text
from backend.esm_data.generator import DocumentGenerator
from backend.esm_data.judge import AuditStressTestReport, LLMJudge
from backend.esm_data.models import AuditRequest, TaskStatusResponse, TemplateCreateRequest
from backend.esm_data.providers import get_provider
from backend.seed import seed_data_from_yaml


__all__ = ["app"]

PROJECT_ROOT = Path(str(files("backend"))).parent
RUN_DIR = PROJECT_ROOT / "data" / "runtime_staging"

logger = logging.getLogger(__name__)
cpu_process_pool: ProcessPoolExecutor = ProcessPoolExecutor(max_workers=2)

@asynccontextmanager
async def lifespan(app: FastAPI):
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
    #add server cleanup commands here later



app = FastAPI(
    title="ESM Data Automation API",
    description="backend",
    lifespan=lifespan
)

def _extract_context_cpu_worker(staging_path_str: str) -> str:
    """
    worker function running inside seperate OS process
    byplasses global interpreter lock to completely parse massive files
    """

    worker_path = Path(staging_path_str)

    valid_workspace_files = [
        file for file in worker_path.iterdir()
        if file.is_file() and file.suffix.lower() in EXTRACTOR_MAP
    ]

    if not valid_workspace_files:
        raise ValueError("No text could be scanned!")
    
    return "\n\n".join(
        f"--- SOURCE CONTENT ASSET: {file_path.name} ---\n{extract_text(file_path)}"
        for file_path in valid_workspace_files
    )


async def run_heavy_processing(
    *,
    task_id: str,
    target_doc: str,
    model_provider: str,
    staging_path: Path
) -> None:
    """
    Handles the long document reading and AI tasks
    """

    async with async_session_creator() as session:
        task = await session.get(Task, task_id)

        if not task:
            logger.error(f"Aborting worker: tracking ticket context {task_id} not found")
            return
        
        task.status = "PROCESSING"
        await session.commit()

        statement = (
            select(TemplateQuestion)
            .join(FormTemplate)
            .where(FormTemplate.name == target_doc.upper())
            .order_by(TemplateQuestion.sort_order)
        )
        result = await session.exec(statement)
        target_questions = [question.text for question in result.all()]
    
    try:
        if not target_questions:
            raise ValueError(f"No operational fields found for data blueprint: '{target_doc}'")
        
        loop = asyncio.get_running_loop()
        final_unified_context = await loop.run_in_executor(
            cpu_process_pool,
            _extract_context_cpu_worker,
            str(staging_path)
        )

        provider_instance = get_provider(name=model_provider)
        generator = DocumentGenerator(provider=provider_instance)

        report = await asyncio.to_thread(
            generator.execute_extraction,
            target_questions,
            final_unified_context
        )

        async with async_session_creator() as session:
            task = await session.get(Task, task_id)
            if not task:
                return
            task.status = "COMPLETED"
            task.report_json = json.dumps(report)
            task.source_context = final_unified_context
            await session.commit()
        
    except Exception as error:
        async with async_session_creator() as session:
            task = await session.get(Task, task_id)
            if not task:
                return
            task.status = "FAILED"
            task.detail = str(error)
            await session.commit()
    
    finally:
        if staging_path.exists():
            await asyncio.to_thread(shutil.rmtree, staging_path)
        

@app.get("/api/templates")
async def get_templates(session: AsyncSession = Depends(get_db_session)) -> list[str]:
    """
    Gets available template keys from database registry
    """

    result = await session.exec(select(FormTemplate))
    return [template.name for template in result.all()]
        
@app.post("/api/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_document(
    *,
    background_tasks: BackgroundTasks,
    target_doc: str = Form(...),
    model_provider: str = Form("gemini"),
    custom_name: str | None = Form(None),
    files: list[UploadFile] = File(...),
    session: AsyncSession = Depends(get_db_session)
) -> JSONResponse:
    """
    Saves input files to disk,
    logs new job in db w/ side-thread,
    fire up background processing
    return tracking JSON reciept
    """

    task_id = str(uuid.uuid4())
    task_staging_path = RUN_DIR / task_id
    task_staging_path.mkdir(parents=True, exist_ok=True)

    try:

        for uploaded_file in files:
            if not uploaded_file.filename:
                continue
            file_disk_path = task_staging_path / Path(uploaded_file.filename).name
            content = await uploaded_file.read()
            await asyncio.to_thread(file_disk_path.write_bytes, content)
        
        new_task = Task(task_id=task_id, status="PENDING", custom_name=custom_name)
        session.add(new_task)
        await session.commit()

        background_tasks.add_task(
            run_heavy_processing,
            task_id=task_id,
            target_doc=target_doc.upper(),
            model_provider=model_provider,
            staging_path=task_staging_path
        )

        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"task_id": task_id, "status": "PENDING"}
        )

    except Exception as error:
        if task_staging_path.exists():
            shutil.rmtree(task_staging_path)
        
        logger.error("Failure during file staging loop", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="internal server error happened while staging scientific assets."
        )
    

@app.get("/api/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str, session: AsyncSession = Depends(get_db_session)) -> TaskStatusResponse:
    """
    Look up a specific tracking code inside db, 
    checks if AI is still writing, finished, or crashed
    """

    task = await session.get(Task, task_id)

    if not task:
        raise HTTPException(status_code=404, detail="The request job token does not exist.")
    
    return TaskStatusResponse(
        task_id=task.task_id,
        status=task.status,
        custom_name=task.custom_name,
        report=json.loads(task.report_json) if task.report_json else None,
        detail=task.detail
    )

@app.post("/api/templates", status_code=status.HTTP_201_CREATED)
async def create_custom_template(
    payload: TemplateCreateRequest,
    session: AsyncSession = Depends(get_db_session)
) -> dict[str, str]:
    """
    Saves a brand new form template into the database
    making it instantly available
    """

    template_name_upper = payload.name.upper()

    existing = await session.exec(
        select(FormTemplate).where(FormTemplate.name == template_name_upper)
    )
    if existing.one_or_none():
        raise HTTPException(status_code=400, detail=f"Template '{template_name_upper}' already exists!")
    
    db_questions = [
        TemplateQuestion(text=question_text, sort_order=index)
        for index, question_text in enumerate(payload.questions)
    ]

    new_template = FormTemplate(
        name=template_name_upper,
        description=payload.description,
        questions=db_questions
    )

    session.add(new_template)
    await session.commit()
    return {
        "status": "SUCCESS",
        "message": f"Template '{template_name_upper}' successfully registered!"
    }

@app.get("/api/tasks", response_model=list[TaskStatusResponse])
async def list_all_tasks(session: AsyncSession = Depends(get_db_session)) -> list[Task]:
    """
    Gets every tracking ticket stored in db,
    allows scientists to look at their history of generated template records
    """

    result = await session.exec(select(Task).order_by(Task.task_id))
    return result.all()

@app.post("/api/audit")
async def run_audit(payload: AuditRequest, model_provider: str = Query("gemini")) -> AuditStressTestReport | dict[str, Never]:
    """
    Run stability test w/o blocking primary application
    """

    try:
        provider_instance = get_provider(name=model_provider)
        judge = LLMJudge(provider=provider_instance)
    except Exception as error:
        raise HTTPException(status_code=400, detail=f"LLM Judge Provider Failure: {error}")
    
    answers_as_text = json.dumps(payload.answers, indent=2)
    try:
        metrics = await judge.run_stability_stress_test_async(
            source_content=payload.source_context,
            paste_content=answers_as_text,
            prefix_label="API_EVAL",
            i_iterations=payload.iterations
        )
        return metrics
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Stability Audit Failure: {str(error)}")
    