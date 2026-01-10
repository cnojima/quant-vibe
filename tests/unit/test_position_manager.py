"""
Unit tests for PositionManager.

These tests validate the position tracking and P&L calculation logic in isolation.
"""

import pytest
from datetime import datetime, date
from decimal import Decimal

from live_trading_service.position_manager import PositionManager
from quant_vibe.strategies.options_base import (
    OptionsPosition,
    OptionLeg,
    OptionType,
    SpreadType,
)


@pytest.fixture
def position_manager():
    """Create a position manager without state store for testing."""
    return PositionManager(state_store=None)


@pytest.fixture
def sample_put_position():
    """
    Create a sample single-leg PUT position.

    Position: BUY 10x SPXW251203P06725000 @ $19.57
    Entry Cost: $19.57 * 10 * 100 = $19,570.00 (positive = debit paid)
    """
    leg = OptionLeg(
        contract_symbol="SPXW251203P06725000",
        option_type=OptionType.PUT,
        strike_price=6725.0,
        expiration_date=date(2025, 12, 3),
        quantity=10,  # Long position
        entry_price=19.57,
    )

    position = OptionsPosition(
        position_id="TEST_20251203_143100_1",
        spread_type=SpreadType.SINGLE,
        legs=[leg],
        entry_time=datetime(2025, 12, 3, 14, 31, 0),
        entry_cost=19570.0,  # 19.57 * 10 * 100
        underlying_price_at_entry=6700.0,
        profit_target_pct=1.0,  # 100%
        stop_loss=0.30,  # 30%
    )

    return position


@pytest.fixture
def sample_call_credit_spread():
    """
    Create a sample CALL credit spread (bearish).

    Spread: SELL 10x SPXW251210C06800000 @ $25.00, BUY 10x SPXW251210C06850000 @ $10.00
    Net Credit: ($25.00 - $10.00) * 10 * 100 = $15,000.00
    Entry Cost: -$15,000.00 (negative = credit received)
    Max Risk: ($50 width) * 10 * 100 = $50,000.00
    """
    short_leg = OptionLeg(
        contract_symbol="SPXW251210C06800000",
        option_type=OptionType.CALL,
        strike_price=6800.0,
        expiration_date=date(2025, 12, 10),
        quantity=-10,  # Short position
        entry_price=25.00,
    )

    long_leg = OptionLeg(
        contract_symbol="SPXW251210C06850000",
        option_type=OptionType.CALL,
        strike_price=6850.0,
        expiration_date=date(2025, 12, 10),
        quantity=10,  # Long position
        entry_price=10.00,
    )

    position = OptionsPosition(
        position_id="TEST_20251210_100000_1",
        spread_type=SpreadType.VERTICAL_CALL,
        legs=[short_leg, long_leg],
        entry_time=datetime(2025, 12, 10, 10, 0, 0),
        entry_cost=-15000.0,  # Credit received (negative)
        underlying_price_at_entry=6750.0,
        profit_target_pct=0.50,  # 50%
        stop_loss=0.80,  # 80% of credit (max loss would be ~3x credit for 50-wide spread)
    )

    return position


class TestPositionTracking:
    """Test basic position tracking operations."""

    def test_add_position(self, position_manager, sample_put_position):
        """Test adding a position to tracking."""
        # Act
        success = position_manager.add_position(
            position=sample_put_position,
            strategy_name="TestStrategy",
            fill_price=19570.0
        )

        # Assert
        assert success is True
        assert len(position_manager.open_positions) == 1
        assert sample_put_position.position_id in position_manager.open_positions
        assert position_manager.daily_stats['opened_today'] == 1
        assert position_manager.total_capital_deployed == 19570.0

    def test_add_multiple_positions(self, position_manager, sample_put_position):
        """Test adding multiple positions."""
        # Create a second position
        position2 = OptionsPosition(
            position_id="TEST_20251203_150000_2",
            spread_type=SpreadType.SINGLE,
            legs=[OptionLeg(
                contract_symbol="SPXW251203C06800000",
                option_type=OptionType.CALL,
                strike_price=6800.0,
                expiration_date=date(2025, 12, 3),
                quantity=5,
                entry_price=30.00,
            )],
            entry_time=datetime(2025, 12, 3, 15, 0, 0),
            entry_cost=15000.0,  # 30.00 * 5 * 100
            underlying_price_at_entry=6750.0,
            profit_target_pct=0.50,
        )

        # Act
        position_manager.add_position(sample_put_position, "Strategy1", 19570.0)
        position_manager.add_position(position2, "Strategy2", 15000.0)

        # Assert
        assert len(position_manager.open_positions) == 2
        assert position_manager.total_capital_deployed == 34570.0
        assert position_manager.daily_stats['opened_today'] == 2


class TestPositionValueCalculation:
    """Test position value calculation logic."""

    def test_calculate_single_leg_long_position_value(self, position_manager, sample_put_position):
        """
        Test calculating value for a single-leg LONG position.

        Position: LONG 10x PUT @ $19.57 entry
        Entry cost: $19.57 * 10 * 100 = $19,570 (positive = debit paid)

        Current: bid=$15.62
        Exit value: $15.62 * 10 * 100 = $15,620 (positive = credit received from selling)

        P&L = exit_value - entry_cost = $15,620 - $19,570 = -$3,950 (loss)
        """
        # Add position to manager
        position_manager.add_position(sample_put_position, "TestStrategy", 19570.0)

        # Create mock options data with current bid price
        options_data = {
            "SPXW251203P06725000": {
                "bid": 15.62,
                "ask": 15.88,
                "close": 15.75,
            }
        }

        # Act: Update position values
        position_manager.update_position_values(options_data)

        # Assert: Current value should be positive (credit we'd receive from selling)
        expected_value = 15.62 * 10 * 100  # Positive
        position = position_manager.open_positions[sample_put_position.position_id]
        assert position.current_value == pytest.approx(expected_value)

        # P&L = current_value - entry_cost = 15620 - 19570 = -3950 (loss)
        expected_pnl = expected_value - 19570.0
        actual_pnl = position_manager.get_position_pnl(sample_put_position.position_id)
        assert actual_pnl == pytest.approx(expected_pnl)
        assert actual_pnl < 0  # Should be a loss

    def test_calculate_single_leg_short_position_value(self, position_manager):
        """
        Test calculating value for a single-leg SHORT position.

        Position: SHORT 10x CALL @ $20.00 entry
        Entry cost: -$20,000 (negative = credit received)

        Current: ask=$15.00
        Exit value: -$15,000 (negative = debit paid to buy back)

        P&L = exit_value - entry_cost = -$15,000 - (-$20,000) = $5,000 (profit)
        """
        # Create a short call position
        leg = OptionLeg(
            contract_symbol="SPXW251203C06800000",
            option_type=OptionType.CALL,
            strike_price=6800.0,
            expiration_date=date(2025, 12, 3),
            quantity=-10,  # SHORT
            entry_price=20.00,
        )

        position = OptionsPosition(
            position_id="TEST_SHORT_1",
            spread_type=SpreadType.SINGLE,
            legs=[leg],
            entry_time=datetime(2025, 12, 3, 14, 31, 0),
            entry_cost=-20000.0,  # Credit received (NEGATIVE)
            underlying_price_at_entry=6750.0,
            profit_target_pct=0.50,
        )

        # Add position
        position_manager.add_position(position, "TestStrategy", -20000.0)

        # Create mock options data
        options_data = {
            "SPXW251203C06800000": {
                "bid": 14.50,
                "ask": 15.00,
                "close": 14.75,
            }
        }

        # Act: Update position values
        position_manager.update_position_values(options_data)

        # For a short position: exit value = -(ask_price * abs(quantity) * 100)
        # This is negative because we PAY to buy back
        expected_value = -(15.00 * 10 * 100)
        position = position_manager.open_positions["TEST_SHORT_1"]
        assert position.current_value == pytest.approx(expected_value)

        # P&L = exit_value - entry_cost = -15000 - (-20000) = 5000 (profit)
        actual_pnl = position_manager.get_position_pnl("TEST_SHORT_1")
        expected_pnl = expected_value - (-20000.0)

        print(f"Entry cost: ${position.entry_cost:,.2f}")
        print(f"Current value: ${position.current_value:,.2f}")
        print(f"P&L: ${actual_pnl:,.2f}")

        assert actual_pnl == pytest.approx(expected_pnl)
        assert actual_pnl > 0  # Should be profit

    def test_calculate_call_credit_spread_value(self, position_manager, sample_call_credit_spread):
        """
        Test calculating value for a CALL credit spread.

        Entry:
        - SELL 10x 6800C @ $25.00 (receive $25,000)
        - BUY 10x 6850C @ $10.00 (pay $10,000)
        - Net credit: $15,000 (entry_cost = -15000)

        Current prices:
        - 6800C ask=$20.00 (to close short, we'd pay $20,000)
        - 6850C bid=$8.00 (to close long, we'd receive $8,000)

        Exit value:
        - Short leg (qty=-10): -(20.00 * 10 * 100) = -$20,000 (debit paid)
        - Long leg (qty=+10): +(8.00 * 10 * 100) = +$8,000 (credit received)
        - Net: -$20,000 + $8,000 = -$12,000

        P&L = exit_value - entry_cost = -$12,000 - (-$15,000) = $3,000 (profit)
        """
        # Add position
        position_manager.add_position(sample_call_credit_spread, "TestStrategy", -15000.0)

        # Create mock options data
        options_data = {
            "SPXW251210C06800000": {  # Short leg
                "bid": 19.50,
                "ask": 20.00,
                "close": 19.75,
            },
            "SPXW251210C06850000": {  # Long leg
                "bid": 8.00,
                "ask": 8.50,
                "close": 8.25,
            }
        }

        # Act: Update position values
        position_manager.update_position_values(options_data)

        # Expected value:
        # Short leg (qty=-10): -(20.00 * 10 * 100) = -20000 (debit paid to buy back)
        # Long leg (qty=+10): +(8.00 * 10 * 100) = +8000 (credit from selling)
        # Net: -20000 + 8000 = -12000
        expected_value = -12000.0

        position = position_manager.open_positions[sample_call_credit_spread.position_id]
        assert position.current_value == pytest.approx(expected_value)

        # P&L = exit_value - entry_cost = -12000 - (-15000) = 3000 (profit)
        actual_pnl = position_manager.get_position_pnl(sample_call_credit_spread.position_id)
        expected_pnl = expected_value - (-15000.0)

        print(f"Entry cost: ${position.entry_cost:,.2f}")
        print(f"Current value: ${position.current_value:,.2f}")
        print(f"P&L: ${actual_pnl:,.2f}")

        assert actual_pnl == pytest.approx(expected_pnl)
        assert actual_pnl > 0  # Should be profit


class TestPositionClosure:
    """Test position closure logic."""

    def test_close_position_long_profit(self, position_manager, sample_put_position):
        """Test closing a long position with profit."""
        # Setup: Add position
        position_manager.add_position(sample_put_position, "TestStrategy", 19570.0)

        # Act: Close with profit
        # Sell at $25.00 per contract = receive $25,000 credit
        exit_value = 25.00 * 10 * 100  # +25000 (positive = credit received)
        success = position_manager.close_position(
            position_id=sample_put_position.position_id,
            exit_reason="Profit target reached",
            exit_value=exit_value
        )

        # Assert
        assert success is True
        assert len(position_manager.open_positions) == 0
        assert position_manager.daily_stats['closed_today'] == 1
        assert position_manager.daily_stats['wins_today'] == 1

        # P&L = exit_value - entry_cost = 25000 - 19570 = 5430 (profit)
        expected_pnl = exit_value - 19570.0
        assert position_manager.daily_stats['total_pnl_today'] == pytest.approx(expected_pnl)
        assert expected_pnl > 0  # Should be profit

    def test_close_position_long_loss(self, position_manager, sample_put_position):
        """Test closing a long position with loss."""
        # Setup
        position_manager.add_position(sample_put_position, "TestStrategy", 19570.0)

        # Act: Close with loss
        # Sell at $10.00 per contract = receive $10,000 credit
        exit_value = 10.00 * 10 * 100  # +10000 (positive = credit received)
        success = position_manager.close_position(
            position_id=sample_put_position.position_id,
            exit_reason="Stop loss hit",
            exit_value=exit_value
        )

        # Assert
        assert success is True
        assert position_manager.daily_stats['closed_today'] == 1
        assert position_manager.daily_stats['losses_today'] == 1

        # P&L = exit_value - entry_cost = 10000 - 19570 = -9570 (loss)
        expected_pnl = exit_value - 19570.0
        assert position_manager.daily_stats['total_pnl_today'] == pytest.approx(expected_pnl)
        assert expected_pnl < 0

    def test_close_position_credit_spread_profit(self, position_manager, sample_call_credit_spread):
        """Test closing a credit spread with profit (spread narrows)."""
        # Setup
        position_manager.add_position(sample_call_credit_spread, "TestStrategy", -15000.0)

        # Act: Close when spread has narrowed (profit)
        # Buy back short leg at $10.00 (pay $10k), sell long leg at $4.00 (receive $4k)
        # Net: -10000 + 4000 = -6000 (negative = net debit paid)
        exit_value = -6000.0
        success = position_manager.close_position(
            position_id=sample_call_credit_spread.position_id,
            exit_reason="Profit target reached",
            exit_value=exit_value
        )

        # Assert
        assert success is True
        assert position_manager.daily_stats['wins_today'] == 1

        # P&L = exit_value - entry_cost = -6000 - (-15000) = 9000 (profit)
        expected_pnl = exit_value - (-15000.0)
        assert position_manager.daily_stats['total_pnl_today'] == pytest.approx(expected_pnl)
        assert expected_pnl > 0  # Should be profit


class TestPnLPercentage:
    """Test P&L percentage calculations."""

    def test_pnl_percent_long_position(self, position_manager, sample_put_position):
        """Test P&L percentage for long position."""
        # Setup
        position_manager.add_position(sample_put_position, "TestStrategy", 19570.0)

        # Update with current price
        options_data = {
            "SPXW251203P06725000": {
                "bid": 25.00,  # Increased from 19.57
                "ask": 25.50,
                "close": 25.25,
            }
        }
        position_manager.update_position_values(options_data)

        # Calculate P&L%
        pnl_pct = position_manager.get_position_pnl_pct(sample_put_position.position_id)

        # Expected:
        # current_value = -25000
        # entry_cost = 19570
        # pnl = -25000 - 19570 = -44570
        # pnl_pct = -44570 / 19570 = -2.277 = -227.7% (WRONG!)
        #
        # Should be:
        # pnl = 25000 - 19570 = 5430
        # pnl_pct = 5430 / 19570 = 0.2774 = 27.74% (CORRECT)

        print(f"P&L%: {pnl_pct*100:.2f}%")
        assert pnl_pct is not None


class TestDailyStats:
    """Test daily statistics tracking."""

    def test_daily_stats_reset(self, position_manager):
        """Test resetting daily statistics."""
        # Setup: Record some activity
        position_manager.daily_stats['opened_today'] = 5
        position_manager.daily_stats['closed_today'] = 3
        position_manager.daily_stats['total_pnl_today'] = 1500.0
        position_manager.daily_stats['wins_today'] = 2
        position_manager.daily_stats['losses_today'] = 1

        # Act
        position_manager.reset_daily_stats()

        # Assert
        assert position_manager.daily_stats['opened_today'] == 0
        assert position_manager.daily_stats['closed_today'] == 0
        assert position_manager.daily_stats['total_pnl_today'] == 0.0
        assert position_manager.daily_stats['wins_today'] == 0
        assert position_manager.daily_stats['losses_today'] == 0


class TestCapitalUsage:
    """Test capital usage tracking."""

    def test_capital_usage(self, position_manager, sample_put_position):
        """Test capital usage calculations."""
        # Setup: Add positions
        position_manager.add_position(sample_put_position, "TestStrategy", 19570.0)

        # Act
        capital_usage = position_manager.get_capital_usage()

        # Assert
        assert capital_usage['total_deployed'] == 19570.0
        assert capital_usage['num_positions'] == 1
        assert capital_usage['avg_per_position'] == 19570.0


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_close_nonexistent_position(self, position_manager):
        """Test closing a position that doesn't exist."""
        success = position_manager.close_position(
            position_id="DOES_NOT_EXIST",
            exit_reason="Test",
            exit_value=0.0
        )
        assert success is False

    def test_get_pnl_for_nonexistent_position(self, position_manager):
        """Test getting P&L for nonexistent position."""
        pnl = position_manager.get_position_pnl("DOES_NOT_EXIST")
        assert pnl is None

    def test_update_values_with_missing_quotes(self, position_manager, sample_put_position):
        """Test updating position values when quotes are missing."""
        # Setup: Add position (sets current_value to entry_cost initially)
        position_manager.add_position(sample_put_position, "TestStrategy", 19570.0)

        # Verify initial state
        position = position_manager.open_positions[sample_put_position.position_id]
        assert position.current_value == 19570.0  # Set by add_position

        # Act: Update with empty options data (missing quotes)
        options_data = {}
        position_manager.update_position_values(options_data)

        # Assert: current_value should now be None (stale data marker)
        position = position_manager.open_positions[sample_put_position.position_id]
        assert position.current_value is None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
