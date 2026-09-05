from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.database import get_db
from app.models.application import Application
from app.models.customer import Customer, CustomerUser
from app.models.enums import CustomerRole, CustomerStatus, UserStatus
from app.models.user import User
from app.schemas.auth import Token, UserCreate, UserLogin, UserResponse
from app.services.wallet_service import WalletService

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_in: UserCreate, db: Annotated[AsyncSession, Depends(get_db)]
) -> dict[str, Any]:
    """Business registers, creates Customer, Admin User, CustomerUser link, default Application, and Wallet."""
    # Check if user email exists
    stmt = select(User).where(User.email == user_in.email)
    existing_user = (await db.execute(stmt)).scalar_one_or_none()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "EMAIL_EXISTS",
                "message": "An account with this email already exists.",
            },
        )

    # Create Customer
    customer = Customer(
        company_name=user_in.company_name,
        email=user_in.email,
        phone=user_in.phone,
        status=CustomerStatus.ACTIVE,
        country_code="+91",
    )
    db.add(customer)
    await db.flush()

    # Create User
    hashed_pwd = hash_password(user_in.password)
    user = User(
        email=user_in.email,
        password_hash=hashed_pwd,
        first_name=user_in.first_name,
        last_name=user_in.last_name,
        phone=user_in.phone,
        status=UserStatus.ACTIVE,
        email_verified=False,
    )
    db.add(user)
    await db.flush()

    # Link Customer and User
    cu_link = CustomerUser(
        customer_id=customer.id,
        user_id=user.id,
        role=CustomerRole.OWNER,
    )
    db.add(cu_link)

    # Create default Application (required for API key creation)
    default_app = Application(
        customer_id=customer.id,
        name=f"{user_in.company_name} - Default",
        description="Auto-created default application",
    )
    db.add(default_app)
    await db.flush()

    # Create Wallet with initial credits
    await WalletService.get_or_create_wallet(db, customer.id)

    await db.commit()
    await db.refresh(user)

    return {
        "id": user.id,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "phone": user.phone,
        "status": user.status.value,
        "customer_id": customer.id,
        "created_at": user.created_at,
    }


@router.post("/login", response_model=Token)
async def login(
    credentials: UserLogin, db: Annotated[AsyncSession, Depends(get_db)]
) -> dict[str, str]:
    """Logs in user with email & password, returns JWT tokens."""
    stmt = select(User).where(User.email == credentials.email)
    user = (await db.execute(stmt)).scalar_one_or_none()

    if not user or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_CREDENTIALS", "message": "Incorrect email or password."},
        )

    # Fetch customer_id
    cu_stmt = select(CustomerUser).where(CustomerUser.user_id == user.id)
    cu = (await db.execute(cu_stmt)).scalar_one_or_none()
    customer_id = cu.customer_id if cu else ""

    access_token = create_access_token(data={"sub": user.id, "customer_id": customer_id})
    refresh_token = create_refresh_token(data={"sub": user.id, "customer_id": customer_id})

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user_tuple: Annotated[tuple[User, Customer], Depends(get_current_user)],
) -> dict[str, Any]:
    """Returns profile of currently authenticated user."""
    user, customer = current_user_tuple
    return {
        "id": user.id,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "phone": user.phone,
        "status": user.status.value,
        "customer_id": customer.id,
        "created_at": user.created_at,
    }
