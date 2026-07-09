"""household 도메인 Pydantic 스키마 — api-spec.md §4.

서버측 전량 재검증 (CWE-20/602 — 클라이언트 값 불신):
- members 1~10명
- memberType 열거값 (adult_m/adult_f/teen/child/toddler)
- 유형별 나이 범위: 성인 20~99 / 청소년 13~19 / 어린이 7~12 / 유아 0~6
"""

from typing import Literal

from pydantic import Field, model_validator

from app.core.schema import CamelModel

MemberType = Literal["adult_m", "adult_f", "teen", "child", "toddler"]

MEMBER_AGE_RANGE: dict[str, tuple[int, int]] = {
    "adult_m": (20, 99),
    "adult_f": (20, 99),
    "teen": (13, 19),
    "child": (7, 12),
    "toddler": (0, 6),
}


class HouseholdMemberIn(CamelModel):
    member_type: MemberType
    age: int

    @model_validator(mode="after")
    def validate_age_range(self) -> "HouseholdMemberIn":
        low, high = MEMBER_AGE_RANGE[self.member_type]
        if not (low <= self.age <= high):
            raise ValueError(f"age out of range for {self.member_type} ({low}~{high})")
        return self


class HouseholdUpdateRequest(CamelModel):
    members: list[HouseholdMemberIn] = Field(min_length=1, max_length=10)


class HouseholdMemberOut(CamelModel):
    member_type: str
    age: int


class HouseholdResponse(CamelModel):
    members: list[HouseholdMemberOut]
    size: int
