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
} from '../types/api';

// Auth queries
export function useLogin() {
  return useMutation({
    mutationFn: async (data: LoginRequest) => {
      const response = await apiClient.post<LoginResponse>('/auth/login', {
        username: data.username,
        password: data.password,
      });
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
      const response = await apiClient.get<{ success: boolean; services: Service[]; count: number }>('/services/');
      return response.data.services;
    },
    refetchInterval: 5000, // Poll every 5 seconds
  });
}

export function useServiceAction() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ serviceName, action }: { serviceName: string; action: 'start' | 'stop' | 'restart' }) => {
      const response = await apiClient.post(`/services/${serviceName}/${action}`);
      return response.data;
    },
    onSuccess: () => {
      // Invalidate services query to refresh the list
      queryClient.invalidateQueries({ queryKey: ['services'] });
    },
  });
}

export function useServiceLogs(serviceName: string, tail: number = 100) {
  return useQuery({
    queryKey: ['service-logs', serviceName, tail],
    queryFn: async () => {
      const response = await apiClient.get<{ logs: string }>(`/services/${serviceName}/logs`, {
        params: { tail },
      });
      return response.data.logs;
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
    refetchInterval: 60000, // Refresh every minute
  });
}

export function useRefreshToken() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      const response = await apiClient.post('/tokens/refresh');
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['token-status'] });
    },
  });
}

export function useOAuthUrl() {
  return useQuery({
    queryKey: ['oauth-url'],
    queryFn: async () => {
      const response = await apiClient.get<{
        success: boolean;
        oauth_url: string;
        callback_url: string;
        instructions: string[];
      }>('/tokens/oauth-url');
      return response.data;
    },
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

// Live trading queries
export function useLiveStatus() {
  return useQuery({
    queryKey: ['live-status'],
    queryFn: async () => {
      const response = await apiClient.get<LiveEngineStatus>('/live/status');
      return response.data;
    },
    refetchInterval: 5000,
  });
}

export function useLivePositions(status: 'open' | 'closed' | 'all' = 'open', limit: number = 100) {
  return useQuery({
    queryKey: ['live-positions', status, limit],
    queryFn: async () => {
      const response = await apiClient.get<{ positions: Position[]; count: number; filter: string }>('/live/positions', {
        params: { status, limit },
      });
      return response.data.positions;
    },
    refetchInterval: 5000,
  });
}

export function useLiveOrders(limit: number = 100, status: 'open' | 'filled' | 'rejected' | 'cancelled' | 'all' = 'all') {
  return useQuery({
    queryKey: ['live-orders', limit, status],
    queryFn: async () => {
      const response = await apiClient.get<{ orders: Order[]; count: number; filter: string }>('/live/orders', {
        params: { limit, status },
      });
      return response.data.orders;
    },
    refetchInterval: 5000,
  });
}

export function useLiveEvents(limit: number = 100, eventType?: string, severity?: string) {
  return useQuery({
    queryKey: ['live-events', limit, eventType, severity],
    queryFn: async () => {
      const response = await apiClient.get<{ events: Event[]; count: number; filters: any }>('/live/events', {
        params: { limit, event_type: eventType, severity },
      });
      return response.data.events;
    },
    refetchInterval: 5000,
  });
}

export function useLiveStats(startTime?: string, endTime?: string) {
  return useQuery({
    queryKey: ['live-stats', startTime, endTime],
    queryFn: async () => {
      const response = await apiClient.get<{stats: TradingStats; time_range: {start: string | null; end: string | null}}>('/live/stats', {
        params: { start_time: startTime, end_time: endTime },
      });
      return response.data.stats;
    },
    refetchInterval: 5000, // Poll every 5 seconds
  });
}

export function useDailyReport(reportDate?: string) {
  return useQuery({
    queryKey: ['daily-report', reportDate],
    queryFn: async () => {
      const response = await apiClient.get<{report: any; generated_at: string}>('/live/daily-report', {
        params: reportDate ? { report_date: reportDate } : {},
      });
      return response.data.report;
    },
  });
}

export function useRecentDailyReports(days: number = 7) {
  return useQuery({
    queryKey: ['daily-reports-recent', days],
    queryFn: async () => {
      const response = await apiClient.get<{reports: any[]; count: number; days: number}>('/live/daily-reports/recent', {
        params: { days },
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
    refetchInterval: 10000, // Refresh every 10 seconds
  });
}

export function useLiveTradesVisualization(days: number = 7) {
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
    refetchInterval: 30000, // Refresh every 30 seconds
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
      // Stop polling when completed or failed
      const data = query.state.data;
      if (data?.status === 'completed' || data?.status === 'failed') {
        return false;
      }
      return 2000; // Poll every 2 seconds while running
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

export function useBacktestHistory(limit: number = 50) {
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
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (backtestId: string) => {
      const response = await apiClient.delete(`/backtests/${backtestId}`);
      return response.data;
    },
    onSuccess: () => {
      // Invalidate backtest history to refresh the list
      queryClient.invalidateQueries({ queryKey: ['backtest-history'] });
    },
  });
}

export function useDeleteAllBacktests() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      const response = await apiClient.delete('/backtests/all/confirm');
      return response.data;
    },
    onSuccess: () => {
      // Invalidate backtest history to refresh the list
      queryClient.invalidateQueries({ queryKey: ['backtest-history'] });
    },
  });
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
      // Invalidate analysis query to refresh results
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
    retry: false, // Don't retry if analysis doesn't exist (404)
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
      // Invalidate analysis query
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
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (config: any) => {
      const response = await apiClient.put('/config/backtest', { config });
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['config-backtest'] });
    },
  });
}

export function useUpdateLiveConfig() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (config: any) => {
      const response = await apiClient.put('/config/live', { config });
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['config-live'] });
    },
  });
}

export function useBacktestSchema() {
  return useQuery({
    queryKey: ['schema-backtest'],
    queryFn: async () => {
      const response = await apiClient.get<{ schema: any }>('/config/schema/backtest');
      return response.data.schema;
    },
    staleTime: Infinity, // Schema doesn't change often
  });
}

export function useLiveSchema() {
  return useQuery({
    queryKey: ['schema-live'],
    queryFn: async () => {
      const response = await apiClient.get<{ schema: any }>('/config/schema/live');
      return response.data.schema;
    },
    staleTime: Infinity, // Schema doesn't change often
  });
}
// Live trading strategy management queries
export function useLiveStrategies() {
  return useQuery({
    queryKey: ['live-strategies'],
    queryFn: async () => {
      const response = await apiClient.get<StrategyListResponse>('/strategies/list');
      return response.data;
    },
    refetchInterval: 5000, // Refresh every 5 seconds
  });
}

export function useLiveStrategy(strategyName: string) {
  return useQuery({
    queryKey: ['live-strategy', strategyName],
    queryFn: async () => {
      const response = await apiClient.get<StrategyInfo>(`/strategies/${strategyName}`);
      return response.data;
    },
    enabled: !!strategyName,
  });
}

export function useToggleLiveStrategy() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ strategyName, enabled }: { strategyName: string; enabled: boolean }) => {
      const response = await apiClient.post(`/strategies/${strategyName}/toggle`, { enabled });
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['live-strategies'] });
      queryClient.invalidateQueries({ queryKey: ['config-live'] });
    },
  });
}

export function useUpdateLiveStrategyParams() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ strategyName, params }: { strategyName: string; params: Record<string, any> }) => {
      const response = await apiClient.put(`/strategies/${strategyName}/params`, { params });
      return response.data;
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['live-strategies'] });
      queryClient.invalidateQueries({ queryKey: ['live-strategy', variables.strategyName] });
      queryClient.invalidateQueries({ queryKey: ['config-live'] });
    },
  });
}

// Optimization queries
export function useRunOptimization() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (request: any) => {
      const response = await apiClient.post('/optimization/run', request);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['optimization-history'] });
    },
  });
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
      // Poll every 2 seconds if running, otherwise don't poll
      return query.state.data?.status === 'running' || query.state.data?.status === 'pending' ? 2000 : false;
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

export function useOptimizationHistory(limit: number = 50) {
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
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (optimizationId: string) => {
      const response = await apiClient.delete(`/optimization/${optimizationId}`);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['optimization-history'] });
    },
  });
}

export function useDeleteAllOptimizations() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      const response = await apiClient.delete('/optimization/');
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['optimization-history'] });
    },
  });
}
