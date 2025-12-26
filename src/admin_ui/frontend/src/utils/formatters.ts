import { formatDistanceToNow, format } from 'date-fns';

export function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

export function formatPercent(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'percent',
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(value / 100);
}

export function formatNumber(value: number, decimals: number = 0): string {
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

export function formatDateTime(date: string | Date): string {
  return format(new Date(date), 'MMM d, yyyy HH:mm:ss');
}

export function formatDate(date: string | Date): string {
  return format(new Date(date), 'MMM d, yyyy');
}

export function formatTime(date: string | Date): string {
  return format(new Date(date), 'HH:mm:ss');
}

export function formatTimeAgo(date: string | Date): string {
  return formatDistanceToNow(new Date(date), { addSuffix: true });
}

export function formatUptime(seconds: number): string {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);

  const parts: string[] = [];
  if (days > 0) parts.push(`${days}d`);
  if (hours > 0) parts.push(`${hours}h`);
  if (minutes > 0 || parts.length === 0) parts.push(`${minutes}m`);

  return parts.join(' ');
}

export function formatTimeRemaining(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);

  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  } else if (minutes > 0) {
    return `${minutes}m ${secs}s`;
  } else {
    return `${secs}s`;
  }
}

export function getPnlColor(pnl: number): string {
  if (pnl > 0) return 'text-green-600';
  if (pnl < 0) return 'text-red-600';
  return 'text-gray-600';
}

export function getStatusColor(status: string): string {
  const statusColors: Record<string, string> = {
    running: 'text-green-600',
    stopped: 'text-gray-600',
    error: 'text-red-600',
    open: 'text-blue-600',
    closed: 'text-gray-600',
    pending: 'text-yellow-600',
    filled: 'text-green-600',
    cancelled: 'text-gray-600',
    rejected: 'text-red-600',
  };
  return statusColors[status] || 'text-gray-600';
}

export function getStatusBadgeColor(status: string): string {
  const statusColors: Record<string, string> = {
    running: 'bg-green-100 text-green-800',
    stopped: 'bg-gray-100 text-gray-800',
    error: 'bg-red-100 text-red-800',
    open: 'bg-blue-100 text-blue-800',
    closed: 'bg-gray-100 text-gray-800',
    pending: 'bg-yellow-100 text-yellow-800',
    filled: 'bg-green-100 text-green-800',
    cancelled: 'bg-gray-100 text-gray-800',
    rejected: 'bg-red-100 text-red-800',
  };
  return statusColors[status] || 'bg-gray-100 text-gray-800';
}
