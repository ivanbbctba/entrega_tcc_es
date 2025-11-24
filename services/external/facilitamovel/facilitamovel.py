from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import os
import requests


@dataclass(frozen=True)
class FacilitaMovelConfig:
    user: str
    password: str
    hash_seguranca: str
    base_url: str = "https://www.facilitamovel.com.br/api"
    timeout: int = 30


class FacilitaMovelError(Exception):
    """Raised for Facilita Móvel specific API errors."""


class FacilitaMovelClient:
    def __init__(self, config: FacilitaMovelConfig):
        if not config.user or not config.password or not config.hash_seguranca:
            raise ValueError("User, password, and hash_seguranca are required")
        self.user = config.user
        self.password = config.password
        self.hash_seguranca = config.hash_seguranca
        self.base_url = config.base_url.rstrip("/")
        self.timeout = config.timeout

    def _get_headers(self) -> Dict[str, str]:
        return {
            "user": self.user,
            "password": self.password,
            "hashSeguranca": self.hash_seguranca,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _request(
            self,
            endpoint: str,
            method: str = "POST",
            payload: Optional[Dict[str, Any]] = None,
    ) -> Any:
        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers()
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                json=payload or {},
                timeout=self.timeout,
            )
            response.raise_for_status()
            if not response.text.strip():
                return {}
            return response.json()
        except requests.RequestException as e:
            raise FacilitaMovelError(f"API request failed: {str(e)}") from e
        except ValueError as e:
            raise FacilitaMovelError(
                f"Invalid JSON response: {str(e)}. Body: {response.text if 'response' in locals() else 'No response'}") from e

    def send_sms(
            self,
            to: str,
            message: str,
            external_key: Optional[str] = None,
            schedule_at: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Send a single SMS message.

        Args:
            to: Recipient phone number (e.g., "+5541991710901")
            message: The message text
            external_key: Optional custom key for tracking (sent in payload as "externalkey")
            schedule_at: Optional datetime for scheduling the message

        Returns:
            Dict with 'success', 'protocol' (smsid), and 'raw' response

        Note: external_key is sent in the JSON payload because the API requires it in the request body.
        """
        endpoint = "/simpleSendJson.ft"
        payload = {"phone": to, "message": message}
        if external_key:
            payload["externalkey"] = external_key
        if schedule_at:
            payload.update(
                {
                    "day": schedule_at.strftime("%d"),
                    "month": schedule_at.strftime("%m"),
                    "year": schedule_at.strftime("%Y"),
                    "hour": schedule_at.strftime("%H"),
                    "minute": schedule_at.strftime("%M"),
                }
            )
        data = self._request(endpoint, payload=payload)
        success = data.get("result", "").lower() == "success" and data.get("code") in ("1", "2")
        protocol = data.get("smsid")
        return {"success": success, "protocol": protocol, "raw": data}

    def send_bulk(self, messages: List[Tuple[str, str]]) -> Dict[str, Any]:
        if not messages:
            raise ValueError("Messages list cannot be empty")
        endpoint = "/multipleSendJson.ft"
        payload = {"messages": [{"phone": to, "message": msg} for to, msg in messages]}
        data = self._request(endpoint, payload=payload)
        success = data.get("result", "").lower() == "success" and data.get("code") in ("1", "2")
        accepted_ids = data.get("sms-ids-aceitos", [])
        return {
            "success": success,
            "count": len(messages),
            "accepted": len(accepted_ids),
            "invalid": data.get("total-invalidos"),
            "accepted_ids": accepted_ids,
            "raw": data,
        }

    def get_message_status(
            self, protocol: Optional[str] = None, external_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get the status of a sent message.

        Args:
            protocol: The smsid returned from send_sms (optional if using external_key)
            external_key: The custom key used when sending (optional if using protocol)

        Returns:
            Dict with 'success', 'status', and 'raw' response

        Note: If using external_key, it's sent in the payload as {"externalkeys": [{"key": external_key}]}
        because the API requires it in the request body for querying by key.
        """
        if not (protocol or external_key):
            raise ValueError("Either protocol or external_key is required")
        if protocol:
            endpoint = "/dlrStatusJson.ft"
            payload = {"smsid": protocol}
        else:
            endpoint = "/dlrByExternalKeyJson.ft"
            payload = {"externalkeys": [{"key": external_key}]}
        data = self._request(endpoint, payload=payload)
        if not data:
            return {"success": False, "status": None, "raw": "No data returned (possibly no message found)"}
        if isinstance(data, list):
            data = data[0] if data else {}
        success = data.get("result", "").lower() == "success"
        status = data.get("status")
        return {"success": success, "status": status, "raw": data}

    def get_balance(self) -> Dict[str, Any]:
        endpoint = "/checkCreditJson.ft"
        data = self._request(endpoint)
        success = data.get("result", "").lower() == "success"
        return {
            "success": success,
            "balance": data.get("credits"),
            "expires_at": data.get("date-expires"),
            "raw": data,
        }

    def list_received(self) -> Dict[str, Any]:
        endpoint = "/readMOJson.ft"
        data = self._request(endpoint)
        if isinstance(data, list):
            return {"success": True, "messages": data, "raw": data}
        success = data.get("result", "").lower() == "success"
        return {"success": success, "raw": data}

    def cancel_scheduled(self, protocol: str) -> Dict[str, Any]:
        endpoint = "/deleteMsgAgendadasPorIdJson.ft"
        payload = {"smsids": [{"smsid": protocol}]}
        data = self._request(endpoint, payload=payload)
        success = data.get("result", "").lower() == "success"
        return {"success": success, "raw": data}

    def ping(self) -> bool:
        try:
            data = self._request("/checkCreditJson.ft")
            return data.get("result", "").lower() == "success"
        except FacilitaMovelError:
            return False


def _load_env_from_example() -> None:
    if os.environ.get("_FACILITAMOVEL_ENV_LOADED") == "1":
        return
    current_dir = os.path.abspath(os.path.dirname(__file__))
    while current_dir != os.path.dirname(current_dir):
        for env_file in [".env", ".env.example"]:
            path = os.path.join(current_dir, env_file)
            if os.path.isfile(path):
                with open(path, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if "=" in line:
                            key, value = line.split("=", 1)
                            key = key.strip()
                            value = value.strip().strip('"').strip("'")
                            if key and key not in os.environ:
                                os.environ[key] = value
                os.environ["_FACILITAMOVEL_ENV_LOADED"] = "1"
                return
        current_dir = os.path.dirname(current_dir)


def load_config_from_env() -> FacilitaMovelConfig:
    _load_env_from_example()
    user = os.getenv("FACILITA_MOVEL_USER")
    password = os.getenv("FACILITA_MOVEL_PASSWORD")
    hash_seguranca = os.getenv("FACILITA_MOVEL_HASH")
    base_url = os.getenv("FACILITA_MOVEL_BASE_URL", "https://www.facilitamovel.com.br/api")
    timeout = int(os.getenv("FACILITA_MOVEL_TIMEOUT", "30"))
    if not user or not password or not hash_seguranca:
        raise ValueError(
            "FACILITA_MOVEL_USER, FACILITA_MOVEL_PASSWORD, and FACILITA_MOVEL_HASH must be set (check .env.example)")
    return FacilitaMovelConfig(
        user=user,
        password=password,
        hash_seguranca=hash_seguranca,
        base_url=base_url,
        timeout=timeout,
    )


def test_all_functions():
    config = load_config_from_env()
    client = FacilitaMovelClient(config)

    # Test ping
    ping_result = client.ping()
    print("Ping result:", ping_result)

    # Test get_balance
    balance = client.get_balance()
    print("Balance:", balance)

    # Test list_received
    received = client.list_received()
    print("Received messages:", received)

    # Test send_sms with external_key (use numeric string as per API examples)
    external_key = "12345"
    send_result = client.send_sms(
        to="+5541991710901",
        message="Test message from FacilitaMovelClient",
        external_key=external_key
    )
    print("Send SMS result:", send_result)
    protocol = send_result.get("protocol")

    # Test get_message_status with protocol
    if protocol:
        status_by_protocol = client.get_message_status(protocol=protocol)
        print("Message status by protocol:", status_by_protocol)

    # Test get_message_status with external_key
    status_by_key = client.get_message_status(external_key=external_key)
    print("Message status by external_key:", status_by_key)

    # Test send_bulk
    bulk_messages = [("+5541991710901", "Test bulk message 1"), ("+5541991710901", "Test bulk message 2")]
    bulk_result = client.send_bulk(bulk_messages)
    print("Bulk send result:", bulk_result)

    # Test scheduled send and cancel
    schedule_at = datetime.now() + timedelta(minutes=10)
    sched_result = client.send_sms(to="+5541991710901", message="Test scheduled message", schedule_at=schedule_at)
    print("Scheduled send result:", sched_result)
    sched_protocol = sched_result.get("protocol")
    if sched_protocol:
        cancel_result = client.cancel_scheduled(sched_protocol)
        print("Cancel scheduled result:", cancel_result)

    # Return True if all major operations succeeded, for test passing
    all_success = (
            ping_result and
            balance.get("success", False) and
            received.get("success", False) and
            send_result.get("success", False) and
            bulk_result.get("success", False) and
            (not sched_protocol or cancel_result.get("success", False))
    )
    return all_success


if __name__ == "__main__":
    test_all_functions()