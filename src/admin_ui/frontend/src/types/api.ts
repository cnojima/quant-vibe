// API response types for QuantVibe Admin UI

export interface Service {
  name: string;
  status: 'running' | 'stopped' | 'error';
  uptime_seconds: number;
  container_id?: string;
}

export interface TokenStatus {
  has_token: boolean;
  access_token_issued?: string;
  refresh_token_issued?: string;
  access_token_expires_at?: string;
  refresh_token_expires_at?: string;
  access_token_expired?: boolean;
  refresh_token_expired?: boolean;
  is_access_token_expired?: boolean;  // From token_service
  is_refresh_token_expired?: boolean;  // From token_service
  access_token_age_seconds?: number;
  access_token_age_minutes?: number;
  expires_in?: number;
  token_type?: string;
  scope?: string;
  source?: string;
  message?: string;
  database_exists?: boolean;
  instructions?: string[];
  requires_oauth?: boolean;
  client_init_error?: string;
}

export interface LiveEngineStatus {
  running: boolean;
  state: string;
  paper_trading: boolean | null;
  total_bars_processed: number | null;
  total_signals_generated: number | null;
  uptime_seconds: number | null;
  last_update: string;
  metadata: any;
  data_feed_mode?: 'live' | 'replay';
}

export interface OptionLeg {
  contract_symbol: string;
  quantity: number;
  side: 'buy' | 'sell';
  action?: 'buy' | 'sell';
  entry_price: number;
  price?: number;
  current_price: number | null;
  strike_price: number;
  contract_type: 'call' | 'put';
  option_type?: string;
  expiration_date: string;
}

export interface Position {
  position_id: string;
  strategy_name: string;
  strategy?: string;
  symbol?: string;
  spread_type?: string;
  status: 'open' | 'closed';
  entry_time: string;
  entry_cost: number;
  entry_price?: number;
  current_value: number | null;
  current_price?: number;
  quantity?: number;
  exit_time: string | null;
  exit_value: number | null;
  exit_reason: string | null;
  unrealized_pnl: number | null;
  realized_pnl: number | null;
  legs: OptionLeg[];
  metadata?: Record<string, any>;
}

export interface Order {
  order_id: string;
  position_id: string;
  strategy_name?: string;
  order_type: 'entry' | 'exit' | 'profit_target' | 'stop_loss';
  action_type?: 'opening' | 'closing';
  status: 'pending' | 'submitted' | 'accepted' | 'filled' | 'cancelled' | 'rejected';
  submitted_time: string | null;
  filled_time: string | null;
  timestamp?: string;
  symbol: string;
  quantity: number;
  side: 'buy' | 'sell';
  action?: string;
  price?: number;
  limit_price: number | null;
  filled_price: number | null;
  metadata?: Record<string, any>;
}

export interface Event {
  id: number;
  timestamp: string;
  event_type: 'signal' | 'order' | 'fill' | 'error' | 'system';
  severity: 'info' | 'warning' | 'error';
  message: string;
  metadata?: Record<string, any>;
}

export interface TradingStats {
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  total_pnl: number;
  average_pnl: number;
  avg_win?: number;
  avg_loss?: number;
  sharpe_ratio: number | null;
  max_drawdown: number | null;
}

export interface Strategy {
  name: string;
  enabled: boolean;
  description?: string;
  params: Record<string, any>;
}

export interface BacktestRequest {
  strategy_name: string;
  params: Record<string, any>;
  parameters?: Record<string, any>;
  start_date: string;
  end_date: string;
  initial_capital?: number;
  underlying_ticker?: string;
  min_dte?: number;
  max_dte?: number;
}

export interface BacktestStatus {
  backtest_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  progress: number;
  message: string;
  error?: string;
  started_at?: string;
  completed_at?: string;
}

export interface EquityPoint {
  timestamp: string;
  portfolio_value: number;
  cash: number;
}

// Matches Trade Pydantic model (src/quant_vibe/models/market_data.py)
export interface Trade {
  trade_id: string;
  position_id: string;
  strategy_name: string;
  spread_type: string;
  entry_time: string;
  exit_time: string;
  entry_premium: number;  // Renamed from entry_cost
  exit_premium: number;   // Renamed from exit_value
  pnl: number;
  pnl_pct: number;        // Renamed from pnl_percent
  entry_trigger?: string;
  exit_reason: string;
  entry_underlying_price: number;  // Renamed from underlying_entry
  exit_underlying_price: number;   // Renamed from underlying_exit
  max_risk: number;
  max_profit?: number;
  peak_value?: number;
  legs: OptionLeg[];
  duration_minutes?: number;  // Optional for backward compatibility
}

export interface UnderlyingBar {
  timestamp: string;
  ticker: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  vwap?: number;
  transactions?: number;
}

export interface BacktestResult {
  backtest_id: string;
  strategy_name: string;
  start_date: string;
  end_date: string;
  initial_capital: number;
  final_capital: number;
  total_pnl: number;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  sharpe_ratio: number | null;
  max_drawdown: number | null;
  equity_curve: EquityPoint[];
  underlying_bars?: UnderlyingBar[];
  trades: Trade[];
  status?: 'pending' | 'running' | 'completed' | 'failed';
  created_at?: string;
  parameters?: Record<string, any>;
  metrics?: {
    total_return: number;
    sharpe_ratio: number | null;
    max_drawdown: number;
    win_rate: number;
  };
}

export interface WebSocketMessage {
  type: 'event' | 'heartbeat' | 'error';
  data: any;
  timestamp: string;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export interface StrategyInfo {
  name: string;
  enabled: boolean;
  description: string;
  params: Record<string, any>;
}

export interface StrategyListResponse {
  strategies: StrategyInfo[];
  count: number;
}

export interface StrategyToggleRequest {
  enabled: boolean;
}

export interface StrategyUpdateRequest {
  params: Record<string, any>;
}

export interface ActiveStrategyStats {
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  total_pnl: number;
  win_rate: number;
}

export interface ActiveStrategy {
  name: string;
  enabled: boolean;
  params: Record<string, any>;
  stats: ActiveStrategyStats;
}

export interface ActiveStrategiesResponse {
  strategies: ActiveStrategy[];
  count: number;
}

// ==================== Backtest Analysis Types ====================

export interface GreeksAnalysis {
  dominant_factor: string;
  delta_contribution: number;
  theta_contribution: number;
  vega_contribution: number;
  gamma_contribution: number;
  entry_delta?: number | null;
  exit_delta?: number | null;
  theta_decay_total?: number | null;
}

export interface MarketConditions {
  underlying_move_pct: number;
  underlying_move_direction: 'up' | 'down' | 'flat';
  volatility_change_pct?: number | null;
  market_regime: 'trending_up' | 'trending_down' | 'choppy' | 'volatile_spike';
  intraday_range_pct?: number | null;
}

export interface StrategyAdherence {
  within_all_rules: boolean;
  rule_violations: string[];
  edge_case_flags: string[];
  entry_quality_score: number;
}

export interface ExitTiming {
  exit_reason: string;
  held_pct_of_max_duration: number;
  was_optimal: boolean;
  profit_captured_pct?: number | null;
  could_have_exited_better: boolean;
  timing_notes?: string | null;
}

export interface MacroEvent {
  event_type: string;
  event_date: string;
  description: string;
  proximity_to_trade: string;
  likely_impact: 'high' | 'medium' | 'low';
}

export interface TradeInsights {
  greeks: GreeksAnalysis;
  market_conditions: MarketConditions;
  strategy_adherence: StrategyAdherence;
  exit_timing: ExitTiming;
  macro_events: MacroEvent[];
}

export interface TradeInsight {
  trade_id: string;
  pnl: number;
  pnl_pct: number;
  std_devs_from_mean: number;
  insights: TradeInsights;
  generalization_potential: 'high' | 'medium' | 'low';
  key_takeaway: string;
}

export interface EntryTimingPattern {
  best_hour: number;
  worst_hour: number;
  hourly_stats: Record<number, {
    avg_pnl: number;
    win_rate: number;
    count: number;
  }>;
}

export interface ExitReasonPattern {
  profit_target_win_rate: number;
  stop_loss_win_rate: number;
  expiration_win_rate: number;
  trailing_stop_win_rate: number;
  exit_reason_counts: Record<string, number>;
  exit_reason_avg_pnl: Record<string, number>;
}

export interface DTEPerformance {
  dte_buckets: Record<string, {
    avg_pnl: number;
    win_rate: number;
    count: number;
  }>;
  optimal_dte_range: string;
}

export interface StrikeSelectionPattern {
  otm_pct_buckets: Record<string, {
    avg_pnl: number;
    win_rate: number;
    count: number;
  }>;
  optimal_otm_pct: number;
}

export interface Patterns {
  entry_timing?: EntryTimingPattern | null;
  exit_reasons?: ExitReasonPattern | null;
  dte_performance?: DTEPerformance | null;
  strike_selection?: StrikeSelectionPattern | null;
  additional_patterns?: Record<string, any>;
}

export interface AnalysisFindings {
  big_winners: TradeInsight[];
  big_losers: TradeInsight[];
  patterns: Patterns;
}

export interface AnalysisResult {
  analysis_id?: number | null;
  backtest_id: string;
  analyzed_at: string;
  total_trades: number;
  outlier_threshold_pct: number;
  num_big_winners: number;
  num_big_losers: number;
  findings: AnalysisFindings;
  summary_markdown: string;
  recommendations_markdown: string;
  analyzer_version?: string;
}
