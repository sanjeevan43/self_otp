from pydantic import BaseModel


class UsageMetricsResponse(BaseModel):
    total_sent: int
    delivered: int
    failed: int
    delivery_rate: float
    total_cost: float
    credit_balance: float
    currency: str


class PlanResponse(BaseModel):
    id: str
    name: str
    price_monthly: float
    currency: str
    features: list[str]
    is_current: bool
