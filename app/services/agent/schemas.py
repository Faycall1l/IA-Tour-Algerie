from pydantic import BaseModel, Field


class DayPlan(BaseModel):
    day_number: int = Field(ge=1)
    items: list[str] = Field(default_factory=list)
    description: str = ""


class TripOptimizerOutput(BaseModel):
    days: list[DayPlan] = Field(default_factory=list)
    budget_spent: float = 0
    budget_remaining: float = 0
    gaps: list[str] = Field(default_factory=list)
    optimization_score: float = Field(default=0.0, ge=0, le=100)
    suggestions: list[str] = Field(default_factory=list)


class TopPOI(BaseModel):
    id: str = ""
    name: str = ""
    category: str = ""
    review_score: float | None = None


class WilayaBriefOutput(BaseModel):
    wilaya: str = ""
    top_pois: list[TopPOI] = Field(default_factory=list)
    experiences: list[str] = Field(default_factory=list)
    transport_estimate: int | None = None
    best_months: list[str] = Field(default_factory=list)
    review_highlights: list[str] = Field(default_factory=list)
    practical_tips: list[str] = Field(default_factory=list)


class CoordinatorOutput(BaseModel):
    action: str = ""
    result: TripOptimizerOutput | WilayaBriefOutput | dict | None = None
    rationale: str = ""
