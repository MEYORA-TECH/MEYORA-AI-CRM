from decimal import Decimal
from typing import Annotated, Any, Generic, TypeVar

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    StringConstraints,
    field_validator,
)

T = TypeVar("T")

# Money is Numeric in Postgres; JSON clients get a number.
Money = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
LongText = Annotated[str, StringConstraints(max_length=20_000)]
Currency = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
Url = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
Phone = Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)]

Tag = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class OutputModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TaggedInput(InputModel):
    tags: list[Tag] | None = Field(default=None, max_length=30)
    custom_fields: dict[str, Any] | None = None

    @field_validator("tags")
    @classmethod
    def _dedupe_tags(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        seen: dict[str, None] = {}
        for tag in v:
            seen.setdefault(tag.lower(), None)
        return list(seen)

    @field_validator("custom_fields")
    @classmethod
    def _limit_custom_fields(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        if v is not None and (len(v) > 50 or len(str(v)) > 10_000):
            raise ValueError("custom_fields is too large")
        return v


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
