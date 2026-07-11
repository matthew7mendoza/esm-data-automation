"""
Tables that we want to save to db
"""

from datetime import UTC, datetime

from sqlmodel import Field, Relationship, SQLModel

__all__ = ["ApiToken", "FormTemplate", "Task", "TemplateQuestion"]


class FormTemplate(SQLModel, table=True):
    """
    Config schema representing document form (like ReadME, DMP, ect..)
    """

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    description: str | None = None
    questions: list["TemplateQuestion"] = Relationship(
        back_populates="template", cascade_delete=True
    )


class TemplateQuestion(SQLModel, table=True):
    """
    Individual question that belongs inside a specific FormTemplate
    """

    id: int | None = Field(default=None, primary_key=True)
    text: str = Field(max_length=500)
    sort_order: int = Field(default=0)
    template_id: int = Field(foreign_key="formtemplate.id", ondelete="CASCADE")
    template: FormTemplate = Relationship(back_populates="questions")


class Task(SQLModel, table=True):
    """
    Tracking ticket to follow the progress of background jobs
    """

    task_id: str = Field(primary_key=True)
    status: str = Field(default="PENDING", index=True)
    custom_name: str | None = Field(default=None)
    report_json: str | None = Field(default=None)
    source_context: str | None = Field(default=None)
    detail: str | None = Field(default=None)


class ApiToken(SQLModel, table=True):
    """
    Secure access token for CLI authentication.
    """

    token_string: str = Field(primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    is_active: bool = Field(default=True)
