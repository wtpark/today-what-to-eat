from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, Field, field_validator, model_validator

Storage = Literal["냉장", "냉동", "실온"]
ConditionStatus = Literal["normal", "needs_review", "excluded"]
PreviousMealAvoidance = Literal[
    "none",
    "soft",
    "exclude_cuisine",
    "exclude_type",
    "exclude_either",
    "exclude_both",
]


class IngredientCreate(BaseModel):
    ingredient_id: str
    detail_name: str = ""
    quantity: float = Field(gt=0)
    unit: str = Field(min_length=1, max_length=20)
    storage: Storage
    purchase_date: date
    expiry_date: date | None = None
    opened: bool = False
    opened_date: date | None = None
    priority_override: bool = False
    condition_status: ConditionStatus = "normal"
    condition_notes: list[str] = Field(default_factory=list)
    note: str = ""

    @field_validator("unit")
    @classmethod
    def validate_unit(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("단위는 비워둘 수 없습니다.")
        return value

    @model_validator(mode="after")
    def validate_dates_and_condition(self):
        if self.expiry_date and self.expiry_date < self.purchase_date:
            raise ValueError("표시기한은 구매일보다 빠를 수 없습니다.")
        if self.opened:
            self.opened_date = self.opened_date or self.purchase_date
            if self.opened_date < self.purchase_date:
                raise ValueError("개봉일은 구매일보다 빠를 수 없습니다.")
        else:
            self.opened_date = None
        if self.condition_status == "normal":
            self.condition_notes = []
        return self


class IngredientUpdate(BaseModel):
    detail_name: str | None = None
    purchase_date: date | None = None
    quantity: float | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, max_length=20)
    storage: Storage | None = None
    expiry_date: date | None = None
    opened: bool | None = None
    opened_date: date | None = None
    priority_override: bool | None = None
    condition_status: ConditionStatus | None = None
    condition_notes: list[str] | None = None
    note: str | None = None

    @field_validator("unit")
    @classmethod
    def validate_optional_unit(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("단위는 비워둘 수 없습니다.")
        return value


class RepurchaseRequest(BaseModel):
    quantity: float = Field(gt=0)
    unit: str = Field(min_length=1, max_length=20)
    purchase_date: date
    expiry_date: date | None = None
    detail_name: str | None = None
    note: str = ""

    @field_validator("unit")
    @classmethod
    def validate_unit(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("단위는 비워둘 수 없습니다.")
        return value

    @model_validator(mode="after")
    def validate_dates(self):
        if self.expiry_date and self.expiry_date < self.purchase_date:
            raise ValueError("표시기한은 구매일보다 빠를 수 없습니다.")
        return self


class SeasoningUpdate(BaseModel):
    owned_ids: list[str]


class RecommendationRequest(BaseModel):
    preferred_cuisine: str = "상관없음"
    cuisine_preference_strength: Literal["soft", "priority", "strict"] = "priority"
    preferred_meal_type: str = "상관없음"
    previous_meal_cuisine: str = Field(
        default="입력하지 않음",
        validation_alias=AliasChoices("previous_meal_cuisine", "lunch_cuisine"),
    )
    previous_meal_type: str = Field(
        default="입력하지 않음",
        validation_alias=AliasChoices("previous_meal_type", "lunch_meal_type"),
    )
    previous_meal_avoidance: PreviousMealAvoidance = Field(
        default="soft",
        validation_alias=AliasChoices("previous_meal_avoidance", "lunch_avoidance"),
    )
    max_cooking_minutes: int = Field(default=30, ge=5, le=180)
    appliances: list[str]
    recommendation_mode: Literal["fridge", "balanced", "taste"] = "balanced"
    repeat_avoidance: Literal["low", "medium", "high"] = "medium"
    temporary_owned_seasoning_ids: list[str] | None = None
    excluded_ingredient_ids: list[str] = Field(default_factory=list)
    allow_substitutions: bool = True

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_avoidance(cls, data: Any):
        if isinstance(data, dict):
            data = dict(data)
            legacy = data.get("previous_meal_avoidance", data.get("lunch_avoidance"))
            if legacy == "exclude_cuisine_and_type":
                # Legacy behavior excluded a recipe when either dimension matched.
                data["previous_meal_avoidance"] = "exclude_either"
        return data


class UsageItem(BaseModel):
    inventory_id: int
    remaining_quantity: float = Field(ge=0)


class MealCompleteRequest(BaseModel):
    recipe_id: str
    eaten_at: datetime
    meal_slot: str
    usage: list[UsageItem] = Field(min_length=1)
    note: str = ""


class DemoLoadRequest(BaseModel):
    only_when_empty: bool = True
    profile: Literal["balanced", "korean"] = "balanced"
    load_balanced_pantry: bool = True
