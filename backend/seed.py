"""
Load initial form data from YAML file into the database
"""

import asyncio
import logging
from importlib.resources import files
from pathlib import Path

import yaml
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.esm_data.database import async_session_creator, init_db_tables
from backend.esm_data.db_models import FormTemplate, TemplateQuestion
from backend.esm_data.generator import TemplateConfig
from backend.esm_data.models import TemplateName

__all__ = ["add_single_template", "seed_data_from_yaml"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s %(message)s]",
    datefmt="%Y-%m-%d %H:%M:%S",
    force=True,
)
logger = logging.getLogger(__name__)


async def add_single_template(
    session: AsyncSession, name: TemplateName, contents: TemplateConfig
) -> None:
    """
    Handles the database checks and insertion for one single form template
    """

    template_upper = name.upper()

    result = await session.exec(
        select(FormTemplate).where(FormTemplate.name == template_upper)
    )

    if result.one_or_none():
        logger.warning(f"'{template_upper}' is already in database, skipping...")
        return

    logger.info(f"Adding form layout: {template_upper}")

    questions_list = contents.get("questions", [])
    db_questions = [
        TemplateQuestion(text=question_text, sort_order=index)
        for index, question_text in enumerate(questions_list)
    ]

    db_template = FormTemplate(name=template_upper, questions=db_questions)
    session.add(db_template)


async def seed_data_from_yaml() -> None:
    """
    Reads templates.yaml and drives the database seeding
    """

    logger.info("Starting database tables...")
    await init_db_tables()

    yaml_path = Path(str(files("backend.esm_data"))) / "templates.yaml"
    if not yaml_path.exists():
        logger.error(f"Could not find the file at: {yaml_path.resolve()}")
        return

    raw_config = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    templates_source = raw_config.get("DOCUMENT_TEMPLATES", {})

    async with async_session_creator() as session:
        for template_name, contents in templates_source.items():
            await add_single_template(session, template_name, contents)

        await session.commit()

    logger.info("Database seeding completed successfully!")


if __name__ == "__main__":
    asyncio.run(seed_data_from_yaml())
