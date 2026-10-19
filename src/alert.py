"""
Reactions to a FAIL verdict.

send_esp32_alert() is real: once the ESP32-CAM is flashed with this
project's firmware (Phase 3), it drives the LED + buzzer via a plain
HTTP GET to /alert.

send_plc_fail_signal() is explicitly OUT OF SCOPE for this demo. It is a
stub that only logs what it would do - there is no PLC/SCADA/OPC
integration here, and this function must never be changed to claim
otherwise without actually building and testing that integration.
"""
from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)


def send_esp32_alert(esp32_base_url: str, state: bool, timeout: float = 2.0) -> bool:
    """
    GETs {esp32_base_url}/alert?state=0|1 to drive the ESP32-CAM's LED/buzzer.
    Returns True on success, False on any network failure (logged, not raised) -
    a flaky Wi-Fi link to one board shouldn't crash the demo.
    """
    url = f"{esp32_base_url.rstrip('/')}/alert"
    try:
        resp = requests.get(url, params={"state": int(state)}, timeout=timeout)
        resp.raise_for_status()
        return True
    except requests.RequestException as exc:
        logger.warning("ESP32 alert call failed (%s): %s", url, exc)
        return False


def send_plc_fail_signal(*_args, **_kwargs) -> None:
    """
    STUB - out of scope for this demo. Does not talk to any PLC/SCADA/OPC
    system. Only logs what a real integration would have done.
    """
    logger.info("[STUB] would send FAIL signal to PLC (no real PLC/SCADA/OPC integration exists)")
