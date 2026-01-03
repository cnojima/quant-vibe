"""
Unit tests for Pydantic models.

Tests verify:
- Model validation rules
- Timestamp UTC awareness
- Symbol normalization
- OHLCV constraints
- Serialization/deserialization
- Helper methods
"""

import pytest
from datetime import datetime, date, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo
from pydantic import ValidationError

from quant_vibe.models import OptionsBar, UnderlyingBar, Trade
from quant_vibe.utils import now_utc


class TestOptionsBar:
    """Test OptionsBar model validation and behavior"""

    @pytest.fixture
    def valid_options_bar_data(self):
        """Create valid options bar data"""
        return {
            "timestamp": now_utc(),
            "contract_symbol": "SPXW260123P06860000",
            "underlying_ticker": "SPX",
            "strike_price": Decimal("6860.00"),
            "contract_type": "put",
            "expiration_date": date(2026, 1, 23),
            "open": Decimal("10.20"),
            "high": Decimal("10.80"),
            "low": Decimal("10.00"),
            "close": Decimal("10.50"),
            "volume": 100,
            "bid": Decimal("10.40"),
            "ask": Decimal("10.60"),
            "mark": Decimal("10.50"),
        }

    def test_create_valid_options_bar(self, valid_options_bar_data):
        """Test creating valid options bar"""
        bar = OptionsBar(**valid_options_bar_data)

        assert bar.contract_symbol == "SPXW260123P06860000"
        assert bar.strike_price == Decimal("6860.00")
        assert bar.contract_type == "put"
        assert bar.volume == 100

    def test_timestamp_must_be_utc_aware(self, valid_options_bar_data):
        """Test that naive timestamps are rejected"""
        # Naive timestamp should be rejected
        valid_options_bar_data["timestamp"] = datetime(2026, 1, 2, 14, 30)

        with pytest.raises(ValidationError, match="naive"):
            OptionsBar(**valid_options_bar_data)

    def test_timestamp_conversion_from_aware(self, valid_options_bar_data):
        """Test that UTC-aware timestamps are accepted"""
        # UTC-aware timestamp
        valid_options_bar_data["timestamp"] = datetime(2026, 1, 2, 14, 30, tzinfo=ZoneInfo("UTC"))

        bar = OptionsBar(**valid_options_bar_data)

        # Should remain UTC-aware
        assert bar.timestamp.tzinfo == ZoneInfo("UTC")

    def test_symbol_normalization(self, valid_options_bar_data):
        """Test that symbols are normalized"""
        # With spaces (Schwab format)
        valid_options_bar_data["contract_symbol"] = "SPXW  260123P06860000"

        bar = OptionsBar(**valid_options_bar_data)

        # Should be normalized (no spaces)
        assert bar.contract_symbol == "SPXW260123P06860000"
        assert " " not in bar.contract_symbol

    def test_contract_type_lowercase(self, valid_options_bar_data):
        """Test that contract type must be lowercase"""
        # Pydantic Literal is strict - uppercase is rejected
        valid_options_bar_data["contract_type"] = "PUT"

        with pytest.raises(ValidationError):
            OptionsBar(**valid_options_bar_data)

    def test_high_must_be_gte_low(self, valid_options_bar_data):
        """Test that high must be >= low"""
        valid_options_bar_data["high"] = Decimal("9.00")
        valid_options_bar_data["low"] = Decimal("10.00")

        with pytest.raises(ValidationError, match=r"(High|must be >= low)"):
            OptionsBar(**valid_options_bar_data)

    def test_high_must_be_gte_open(self, valid_options_bar_data):
        """Test that high must be >= open"""
        valid_options_bar_data["high"] = Decimal("9.00")
        valid_options_bar_data["open"] = Decimal("10.00")

        with pytest.raises(ValidationError, match=r"(High|must be >= open)"):
            OptionsBar(**valid_options_bar_data)

    def test_high_must_be_gte_close(self, valid_options_bar_data):
        """Test that high must be >= close"""
        valid_options_bar_data["high"] = Decimal("9.00")
        valid_options_bar_data["close"] = Decimal("10.00")

        with pytest.raises(ValidationError, match=r"(High|must be >= close)"):
            OptionsBar(**valid_options_bar_data)

    def test_low_must_be_lte_open(self, valid_options_bar_data):
        """Test that low must be <= open"""
        valid_options_bar_data["low"] = Decimal("11.00")
        valid_options_bar_data["open"] = Decimal("10.00")

        with pytest.raises(ValidationError, match=r"(Low|must be <= open)"):
            OptionsBar(**valid_options_bar_data)

    def test_low_must_be_lte_close(self, valid_options_bar_data):
        """Test that low must be <= close"""
        valid_options_bar_data["low"] = Decimal("11.00")
        valid_options_bar_data["close"] = Decimal("10.00")

        with pytest.raises(ValidationError, match=r"(Low|must be <= close)"):
            OptionsBar(**valid_options_bar_data)

    def test_ask_must_be_gte_bid(self, valid_options_bar_data):
        """Test that ask must be >= bid"""
        valid_options_bar_data["ask"] = Decimal("10.00")
        valid_options_bar_data["bid"] = Decimal("10.50")

        with pytest.raises(ValidationError, match=r"(Ask|must be >= bid)"):
            OptionsBar(**valid_options_bar_data)

    def test_ask_gte_bid_validation_skipped_when_none(self, valid_options_bar_data):
        """Test that ask >= bid validation is skipped when bid is None"""
        valid_options_bar_data["ask"] = Decimal("10.00")
        valid_options_bar_data["bid"] = None

        # Should not raise - validation is skipped when bid is None
        bar = OptionsBar(**valid_options_bar_data)
        assert bar.ask == Decimal("10.00")
        assert bar.bid is None

    def test_negative_prices_rejected(self, valid_options_bar_data):
        """Test that negative prices are rejected"""
        valid_options_bar_data["bid"] = Decimal("-10.00")

        with pytest.raises(ValidationError):
            OptionsBar(**valid_options_bar_data)

    def test_negative_volume_rejected(self, valid_options_bar_data):
        """Test that negative volume is rejected"""
        valid_options_bar_data["volume"] = -100

        with pytest.raises(ValidationError):
            OptionsBar(**valid_options_bar_data)

    def test_model_is_immutable(self, valid_options_bar_data):
        """Test that model is frozen (immutable)"""
        bar = OptionsBar(**valid_options_bar_data)

        with pytest.raises(ValidationError, match="frozen"):
            bar.close = Decimal("11.00")

    def test_serialization_roundtrip(self, valid_options_bar_data):
        """Test serialization and deserialization"""
        bar1 = OptionsBar(**valid_options_bar_data)

        # To dict
        data = bar1.model_dump()

        # From dict
        bar2 = OptionsBar(**data)

        assert bar1.contract_symbol == bar2.contract_symbol
        assert bar1.strike_price == bar2.strike_price
        assert bar1.close == bar2.close

    def test_json_serialization(self, valid_options_bar_data):
        """Test JSON serialization"""
        bar1 = OptionsBar(**valid_options_bar_data)

        # To JSON
        json_str = bar1.model_dump_json()

        # From JSON
        bar2 = OptionsBar.model_validate_json(json_str)

        assert bar1.contract_symbol == bar2.contract_symbol
        assert bar1.strike_price == bar2.strike_price

    def test_calculate_mark(self, valid_options_bar_data):
        """Test mark price calculation"""
        bar = OptionsBar(**valid_options_bar_data)

        calculated_mark = bar.calculate_mark()
        expected_mark = (bar.bid + bar.ask) / 2

        assert calculated_mark == expected_mark

    def test_calculate_mark_with_none_bid_ask(self, valid_options_bar_data):
        """Test mark price calculation when bid/ask are None"""
        valid_options_bar_data["bid"] = None
        valid_options_bar_data["ask"] = None
        valid_options_bar_data["mark"] = None

        bar = OptionsBar(**valid_options_bar_data)

        assert bar.calculate_mark() is None

    def test_optional_quote_fields(self, valid_options_bar_data):
        """Test that bid/ask/mark can be None"""
        valid_options_bar_data["bid"] = None
        valid_options_bar_data["ask"] = None
        valid_options_bar_data["mark"] = None

        bar = OptionsBar(**valid_options_bar_data)

        assert bar.bid is None
        assert bar.ask is None
        assert bar.mark is None

    def test_intrinsic_value_itm_call(self, valid_options_bar_data):
        """Test intrinsic value for ITM call"""
        valid_options_bar_data["contract_type"] = "call"
        valid_options_bar_data["strike_price"] = Decimal("6000.00")

        bar = OptionsBar(**valid_options_bar_data)

        # Underlying at 6100, call strike 6000 → intrinsic = 100
        intrinsic = bar.intrinsic_value(Decimal("6100.00"))
        assert intrinsic == Decimal("100.00")

    def test_intrinsic_value_otm_call(self, valid_options_bar_data):
        """Test intrinsic value for OTM call"""
        valid_options_bar_data["contract_type"] = "call"
        valid_options_bar_data["strike_price"] = Decimal("6200.00")

        bar = OptionsBar(**valid_options_bar_data)

        # Underlying at 6100, call strike 6200 → intrinsic = 0
        intrinsic = bar.intrinsic_value(Decimal("6100.00"))
        assert intrinsic == Decimal("0")

    def test_intrinsic_value_itm_put(self, valid_options_bar_data):
        """Test intrinsic value for ITM put"""
        valid_options_bar_data["contract_type"] = "put"
        valid_options_bar_data["strike_price"] = Decimal("6200.00")

        bar = OptionsBar(**valid_options_bar_data)

        # Underlying at 6100, put strike 6200 → intrinsic = 100
        intrinsic = bar.intrinsic_value(Decimal("6100.00"))
        assert intrinsic == Decimal("100.00")

    def test_intrinsic_value_otm_put(self, valid_options_bar_data):
        """Test intrinsic value for OTM put"""
        valid_options_bar_data["contract_type"] = "put"
        valid_options_bar_data["strike_price"] = Decimal("6000.00")

        bar = OptionsBar(**valid_options_bar_data)

        # Underlying at 6100, put strike 6000 → intrinsic = 0
        intrinsic = bar.intrinsic_value(Decimal("6100.00"))
        assert intrinsic == Decimal("0")

    def test_is_itm_call(self, valid_options_bar_data):
        """Test ITM check for call"""
        valid_options_bar_data["contract_type"] = "call"
        valid_options_bar_data["strike_price"] = Decimal("6000.00")

        bar = OptionsBar(**valid_options_bar_data)

        assert bar.is_itm(Decimal("6100.00")) is True  # Underlying > strike
        assert bar.is_itm(Decimal("5900.00")) is False  # Underlying < strike

    def test_is_itm_put(self, valid_options_bar_data):
        """Test ITM check for put"""
        valid_options_bar_data["contract_type"] = "put"
        valid_options_bar_data["strike_price"] = Decimal("6200.00")

        bar = OptionsBar(**valid_options_bar_data)

        assert bar.is_itm(Decimal("6100.00")) is True  # Underlying < strike
        assert bar.is_itm(Decimal("6300.00")) is False  # Underlying > strike

    def test_is_atm(self, valid_options_bar_data):
        """Test ATM check"""
        valid_options_bar_data["strike_price"] = Decimal("6100.00")

        bar = OptionsBar(**valid_options_bar_data)

        # Within 1% of strike
        assert bar.is_atm(Decimal("6105.00")) is True
        assert bar.is_atm(Decimal("6095.00")) is True

        # Outside 1% threshold
        assert bar.is_atm(Decimal("6200.00")) is False


class TestUnderlyingBar:
    """Test UnderlyingBar model validation"""

    @pytest.fixture
    def valid_underlying_bar_data(self):
        """Create valid underlying bar data"""
        return {
            "timestamp": now_utc(),
            "ticker": "SPX",
            "open": Decimal("6100.00"),
            "high": Decimal("6120.00"),
            "low": Decimal("6090.00"),
            "close": Decimal("6110.00"),
            "volume": 1000000,
        }

    def test_create_valid_underlying_bar(self, valid_underlying_bar_data):
        """Test creating valid underlying bar"""
        bar = UnderlyingBar(**valid_underlying_bar_data)

        assert bar.ticker == "SPX"
        assert bar.close == Decimal("6110.00")

    def test_timestamp_must_be_utc_aware(self, valid_underlying_bar_data):
        """Test that naive timestamps are rejected"""
        valid_underlying_bar_data["timestamp"] = datetime(2026, 1, 2, 14, 30)

        with pytest.raises(ValidationError, match="naive"):
            UnderlyingBar(**valid_underlying_bar_data)

    def test_timestamp_conversion_from_aware(self, valid_underlying_bar_data):
        """Test that UTC-aware timestamps are accepted"""
        valid_underlying_bar_data["timestamp"] = datetime(2026, 1, 2, 14, 30, tzinfo=ZoneInfo("UTC"))

        bar = UnderlyingBar(**valid_underlying_bar_data)

        assert bar.timestamp.tzinfo == ZoneInfo("UTC")

    def test_ohlc_constraints(self, valid_underlying_bar_data):
        """Test OHLC constraints"""
        # High must be >= low
        valid_underlying_bar_data["high"] = Decimal("6000.00")
        valid_underlying_bar_data["low"] = Decimal("6100.00")

        with pytest.raises(ValidationError, match=r"(High|must be >= low)"):
            UnderlyingBar(**valid_underlying_bar_data)

    def test_serialization(self, valid_underlying_bar_data):
        """Test serialization"""
        bar1 = UnderlyingBar(**valid_underlying_bar_data)

        data = bar1.model_dump()
        bar2 = UnderlyingBar(**data)

        assert bar1.ticker == bar2.ticker
        assert bar1.close == bar2.close


class TestTrade:
    """Test Trade model validation"""

    @pytest.fixture
    def valid_trade_data(self):
        """Create valid trade data"""
        entry_time = now_utc() - timedelta(hours=1)
        exit_time = now_utc()

        return {
            "trade_id": "trade_001",
            "position_id": "pos_001",
            "strategy_name": "bullish_vertical_put",
            "spread_type": "vertical_put",
            "entry_time": entry_time,
            "exit_time": exit_time,
            "entry_premium": Decimal("1.50"),
            "entry_underlying_price": Decimal("6100.00"),
            "exit_premium": Decimal("0.75"),
            "exit_underlying_price": Decimal("6120.00"),
            "exit_reason": "profit_target",
            "pnl": Decimal("0.75"),
            "pnl_pct": Decimal("0.50"),
            "max_risk": Decimal("18.50"),
            "legs": [
                {"symbol": "SPXW260123P06100000", "quantity": 1, "side": "buy"},
                {"symbol": "SPXW260123P06080000", "quantity": -1, "side": "sell"},
            ],
        }

    def test_create_valid_trade(self, valid_trade_data):
        """Test creating valid trade"""
        trade = Trade(**valid_trade_data)

        assert trade.trade_id == "trade_001"
        assert trade.pnl == Decimal("0.75")

    def test_timestamps_must_be_utc_aware(self, valid_trade_data):
        """Test that naive timestamps are rejected"""
        valid_trade_data["entry_time"] = datetime(2026, 1, 2, 13, 30)
        valid_trade_data["exit_time"] = datetime(2026, 1, 2, 14, 30)

        with pytest.raises(ValidationError, match="naive"):
            Trade(**valid_trade_data)

    def test_timestamps_conversion_from_aware(self, valid_trade_data):
        """Test that UTC-aware timestamps are accepted"""
        valid_trade_data["entry_time"] = datetime(2026, 1, 2, 13, 30, tzinfo=ZoneInfo("UTC"))
        valid_trade_data["exit_time"] = datetime(2026, 1, 2, 14, 30, tzinfo=ZoneInfo("UTC"))

        trade = Trade(**valid_trade_data)

        assert trade.entry_time.tzinfo == ZoneInfo("UTC")
        assert trade.exit_time.tzinfo == ZoneInfo("UTC")

    def test_exit_must_be_after_entry(self, valid_trade_data):
        """Test that exit_time > entry_time"""
        valid_trade_data["exit_time"] = valid_trade_data["entry_time"] - timedelta(hours=1)

        with pytest.raises(ValidationError, match=r"(Exit time|must be after entry time)"):
            Trade(**valid_trade_data)

    def test_holding_period_calculations(self, valid_trade_data):
        """Test holding period helpers"""
        trade = Trade(**valid_trade_data)

        # Entry to exit is 1 hour (allow microsecond precision)
        assert trade.holding_period_seconds() == pytest.approx(3600.0, abs=0.001)
        assert trade.holding_period_minutes() == pytest.approx(60.0, abs=0.001)
        assert trade.holding_period_hours() == pytest.approx(1.0, abs=0.001)

    def test_is_winner(self, valid_trade_data):
        """Test winner/loser classification"""
        valid_trade_data["pnl"] = Decimal("10.00")
        trade = Trade(**valid_trade_data)

        assert trade.is_winner() is True
        assert trade.is_loser() is False

    def test_is_loser(self, valid_trade_data):
        """Test loser classification"""
        valid_trade_data["pnl"] = Decimal("-10.00")
        trade = Trade(**valid_trade_data)

        assert trade.is_winner() is False
        assert trade.is_loser() is True

    def test_serialization(self, valid_trade_data):
        """Test serialization"""
        trade1 = Trade(**valid_trade_data)

        data = trade1.model_dump()
        trade2 = Trade(**data)

        assert trade1.trade_id == trade2.trade_id
        assert trade1.pnl == trade2.pnl


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
