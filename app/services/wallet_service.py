import logging

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import WalletStatus, WalletTxnType
from app.models.wallet import Wallet, WalletTransaction

logger = logging.getLogger(__name__)


class WalletService:
    @staticmethod
    async def get_or_create_wallet(session: AsyncSession, customer_id: str) -> Wallet:
        stmt = select(Wallet).where(Wallet.customer_id == customer_id)
        result = await session.execute(stmt)
        wallet = result.scalar_one_or_none()
        if not wallet:
            wallet = Wallet(
                customer_id=customer_id,
                balance=100.0,
                currency="INR",
                status=WalletStatus.ACTIVE,
            )  # 100 free initial credits
            session.add(wallet)
            await session.flush()
        return wallet

    @staticmethod
    async def deduct_credits_atomic(
        session: AsyncSession,
        customer_id: str,
        cost: float,
        reference_type: str,
        reference_id: str,
    ) -> float:
        """
        Executes atomic wallet deduction.
        Raises HTTP 402 PAYMENT_REQUIRED if balance is below cost.
        """
        wallet = await WalletService.get_or_create_wallet(session, customer_id)
        balance_before = wallet.balance

        if balance_before < cost:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "code": "INSUFFICIENT_FUNDS",
                    "message": "Wallet balance is insufficient to dispatch OTP.",
                    "current_balance": balance_before,
                    "required_credits": cost,
                },
            )

        # Atomic SQL update
        stmt = (
            update(Wallet)
            .where(Wallet.id == wallet.id, Wallet.balance >= cost)
            .values(balance=Wallet.balance - cost)
            .execution_options(synchronize_session="fetch")
        )
        result = await session.execute(stmt)

        rowcount = getattr(result, "rowcount", 0)
        if rowcount == 0:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "code": "INSUFFICIENT_FUNDS",
                    "message": "Wallet balance is insufficient to dispatch OTP.",
                    "current_balance": balance_before,
                    "required_credits": cost,
                },
            )

        await session.refresh(wallet)
        balance_after = wallet.balance

        # Add immutable transaction ledger entry
        transaction = WalletTransaction(
            wallet_id=wallet.id,
            transaction_type=WalletTxnType.DEBIT,
            amount=cost,
            balance_before=balance_before,
            balance_after=balance_after,
            reference_type=reference_type,
            reference_id=reference_id,
            description="OTP Dispatch Debit",
        )
        session.add(transaction)
        await session.flush()
        return balance_after

    @staticmethod
    async def refund_credits(
        session: AsyncSession,
        customer_id: str,
        cost: float,
        reference_type: str,
        reference_id: str,
        reason: str = "Meta delivery failure",
    ) -> float:
        """Refunds credits to wallet on delivery failure."""
        wallet = await WalletService.get_or_create_wallet(session, customer_id)
        balance_before = wallet.balance
        balance_after = balance_before + cost

        wallet.balance = balance_after
        await session.flush()

        transaction = WalletTransaction(
            wallet_id=wallet.id,
            transaction_type=WalletTxnType.REFUND,
            amount=cost,
            balance_before=balance_before,
            balance_after=balance_after,
            reference_type=reference_type,
            reference_id=reference_id,
            description=f"Refund: {reason}",
        )
        session.add(transaction)
        await session.flush()
        return balance_after

    @staticmethod
    async def topup_wallet(
        session: AsyncSession,
        customer_id: str,
        amount: float,
        reference_id: str,
    ) -> float:
        """Topup credits to wallet on payment gateway success."""
        wallet = await WalletService.get_or_create_wallet(session, customer_id)
        balance_before = wallet.balance
        balance_after = balance_before + amount

        wallet.balance = balance_after
        await session.flush()

        transaction = WalletTransaction(
            wallet_id=wallet.id,
            transaction_type=WalletTxnType.CREDIT,
            amount=amount,
            balance_before=balance_before,
            balance_after=balance_after,
            reference_type="payment",
            reference_id=reference_id,
            description="Wallet Topup Credit",
        )
        session.add(transaction)
        await session.flush()
        return balance_after
