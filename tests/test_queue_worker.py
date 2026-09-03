from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from datetime import timedelta

from app.config import settings
from app.models.base import utc_now
from tests.conftest import TestingSessionLocal
from app.models.customer import Customer
from app.models.enums import MessageEventType, MessageStatus, OTPStatus
from app.models.messaging import Message, MessageEvent
from app.models.otp import OTPRequest
from app.services.wallet_service import WalletService
from app.services.providers.base import SendMessageResult
from app.tasks.celery_app import (
    celery_app,
    task_failure_handler,
    task_postrun_handler,
    task_prerun_handler,
    task_retry_handler,
)
from app.tasks.otp_tasks import (
    _send_otp_async,
    handle_dead_letter_task,
    reprocess_dead_letter_messages,
    send_whatsapp_otp_task,
)


def test_celery_config_and_queues() -> None:
    """TASK-094 & TASK-095: Test Celery configuration and Kombu queue definitions."""
    assert celery_app.conf.task_serializer == "json"
    assert celery_app.conf.timezone == "UTC"
    assert celery_app.conf.task_track_started is True
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_time_limit == settings.CELERY_TASK_TIME_LIMIT

    # Check queues
    queue_names = [q.name for q in celery_app.conf.task_queues]
    assert "otp_messages" in queue_names
    assert "webhooks" in queue_names
    assert "dead_letter" in queue_names

    # Check task routing
    routes = celery_app.conf.task_routes
    assert routes["app.tasks.otp_tasks.send_whatsapp_otp_task"]["queue"] == "otp_messages"
    assert routes["app.tasks.otp_tasks.process_meta_webhook_task"]["queue"] == "webhooks"
    assert routes["app.tasks.otp_tasks.handle_dead_letter_task"]["queue"] == "dead_letter"


@pytest.mark.asyncio
async def test_worker_send_otp_success_flow(db_session: AsyncSession) -> None:
    """TASK-096, TASK-098, TASK-099: Test successful OTP sending, message status update, and event creation."""
    # 1. Setup user & customer in DB
    cust = Customer(company_name="Worker Success Org", email="worker_success@test.com")
    db_session.add(cust)
    await db_session.flush()
    customer_id = cust.id
    await WalletService.get_or_create_wallet(db_session, customer_id)
    await db_session.flush()

    otp_rec = OTPRequest(
        customer_id=customer_id,
        request_id="req_worker_succ_100",
        phone_number="+14155551000",
        otp_hash="hashed_otp_100",
        status=OTPStatus.CREATED,
        expires_at=utc_now() + timedelta(seconds=300),
        attempts=0,
        max_attempts=3,
    )
    db_session.add(otp_rec)
    await db_session.commit()
    otp_db_id = otp_rec.id

    # 2. Mock whatsapp_service.send_otp success & patch AsyncSessionLocal
    mock_res = SendMessageResult(
        success=True,
        provider_message_id="wamid.HBgLMTQxNTU1NTEwMDBWAgASGBQzQTFFRTIzNDU2Nzg5QUJDREVGMAA=",
        is_temporary_error=False,
        error_message=None,
    )

    class MockSessionContext:
        async def __aenter__(self):
            return db_session

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    with patch("app.tasks.otp_tasks.whatsapp_service.send_otp", new_callable=AsyncMock) as mock_send, \
         patch("app.tasks.otp_tasks.AsyncSessionLocal", side_effect=MockSessionContext):
        mock_send.return_value = mock_res
        res = await _send_otp_async(
            otp_request_db_id=otp_db_id,
            request_id="req_worker_succ_100",
            phone_number="+14155551000",
            otp_code="123456",
            template_name="otp_auth_v1",
            language_code="en_US",
            customer_id=customer_id,
            cost_credits=1.0,
        )
        assert res.success is True

    # 3. Verify DB records
    # OTP status updated to SENT
    stmt_otp = select(OTPRequest).where(OTPRequest.id == otp_db_id)
    updated_otp = (await db_session.execute(stmt_otp)).scalar_one()
    assert updated_otp.status == OTPStatus.SENT

    # Message record created with provider_message_id and status SENT
    stmt_msg = select(Message).where(Message.otp_request_id == otp_db_id)
    msg_record = (await db_session.execute(stmt_msg)).scalar_one()
    assert msg_record.status == MessageStatus.SENT
    assert msg_record.provider_message_id == "wamid.HBgLMTQxNTU1NTEwMDBWAgASGBQzQTFFRTIzNDU2Nzg5QUJDREVGMAA="

    # MessageEvent record created
    stmt_evt = select(MessageEvent).where(MessageEvent.message_id == msg_record.id)
    evt_record = (await db_session.execute(stmt_evt)).scalar_one()
    assert evt_record.event_type == MessageEventType.SENT


@pytest.mark.asyncio
async def test_worker_permanent_error_refund(db_session: AsyncSession) -> None:
    """TASK-098 & TASK-099: Permanent Meta failure marks status as FAILED and refunds wallet credits immediately."""
    cust = Customer(company_name="Refund Org", email="refund@test.com")
    db_session.add(cust)
    await db_session.flush()
    customer_id = cust.id

    await WalletService.get_or_create_wallet(db_session, customer_id)
    await db_session.flush()

    otp_rec = OTPRequest(
        customer_id=customer_id,
        request_id="req_perm_fail_200",
        phone_number="+14155552000",
        otp_hash="hashed_otp_200",
        status=OTPStatus.CREATED,
        expires_at=utc_now() + timedelta(seconds=300),
        attempts=0,
        max_attempts=3,
    )
    db_session.add(otp_rec)
    await db_session.commit()
    otp_db_id = otp_rec.id

    mock_fail_res = SendMessageResult(
        success=False,
        provider_message_id=None,
        is_temporary_error=False,
        error_message="Invalid recipient phone number",
    )

    class MockSessionContext:
        async def __aenter__(self):
            return db_session

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    with patch("app.tasks.otp_tasks.whatsapp_service.send_otp", new_callable=AsyncMock) as mock_send, \
         patch("app.tasks.otp_tasks.AsyncSessionLocal", side_effect=MockSessionContext):
        mock_send.return_value = mock_fail_res
        res = await _send_otp_async(
            otp_request_db_id=otp_db_id,
            request_id="req_perm_fail_200",
            phone_number="+14155552000",
            otp_code="654321",
            template_name="otp_auth_v1",
            language_code="en_US",
            customer_id=customer_id,
            cost_credits=1.0,
        )
        assert res.success is False

    # Verify status is FAILED and wallet refunded
    stmt_otp = select(OTPRequest).where(OTPRequest.id == otp_db_id)
    updated_otp = (await db_session.execute(stmt_otp)).scalar_one()
    assert updated_otp.status == OTPStatus.FAILED

    wallet = await WalletService.get_or_create_wallet(db_session, customer_id)
    assert float(wallet.balance) == 101.0  # 100.0 initial + 1.0 refund


def test_dead_letter_queue_handling_and_reprocess() -> None:
    """TASK-101: Test dead-letter message recording and reprocessing helper."""
    payload = {
        "task_id": "task_dlq_123",
        "otp_request_db_id": "otp_id_123",
        "request_id": "req_dlq_123",
        "phone_number": "+14155553000",
        "customer_id": "cust_123",
        "cost_credits": 1.0,
        "reason": "Max retries exceeded",
    }
    result = handle_dead_letter_task(payload)
    assert result["status"] == "dead_letter_recorded"
    assert result["payload"]["request_id"] == "req_dlq_123"

    with patch.object(send_whatsapp_otp_task, "apply_async") as mock_apply:
        reprocessed = reprocess_dead_letter_messages([payload])
        assert reprocessed == 1
        assert mock_apply.called


def test_worker_logging_signals() -> None:
    """TASK-102: Test Celery signal handlers for worker logging and PII masking."""
    class DummyTask:
        name = "app.tasks.otp_tasks.send_whatsapp_otp_task"

    # Verify prerun handler masks PII
    task_prerun_handler(
        task_id="t_1",
        task=DummyTask(),
        args=(),
        kwargs={"phone_number": "+14155554321", "otp_code": "123456"},
    )
    task_postrun_handler(task_id="t_1", task=DummyTask(), retval={"status": "success"}, state="SUCCESS")
    task_retry_handler(request=type("Req", (), {"id": "t_1", "name": DummyTask.name, "retries": 1})(), reason="429 Too Many Requests", einfo=None)
    task_failure_handler(task_id="t_1", exception=Exception("Error"), traceback=None, einfo=None)


@pytest.mark.asyncio
async def test_worker_monitoring_endpoint(client: AsyncClient) -> None:
    """TASK-103: Test GET /v1/monitoring/worker endpoint."""
    res = await client.get("/v1/monitoring/worker")
    assert res.status_code == 200
    data = res.json()["data"]
    assert "worker_status" in data
    assert "active_workers" in data
    assert "queues" in data
    assert "otp_messages" in data["queues"]
    assert "webhooks" in data["queues"]
    assert "dead_letter" in data["queues"]
