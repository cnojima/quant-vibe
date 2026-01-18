"""Data loader for replay service - loads historical bars from TimescaleDB."""

from datetime import datetime
from typing import List, Tuple

from quant_vibe.logging import get_logger
from quant_vibe.data.timescale_store import TimescaleStore
from quant_vibe.models import OptionsBar, UnderlyingBar

logger = get_logger(__name__)


class ReplayDataLoader:
    """Loads historical market data from TimescaleDB for replay."""

    def __init__(self, ts_store: TimescaleStore):
        """Initialize data loader with TimescaleDB connection."""
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

        Returns:
            Tuple of (options_bars, underlying_bars)

        Raises:
            ValueError: If no data found for timeframe
        """
        logger.info(
            f"Loading data from {start_time} to {end_time} "
            f"for {underlying_ticker} (DTE {min_dte}-{max_dte})"
        )

        # Load options bars - always use 1-minute for replay
        options_bars = self.ts_store.get_options_for_backtest(
            start_time,  # Pass positionally as start_date
            end_time,    # Pass positionally as end_date
            underlying_ticker,  # Pass positionally
            min_dte=min_dte,
            max_dte=max_dte,
            timeframe="1min",
        )

        if not options_bars:
            raise ValueError(
                f"No options data found for {underlying_ticker} "
                f"from {start_time} to {end_time}"
            )

        logger.info(f"Loaded {len(options_bars):,} options bars")

        # Load underlying bars with fallback to derived prices
        underlying_bars = self._load_underlying_bars(
            underlying_ticker, start_time, end_time
        )

        logger.info(f"Loaded {len(underlying_bars):,} underlying bars")
        return options_bars, underlying_bars

    def _load_underlying_bars(
        self, ticker: str, start_time: datetime, end_time: datetime
    ) -> List[UnderlyingBar]:
        """Load underlying bars with fallback to options-derived prices."""
        underlying_bars = self.ts_store.get_underlying_bars(
            ticker=ticker,
            start_time=start_time,
            end_time=end_time,
        )

        if underlying_bars:
            return underlying_bars

        # Fallback to derived prices from options
        logger.warning(f"No underlying bars found for {ticker}, using derived prices")

        underlying_bars = self.ts_store.get_underlying_price_from_options(
            underlying_ticker=ticker,
            start_time=start_time,
            end_time=end_time,
        )

        if not underlying_bars:
            raise ValueError(
                "No underlying data found (neither direct bars nor options-derived prices)"
            )

        return underlying_bars

    def get_unique_timestamps(
        self, options_bars: List[OptionsBar], underlying_bars: List[UnderlyingBar]
    ) -> List[datetime]:
        """Get sorted list of unique timestamps from both bar lists."""
        timestamps = {bar.timestamp for bar in options_bars}
        timestamps.update(bar.timestamp for bar in underlying_bars)
        return sorted(timestamps)