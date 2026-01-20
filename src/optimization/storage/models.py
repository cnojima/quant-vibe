"""
SQLAlchemy models for optimization storage.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column, String, Integer, Float, DateTime, Text, Boolean,
    JSON, Index, ForeignKey, UniqueConstraint
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship


Base = declarative_base()


class OptimizationRun(Base):
    """Model for optimization run metadata."""

    __tablename__ = "optimization_runs"

    optimization_id = Column(String, primary_key=True)
    strategy_name = Column(String, nullable=False)
    optimization_type = Column(String, default="grid_search")
    status = Column(String, default="pending")  # pending, running, completed, failed, cancelled

    # Date ranges
    train_start_date = Column(DateTime, nullable=False)
    train_end_date = Column(DateTime, nullable=False)
    test_start_date = Column(DateTime, nullable=True)
    test_end_date = Column(DateTime, nullable=True)

    # Configuration
    initial_capital = Column(Float, default=100000)
    underlying_ticker = Column(String, default="SPX")
    timeframe = Column(String, default="5min")

    # Parameter grids (JSON)
    param_grid = Column(JSON, nullable=False)
    fixed_params = Column(JSON, nullable=True)

    # Progress tracking
    total_combinations = Column(Integer, nullable=False)
    progress_current = Column(Integer, default=0)
    progress_total = Column(Integer, default=0)
    estimated_completion_time = Column(DateTime, nullable=True)

    # Results summary
    best_params = Column(JSON, nullable=True)
    best_sharpe_ratio = Column(Float, nullable=True)
    best_total_return = Column(Float, nullable=True)
    best_win_rate = Column(Float, nullable=True)
    best_max_drawdown = Column(Float, nullable=True)

    # File paths
    results_csv_path = Column(String, nullable=True)
    results_json_path = Column(String, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Error tracking
    error_message = Column(Text, nullable=True)
    error_traceback = Column(Text, nullable=True)

    # Relationships
    results = relationship("OptimizationResult", back_populates="optimization_run")

    # Indexes
    __table_args__ = (
        Index("idx_optimization_status", "status"),
        Index("idx_optimization_created", "created_at"),
        Index("idx_optimization_strategy", "strategy_name"),
    )


class OptimizationResult(Base):
    """Model for individual optimization results."""

    __tablename__ = "optimization_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    optimization_id = Column(String, ForeignKey("optimization_runs.optimization_id"))
    combination_index = Column(Integer, nullable=False)

    # Parameters (JSON for flexibility)
    parameters = Column(JSON, nullable=False)

    # Performance metrics
    sharpe_ratio = Column(Float, nullable=True)
    total_return = Column(Float, nullable=True)
    annualized_return = Column(Float, nullable=True)
    win_rate = Column(Float, nullable=True)
    profit_factor = Column(Float, nullable=True)
    max_drawdown = Column(Float, nullable=True)
    total_trades = Column(Integer, nullable=True)
    winning_trades = Column(Integer, nullable=True)
    losing_trades = Column(Integer, nullable=True)
    avg_win = Column(Float, nullable=True)
    avg_loss = Column(Float, nullable=True)
    largest_win = Column(Float, nullable=True)
    largest_loss = Column(Float, nullable=True)
    max_consecutive_wins = Column(Integer, nullable=True)
    max_consecutive_losses = Column(Integer, nullable=True)

    # Walk-forward specific
    train_sharpe_ratio = Column(Float, nullable=True)
    train_total_return = Column(Float, nullable=True)
    test_sharpe_ratio = Column(Float, nullable=True)
    test_total_return = Column(Float, nullable=True)

    # Additional metrics (JSON for extensibility)
    additional_metrics = Column(JSON, nullable=True)

    # Rankings
    sharpe_rank = Column(Integer, nullable=True)
    return_rank = Column(Integer, nullable=True)
    win_rate_rank = Column(Integer, nullable=True)

    # Timestamp
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    optimization_run = relationship("OptimizationRun", back_populates="results")

    # Indexes and constraints
    __table_args__ = (
        UniqueConstraint("optimization_id", "combination_index"),
        Index("idx_result_optimization", "optimization_id"),
        Index("idx_result_sharpe", "sharpe_ratio"),
        Index("idx_result_return", "total_return"),
        Index("idx_result_win_rate", "win_rate"),
    )


class OptimizationCacheStatus(Base):
    """Model for tracking cache usage."""

    __tablename__ = "optimization_cache_status"

    cache_key = Column(String, primary_key=True)
    underlying_ticker = Column(String, nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    timeframe = Column(String, nullable=False)

    # Data statistics
    num_options_rows = Column(Integer, nullable=False)
    num_underlying_rows = Column(Integer, nullable=False)
    data_size_mb = Column(Float, nullable=False)

    # Usage statistics
    hit_count = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_accessed_at = Column(DateTime, default=datetime.utcnow)

    # Indexes
    __table_args__ = (
        Index("idx_cache_ticker", "underlying_ticker"),
        Index("idx_cache_accessed", "last_accessed_at"),
    )