from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AgeGroup = Literal["infant", "child", "teen", "adult"]


class Member(BaseModel):
    age_group: AgeGroup


class HouseholdCreate(BaseModel):
    region: Literal["KR", "US"] = "KR"
    members: list[Member] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)


class HouseholdRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    region: str
    members: list
    allergies: list
    preferences: list
    created_at: datetime
