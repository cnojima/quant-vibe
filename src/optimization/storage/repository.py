"""
Database repository for optimization data.

Handles all database operations for optimization runs and results.
"""

import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import create_engine, text, desc, asc
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError

from quant_vibe.logging import get_logger
from quant_vibe.utils import now_utc

from .models import Base, OptimizationRun, OptimizationResult, OptimizationCacheStatus


logger = get_logger(__name__)


class OptimizationRepository:
    """Repository for optimization database operations."""

    def __init__(self, db_connection_string: str):
        """Initialize repository.

        Args:
            db_connection_string: PostgreSQL connection string
        """
        self.engine = create_engine(db_connection_string)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self._executor = ThreadPoolExecutor(max_workers=4)

    async def create_optimization_run(
        self,
        optimization_id: str,
        strategy_name: str,
        param_grid: Dict[str, List[Any]],
        train_start_date: datetime,
        train_end_date: datetime,
        total_combinations: int,
        optimization_type: str = "grid_search",
        test_start_date: Optional[datetime] = None,
        test_end_date: Optional[datetime] = None,
        initial_capital: float = 100000.0,
        fixed_params: Optional[Dict[str, Any]] = None,
        underlying_ticker: str = "SPX",
        timeframe: str = "5min",
    ) -> bool:
        """Create a new optimization run record (async wrapper).

        Args:
            optimization_id: Unique optimization ID
            strategy_name: Strategy name
            param_grid: Parameter grid
            train_start_date: Training start date
            train_end_date: Training end date
            total_combinations: Total parameter combinations
            optimization_type: Type of optimization
            test_start_date: Test start date (walk-forward)
            test_end_date: Test end date (walk-forward)
            initial_capital: Initial capital
            fixed_params: Fixed parameters
            underlying_ticker: Underlying ticker
            timeframe: Data timeframe

        Returns:
            True if created successfully
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self._create_optimization_run_sync,
            optimization_id,
            strategy_name,
            param_grid,
            train_start_date,
            train_end_date,
            total_combinations,
            optimization_type,
            test_start_date,
            test_end_date,
            initial_capital,
            fixed_params,
            underlying_ticker,
            timeframe,
        )

    def _create_optimization_run_sync(
        self,
        optimization_id: str,
        strategy_name: str,
        param_grid: Dict[str, List[Any]],
        train_start_date: datetime,
        train_end_date: datetime,
        total_combinations: int,
        optimization_type: str = "grid_search",
        test_start_date: Optional[datetime] = None,
        test_end_date: Optional[datetime] = None,
        initial_capital: float = 100000.0,
        fixed_params: Optional[Dict[str, Any]] = None,
        underlying_ticker: str = "SPX",
        timeframe: str = "5min",
    ) -> bool:
        """Create a new optimization run record.

        Args:
            optimization_id: Unique optimization ID
            strategy_name: Strategy name
            param_grid: Parameter grid
            train_start_date: Training start date
            train_end_date: Training end date
            total_combinations: Total parameter combinations
            optimization_type: Type of optimization
            test_start_date: Test start date (walk-forward)
            test_end_date: Test end date (walk-forward)
            initial_capital: Initial capital
            fixed_params: Fixed parameters
            underlying_ticker: Underlying ticker
            timeframe: Data timeframe

        Returns:
            True if created successfully
        """
        try:
            with self.SessionLocal() as session:
                optimization_run = OptimizationRun(
                    optimization_id=optimization_id,
                    strategy_name=strategy_name,
                    optimization_type=optimization_type,
                    status="pending",
                    train_start_date=train_start_date,
                    train_end_date=train_end_date,
                    test_start_date=test_start_date,
                    test_end_date=test_end_date,
                    initial_capital=initial_capital,
                    underlying_ticker=underlying_ticker,
                    timeframe=timeframe,
                    param_grid=param_grid,
                    fixed_params=fixed_params,
                    total_combinations=total_combinations,
                    created_at=now_utc(),
                )

                session.add(optimization_run)
                session.commit()

                logger.info(f"[Repository] Created optimization run: {optimization_id}")
                return True

        except SQLAlchemyError as e:
            logger.error(f"[Repository] Error creating optimization run: {e}")
            raise  # Re-raise to let caller handle with full error details

    async def update_optimization_status(
        self,
        optimization_id: str,
        status: str,
        error_message: Optional[str] = None,
    ) -> bool:
        """Update optimization status (async wrapper).

        Args:
            optimization_id: Optimization ID
            status: New status
            error_message: Error message if failed

        Returns:
            True if updated successfully
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self._update_optimization_status_sync,
            optimization_id,
            status,
            error_message,
        )

    def _update_optimization_status_sync(
        self,
        optimization_id: str,
        status: str,
        error_message: Optional[str] = None,
    ) -> bool:
        """Update optimization status.

        Args:
            optimization_id: Optimization ID
            status: New status
            error_message: Error message if failed

        Returns:
            True if updated successfully
        """
        try:
            with self.SessionLocal() as session:
                optimization = session.query(OptimizationRun).filter_by(
                    optimization_id=optimization_id
                ).first()

                if not optimization:
                    logger.error(f"[Repository] Optimization {optimization_id} not found")
                    return False

                optimization.status = status
                optimization.updated_at = now_utc()

                if status == "running" and not optimization.started_at:
                    optimization.started_at = now_utc()
                elif status in ["completed", "failed", "cancelled"]:
                    optimization.completed_at = now_utc()

                if error_message:
                    optimization.error_message = error_message

                session.commit()

                logger.info(f"[Repository] Updated optimization {optimization_id} status to {status}")
                return True

        except SQLAlchemyError as e:
            logger.error(f"[Repository] Error updating optimization status: {e}")
            return False

    async def update_optimization_progress(
        self,
        optimization_id: str,
        progress_current: int,
        progress_total: int,
        estimated_completion_time: Optional[datetime] = None,
    ) -> bool:
        """Update optimization progress (async wrapper).

        Args:
            optimization_id: Optimization ID
            progress_current: Current combination
            progress_total: Total combinations
            estimated_completion_time: ETA

        Returns:
            True if updated successfully
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self._update_optimization_progress_sync,
            optimization_id,
            progress_current,
            progress_total,
            estimated_completion_time,
        )

    def _update_optimization_progress_sync(
        self,
        optimization_id: str,
        progress_current: int,
        progress_total: int,
        estimated_completion_time: Optional[datetime] = None,
    ) -> bool:
        """Update optimization progress.

        Args:
            optimization_id: Optimization ID
            progress_current: Current combination
            progress_total: Total combinations
            estimated_completion_time: ETA

        Returns:
            True if updated successfully
        """
        try:
            with self.SessionLocal() as session:
                optimization = session.query(OptimizationRun).filter_by(
                    optimization_id=optimization_id
                ).first()

                if not optimization:
                    return False

                optimization.progress_current = progress_current
                optimization.progress_total = progress_total
                optimization.estimated_completion_time = estimated_completion_time
                optimization.updated_at = now_utc()

                session.commit()
                return True

        except SQLAlchemyError as e:
            logger.error(f"[Repository] Error updating progress: {e}")
            return False

    async def save_optimization_results(
        self,
        optimization_id: str,
        results: List[Dict[str, Any]],
    ) -> int:
        """Save optimization results to database (async wrapper).

        Args:
            optimization_id: Optimization ID
            results: List of result dictionaries

        Returns:
            Number of results saved
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self._save_optimization_results_sync,
            optimization_id,
            results,
        )

    def _save_optimization_results_sync(
        self,
        optimization_id: str,
        results: List[Dict[str, Any]],
    ) -> int:
        """Save optimization results to database.

        Args:
            optimization_id: Optimization ID
            results: List of result dictionaries

        Returns:
            Number of results saved
        """
        try:
            with self.SessionLocal() as session:
                saved = 0

                for i, result in enumerate(results):
                    # Extract metrics
                    optimization_result = OptimizationResult(
                        optimization_id=optimization_id,
                        combination_index=i,
                        parameters={k: v for k, v in result.items()
                                  if not k.startswith("_") and k not in [
                                      "sharpe_ratio", "total_return", "win_rate",
                                      "profit_factor", "max_drawdown", "total_trades",
                                      "winning_trades", "losing_trades", "avg_win",
                                      "avg_loss", "largest_win", "largest_loss",
                                      "max_consecutive_wins", "max_consecutive_losses",
                                      "train_sharpe_ratio", "train_total_return",
                                      "test_sharpe_ratio", "test_total_return",
                                      "timestamp"
                                  ]},
                        sharpe_ratio=self._to_float(result.get("sharpe_ratio")),
                        total_return=self._to_float(result.get("total_return")),
                        annualized_return=self._to_float(result.get("annualized_return")),
                        win_rate=self._to_float(result.get("win_rate")),
                        profit_factor=self._to_float(result.get("profit_factor")),
                        max_drawdown=self._to_float(result.get("max_drawdown")),
                        total_trades=self._to_int(result.get("total_trades")),
                        winning_trades=self._to_int(result.get("winning_trades")),
                        losing_trades=self._to_int(result.get("losing_trades")),
                        avg_win=self._to_float(result.get("avg_win")),
                        avg_loss=self._to_float(result.get("avg_loss")),
                        largest_win=self._to_float(result.get("largest_win")),
                        largest_loss=self._to_float(result.get("largest_loss")),
                        max_consecutive_wins=self._to_int(result.get("max_consecutive_wins")),
                        max_consecutive_losses=self._to_int(result.get("max_consecutive_losses")),
                        train_sharpe_ratio=self._to_float(result.get("train_sharpe_ratio")),
                        train_total_return=self._to_float(result.get("train_total_return")),
                        test_sharpe_ratio=self._to_float(result.get("test_sharpe_ratio")),
                        test_total_return=self._to_float(result.get("test_total_return")),
                        created_at=now_utc(),
                    )

                    session.add(optimization_result)
                    saved += 1

                session.commit()

                logger.info(f"[Repository] Saved {saved} results for {optimization_id}")
                return saved

        except SQLAlchemyError as e:
            logger.error(f"[Repository] Error saving results: {e}")
            return 0

    async def update_best_results(
        self,
        optimization_id: str,
        best_params: Dict[str, Any],
        best_sharpe_ratio: float,
        best_total_return: float,
        best_win_rate: float,
        best_max_drawdown: float,
    ) -> bool:
        """Update best results for an optimization (async wrapper).

        Args:
            optimization_id: Optimization ID
            best_params: Best parameter combination
            best_sharpe_ratio: Best Sharpe ratio
            best_total_return: Best total return
            best_win_rate: Best win rate
            best_max_drawdown: Best max drawdown

        Returns:
            True if updated successfully
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self._update_best_results_sync,
            optimization_id,
            best_params,
            best_sharpe_ratio,
            best_total_return,
            best_win_rate,
            best_max_drawdown,
        )

    def _update_best_results_sync(
        self,
        optimization_id: str,
        best_params: Dict[str, Any],
        best_sharpe_ratio: float,
        best_total_return: float,
        best_win_rate: float,
        best_max_drawdown: float,
    ) -> bool:
        """Update best results for an optimization.

        Args:
            optimization_id: Optimization ID
            best_params: Best parameter combination
            best_sharpe_ratio: Best Sharpe ratio
            best_total_return: Best total return
            best_win_rate: Best win rate
            best_max_drawdown: Best max drawdown

        Returns:
            True if updated successfully
        """
        try:
            with self.SessionLocal() as session:
                optimization = session.query(OptimizationRun).filter_by(
                    optimization_id=optimization_id
                ).first()

                if not optimization:
                    return False

                optimization.best_params = best_params
                optimization.best_sharpe_ratio = best_sharpe_ratio
                optimization.best_total_return = best_total_return
                optimization.best_win_rate = best_win_rate
                optimization.best_max_drawdown = best_max_drawdown
                optimization.updated_at = now_utc()

                session.commit()
                return True

        except SQLAlchemyError as e:
            logger.error(f"[Repository] Error updating best results: {e}")
            return False

    async def compute_rankings(self, optimization_id: str) -> bool:
        """Compute rankings for optimization results (async wrapper).

        Args:
            optimization_id: Optimization ID

        Returns:
            True if rankings computed successfully
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self._compute_rankings_sync,
            optimization_id,
        )

    def _compute_rankings_sync(self, optimization_id: str) -> bool:
        """Compute rankings for optimization results.

        Args:
            optimization_id: Optimization ID

        Returns:
            True if rankings computed successfully
        """
        try:
            with self.SessionLocal() as session:
                # Get all results for this optimization
                results = session.query(OptimizationResult).filter_by(
                    optimization_id=optimization_id
                ).all()

                # Sort by Sharpe ratio and assign ranks
                sorted_by_sharpe = sorted(results, key=lambda x: x.sharpe_ratio or 0, reverse=True)
                for rank, result in enumerate(sorted_by_sharpe, 1):
                    result.sharpe_rank = rank

                # Sort by total return and assign ranks
                sorted_by_return = sorted(results, key=lambda x: x.total_return or 0, reverse=True)
                for rank, result in enumerate(sorted_by_return, 1):
                    result.return_rank = rank

                # Sort by win rate and assign ranks
                sorted_by_winrate = sorted(results, key=lambda x: x.win_rate or 0, reverse=True)
                for rank, result in enumerate(sorted_by_winrate, 1):
                    result.win_rate_rank = rank

                session.commit()

                logger.info(f"[Repository] Computed rankings for {optimization_id}")
                return True

        except SQLAlchemyError as e:
            logger.error(f"[Repository] Error computing rankings: {e}")
            return False

    async def get_optimization_status(self, optimization_id: str) -> Optional[Dict[str, Any]]:
        """Get optimization status (async wrapper).

        Args:
            optimization_id: Optimization ID

        Returns:
            Status dictionary or None
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self._get_optimization_status_sync,
            optimization_id,
        )

    def _get_optimization_status_sync(self, optimization_id: str) -> Optional[Dict[str, Any]]:
        """Get optimization status.

        Args:
            optimization_id: Optimization ID

        Returns:
            Status dictionary or None
        """
        try:
            with self.SessionLocal() as session:
                optimization = session.query(OptimizationRun).filter_by(
                    optimization_id=optimization_id
                ).first()

                if not optimization:
                    return None

                return {
                    "optimization_id": optimization.optimization_id,
                    "status": optimization.status,
                    "strategy_name": optimization.strategy_name,
                    "optimization_type": optimization.optimization_type,
                    "param_grid": optimization.param_grid,
                    "fixed_params": optimization.fixed_params,
                    "train_start_date": optimization.train_start_date,
                    "train_end_date": optimization.train_end_date,
                    "test_start_date": optimization.test_start_date,
                    "test_end_date": optimization.test_end_date,
                    "initial_capital": optimization.initial_capital,
                    "underlying_ticker": optimization.underlying_ticker,
                    "timeframe": optimization.timeframe,
                    "total_combinations": optimization.total_combinations,
                    "progress_current": optimization.progress_current,
                    "progress_total": optimization.progress_total,
                    "estimated_completion_time": optimization.estimated_completion_time.isoformat()
                        if optimization.estimated_completion_time else None,
                    "started_at": optimization.started_at.isoformat()
                        if optimization.started_at else None,
                    "completed_at": optimization.completed_at.isoformat()
                        if optimization.completed_at else None,
                    "error_message": optimization.error_message,
                    "best_params": optimization.best_params,
                    "best_sharpe_ratio": optimization.best_sharpe_ratio,
                    "best_total_return": optimization.best_total_return,
                    "best_win_rate": optimization.best_win_rate,
                }

        except SQLAlchemyError as e:
            logger.error(f"[Repository] Error getting optimization status: {e}")
            return None

    async def get_optimization_results(
        self,
        optimization_id: str,
        limit: int = 100,
        sort_by: str = "sharpe_ratio",
    ) -> List[Dict[str, Any]]:
        """Get optimization results (async wrapper).

        Args:
            optimization_id: Optimization ID
            limit: Maximum number of results
            sort_by: Sort column

        Returns:
            List of result dictionaries
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self._get_optimization_results_sync,
            optimization_id,
            limit,
            sort_by,
        )

    def _get_optimization_results_sync(
        self,
        optimization_id: str,
        limit: int = 100,
        sort_by: str = "sharpe_ratio",
    ) -> List[Dict[str, Any]]:
        """Get optimization results.

        Args:
            optimization_id: Optimization ID
            limit: Maximum number of results
            sort_by: Sort column

        Returns:
            List of result dictionaries
        """
        try:
            with self.SessionLocal() as session:
                query = session.query(OptimizationResult).filter_by(
                    optimization_id=optimization_id
                )

                # Apply sorting
                if sort_by == "sharpe_ratio":
                    query = query.order_by(desc(OptimizationResult.sharpe_ratio))
                elif sort_by == "total_return":
                    query = query.order_by(desc(OptimizationResult.total_return))
                elif sort_by == "win_rate":
                    query = query.order_by(desc(OptimizationResult.win_rate))

                # Apply limit
                query = query.limit(limit)

                results = []
                for result in query.all():
                    result_dict = {
                        **result.parameters,
                        "sharpe_ratio": result.sharpe_ratio,
                        "total_return": result.total_return,
                        "win_rate": result.win_rate,
                        "profit_factor": result.profit_factor,
                        "max_drawdown": result.max_drawdown,
                        "total_trades": result.total_trades,
                        "sharpe_rank": result.sharpe_rank,
                        "return_rank": result.return_rank,
                        "win_rate_rank": result.win_rate_rank,
                    }
                    results.append(result_dict)

                return results

        except SQLAlchemyError as e:
            logger.error(f"[Repository] Error getting results: {e}")
            return []

    def get_all_optimizations(
        self,
        status_filter: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get all optimization runs.

        Args:
            status_filter: Optional status filter
            limit: Maximum number of runs

        Returns:
            List of optimization run dictionaries
        """
        try:
            with self.SessionLocal() as session:
                query = session.query(OptimizationRun)

                if status_filter:
                    query = query.filter_by(status=status_filter)

                query = query.order_by(desc(OptimizationRun.created_at)).limit(limit)

                runs = []
                for run in query.all():
                    runs.append({
                        "optimization_id": run.optimization_id,
                        "status": run.status,
                        "total_combinations": run.total_combinations,
                        "progress_current": run.progress_current,
                        "created_at": run.created_at.isoformat(),
                        "started_at": run.started_at.isoformat() if run.started_at else None,
                        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                        # Nested request object for frontend compatibility
                        "request": {
                            "strategy_name": run.strategy_name,
                            "optimization_type": run.optimization_type,
                            "train_start_date": run.train_start_date.isoformat() if run.train_start_date else None,
                            "train_end_date": run.train_end_date.isoformat() if run.train_end_date else None,
                            "test_start_date": run.test_start_date.isoformat() if run.test_start_date else None,
                            "test_end_date": run.test_end_date.isoformat() if run.test_end_date else None,
                        },
                    })

                return runs

        except SQLAlchemyError as e:
            logger.error(f"[Repository] Error getting all optimizations: {e}")
            return []

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        """Convert value to float, handling Decimal and None."""
        if value is None:
            return None
        if isinstance(value, Decimal):
            return float(value)
        return float(value)

    @staticmethod
    def _to_int(value: Any) -> Optional[int]:
        """Convert value to int, handling None."""
        if value is None:
            return None
        return int(value)