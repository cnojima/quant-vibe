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
  access_token_age_seconds?: number;
  access_token_age_minutes?: number;
  expires_in?: number;
  token_type?: string;
  scope?: string;
  source?: string;
  message?: string;
  database_exists?: boolean;
  instructions?: string[];
}

export interface LiveEngineStatus {
  is_running: boolean;
  paper_trading: boolean;
  total_pnl: number;
  total_bars_processed: number;
  total_signals_generated: number;
  active_positions_count: number;
  uptime_seconds: number;
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
  expiration_date: string;
}

export interface Position {
  position_id: string;
  strategy_name: string;
  strategy?: string;
  symbol?: string;
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
  order_type: 'entry' | 'exit' | 'profit_target' | 'stop_loss';
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

export interface Trade {
  trade_id: string;
  entry_time: string;
  exit_time: string;
  entry_cost: number;
  exit_value: number;
  pnl: number;
  exit_reason: string;
  legs: OptionLeg[];
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
