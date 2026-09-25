import uuid

from pydantic import Field

from app.models.enums import StageKind
from app.schemas.common import InputModel, Name, OutputModel


class StageInput(InputModel):
    id: uuid.UUID | None = None
    name: Name
    probability: int = Field(ge=0, le=100)
    kind: StageKind = StageKind.OPEN
    color: str = Field(default="slate", max_length=20, pattern=r"^[a-z]+$")


class PipelineCreate(InputModel):
    name: Name
    is_default: bool = False
    stages: list[StageInput] = Field(min_length=3, max_length=20)


class PipelineUpdate(InputModel):
    name: Name | None = None
    is_default: bool | None = None
    stages: list[StageInput] | None = Field(default=None, min_length=3, max_length=20)


class StageOut(OutputModel):
    id: uuid.UUID
    name: str
    position: int
    probability: int
    kind: StageKind
    color: str


class PipelineOut(OutputModel):
    id: uuid.UUID
    name: str
    is_default: bool
    stages: list[StageOut]
