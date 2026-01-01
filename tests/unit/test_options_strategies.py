"""Tests for options trading strategies."""


from quant_vibe.strategies.bullish_vertical_call import BullishVerticalCallStrategy
from quant_vibe.strategies.bullish_vertical_put import BullishVerticalPutStrategy
from quant_vibe.strategies.bollinger_band import BollingerBandStrategy


class TestMaxTradesDaily:
    """Test max_trades_daily functionality for options strategies."""

    def test_default_max_trades_daily(self):
        """Test that default max_trades_daily is 1."""
        strategy_call = BullishVerticalCallStrategy()
        strategy_put = BullishVerticalPutStrategy()

        assert strategy_call.max_trades_daily == 1
        assert strategy_put.max_trades_daily == 1
        assert strategy_call.trades_today == 0
        assert strategy_put.trades_today == 0

    def test_custom_max_trades_daily(self):
        """Test that custom max_trades_daily is set correctly."""
        strategy_call = BullishVerticalCallStrategy(max_trades_daily=3)
        strategy_put = BullishVerticalPutStrategy(max_trades_daily=5)

        assert strategy_call.max_trades_daily == 3
        assert strategy_put.max_trades_daily == 5
        assert strategy_call.trades_today == 0
        assert strategy_put.trades_today == 0

    def test_can_enter_new_position_when_under_limit(self):
        """Test can_enter_new_position returns True when under limit."""
        strategy = BullishVerticalCallStrategy(max_trades_daily=3)

        assert strategy.can_enter_new_position()  # 0 < 3
        strategy.increment_daily_trade_count()
        assert strategy.can_enter_new_position()  # 1 < 3
        strategy.increment_daily_trade_count()
        assert strategy.can_enter_new_position()  # 2 < 3

    def test_can_enter_new_position_when_at_limit(self):
        """Test can_enter_new_position returns False when at limit."""
        strategy = BullishVerticalCallStrategy(max_trades_daily=2)

        strategy.increment_daily_trade_count()
        strategy.increment_daily_trade_count()
        assert strategy.trades_today == 2
        assert not strategy.can_enter_new_position()  # 2 >= 2

    def test_increment_daily_trade_count(self):
        """Test that increment_daily_trade_count increments correctly."""
        strategy = BullishVerticalCallStrategy(max_trades_daily=5)

        assert strategy.trades_today == 0
        strategy.increment_daily_trade_count()
        assert strategy.trades_today == 1
        strategy.increment_daily_trade_count()
        assert strategy.trades_today == 2
        strategy.increment_daily_trade_count()
        assert strategy.trades_today == 3

    def test_reset_daily_state_resets_counter(self):
        """Test that reset_daily_state resets trades_today counter."""
        strategy_call = BullishVerticalCallStrategy(max_trades_daily=3)
        strategy_put = BullishVerticalPutStrategy(max_trades_daily=3)

        # Increment counter
        strategy_call.increment_daily_trade_count()
        strategy_call.increment_daily_trade_count()
        strategy_put.increment_daily_trade_count()

        assert strategy_call.trades_today == 2
        assert strategy_put.trades_today == 1

        # Reset
        strategy_call.reset_daily_state()
        strategy_put.reset_daily_state()

        assert strategy_call.trades_today == 0
        assert strategy_put.trades_today == 0
        assert strategy_call.can_enter_new_position()
        assert strategy_put.can_enter_new_position()

    def test_reset_daily_state_preserves_max_trades_daily(self):
        """Test that reset_daily_state preserves max_trades_daily setting."""
        strategy = BullishVerticalCallStrategy(max_trades_daily=5)

        strategy.increment_daily_trade_count()
        strategy.reset_daily_state()

        assert strategy.max_trades_daily == 5  # Should not change
        assert strategy.trades_today == 0  # Should reset

    def test_multiple_trades_per_day(self):
        """Test that multiple trades can be entered when max_trades_daily > 1."""
        strategy = BullishVerticalCallStrategy(max_trades_daily=3)

        # Simulate entering 3 trades
        for i in range(3):
            assert strategy.can_enter_new_position()
            strategy.increment_daily_trade_count()

        # 4th trade should be blocked
        assert not strategy.can_enter_new_position()

    def test_unlimited_trades_per_day(self):
        """Test that high max_trades_daily value allows many trades."""
        strategy = BullishVerticalCallStrategy(max_trades_daily=999)

        # Simulate entering many trades
        for i in range(100):
            assert strategy.can_enter_new_position()
            strategy.increment_daily_trade_count()

        assert strategy.trades_today == 100
        assert strategy.can_enter_new_position()  # Still under 999

    def test_zero_max_trades_daily(self):
        """Test that max_trades_daily=0 blocks all trades."""
        strategy = BullishVerticalCallStrategy(max_trades_daily=0)

        assert not strategy.can_enter_new_position()  # 0 < 0 is False
        assert strategy.trades_today == 0

    def test_both_strategies_have_independent_counters(self):
        """Test that different strategy instances have independent counters."""
        strategy1 = BullishVerticalCallStrategy(max_trades_daily=2)
        strategy2 = BullishVerticalCallStrategy(max_trades_daily=3)
        strategy3 = BullishVerticalPutStrategy(max_trades_daily=1)

        strategy1.increment_daily_trade_count()
        strategy2.increment_daily_trade_count()
        strategy2.increment_daily_trade_count()

        assert strategy1.trades_today == 1
        assert strategy2.trades_today == 2
        assert strategy3.trades_today == 0

        # Reset only strategy1
        strategy1.reset_daily_state()

        assert strategy1.trades_today == 0
        assert strategy2.trades_today == 2  # Unchanged
        assert strategy3.trades_today == 0  # Unchanged


class TestBollingerBandStrategy:
    """Test BollingerBandStrategy-specific functionality."""

    def test_initialization_with_defaults(self):
        """Test that BollingerBandStrategy initializes with default parameters."""
        strategy = BollingerBandStrategy()

        assert strategy.target_price == 2.0
        assert strategy.buy_limit == 1.0
        assert strategy.sell_target == 2.0
        assert strategy.otm_percent_min == 0.10
        assert strategy.otm_percent_max == 0.15
        assert strategy.price_tolerance == 1.0
        assert strategy.max_trades_daily == 5
        assert strategy.quantity == 10
        assert strategy.min_dte == 0
        assert strategy.max_dte == 45
        assert strategy.profit_target_pct == 1.0
        assert strategy.stop_loss_pct == 0.50
        assert strategy.bb_period == 20
        assert strategy.bb_std == 2.0
        assert strategy.bb_threshold == 0.0

    def test_initialization_with_custom_params(self):
        """Test that BollingerBandStrategy accepts custom parameters."""
        strategy = BollingerBandStrategy(
            target_price=3.0,
            otm_percent_min=0.15,
            otm_percent_max=0.20,
            max_trades_daily=3,
            quantity=5,
            bb_period=30,
            bb_std=3.0,
        )

        assert strategy.target_price == 3.0
        assert strategy.otm_percent_min == 0.15
        assert strategy.otm_percent_max == 0.20
        assert strategy.max_trades_daily == 3
        assert strategy.quantity == 5
        assert strategy.bb_period == 30
        assert strategy.bb_std == 3.0

    def test_get_strategy_name(self):
        """Test that get_strategy_name returns correct name."""
        strategy = BollingerBandStrategy()
        assert strategy.get_strategy_name() == "BollingerBand"

    def test_get_description(self):
        """Test that get_description returns valid description."""
        strategy = BollingerBandStrategy(
            bb_period=20,
            bb_std=2.0,
            otm_percent_min=0.10,
            otm_percent_max=0.15,
            target_price=2.0,
            profit_target_pct=1.0,
            max_trades_daily=5,
        )
        description = strategy.get_description()

        assert "Bollinger Band" in description
        assert "20" in description  # bb_period
        assert "2.0" in description  # bb_std
        assert "10" in description  # 10% OTM min
        assert "15" in description  # 15% OTM max
        assert "$2" in description  # target_price
        assert "100%" in description  # profit_target_pct
        assert "5" in description  # max_trades_daily

    def test_max_trades_daily_enforced(self):
        """Test that max_trades_daily is enforced for BollingerBandStrategy."""
        strategy = BollingerBandStrategy(max_trades_daily=2)

        assert strategy.can_enter_new_position()
        strategy.increment_daily_trade_count()
        assert strategy.can_enter_new_position()
        strategy.increment_daily_trade_count()
        assert not strategy.can_enter_new_position()

    def test_bollinger_parameters_stored(self):
        """Test that Bollinger Band parameters are stored correctly."""
        strategy = BollingerBandStrategy(
            bb_period=50,
            bb_std=1.5,
            bb_threshold=0.05,
        )

        assert strategy.bb_period == 50
        assert strategy.bb_std == 1.5
        assert strategy.bb_threshold == 0.05
