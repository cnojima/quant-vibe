"""Data loader for replay service - loads historical bars from TimescaleDB."""

import logging
from datetime import datetime
from typing import List, Tuple

from quant_vibe.data.timescale_store import TimescaleStore
from quant_vibe.models import OptionsBar, UnderlyingBar


logger = logging.getLogger(__name__)


class ReplayDataLoader:
    """Loads historical market data from TimescaleDB for replay."""

    def __init__(self, ts_store: TimescaleStore):
        """Initialize data loader.

        Args:
            ts_store: TimescaleDB connection
        """
        self.ts_store = ts_store

    def load_bars(
        self,
        start_time: datetime,
        end_time: datetime,
        underlying_ticker: str = "SPX",
        min_dte: int = 0,
        max_dte: int = 45,
    ) -> Tuple[List[OptionsBar], List[UnderlyingBar]]:
        """Load options and underlying bars for the specified timeframe.

        Args:
            start_time: Start time (UTC)
            end_time: End time (UTC)
            underlying_ticker: Underlying ticker (default: SPX)
            min_dte: Minimum days to expiration (default: 0)
            max_dte: Maximum days to expiration (default: 45)

        Returns:
            Tuple of (options_bars, underlying_bars)

        Raises:
            ValueError: If no data found for timeframe
        """
        logger.info(f"Loading data from {start_time} to {end_time}...")
        logger.info(f"  Underlying: {underlying_ticker}")
        logger.info(f"  DTE range: {min_dte} - {max_dte}")

        # Load options bars
        options_bars = self.ts_store.get_options_for_backtest(
            underlying_ticker=underlying_ticker,
            start_time=start_time,
            end_time=end_time,
            min_dte=min_dte,
            max_dte=max_dte,
            timeframe="1min",  # Always use 1-minute for replay (matches streaming)
        )

        if not options_bars:
            raise ValueError(
                f"No options data found for {underlying_ticker} "
                f"from {start_time} to {end_time}"
            )

        logger.info(f"  ✓ Loaded {len(options_bars):,} options bars")

        # Load underlying bars
        underlying_bars = self.ts_store.get_underlying_bars(
            ticker=underlying_ticker,
            start_time=start_time,
            end_time=end_time,
        )

        if not underlying_bars:
            logger.warning(
                f"No underlying bars found for {underlying_ticker}, "
                f"falling back to derived prices from options..."
            )

            # Fallback: derive from options
            underlying_bars = self.ts_store.get_underlying_price_from_options(
                underlying_ticker=underlying_ticker,
                start_time=start_time,
                end_time=end_time,
            )

            if not underlying_bars:
                raise ValueError(
                    f"No underlying data found (neither underlying_bars table "
                    f"nor options-derived prices)"
                )

        logger.info(f"  ✓ Loaded {len(underlying_bars):,} underlying bars")

        return options_bars, underlying_bars

    def get_unique_timestamps(
        self, options_bars: List[OptionsBar], underlying_bars: List[UnderlyingBar]
    ) -> List[datetime]:
        """Get sorted list of unique timestamps from both bar lists.

        Args:
            options_bars: List of options bars
            underlying_bars: List of underlying bars

        Returns:
            Sorted list of unique timestamps
        """
        timestamps = set()

        for bar in options_bars:
            timestamps.add(bar.timestamp)

        for bar in underlying_bars:
            timestamps.add(bar.timestamp)

        return sorted(timestamps)
