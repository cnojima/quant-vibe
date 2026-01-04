# BIS
        self,
        spread_width: float = 10.0,  # Tighter spreads for 0DTE scalping
        observation_period: int = 15,  # Quick observation (15 mins)
        iv_threshold: float = 0.15,  # Minimum IV (15%)
        iv_spike_pct: float = 0.10,  # IV must increase by 10% from recent avg
        profit_target_min: float = 0.30,  # 30% profit target
        profit_target_max: float = 0.50,  # 50% profit target
        trailing_stop_pct: float = 0.03,  # Tight 3% trailing stop
        stop_loss_pct: float = 0.75,  # Stop loss at 75% of max risk
        min_dte: int = 0,  # 0DTE only
        max_dte: int = 0,  # 0DTE only
        num_spreads: int = 5,  # Smaller size for scalping
        min_volume: int = 20,  # Lower volume requirement for 0DTE
        min_bid_ask_spread_pct: float = 15.0,  # Wider spreads acceptable for 0DTE
        max_trades_daily: int = 2,  # Allow 1-2 scalps per day
        momentum_lookback: int = 5,  # Bars to look back for momentum
        iv_lookback: int = 30,  # Bars to look back for IV average
# BBL
        self,
        target_contract_price: float = 2.0,
        limit_buy_price: float = 1.0,
        profit_target_price: float = 2.0,
        otm_percent_min: float = 0.10,  # 10% OTM minimum
        otm_percent_max: float = 0.15,  # 15% OTM maximum
        price_tolerance: float = 1.0,  # How far from $2 to accept
        max_trades_daily: int = 5,
        quantity: int = 10,
        min_dte: int = 0,
        max_dte: int = 45,
        stop_loss_pct: Optional[float] = 0.50,  # 50% stop loss
        order_expiry_minutes: int = 60,  # Cancel unfilled orders after 60 min
        bb_period: int = 20,  # Bollinger Band period
        bb_std: float = 2.0,  # Bollinger Band standard deviations
        bb_threshold: float = 0.0,  # How close to band to trigger (0 = at band)
# BB
        self,
        target_price: float = 2.0,
        buy_limit: float = 1.0,
        sell_target: float = 2.0,
        otm_percent_min: float = 0.10,  # 10% OTM minimum
        otm_percent_max: float = 0.15,  # 15% OTM maximum
        price_tolerance: float = 1.0,  # How far from target_price to search
        max_trades_daily: int = 5,
        quantity: int = 10,
        min_dte: int = 0,
        max_dte: int = 45,
        profit_target_pct: float = 1.0,  # 100% profit (buy at 1, sell at 2)
        stop_loss_pct: Optional[float] = 0.50,  # 50% stop loss
        bb_period: int = 20,  # Bollinger Band period
        bb_std: float = 2.0,  # Bollinger Band standard deviations
        bb_threshold: float = 0.0,  # How close to band to trigger (0 = at band)
# BVC
        self,
        spread_width: float = 20.0,
        observation_period: int = 30,  # minutes to watch market open
        pullback_amount: float = 50.0,  # dollar amount for pullback signal
        profit_target_min: float = 0.5,  # 50%
        profit_target_max: float = 1.0,  # 100%
        trailing_stop_pct: float = 0.05,  # 5%
        min_dte: int = 7,  # minimum days to expiration
        max_dte: int = 45,  # maximum days to expiration
        num_spreads: int = 10,  # number of spreads to open per signal
        max_trades_daily: int = 1,  # maximum trades per day

# BVP
        self,
        spread_width: float = 20.0,
        observation_period: int = 30,  # minutes to watch market open
        pullback_amount: float = 50.0,  # dollar amount for pullback signal
        profit_target_min: float = 0.5,  # 50%
        profit_target_max: float = 1.0,  # 100%
        trailing_stop_pct: float = 0.05,  # 5%
        min_dte: int = 7,  # minimum days to expiration
        max_dte: int = 45,  # maximum days to expiration
        num_spreads: int = 10,  # number of spreads to open per signal
        min_volume: int = 50,  # minimum volume per contract
        min_bid_ask_spread_pct: float = 10.0,  # maximum bid/ask spread percentage
        max_trades_daily: int = 1,  # maximum trades per day
        stop_loss_pct: Optional[float] = None,
# CTL
        self,
        target_contract_price: float = 2.0,
        limit_buy_price: float = 1.0,
        profit_target_price: float = 2.0,
        otm_percent_min: float = 0.10,  # 10% OTM minimum
        otm_percent_max: float = 0.15,  # 15% OTM maximum
        price_tolerance: float = 1.0,  # How far from $2 to accept
        max_trades_daily: int = 5,
        quantity: int = 10,
        min_dte: int = 0,
        max_dte: int = 45,
        stop_loss_pct: Optional[float] = 0.50,  # 50% stop loss
        order_expiry_minutes: int = 60,  # Cancel unfilled orders after 60 min
# CT
        self,
        target_price: float = 2.0,
        buy_limit: float = 1.0,
        sell_target: float = 2.0,
        price_tolerance: float = 0.50,  # How far from target_price to search
        max_trades_daily: int = 5,
        quantity: int = 10,
        min_dte: int = 0,
        max_dte: int = 45,
        profit_target_pct: float = 1.0,  # 100% profit (buy at 1, sell at 2)
        stop_loss_pct: Optional[float] = None,
        observation_period: Optional[int] = None,  # Accepted for compatibility, not used
        **kwargs  # Accept any additional parameters from optimizer
# HM
        self,
        otm_percent_min: float = -0.05,  # 5% OTM minimum
        otm_percent_max: float = 0.05,  # 10% OTM maximum
        entry_time_before_close: int = 15,  # minutes before close (3:45 PM ET)
        num_contracts: int = 10,  # number of contracts to buy
        trailing_stop_pct: float = 0.05,  # 5% trailing stop
        min_volume: int = 50,  # minimum volume per contract
        max_bid_ask_spread_pct: float = 15.0,  # maximum bid/ask spread percentage
        max_trades_daily: int = 3,  # maximum trades per day
# NBP
        self,
        spread_width: float = 20.0,
        profit_target: float = 0.5,  # 50%
        min_dte: int = 7,
        max_dte: int = 45,
        num_spreads: int = 10,
        max_trades_daily: int = 1,
