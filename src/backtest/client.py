"""
Client for interacting with the Backtest Service.

This client provides a programmatic interface for the backtest service,
handling HTTP communication and async operations.
"""

import asyncio
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional
import aiohttp
from redis.asyncio import Redis

from quant_vibe.logging import get_logger


logger = get_logger(__name__)


class BacktestClient:
    """
    Client for the Backtest Service.

    This client can operate in two modes:
    1. API Mode: Calls the backtest service via HTTP
    2. Direct Mode: Runs backtests directly (for testing/development)
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        redis_client: Optional[Redis] = None,
        db_connection_string: Optional[str] = None,
        mode: str = "api",
    ):
        """
        Initialize the backtest client.

        Args:
            base_url: Base URL for backtest service (default: from env or http://localhost:8001)
            redis_client: Redis client for direct mode
            db_connection_string: Database connection string for direct mode
            mode: Operation mode ("api" or "direct")
        """
        self.mode = mode

        if mode == "api":
            # API mode - use HTTP calls
            self.base_url = base_url or os.getenv("BACKTEST_SERVICE_URL", "http://localhost:8001")
            if self.base_url.endswith("/"):
                self.base_url = self.base_url[:-1]
        else:
            # Direct mode - use service directly
            self.redis_client = redis_client
            self.db_connection_string = db_connection_string
            self._service = None

    async def _get_service(self):
        """Get or create the direct service instance."""
        if self.mode != "direct":
            raise ValueError("Service only available in direct mode")

        if self._service is None:
            from .service import BacktestService
            self._service = BacktestService(
                redis_client=self.redis_client,
                db_connection_string=self.db_connection_string,
            )
        return self._service

    async def create_backtest(
        self,
        strategy_name: str,
        start_date: datetime,
        end_date: datetime,
        initial_capital: float = 100000.0,
        params: Optional[Dict[str, Any]] = None,
        ticker: str = "$SPX",
        timeframe: str = "5min",
        description: Optional[str] = None,
    ) -> str:
        """
        Create and start a new backtest.

        Args:
            strategy_name: Strategy to backtest
            start_date: Start date
            end_date: End date
            initial_capital: Starting capital
            params: Strategy parameters
            ticker: Ticker symbol
            timeframe: Data timeframe
            description: Optional description

        Returns:
            Backtest ID
        """
        if self.mode == "api":
            # API mode - HTTP call
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/api/backtests"

                payload = {
                    "strategy_name": strategy_name,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "initial_capital": initial_capital,
                    "params": params or {},
                    "ticker": ticker,
                    "timeframe": timeframe,
                    "description": description,
                }

                try:
                    async with session.post(url, json=payload) as resp:
                        resp.raise_for_status()
                        data = await resp.json()
                        return data["backtest_id"]
                except aiohttp.ClientError as e:
                    logger.error(f"Failed to create backtest: {e}")
                    raise
        else:
            # Direct mode
            service = await self._get_service()
            return await service.create_backtest(
                strategy_name=strategy_name,
                start_date=start_date,
                end_date=end_date,
                initial_capital=initial_capital,
                params=params,
                ticker=ticker,
                timeframe=timeframe,
                description=description,
            )

    async def run_backtest(self, backtest_id: str) -> Dict[str, Any]:
        """
        Execute a backtest.

        Args:
            backtest_id: Backtest ID to run

        Returns:
            Backtest results
        """
        if self.mode == "api":
            # API mode - HTTP call
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/api/backtests/{backtest_id}/run"

                try:
                    async with session.post(url) as resp:
                        resp.raise_for_status()
                        return await resp.json()
                except aiohttp.ClientError as e:
                    logger.error(f"Failed to run backtest: {e}")
                    raise
        else:
            # Direct mode
            service = await self._get_service()
            return await service.run_backtest(backtest_id)

    async def get_status(self, backtest_id: str) -> Optional[Dict[str, Any]]:
        """
        Get backtest status.

        Args:
            backtest_id: Backtest ID

        Returns:
            Status dict or None
        """
        if self.mode == "api":
            # API mode - HTTP call
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/api/backtests/{backtest_id}/status"

                try:
                    async with session.get(url) as resp:
                        if resp.status == 404:
                            return None
                        resp.raise_for_status()
                        return await resp.json()
                except aiohttp.ClientError as e:
                    logger.error(f"Failed to get status: {e}")
                    return None
        else:
            # Direct mode
            service = await self._get_service()
            return await service.get_status(backtest_id)

    async def get_results(self, backtest_id: str) -> Optional[Dict[str, Any]]:
        """
        Get backtest results.

        Args:
            backtest_id: Backtest ID

        Returns:
            Results dict or None
        """
        if self.mode == "api":
            # API mode - HTTP call
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/api/backtests/{backtest_id}/results"

                try:
                    async with session.get(url) as resp:
                        if resp.status == 404:
                            return None
                        resp.raise_for_status()
                        return await resp.json()
                except aiohttp.ClientError as e:
                    logger.error(f"Failed to get results: {e}")
                    return None
        else:
            # Direct mode - not implemented for results
            # Results are stored separately
            raise NotImplementedError("Direct mode doesn't support get_results")

    async def list_backtests(
        self,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        List backtests.

        Args:
            status: Filter by status
            limit: Maximum results

        Returns:
            List of backtest metadata
        """
        if self.mode == "api":
            # API mode - HTTP call
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/api/backtests"
                params = {}
                if status:
                    params["status"] = status
                params["limit"] = limit

                try:
                    async with session.get(url, params=params) as resp:
                        resp.raise_for_status()
                        data = await resp.json()
                        return data.get("backtests", [])
                except aiohttp.ClientError as e:
                    logger.error(f"Failed to list backtests: {e}")
                    return []
        else:
            # Direct mode
            service = await self._get_service()
            return await service.list_backtests(status=status, limit=limit)

    async def cancel_backtest(self, backtest_id: str) -> bool:
        """
        Cancel a running backtest.

        Args:
            backtest_id: Backtest ID

        Returns:
            True if cancelled
        """
        if self.mode == "api":
            # API mode - HTTP call
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/api/backtests/{backtest_id}/cancel"

                try:
                    async with session.post(url) as resp:
                        if resp.status == 404:
                            return False
                        resp.raise_for_status()
                        data = await resp.json()
                        return data.get("success", False)
                except aiohttp.ClientError as e:
                    logger.error(f"Failed to cancel backtest: {e}")
                    return False
        else:
            # Direct mode
            service = await self._get_service()
            return await service.cancel_backtest(backtest_id)

    async def wait_for_completion(
        self,
        backtest_id: str,
        timeout: float = 600.0,
        poll_interval: float = 2.0,
    ) -> Dict[str, Any]:
        """
        Wait for a backtest to complete.

        Args:
            backtest_id: Backtest ID
            timeout: Maximum wait time in seconds
            poll_interval: Status check interval in seconds

        Returns:
            Final status

        Raises:
            TimeoutError: If backtest doesn't complete within timeout
        """
        start_time = asyncio.get_event_loop().time()

        while True:
            status = await self.get_status(backtest_id)

            if not status:
                raise ValueError(f"Backtest {backtest_id} not found")

            if status["status"] in ["completed", "failed", "cancelled"]:
                return status

            # Check timeout
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                raise TimeoutError(
                    f"Backtest {backtest_id} did not complete within {timeout} seconds"
                )

            # Wait before next check
            await asyncio.sleep(poll_interval)

    async def create_and_run_backtest(
        self,
        strategy_name: str,
        start_date: datetime,
        end_date: datetime,
        initial_capital: float = 100000.0,
        params: Optional[Dict[str, Any]] = None,
        ticker: str = "$SPX",
        timeframe: str = "5min",
        description: Optional[str] = None,
        wait: bool = True,
        timeout: float = 600.0,
    ) -> Dict[str, Any]:
        """
        Create and run a backtest, optionally waiting for completion.

        Args:
            strategy_name: Strategy to backtest
            start_date: Start date
            end_date: End date
            initial_capital: Starting capital
            params: Strategy parameters
            ticker: Ticker symbol
            timeframe: Data timeframe
            description: Optional description
            wait: Whether to wait for completion
            timeout: Maximum wait time if wait=True

        Returns:
            If wait=True: Final results
            If wait=False: Initial status with backtest_id
        """
        # Create backtest
        backtest_id = await self.create_backtest(
            strategy_name=strategy_name,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            params=params,
            ticker=ticker,
            timeframe=timeframe,
            description=description,
        )

        logger.info(f"Created backtest {backtest_id}")

        # Run backtest
        await self.run_backtest(backtest_id)

        if wait:
            # Wait for completion
            status = await self.wait_for_completion(backtest_id, timeout=timeout)

            if status["status"] == "completed":
                # Get results
                results = await self.get_results(backtest_id)
                if results:
                    return results
                else:
                    logger.warning(f"No results found for completed backtest {backtest_id}")
                    return status
            else:
                return status
        else:
            # Return immediately
            return {"backtest_id": backtest_id, "status": "running"}

    def close(self):
        """Clean up resources."""
        # Nothing to clean up for HTTP client
        pass