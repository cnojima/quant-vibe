import { useQuery, useMutation, useQueryClient, UseQueryOptions } from '@tanstack/react-query';
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
} from '../types/api';

// Auth queries
export function useLogin() {
  return useMutation({
    mutationFn: async (data: LoginRequest) => {
      const formData = new FormData();
      formData.append('username', data.username);
      formData.append('password', data.password);

      const response = await apiClient.post<LoginResponse>('/auth/login', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
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
      const response = await apiClient.get<Service[]>('/services/');
      return response.data;
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
      const response = await apiClient.get<Position[]>('/live/positions', {
        params: { status, limit },
      });
      return response.data;
    },
    refetchInterval: 5000,
  });
}

export function useLiveOrders(limit: number = 100) {
  return useQuery({
    queryKey: ['live-orders', limit],
    queryFn: async () => {
      const response = await apiClient.get<Order[]>('/live/orders', {
        params: { limit },
      });
      return response.data;
    },
    refetchInterval: 5000,
  });
}

export function useLiveEvents(limit: number = 100, eventType?: string, severity?: string) {
  return useQuery({
    queryKey: ['live-events', limit, eventType, severity],
    queryFn: async () => {
      const response = await apiClient.get<Event[]>('/live/events', {
        params: { limit, event_type: eventType, severity },
      });
      return response.data;
    },
    refetchInterval: 5000,
  });
}

export function useLiveStats(startTime?: string, endTime?: string) {
  return useQuery({
    queryKey: ['live-stats', startTime, endTime],
    queryFn: async () => {
      const response = await apiClient.get<TradingStats>('/live/stats', {
        params: { start_time: startTime, end_time: endTime },
      });
      return response.data;
    },
  });
}

// Backtest queries
export function useStrategies() {
  return useQuery({
    queryKey: ['strategies'],
    queryFn: async () => {
      const response = await apiClient.get<Strategy[]>('/backtests/strategies');
      return response.data;
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
    refetchInterval: (data) => {
      // Stop polling when completed or failed
      if (data?.status === 'completed' || data?.status === 'failed') {
        return false;
      }
      return 2000; // Poll every 2 seconds while running
    },
  });
}

export function useBacktestResults(backtestId: string | null) {
  return useQuery({
    queryKey: ['backtest-results', backtestId],
    queryFn: async () => {
      if (!backtestId) throw new Error('No backtest ID');
      const response = await apiClient.get<BacktestResult>(`/backtests/${backtestId}/results`);
      return response.data;
    },
    enabled: !!backtestId,
  });
}

export function useBacktestHistory(limit: number = 50) {
  return useQuery({
    queryKey: ['backtest-history', limit],
    queryFn: async () => {
      const response = await apiClient.get<BacktestResult[]>('/backtests/history', {
        params: { limit },
      });
      return response.data;
    },
  });
}
