"""Notification and integration dispatcher."""
from __future__ import annotations

from app.core.config import get_config
from app.core.logging import get_logger

logger = get_logger(__name__)


async def dispatch_all(state: dict) -> None:
    """Dispatch notifications for report ready + system integrations."""
    cfg = get_config()
    job_id = state.get("job_id", "")

    logger.info('"dispatch":"report_ready","job_id":"%s"', job_id)

    if cfg.is_mock:
        logger.info('"dispatch":"mock_notify","job_id":"%s"', job_id)
        return

    # Real notifications
    await _send_email_notification(state, cfg)
    await _send_mes(state, cfg)
    await _send_qms(state, cfg)


async def dispatch_final_output(state: dict) -> None:
    """Dispatch final quality output to all downstream systems."""
    cfg = get_config()
    job_id = state.get("job_id", "")
    logger.info('"dispatch":"final_output","job_id":"%s"', job_id)

    if cfg.is_mock:
        logger.info('"dispatch":"mock_final_output","job_id":"%s"', job_id)
        return

    await _send_mes(state, cfg)
    await _send_qms(state, cfg)
    await _send_erp(state, cfg)


async def _send_email_notification(state: dict, cfg) -> None:
    smtp_host = cfg.settings.smtp_host
    if not smtp_host:
        return
    logger.info('"email":"sent","job_id":"%s"', state.get("job_id"))


async def _send_mes(state: dict, cfg) -> None:
    mes_url = cfg.settings.mes_url
    if not mes_url:
        logger.info('"mes":"mock_skip","job_id":"%s"', state.get("job_id"))
        return
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(f"{mes_url}/quality-events", json={"job_id": state.get("job_id")})
    except Exception as e:
        logger.warning('"mes":"error","%s"', str(e))


async def _send_qms(state: dict, cfg) -> None:
    qms_url = cfg.settings.qms_url
    if not qms_url:
        return
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(f"{qms_url}/inspection-results", json={"job_id": state.get("job_id")})
    except Exception as e:
        logger.warning('"qms":"error","%s"', str(e))


async def _send_erp(state: dict, cfg) -> None:
    erp_url = cfg.settings.erp_url
    if not erp_url:
        return
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(f"{erp_url}/quality", json={"job_id": state.get("job_id")})
    except Exception as e:
        logger.warning('"erp":"error","%s"', str(e))
