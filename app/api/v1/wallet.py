from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_api_key_context, get_current_user
from app.database import get_db
from app.models.api_key import APIKey
from app.models.application import Application
from app.models.customer import Customer
from app.models.user import User
from app.models.wallet import WalletTransaction
from app.schemas.wallet import WalletBalanceResponse, WalletTopupRequest, WalletTransactionResponse
from app.services.wallet_service import WalletService

router = APIRouter(prefix="/wallet", tags=["Wallet & Billing"])


@router.get("/balance", response_model=WalletBalanceResponse)
async def get_wallet_balance(
    api_auth: Annotated[tuple[APIKey, Application, Customer], Depends(get_api_key_context)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str | dict[str, Any]]:
    """Returns current wallet balance for the customer account."""
    _, _, customer = api_auth
    wallet = await WalletService.get_or_create_wallet(db, customer.id)
    return {
        "status": "success",
        "data": {
            "balance": wallet.balance,
            "currency": wallet.currency,
            "status": wallet.status.value,
            "updated_at": wallet.updated_at.isoformat(),
        },
    }


@router.post("/topup", response_model=WalletBalanceResponse)
async def topup_wallet(
    request: WalletTopupRequest,
    current_user_tuple: Annotated[tuple[User, Customer], Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str | dict[str, Any]]:
    """Topup wallet balance via payment gateway integration."""
    _, customer = current_user_tuple
    new_balance = await WalletService.topup_wallet(
        session=db,
        customer_id=customer.id,
        amount=request.amount,
        reference_id=request.reference_id,
    )
    wallet = await WalletService.get_or_create_wallet(db, customer.id)
    await db.commit()

    return {
        "status": "success",
        "data": {
            "balance": new_balance,
            "currency": wallet.currency,
            "status": wallet.status.value,
            "updated_at": wallet.updated_at.isoformat(),
        },
    }


@router.get("/transactions", response_model=list[WalletTransactionResponse])
async def list_wallet_transactions(
    current_user_tuple: Annotated[tuple[User, Customer], Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[dict[str, Any]]:
    """Lists recent wallet transactions ledger for the customer account."""
    _, customer = current_user_tuple
    wallet = await WalletService.get_or_create_wallet(db, customer.id)
    stmt = (
        select(WalletTransaction)
        .where(WalletTransaction.wallet_id == wallet.id)
        .order_by(WalletTransaction.created_at.desc())
        .limit(100)
    )
    result = await db.execute(stmt)
    txs = result.scalars().all()
    return [
        {
            "id": t.id,
            "transaction_type": t.transaction_type.value,
            "amount": t.amount,
            "balance_before": t.balance_before,
            "balance_after": t.balance_after,
            "reference_type": t.reference_type,
            "reference_id": t.reference_id,
            "description": t.description,
            "created_at": t.created_at,
        }
        for t in txs
    ]
