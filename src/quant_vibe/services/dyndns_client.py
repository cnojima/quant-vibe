"""
Sonic.net DynDNS Client

Manages dynamic DNS updates using Sonic.net's DynDNS API.
API Documentation: https://public-api.sonic.net/dyndns
"""

import json
import requests
from typing import Optional
from quant_vibe.logging import get_logger

logger = get_logger(__name__)


class SonicDynDNSClient:
    """Client for Sonic.net DynDNS API."""

    def __init__(
        self,
        userid: str,
        apikey: str,
        hostname: str,
        api_base_url: str = "https://public-api.sonic.net/dyndns",
    ):
        """
        Initialize Sonic.net DynDNS client.

        Args:
            userid: Sonic.net user ID
            apikey: Sonic.net API key for DynDNS
            hostname:
            api_base_url: Base URL for Sonic.net DynDNS API
        """
        self.userid = userid
        self.apikey = apikey
        self.hostname = hostname
        self.api_base_url = api_base_url.rstrip("/")
        self.session = requests.Session()
        self.last_ip: Optional[str] = None

    def ping(self) -> bool:
        """
        Test API connectivity.

        Returns:
            True if API is reachable, False otherwise
        """
        try:
            response = self.session.get(f"{self.api_base_url}/ping", timeout=10)
            response.raise_for_status()
            data = response.json()
            if data.get("result") == 200 and data.get("message") == "PONG":
                logger.debug("API ping successful")
                return True
            logger.warning(f"Unexpected ping response: {data}")
            return False
        except Exception as e:
            logger.error(f"API ping failed: {e}")
            return False

    def get_current_ip(self) -> Optional[str]:
        """
        Get current public IP address from Sonic.net API.

        Returns:
            IP address as string, or None if failed
        """
        try:
            response = self.session.get(f"{self.api_base_url}/ip", timeout=10)
            response.raise_for_status()
            data = response.json()
            ip = data.get("ip")
            if ip:
                logger.debug(f"Current public IP: {ip}")
                return ip
            logger.warning(f"No IP in response: {data}")
            return None
        except Exception as e:
            logger.error(f"Failed to get current IP: {e}")
            return None

    def update_host_record(
        self,
        record_type: str = "A",
        value: Optional[str] = None,
        ttl: int = 300,
    ) -> bool:
        """
        Update DNS host record.

        Args:
            record_type: DNS record type (A, AAAA, TXT)
            value: IP address or value to set. If None, uses current public IP
            ttl: Time-to-live in seconds (default: 300)

        Returns:
            True if update successful, False otherwise
        """
        # Get current IP if value not provided
        if value is None:
            value = self.get_current_ip()
            if value is None:
                logger.error("Cannot update host record: failed to get current IP")
                return False

        # Prepare request data
        data = {
            "userid": self.userid,
            "apikey": self.apikey,
            "hostname": self.hostname,
            "type": record_type,
            "value": value,
            "ttl": ttl,
        }

        try:
            response = self.session.put(
                f"{self.api_base_url}/host",
                json=data,
                timeout=10,
            )
            response.raise_for_status()
            result = response.json()

            if result.get("result") == 200:
                logger.info(
                    f"Successfully updated {self.hostname} ({record_type}) to {value}"
                )
                self.last_ip = value
                return True
            else:
                logger.error(f"Update failed: {result.get('message', 'Unknown error')}")
                return False

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error updating host record: {e}")
            if e.response is not None:
                try:
                    error_data = e.response.json()
                    logger.error(f"Error details: {error_data}")
                except json.JSONDecodeError:
                    logger.error(f"Response text: {e.response.text}")
            return False
        except Exception as e:
            logger.error(f"Failed to update host record: {e}")
            return False

    def needs_update(self) -> tuple[bool, Optional[str]]:
        """
        Check if DNS record needs updating.

        Returns:
            Tuple of (needs_update: bool, current_ip: Optional[str])
        """
        current_ip = self.get_current_ip()
        if current_ip is None:
            logger.warning("Cannot check if update needed: failed to get current IP")
            return False, None

        needs_update = current_ip != self.last_ip
        if needs_update:
            logger.info(
                f"IP change detected: {self.last_ip or 'unknown'} -> {current_ip}"
            )
        else:
            logger.debug(f"IP unchanged: {current_ip}")

        return needs_update, current_ip

    def force_update(self, record_type: str = "A", ttl: int = 300) -> bool:
        """
        Force DNS record update regardless of current IP.

        Args:
            record_type: DNS record type (A, AAAA, TXT)
            ttl: Time-to-live in seconds

        Returns:
            True if update successful, False otherwise
        """
        logger.info(f"Forcing DNS update for {self.hostname}")
        return self.update_host_record(record_type=record_type, ttl=ttl)

    def update_if_changed(self, record_type: str = "A", ttl: int = 300) -> bool:
        """
        Update DNS record only if IP address has changed.

        Args:
            record_type: DNS record type (A, AAAA, TXT)
            ttl: Time-to-live in seconds

        Returns:
            True if update was performed (or not needed), False if update failed
        """
        needs_update, current_ip = self.needs_update()

        if not needs_update:
            logger.debug("No update needed")
            return True

        if current_ip is None:
            return False

        return self.update_host_record(
            record_type=record_type, value=current_ip, ttl=ttl
        )

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.session.close()
