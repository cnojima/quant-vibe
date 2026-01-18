import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from './client';
import type {
  Service,
  TokenStatus,
  LiveEngineStatus,
  Position,
  Order,
  Event,
  TradingStats,
  Strategy,
  BacktestRequest,
  BacktestStatus,
  BacktestResult,
  LoginRequest,
  LoginResponse,
  StrategyInfo,
  StrategyListResponse,
  ActiveStrategiesResponse,
  AnalysisResult,
  AccountsResponse,
  AccountBalanceResponse,
} from '../types/api';

// Helper function to create mutation with query invalidation
function createMutationWithInvalidation<TData = any, TVariables = void>(
  mutationFn: (variables: TVariables) => Promise<TData>,
  queryKeys: string[][] = []
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn,
    onSuccess: () => {
      queryKeys.forEach(key => queryClient.invalidateQueries({ queryKey: key }));
    },
  });
}

// Auth queries
export function useLogin() {
  return useMutation({
    mutationFn: async (data: LoginRequest) => {
      const response = await apiClient.post<LoginResponse>('/auth/login', data);
      return response.data;
    },
    onSuccess: (data) => {
      localStorage.setItem('auth_token', data.access_token);
    },
  });
}

export function useLogout() {
  return useMutation({
    mutationFn: async () => {
      localStorage.removeItem('auth_token');
    },
  });
}

// Service management queries
export function useServices() {
  return useQuery({
    queryKey: ['services'],
    queryFn: async () => {
      const response = await apiClient.get<{ services: Service[]; count: number }>('/services/');
      return response.data.services;
    },
    refetchInterval: 5000,
  });
}

export function useServiceAction() {
  return createMutationWithInvalidation(
    async ({ serviceName, action }: { serviceName: string; action: 'start' | 'stop' | 'restart' }) => {
      const response = await apiClient.post(`/services/${serviceName}/${action}`);
      return response.data;
    },
    [['services']]
  );
}

export function useServiceLogs(serviceName: string, tail = 100) {
  return useQuery({
    queryKey: ['service-logs', serviceName, tail],
    queryFn: async () => {
      const response = await apiClient.get<{ logs: string; lines: number }>(`/services/${serviceName}/logs`, {
        params: { tail },
      });
      return response.data;
    },
    enabled: !!serviceName,
  });
}

// Token management queries
export function useTokenStatus() {
  return useQuery({
    queryKey: ['token-status'],
    queryFn: async () => {
      const response = await apiClient.get<TokenStatus>('/tokens/status');
      return response.data;
    },
    refetchInterval: 60000,
  });
}

export function useRefreshToken() {
  return createMutationWithInvalidation(
    async () => {
      const response = await apiClient.post('/tokens/refresh');
      return response.data;
    },
    [['token-status']]
  );
}

export function useOAuthUrl() {
  return useQuery({
    queryKey: ['oauth-url'],
    queryFn: async () => {
      const response = await apiClient.get<{
        oauth_url: string;
        callback_url: string;
        instructions: string[];
      }>('/tokens/oauth-url');
      return response.data;
    },
    staleTime: 5 * 60 * 1000,
  });
}

// Live trading queries
export function useLiveStatus(tradingMode: 'real' | 'paper' | 'replay' = 'paper') {
  return useQuery({
    queryKey: ['live-status', tradingMode],
    queryFn: async () => {
      const response = await apiClient.get<LiveEngineStatus>('/live/status', {
        params: { trading_mode: tradingMode },
      });
      return response.data;
    },
    refetchInterval: 5000,
  });
}

// Account Management queries
export function useBrokerAccounts(tradingMode: 'real' | 'paper' = 'real') {
  return useQuery({
    queryKey: ['broker-accounts', tradingMode],
    queryFn: async () => {
      const response = await apiClient.get<AccountsResponse>('/live/accounts', {
        params: { trading_mode: tradingMode },
      });
      return response.data;
    },
    refetchInterval: 30000,
  });
}

export function useAccountBalance(
  accountHash: string,
  tradingMode: 'real' | 'paper' = 'real',
  realtime = false
) {
  return useQuery({
    queryKey: ['account-balance', accountHash, tradingMode, realtime],
    queryFn: async () => {
      const response = await apiClient.get<AccountBalanceResponse>(`/live/accounts/${accountHash}/balance`, {
        params: { trading_mode: tradingMode, realtime },
      });
      return response.data;
    },
    refetchInterval: realtime ? 30000 : 60000,
    enabled: !!accountHash,
  });
}

export function useSetDefaultAccount() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ accountHash, tradingMode }: { accountHash: string; tradingMode: 'real' | 'paper' }) => {
      const response = await apiClient.post(`/live/accounts/${accountHash}/set-default`, null, {
        params: { trading_mode: tradingMode },
      });
      return response.data;
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['broker-accounts', variables.tradingMode] });
    },
  });
}

export function useRefreshAccounts() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (tradingMode: 'real' | 'paper' = 'real') => {
      const response = await apiClient.post('/live/accounts/refresh', null, {
        params: { trading_mode: tradingMode },
      });
      return response.data;
    },
    onSuccess: (_, tradingMode) => {
      queryClient.invalidateQueries({ queryKey: ['broker-accounts', tradingMode] });
    },
  });
}

export function useSyncAccountOrders() {
  return useMutation({
    mutationFn: async ({
      accountHash,
      daysBack = 30,
      tradingMode = 'real'
    }: {
      accountHash: string;
      daysBack?: number;
      tradingMode?: 'real' | 'paper';
    }) => {
      const response = await apiClient.post(`/live/accounts/${accountHash}/sync-orders`, null, {
        params: { days_back: daysBack, trading_mode: tradingMode },
      });
      return response.data;
    },
  });
}

// Helper to build query params
function buildQueryParams(params: Record<string, any>): Record<string, any> {
  const result: Record<string, any> = {};
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined) result[key] = value;
  });
  return result;
}

export function useLivePositions(
  status: 'open' | 'closed' | 'all' = 'open',
  limit = 100,
  tradingMode: 'real' | 'paper' | 'replay' = 'paper',
  accountHash?: string
) {
  return useQuery({
    queryKey: ['live-positions', status, limit, tradingMode, accountHash],
    queryFn: async () => {
      const params = buildQueryParams({
        status,
        limit,
        trading_mode: tradingMode,
        account_hash: accountHash,
      });

      const response = await apiClient.get<{ positions: Position[]; count: number }>('/live/positions', {
        params,
      });
      return response.data.positions;
    },
    refetchInterval: 5000,
  });
}

export function useLiveOrders(
  limit = 100,
  status: 'open' | 'filled' | 'rejected' | 'cancelled' | 'all' = 'all',
  tradingMode: 'real' | 'paper' | 'replay' = 'paper',
  accountHash?: string
) {
  return useQuery({
    queryKey: ['live-orders', limit, status, tradingMode, accountHash],
    queryFn: async () => {
      const params = buildQueryParams({
        limit,
        status,
        trading_mode: tradingMode,
        account_hash: accountHash,
      });

      const response = await apiClient.get<{ orders: Order[]; count: number }>('/live/orders', {
        params,
      });
      return response.data.orders;
    },
    refetchInterval: 5000,
  });
}

export function useLiveEvents(
  limit = 100,
  eventType?: string,
  severity?: string,
  tradingMode: 'real' | 'paper' | 'replay' = 'paper'
) {
  return useQuery({
    queryKey: ['live-events', limit, eventType, severity, tradingMode],
    queryFn: async () => {
      const params = buildQueryParams({
        limit,
        event_type: eventType,
        severity,
        trading_mode: tradingMode,
      });

      const response = await apiClient.get<{ events: Event[]; count: number }>('/live/events', {
        params,
      });
      return response.data.events;
    },
    refetchInterval: 5000,
  });
}

export function useClearEvents() {
  return createMutationWithInvalidation(
    async () => {
      const response = await apiClient.delete<{ deleted_count: number; message: string }>('/live/events');
      return response.data;
    },
    [['live-events']]
  );
}

export function useToggleDataFeedMode() {
  return createMutationWithInvalidation(
    async (tradingMode: 'real' | 'paper' = 'paper') => {
      const response = await apiClient.post<{
        message: string;
        previous_mode: string;
        new_mode: string;
        note: string;
      }>(`/live/data-feed/toggle-mode?trading_mode=${tradingMode}`);
      return response.data;
    },
    [['live-status'], ['config-live']]
  );
}

export function useLiveStats(
  startTime?: string,
  endTime?: string,
  tradingMode: 'real' | 'paper' | 'replay' = 'paper'
) {
  return useQuery({
    queryKey: ['live-stats', startTime, endTime, tradingMode],
    queryFn: async () => {
      const params = buildQueryParams({
        start_time: startTime,
        end_time: endTime,
        trading_mode: tradingMode,
      });

      const response = await apiClient.get<{ stats: TradingStats }>('/live/stats', {
        params,
      });
      return response.data.stats;
    },
    refetchInterval: 5000,
  });
}

export function useDailyReport(
  reportDate?: string,
  accountHash?: string,
  tradingMode: 'real' | 'paper' = 'paper'
) {
  return useQuery({
    queryKey: ['daily-report', reportDate, accountHash, tradingMode],
    queryFn: async () => {
      const params = buildQueryParams({
        report_date: reportDate,
        account_hash: accountHash,
        trading_mode: tradingMode,
      });

      const response = await apiClient.get<{ report: any }>('/live/daily-report', {
        params,
      });
      return response.data.report;
    },
  });
}

export function useRecentDailyReports(
  days = 7,
  accountHash?: string,
  tradingMode: 'real' | 'paper' = 'paper'
) {
  return useQuery({
    queryKey: ['daily-reports-recent', days, accountHash, tradingMode],
    queryFn: async () => {
      const params = buildQueryParams({
        days,
        account_hash: accountHash,
        trading_mode: tradingMode,
      });

      const response = await apiClient.get<{ reports: any[]; count: number }>('/live/daily-reports/recent', {
        params,
      });
      return response.data.reports;
    },
  });
}

export function useActiveStrategies() {
  return useQuery({
    queryKey: ['active-strategies'],
    queryFn: async () => {
      const response = await apiClient.get<ActiveStrategiesResponse>('/live/strategies/active');
      return response.data;
    },
    refetchInterval: 10000,
  });
}

export function useLiveTradesVisualization(days = 7) {
  return useQuery({
    queryKey: ['live-trades-visualization', days],
    queryFn: async () => {
      const response = await apiClient.get<{
        trades: any[];
        equity_curve: any[];
        underlying_data: any[];
        initial_capital: number;
        start_date: string;
        end_date: string;
        total_trades: number;
      }>('/live/trades/visualization', {
        params: { days },
      });
      return response.data;
    },
    refetchInterval: 30000,
  });
}

// Backtest queries
export function useStrategies() {
  return useQuery({
    queryKey: ['strategies'],
    queryFn: async () => {
      const response = await apiClient.get<{ strategies: Strategy[]; count: number }>('/backtests/strategies');
      return response.data.strategies;
    },
  });
}

export function useRunBacktest() {
  return useMutation({
    mutationFn: async (request: BacktestRequest) => {
      const response = await apiClient.post<{ backtest_id: string }>('/backtests/run', request);
      return response.data;
    },
  });
}

export function useBacktestStatus(backtestId: string | null) {
  return useQuery({
    queryKey: ['backtest-status', backtestId],
    queryFn: async () => {
      if (!backtestId) throw new Error('No backtest ID');
      const response = await apiClient.get<BacktestStatus>(`/backtests/${backtestId}/status`);
      return response.data;
    },
    enabled: !!backtestId,
    refetchInterval: (query) => {
      const data = query.state.data;
      const isComplete = data?.status === 'completed' || data?.status === 'failed';
      return isComplete ? false : 2000;
    },
  });
}

export function useBacktestResults(backtestId: string | null, status?: string) {
  return useQuery({
    queryKey: ['backtest-results', backtestId],
    queryFn: async () => {
      if (!backtestId) throw new Error('No backtest ID');
      const response = await apiClient.get<BacktestResult>(`/backtests/${backtestId}/results`);
      return response.data;
    },
    enabled: !!backtestId && status === 'completed',
  });
}

export function useBacktestHistory(limit = 50) {
  return useQuery({
    queryKey: ['backtest-history', limit],
    queryFn: async () => {
      const response = await apiClient.get<{ backtests: BacktestResult[]; total: number }>('/backtests/history', {
        params: { limit },
      });
      return response.data.backtests;
    },
  });
}

export function useDeleteBacktest() {
  return createMutationWithInvalidation(
    async (backtestId: string) => {
      const response = await apiClient.delete(`/backtests/${backtestId}`);
      return response.data;
    },
    [['backtest-history']]
  );
}

export function useDeleteAllBacktests() {
  return createMutationWithInvalidation(
    async () => {
      const response = await apiClient.delete('/backtests/all/confirm');
      return response.data;
    },
    [['backtest-history']]
  );
}

// Backtest Analysis queries
export function useAnalyzeBacktest() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ backtestId, outlierStdDevs = 2.0 }: { backtestId: string; outlierStdDevs?: number }) => {
      const response = await apiClient.post<AnalysisResult>(`/backtests/${backtestId}/analyze`, null, {
        params: { outlier_std_devs: outlierStdDevs },
      });
      return response.data;
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['backtest-analysis', variables.backtestId] });
    },
  });
}

export function useBacktestAnalysis(backtestId: string | null) {
  return useQuery({
    queryKey: ['backtest-analysis', backtestId],
    queryFn: async () => {
      if (!backtestId) throw new Error('No backtest ID');
      const response = await apiClient.get<AnalysisResult>(`/backtests/${backtestId}/analysis`);
      return response.data;
    },
    enabled: !!backtestId,
    retry: false,
  });
}

export function useDeleteBacktestAnalysis() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (backtestId: string) => {
      const response = await apiClient.delete(`/backtests/${backtestId}/analysis`);
      return response.data;
    },
    onSuccess: (_data, backtestId) => {
      queryClient.invalidateQueries({ queryKey: ['backtest-analysis', backtestId] });
    },
  });
}

// Configuration queries
export function useConfigList() {
  return useQuery({
    queryKey: ['config-list'],
    queryFn: async () => {
      const response = await apiClient.get<{ configs: any[]; count: number }>('/config/list');
      return response.data;
    },
  });
}

export function useBacktestConfig() {
  return useQuery({
    queryKey: ['config-backtest'],
    queryFn: async () => {
      const response = await apiClient.get<{ config: any }>('/config/backtest');
      return response.data.config;
    },
  });
}

export function useLiveConfig() {
  return useQuery({
    queryKey: ['config-live'],
    queryFn: async () => {
      const response = await apiClient.get<{ config: any }>('/config/live');
      return response.data.config;
    },
  });
}

export function useUpdateBacktestConfig() {
  return createMutationWithInvalidation(
    async (config: any) => {
      const response = await apiClient.put('/config/backtest', { config });
      return response.data;
    },
    [['config-backtest']]
  );
}

export function useUpdateLiveConfig() {
  return createMutationWithInvalidation(
    async (config: any) => {
      const response = await apiClient.put('/config/live', { config });
      return response.data;
    },
    [['config-live']]
  );
}

export function useBacktestSchema() {
  return useQuery({
    queryKey: ['schema-backtest'],
    queryFn: async () => {
      const response = await apiClient.get<{ schema: any }>('/config/schema/backtest');
      return response.data.schema;
    },
    staleTime: Infinity,
  });
}

export function useLiveSchema() {
  return useQuery({
    queryKey: ['schema-live'],
    queryFn: async () => {
      const response = await apiClient.get<{ schema: any }>('/config/schema/live');
      return response.data.schema;
    },
    staleTime: Infinity,
  });
}

// Live trading strategy management queries
export function useLiveStrategies(tradingMode = 'paper') {
  return useQuery({
    queryKey: ['live-strategies', tradingMode],
    queryFn: async () => {
      const response = await apiClient.get<StrategyListResponse>('/strategies/list', {
        params: { trading_mode: tradingMode }
      });
      return response.data;
    },
    refetchInterval: 5000,
  });
}

export function useLiveStrategy(strategyName: string, tradingMode = 'paper') {
  return useQuery({
    queryKey: ['live-strategy', strategyName, tradingMode],
    queryFn: async () => {
      const response = await apiClient.get<StrategyInfo>(`/strategies/${strategyName}`, {
        params: { trading_mode: tradingMode }
      });
      return response.data;
    },
    enabled: !!strategyName,
  });
}

export function useToggleLiveStrategy() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      strategyName,
      enabled,
      tradingMode = 'paper'
    }: {
      strategyName: string;
      enabled: boolean;
      tradingMode?: string;
    }) => {
      const response = await apiClient.post(
        `/strategies/${strategyName}/toggle`,
        { enabled },
        { params: { trading_mode: tradingMode } }
      );
      return response.data;
    },
    onSuccess: (_data, variables) => {
      const mode = variables.tradingMode || 'paper';
      queryClient.invalidateQueries({ queryKey: ['live-strategies', mode] });
      queryClient.invalidateQueries({ queryKey: ['config-live'] });
    },
  });
}

export function useUpdateLiveStrategyParams() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      strategyName,
      params,
      tradingMode = 'paper'
    }: {
      strategyName: string;
      params: Record<string, any>;
      tradingMode?: string;
    }) => {
      const response = await apiClient.put(
        `/strategies/${strategyName}/params`,
        { params },
        { params: { trading_mode: tradingMode } }
      );
      return response.data;
    },
    onSuccess: (_, variables) => {
      const mode = variables.tradingMode || 'paper';
      queryClient.invalidateQueries({ queryKey: ['live-strategies', mode] });
      queryClient.invalidateQueries({ queryKey: ['live-strategy', variables.strategyName, mode] });
      queryClient.invalidateQueries({ queryKey: ['config-live'] });
    },
  });
}

// Optimization queries
export function useRunOptimization() {
  return createMutationWithInvalidation(
    async (request: any) => {
      const response = await apiClient.post('/optimization/run', request);
      return response.data;
    },
    [['optimization-history']]
  );
}

export function useOptimizationStatus(optimizationId: string | null) {
  return useQuery({
    queryKey: ['optimization-status', optimizationId],
    queryFn: async () => {
      const response = await apiClient.get(`/optimization/status/${optimizationId}`);
      return response.data;
    },
    enabled: !!optimizationId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      const isActive = status === 'running' || status === 'pending';
      return isActive ? 2000 : false;
    },
  });
}

export function useOptimizationResults(optimizationId: string | null, status?: string) {
  return useQuery({
    queryKey: ['optimization-results', optimizationId],
    queryFn: async () => {
      const response = await apiClient.get(`/optimization/results/${optimizationId}`);
      return response.data;
    },
    enabled: !!optimizationId && status === 'completed',
  });
}

export function useOptimizationHistory(limit = 50) {
  return useQuery({
    queryKey: ['optimization-history', limit],
    queryFn: async () => {
      const response = await apiClient.get('/optimization/history', {
        params: { limit },
      });
      return response.data;
    },
  });
}

export function useDeleteOptimization() {
  return createMutationWithInvalidation(
    async (optimizationId: string) => {
      const response = await apiClient.delete(`/optimization/${optimizationId}`);
      return response.data;
    },
    [['optimization-history']]
  );
}

export function useDeleteAllOptimizations() {
  return createMutationWithInvalidation(
    async () => {
      const response = await apiClient.delete('/optimization/');
      return response.data;
    },
    [['optimization-history']]
  );
}

// New optimization v2 API hooks
export function useParamGrid(strategyName: string | null) {
  return useQuery({
    queryKey: ['param-grid', strategyName],
    queryFn: async () => {
      const response = await apiClient.get(`/optimization/param-grid/${strategyName}`);
      return response.data;
    },
    enabled: !!strategyName,
  });
}

export function useGenerateParamGrid() {
  return useMutation({
    mutationFn: async (request: {
      strategy_name: string;
      custom_ranges?: Record<string, any[]>;
      optimize_only?: string[];
    }) => {
      const response = await apiClient.post('/optimization/param-grid/generate', request);
      return response.data;
    },
  });
}

export function useValidateParamGrid() {
  return useMutation({
    mutationFn: async (request: {
      strategy_name: string;
      param_grid: Record<string, any[]>;
      max_combinations?: number;
    }) => {
      const response = await apiClient.post('/optimization/param-grid/validate', request);
      return response.data;
    },
  });
}

export function useFixedParams(strategyName: string | null) {
  return useQuery({
    queryKey: ['fixed-params', strategyName],
    queryFn: async () => {
      const response = await apiClient.get(`/optimization/fixed-params/${strategyName}`);
      return response.data;
    },
    enabled: !!strategyName,
  });
}

export function useCancelOptimization() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (optimizationId: string) => {
      const response = await apiClient.post(`/optimization/cancel/${optimizationId}`);
      return response.data;
    },
    onSuccess: (_data, optimizationId) => {
      queryClient.invalidateQueries({ queryKey: ['optimization-status', optimizationId] });
    },
  });
}

export function useClearOptimizationCache() {
  return useMutation({
    mutationFn: async (cacheKey?: string) => {
      const response = await apiClient.post('/optimization/cache/clear', {
        cache_key: cacheKey,
      });
      return response.data;
    },
  });
}

// Reconciliation
export function useReconcilePositions() {
  return createMutationWithInvalidation(
    async ({
      tradingMode = 'real',
      accountHash
    }: {
      tradingMode?: 'real' | 'paper';
      accountHash?: string;
    }) => {
      const url = `/live/reconcile?trading_mode=${tradingMode}${accountHash ? `&account_hash=${accountHash}` : ''}`;
      const response = await apiClient.post<{
        success: boolean;
        message: string;
        status: string;
      }>(url);
      return response.data;
    },
    [['live-positions'], ['live-events'], ['accounts']]
  );
}