from datetime import datetime

from pydantic import BaseModel, Field


class WalletBalanceData(BaseModel):
    balance: float
    currency: str
    status: str
    updated_at: datetime


class WalletBalanceResponse(BaseModel):
    status: str = "success"
    data: WalletBalanceData


class WalletTopupRequest(BaseModel):
    amount: float = Field(..., gt=0, description="Amount to credit to wallet")
    reference_id: str = Field(..., min_length=1, description="Payment or order reference ID")


class WalletTransactionResponse(BaseModel):
    id: str
    transaction_type: str
    amount: float
    balance_before: float
    balance_after: float
    reference_type: str | None = None
    reference_id: str | None = None
    description: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True
