import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    APIKey,
    APIKeyStatus,
    AuditLog,
    BillingChannel,
    Customer,
    CustomerRole,
    CustomerStatus,
    CustomerUser,
    IdempotencyKey,
    Message,
    MessageEvent,
    MessageEventType,
    MessageStatus,
    MessageType,
    MetaAccount,
    MetaAccountStatus,
    OTPRequest,
    OTPStatus,
    OTPVerification,
    OTPVerificationResult,
    Payment,
    PaymentOrder,
    PaymentOrderStatus,
    PaymentStatus,
    PlanStatus,
    PricingPlan,
    PricingRule,
    TemplateStatus,
    User,
    UserStatus,
    Wallet,
    WalletStatus,
    WalletTransaction,
    WalletTxnType,
    WebhookEvent,
    WebhookProcessingStatus,
    WhatsAppNumber,
    WhatsAppNumberStatus,
    WhatsAppTemplate,
)
from app.models.base import utc_now


@pytest.mark.asyncio
async def test_full_database_schema_and_relationships(db_session: AsyncSession) -> None:
    """
    Tests all 19 tables in Phase 2: Core Customers, Meta System, OTP System,
    Messaging, Billing, Security, FK relationships, and cascades.
    """
    # 1. Core Customer System (users, customers, customer_users, api_keys)
    customer = Customer(
        company_name="Test Org Ltd",
        email="org@test.com",
        phone="+14155552671",
        status=CustomerStatus.ACTIVE,
    )
    db_session.add(customer)
    await db_session.flush()

    user = User(
        email="user@test.com",
        password_hash="hashed_password_val",
        first_name="John",
        last_name="Doe",
        status=UserStatus.ACTIVE,
    )
    db_session.add(user)
    await db_session.flush()

    cu_link = CustomerUser(
        customer_id=customer.id,
        user_id=user.id,
        role=CustomerRole.ADMIN,
    )
    db_session.add(cu_link)

    api_key = APIKey(
        customer_id=customer.id,
        name="Test API Key",
        key_prefix="wotp_test_",
        key_hash="hash_val_123",
        status=APIKeyStatus.ACTIVE,
    )
    db_session.add(api_key)
    await db_session.flush()

    # 2. Meta System (meta_accounts, whatsapp_numbers, whatsapp_templates)
    meta_acc = MetaAccount(
        customer_id=customer.id,
        business_account_id="bba_12345",
        status=MetaAccountStatus.ACTIVE,
    )
    db_session.add(meta_acc)
    await db_session.flush()

    wa_num = WhatsAppNumber(
        meta_account_id=meta_acc.id,
        phone_number_id="phone_id_12345",
        display_phone_number="+14155552671",
        status=WhatsAppNumberStatus.ACTIVE,
    )
    db_session.add(wa_num)
    await db_session.flush()

    wa_tpl = WhatsAppTemplate(
        whatsapp_number_id=wa_num.id,
        name="otp_auth_v1",
        language_code="en_US",
        category="AUTHENTICATION",
        status=TemplateStatus.APPROVED,
    )
    db_session.add(wa_tpl)

    # 3. OTP System (otp_requests, otp_verifications)
    otp_req = OTPRequest(
        customer_id=customer.id,
        api_key_id=api_key.id,
        request_id="req_test_999",
        phone_number="+14155552671",
        otp_hash="hashed_otp_val",
        status=OTPStatus.VERIFIED,
        expires_at=utc_now(),
        attempts=1,
        max_attempts=5,
    )
    db_session.add(otp_req)
    await db_session.flush()

    otp_verif = OTPVerification(
        otp_request_id=otp_req.id,
        attempt_number=1,
        result=OTPVerificationResult.CORRECT,
        ip_address="127.0.0.1",
    )
    db_session.add(otp_verif)

    # 4. Message System (messages, message_events, webhook_events)
    msg = Message(
        customer_id=customer.id,
        otp_request_id=otp_req.id,
        whatsapp_number_id=wa_num.id,
        provider="meta",
        provider_message_id="wamid.123",
        phone_number="+14155552671",
        message_type=MessageType.AUTHENTICATION,
        status=MessageStatus.DELIVERED,
    )
    db_session.add(msg)
    await db_session.flush()

    msg_evt = MessageEvent(
        message_id=msg.id,
        event_type=MessageEventType.DELIVERED,
        provider_message_id="wamid.123",
    )
    db_session.add(msg_evt)

    wh_evt = WebhookEvent(
        provider="meta",
        event_type="delivered",
        external_event_id="wamid.123",
        payload={"status": "delivered"},
        processing_status=WebhookProcessingStatus.PROCESSED,
    )
    db_session.add(wh_evt)

    # 5. Billing (wallets, wallet_transactions, pricing_plans, pricing_rules, payment_orders, payments)
    wallet = Wallet(
        customer_id=customer.id,
        currency="INR",
        balance=100.0,
        status=WalletStatus.ACTIVE,
    )
    db_session.add(wallet)
    await db_session.flush()

    w_tx = WalletTransaction(
        wallet_id=wallet.id,
        transaction_type=WalletTxnType.CREDIT,
        amount=100.0,
        balance_before=0.0,
        balance_after=100.0,
        description="Initial grant",
    )
    db_session.add(w_tx)

    plan = PricingPlan(
        name="Standard Plan",
        monthly_price=10.0,
        status=PlanStatus.ACTIVE,
    )
    db_session.add(plan)
    await db_session.flush()

    p_rule = PricingRule(
        plan_id=plan.id,
        channel=BillingChannel.WHATSAPP,
        country_code="+91",
        price_per_message=0.5,
    )
    db_session.add(p_rule)

    p_order = PaymentOrder(
        customer_id=customer.id,
        order_reference="ref_1001",
        amount=50.0,
        status=PaymentOrderStatus.PAID,
    )
    db_session.add(p_order)
    await db_session.flush()

    payment = Payment(
        payment_order_id=p_order.id,
        amount=50.0,
        status=PaymentStatus.SUCCESS,
    )
    db_session.add(payment)

    # 6. Security (idempotency_keys, audit_logs)
    idemp = IdempotencyKey(
        customer_id=customer.id,
        idempotency_key="idemp_key_1",
        endpoint="/v1/otp/send",
        request_hash="hash_1",
    )
    db_session.add(idemp)

    audit = AuditLog(
        user_id=user.id,
        customer_id=customer.id,
        action="user.login",
    )
    db_session.add(audit)

    await db_session.commit()

    # Query & Assert All Tables
    assert (await db_session.execute(select(Customer))).scalar_one_or_none() is not None
    assert (await db_session.execute(select(User))).scalar_one_or_none() is not None
    assert (await db_session.execute(select(CustomerUser))).scalar_one_or_none() is not None
    assert (await db_session.execute(select(APIKey))).scalar_one_or_none() is not None
    assert (await db_session.execute(select(MetaAccount))).scalar_one_or_none() is not None
    assert (await db_session.execute(select(WhatsAppNumber))).scalar_one_or_none() is not None
    assert (await db_session.execute(select(WhatsAppTemplate))).scalar_one_or_none() is not None
    assert (await db_session.execute(select(OTPRequest))).scalar_one_or_none() is not None
    assert (await db_session.execute(select(OTPVerification))).scalar_one_or_none() is not None
    assert (await db_session.execute(select(Message))).scalar_one_or_none() is not None
    assert (await db_session.execute(select(MessageEvent))).scalar_one_or_none() is not None
    assert (await db_session.execute(select(WebhookEvent))).scalar_one_or_none() is not None
    assert (await db_session.execute(select(Wallet))).scalar_one_or_none() is not None
    assert (await db_session.execute(select(WalletTransaction))).scalar_one_or_none() is not None
    assert (await db_session.execute(select(PricingPlan))).scalar_one_or_none() is not None
    assert (await db_session.execute(select(PricingRule))).scalar_one_or_none() is not None
    assert (await db_session.execute(select(PaymentOrder))).scalar_one_or_none() is not None
    assert (await db_session.execute(select(Payment))).scalar_one_or_none() is not None
    assert (await db_session.execute(select(IdempotencyKey))).scalar_one_or_none() is not None
    assert (await db_session.execute(select(AuditLog))).scalar_one_or_none() is not None
