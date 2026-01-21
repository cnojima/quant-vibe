"""
Repository layer for backtest database operations.

This module handles all database interactions for the backtest service.
"""

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from decimal import Decimal

from sqlalchemy import create_engine, text, Column, String, Float, Integer, DateTime, JSON, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

from quant_vibe.logging import get_logger
from quant_vibe.utils import now_utc


logger = get_logger(__name__)

Base = declarative_base()


class BacktestTask(Base):
    """SQLAlchemy model for backtest tasks."""

    __tablename__ = "backtest_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    strategy_name = Column(String(100), nullable=False)
    params = Column(JSON, nullable=False)
    status = Column(
        Enum(
            "pending",
            "running",
            "completed",
            "failed",
            "cancelled",
            name="backtest_status",
        ),
        nullable=False,
        default="pending",
    )
    progress = Column(Float, default=0.0)
    ticker = Column(String(20), nullable=False, default="$SPX")
    timeframe = Column(String(10), nullable=False, default="5min")
    start_date = Column(DateTime(timezone=True), nullable=False)
    end_date = Column(DateTime(timezone=True), nullable=False)
    initial_capital = Column(Float, nullable=False)
    description = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=now_utc)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(String(1000), nullable=True)
    result_id = Column(UUID(as_uuid=True), nullable=True)

    # Performance metrics (stored after completion)
    total_return = Column(Float, nullable=True)
    sharpe_ratio = Column(Float, nullable=True)
    max_drawdown = Column(Float, nullable=True)
    win_rate = Column(Float, nullable=True)
    total_trades = Column(Integer, nullable=True)
    profit_factor = Column(Float, nullable=True)


class BacktestRepository:
    """
    Repository for backtest database operations.

    Handles CRUD operations and queries for backtest tasks and results.
    """

    def __init__(self, connection_string: str):
        """
        Initialize repository with database connection.

        Args:
            connection_string: PostgreSQL connection string
        """
        self.engine = create_engine(connection_string)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def create_tables(self):
        """Create database tables if they don't exist."""
        try:
            Base.metadata.create_all(bind=self.engine)
            logger.info("Database tables created successfully")
        except SQLAlchemyError as e:
            logger.error(f"Failed to create database tables: {str(e)}")
            raise

    def create_backtest_task(
        self,
        backtest_id: str,
        strategy_name: str,
        params: Dict[str, Any],
        start_date: datetime,
        end_date: datetime,
        initial_capital: float,
        ticker: str = "$SPX",
        timeframe: str = "5min",
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new backtest task in the database.

        Args:
            backtest_id: Unique backtest identifier
            strategy_name: Strategy to backtest
            params: Strategy parameters
            start_date: Backtest start date
            end_date: Backtest end date
            initial_capital: Initial capital
            ticker: Ticker symbol
            timeframe: Data timeframe
            description: Optional description

        Returns:
            Created backtest task as dictionary
        """
        with self.SessionLocal() as session:
            try:
                task = BacktestTask(
                    id=uuid.UUID(backtest_id),
                    strategy_name=strategy_name,
                    params=params,
                    start_date=start_date,
                    end_date=end_date,
                    initial_capital=initial_capital,
                    ticker=ticker,
                    timeframe=timeframe,
                    description=description,
                    status="pending",
                    progress=0.0,
                    created_at=now_utc(),
                )

                session.add(task)
                session.commit()

                logger.info(f"Created backtest task {backtest_id} in database")

                return self._task_to_dict(task)

            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Failed to create backtest task: {str(e)}")
                raise

    def update_backtest_status(
        self,
        backtest_id: str,
        status: str,
        progress: Optional[float] = None,
        error_message: Optional[str] = None,
    ) -> bool:
        """
        Update backtest task status.

        Args:
            backtest_id: Backtest identifier
            status: New status
            progress: Progress percentage
            error_message: Error message if failed

        Returns:
            True if updated successfully
        """
        with self.SessionLocal() as session:
            try:
                task = session.query(BacktestTask).filter_by(
                    id=uuid.UUID(backtest_id)
                ).first()

                if not task:
                    logger.warning(f"Backtest task {backtest_id} not found")
                    return False

                task.status = status

                if progress is not None:
                    task.progress = progress

                if error_message:
                    task.error_message = error_message

                if status == "running" and task.started_at is None:
                    task.started_at = now_utc()

                if status in ["completed", "failed", "cancelled"]:
                    task.completed_at = now_utc()

                session.commit()

                logger.info(
                    f"Updated backtest {backtest_id} status to {status}",
                    extra={"progress": progress},
                )

                return True

            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Failed to update backtest status: {str(e)}")
                return False

    def get_backtest_task(self, backtest_id: str) -> Optional[Dict[str, Any]]:
        """
        Get backtest task by ID.

        Args:
            backtest_id: Backtest identifier

        Returns:
            Backtest task as dictionary or None if not found
        """
        with self.SessionLocal() as session:
            try:
                task = session.query(BacktestTask).filter_by(
                    id=uuid.UUID(backtest_id)
                ).first()

                if not task:
                    return None

                return self._task_to_dict(task)

            except SQLAlchemyError as e:
                logger.error(f"Failed to get backtest task: {str(e)}")
                return None

    def list_backtest_tasks(
        self,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        List backtest tasks with optional filtering.

        Args:
            status: Filter by status
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            List of backtest tasks as dictionaries
        """
        with self.SessionLocal() as session:
            try:
                query = session.query(BacktestTask)

                if status:
                    query = query.filter_by(status=status)

                query = query.order_by(BacktestTask.created_at.desc())
                query = query.limit(limit).offset(offset)

                tasks = query.all()

                return [self._task_to_dict(task) for task in tasks]

            except SQLAlchemyError as e:
                logger.error(f"Failed to list backtest tasks: {str(e)}")
                return []

    def save_backtest_results(
        self,
        backtest_id: str,
        results: Dict[str, Any],
    ) -> bool:
        """
        Save backtest results to database.

        Args:
            backtest_id: Backtest identifier
            results: Backtest results

        Returns:
            True if saved successfully
        """
        with self.SessionLocal() as session:
            try:
                task = session.query(BacktestTask).filter_by(
                    id=uuid.UUID(backtest_id)
                ).first()

                if not task:
                    logger.warning(f"Backtest task {backtest_id} not found")
                    return False

                # Update performance metrics
                metrics = results.get("metrics", {})
                task.total_return = metrics.get("total_return")
                task.sharpe_ratio = metrics.get("sharpe_ratio")
                task.max_drawdown = metrics.get("max_drawdown")
                task.win_rate = metrics.get("win_rate")
                task.total_trades = metrics.get("total_trades")
                task.profit_factor = metrics.get("profit_factor")

                # Store detailed results in separate table if needed
                # For now, we're storing summary metrics in the task table

                session.commit()

                logger.info(f"Saved results for backtest {backtest_id}")

                return True

            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Failed to save backtest results: {str(e)}")
                return False

    def get_backtest_results(self, backtest_id: str) -> Optional[Dict[str, Any]]:
        """
        Get backtest results by ID.

        Args:
            backtest_id: Backtest identifier

        Returns:
            Backtest results or None if not found
        """
        task = self.get_backtest_task(backtest_id)
        if not task or task["status"] != "completed":
            return None

        # Return the performance metrics
        return {
            "backtest_id": backtest_id,
            "strategy_name": task["strategy_name"],
            "start_date": task["start_date"],
            "end_date": task["end_date"],
            "initial_capital": task["initial_capital"],
            "total_return": task.get("total_return"),
            "sharpe_ratio": task.get("sharpe_ratio"),
            "max_drawdown": task.get("max_drawdown"),
            "win_rate": task.get("win_rate"),
            "total_trades": task.get("total_trades"),
            "profit_factor": task.get("profit_factor"),
        }

    def delete_backtest_task(self, backtest_id: str) -> bool:
        """
        Delete a backtest task.

        Args:
            backtest_id: Backtest identifier

        Returns:
            True if deleted successfully
        """
        with self.SessionLocal() as session:
            try:
                task = session.query(BacktestTask).filter_by(
                    id=uuid.UUID(backtest_id)
                ).first()

                if not task:
                    return False

                session.delete(task)
                session.commit()

                logger.info(f"Deleted backtest task {backtest_id}")

                return True

            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Failed to delete backtest task: {str(e)}")
                return False

    def _task_to_dict(self, task: BacktestTask) -> Dict[str, Any]:
        """Convert BacktestTask ORM object to dictionary."""
        return {
            "id": str(task.id),
            "strategy_name": task.strategy_name,
            "params": task.params,
            "status": task.status,
            "progress": task.progress,
            "ticker": task.ticker,
            "timeframe": task.timeframe,
            "start_date": task.start_date.isoformat() if task.start_date else None,
            "end_date": task.end_date.isoformat() if task.end_date else None,
            "initial_capital": task.initial_capital,
            "description": task.description,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "error_message": task.error_message,
            "total_return": task.total_return,
            "sharpe_ratio": task.sharpe_ratio,
            "max_drawdown": task.max_drawdown,
            "win_rate": task.win_rate,
            "total_trades": task.total_trades,
            "profit_factor": task.profit_factor,
        }

    def cleanup_old_tasks(self, days: int = 30) -> int:
        """
        Clean up old backtest tasks.

        Args:
            days: Delete tasks older than this many days

        Returns:
            Number of tasks deleted
        """
        with self.SessionLocal() as session:
            try:
                cutoff_date = now_utc() - timedelta(days=days)

                deleted = session.query(BacktestTask).filter(
                    BacktestTask.created_at < cutoff_date,
                    BacktestTask.status.in_(["completed", "failed", "cancelled"]),
                ).delete()

                session.commit()

                logger.info(f"Cleaned up {deleted} old backtest tasks")

                return deleted

            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Failed to clean up old tasks: {str(e)}")
                return 0