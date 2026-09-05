import asyncio
import logging
from datetime import UTC, datetime, timedelta

from app.core.hashing import hash_otp_code
from app.core.security import hash_api_key, hash_password
from app.database import AsyncSessionLocal, Base, engine
from app.models import (
    APIKey,
    APIKeyStatus,
    Application,
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(UTC)


async def seed_database() -> None:
    """Seeds database with default production-ready test datasets."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        try:
            logger.info("Seeding Phase 2 Database tables...")

            # 1. Customer & User
            customer = Customer(
                company_name="Acme Enterprise Inc.",
                email="admin@acme-enterprise.com",
                phone="+14155552671",
                status=CustomerStatus.ACTIVE,
                country_code="+1",
            )
            db.add(customer)
            await db.flush()

            user = User(
                email="admin@acme-enterprise.com",
                password_hash=hash_password("AdminSecurePassword123!"),
                first_name="Alice",
                last_name="Smith",
                phone="+14155552671",
                status=UserStatus.ACTIVE,
                email_verified=True,
            )
            db.add(user)
            await db.flush()

            cu_link = CustomerUser(
                customer_id=customer.id,
                user_id=user.id,
                role=CustomerRole.OWNER,
            )
            db.add(cu_link)

            # 2. Application (required by APIKey, OTPRequest, IdempotencyKey)
            application = Application(
                customer_id=customer.id,
                name="Acme Main App",
                description="Primary production application",
            )
            db.add(application)
            await db.flush()

            # 3. API Key
            raw_key = "wotp_live_seed_key_1234567890"
            api_key = APIKey(
                customer_id=customer.id,
                application_id=application.id,
                name="Primary Production Key",
                key_prefix="wotp_live_",
                key_hash=hash_api_key(raw_key),
                status=APIKeyStatus.ACTIVE,
            )
            db.add(api_key)

            # 4. Meta Account, WhatsApp Number, WhatsApp Template
            meta_account = MetaAccount(
                customer_id=customer.id,
                business_account_id="seed_bba_1001",
                whatsapp_business_account_id="seed_waba_2001",
                access_token_encrypted="encrypted_token_sample",
                status=MetaAccountStatus.ACTIVE,
            )
            db.add(meta_account)
            await db.flush()

            whatsapp_num = WhatsAppNumber(
                meta_account_id=meta_account.id,
                phone_number_id="seed_phone_id_3001",
                display_phone_number="+14155552671",
                verified_name="Acme Official",
                status=WhatsAppNumberStatus.ACTIVE,
            )
            db.add(whatsapp_num)
            await db.flush()

            template = WhatsAppTemplate(
                whatsapp_number_id=whatsapp_num.id,
                meta_template_id="seed_tpl_4001",
                name="otp_auth_v1",
                language_code="en_US",
                category="AUTHENTICATION",
                status=TemplateStatus.APPROVED,
            )
            db.add(template)

            # 5. Pricing Plan & Rules
            plan = PricingPlan(
                name="Enterprise Scale",
                description="High volume enterprise OTP delivery plan",
                monthly_price=99.00,
                status=PlanStatus.ACTIVE,
            )
            db.add(plan)
            await db.flush()

            rule = PricingRule(
                plan_id=plan.id,
                channel=BillingChannel.WHATSAPP,
                country_code="+1",
                price_per_message=1.00,
                currency="USD",
                active=True,
            )
            db.add(rule)

            # 6. Wallet & Transactions
            wallet = Wallet(
                customer_id=customer.id,
                currency="USD",
                balance=500.00,
                status=WalletStatus.ACTIVE,
            )
            db.add(wallet)
            await db.flush()

            tx = WalletTransaction(
                wallet_id=wallet.id,
                transaction_type=WalletTxnType.CREDIT,
                amount=500.00,
                balance_before=0.00,
                balance_after=500.00,
                reference_type="initial_seed",
                reference_id=customer.id,
                description="Initial Enterprise Credit Grant",
            )
            db.add(tx)

            # 7. OTP Request & Verification
            otp_req = OTPRequest(
                customer_id=customer.id,
                application_id=application.id,
                api_key_id=api_key.id,
                request_id="req_seed_otp_8001",
                phone_number="+14155552671",
                otp_hash=hash_otp_code("654321"),
                status=OTPStatus.VERIFIED,
                expires_at=utc_now() + timedelta(minutes=5),
                attempts=1,
                max_attempts=5,
                verified_at=utc_now(),
            )
            db.add(otp_req)
            await db.flush()

            verification = OTPVerification(
                otp_request_id=otp_req.id,
                attempt_number=1,
                result=OTPVerificationResult.CORRECT,
                ip_address="127.0.0.1",
                user_agent="SeedScript/1.0",
            )
            db.add(verification)

            # 8. Messages & Message Events
            msg = Message(
                customer_id=customer.id,
                otp_request_id=otp_req.id,
                whatsapp_number_id=whatsapp_num.id,
                provider="meta",
                provider_message_id="wamid.seed_wamid_9001",
                phone_number="+14155552671",
                message_type=MessageType.AUTHENTICATION,
                status=MessageStatus.DELIVERED,
                sent_at=utc_now(),
                delivered_at=utc_now(),
            )
            db.add(msg)
            await db.flush()

            msg_event = MessageEvent(
                message_id=msg.id,
                event_type=MessageEventType.DELIVERED,
                provider_message_id="wamid.seed_wamid_9001",
                event_data={"status": "delivered"},
            )
            db.add(msg_event)

            # 9. Webhook Events
            wb_event = WebhookEvent(
                provider="meta",
                event_type="delivered",
                external_event_id="wamid.seed_wamid_9001",
                payload={"entry": []},
                processing_status=WebhookProcessingStatus.PROCESSED,
                processed_at=utc_now(),
            )
            db.add(wb_event)

            # 10. Payment Order & Payment
            order = PaymentOrder(
                customer_id=customer.id,
                order_reference="ord_seed_10001",
                amount=500.00,
                currency="USD",
                status=PaymentOrderStatus.PAID,
                provider="stripe",
                provider_order_id="pi_stripe_seed_20001",
            )
            db.add(order)
            await db.flush()

            payment = Payment(
                payment_order_id=order.id,
                provider_payment_id="ch_stripe_seed_30001",
                amount=500.00,
                currency="USD",
                status=PaymentStatus.SUCCESS,
                payment_method="card",
                paid_at=utc_now(),
            )
            db.add(payment)

            # 11. Security (Idempotency & Audit Logs)
            idempotency = IdempotencyKey(
                customer_id=customer.id,
                application_id=application.id,
                idempotency_key="idempotency_key_seed_001",
                endpoint="/v1/otp/send",
                request_hash="seed_request_hash_val",
                response_status=202,
                response_body={"status": "success"},
            )
            db.add(idempotency)

            audit = AuditLog(
                user_id=user.id,
                customer_id=customer.id,
                action="seed.database.initialize",
                resource_type="customer",
                resource_id=customer.id,
                ip_address="127.0.0.1",
                metadata_json={"seeded": True},
            )
            db.add(audit)

            await db.commit()
            logger.info("Phase 2 Database seeding completed successfully!")
        except Exception as e:
            await db.rollback()
            logger.exception(f"Error seeding database: {e}")
            raise


if __name__ == "__main__":
    asyncio.run(seed_database())
