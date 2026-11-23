"""Shared field types and the strict base model."""

from datetime import datetime, timezone
from typing import Annotated

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, PlainSerializer


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Naive datetimes are rejected; aware ones are normalised to UTC and written as ...Z.
UtcDateTime = Annotated[
    AwareDatetime,
    AfterValidator(lambda d: d.astimezone(timezone.utc)),
    PlainSerializer(lambda d: d.isoformat().replace("+00:00", "Z"), return_type=str, when_used="json"),
]

# [0-9] not \d: pydantic's regex engine treats \d as any Unicode digit.
Slug = Annotated[str, Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")]
PartId = Annotated[str, Field(pattern=r"^part-[0-9]{2}$")]
HexColor = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]
# wardrobe ids: like a slug, underscores allowed too (the built-ins are flat_cap, ragged_shorts...)
WardrobeId = Annotated[str, Field(pattern=r"^[a-z0-9]+([_-][a-z0-9]+)*$")]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")
