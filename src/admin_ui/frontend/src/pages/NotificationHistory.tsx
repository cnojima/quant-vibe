import { useState, useEffect } from 'react';
import { Card } from '../components/common/Card';
import { Badge } from '../components/common/Badge';
import { Button } from '../components/common/Button';
import { InfoIcon } from '../components/common/InfoIcon';
import apiClient from '../api/client';
import { formatDistanceToNow } from 'date-fns';

interface NotificationRecord {
  notification_id: number;
  title: string | null;
  message: string;
  notification_type: string;
  priority: number;
  sound: string | null;
  device: string | null;
  sent_successfully: boolean;
  error_message: string | null;
  metadata: any;
  url: string | null;
  url_title: string | null;
  sent_at: string;
}

interface NotificationStats {
  notification_type: string;
  total_count: number;
  success_count: number;
  failure_count: number;
  success_rate: number;
}

export function NotificationHistory() {
  const [notifications, setNotifications] = useState<NotificationRecord[]>([]);
  const [stats, setStats] = useState<NotificationStats[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedType, setSelectedType] = useState<string>('');
  const [showOnlyErrors, setShowOnlyErrors] = useState(false);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [perPage] = useState(50);
  const [statsDays, setStatsDays] = useState(30);
  const [availableTypes, setAvailableTypes] = useState<string[]>([]);
  const [selectedTab, setSelectedTab] = useState<'list' | 'stats'>('list');

  // Fetch notification types
  useEffect(() => {
    fetchTypes();
  }, []);

  // Fetch notifications when filters or page change
  useEffect(() => {
    if (selectedTab === 'list') {
      fetchNotifications();
    }
  }, [page, selectedType, showOnlyErrors, selectedTab]);

  // Fetch stats when stats tab is selected or days change
  useEffect(() => {
    if (selectedTab === 'stats') {
      fetchStats();
    }
  }, [statsDays, selectedTab]);

  const fetchTypes = async () => {
    try {
      const response = await apiClient.get('/notifications/types');
      setAvailableTypes(response.data.types || []);
    } catch (error) {
      console.error('Failed to fetch notification types:', error);
    }
  };

  const fetchNotifications = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        page: page.toString(),
        per_page: perPage.toString(),
      });

      if (selectedType) {
        params.append('notification_type', selectedType);
      }

      if (showOnlyErrors) {
        params.append('sent_successfully', 'false');
      }

      const response = await apiClient.get(`/notifications/history?${params}`);
      setNotifications(response.data.notifications || []);
      setTotal(response.data.total || 0);
    } catch (error) {
      console.error('Failed to fetch notifications:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchStats = async () => {
    setLoading(true);
    try {
      const response = await apiClient.get(`/notifications/stats?days=${statsDays}`);
      setStats(response.data.stats || []);
    } catch (error) {
      console.error('Failed to fetch notification stats:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleCleanup = async () => {
    if (!confirm('Delete notifications older than 90 days?')) {
      return;
    }

    try {
      const response = await apiClient.post('/notifications/cleanup?days=90');
      alert(response.data.message);
      fetchNotifications();
      fetchStats();
    } catch (error: any) {
      alert(`Failed to cleanup notifications: ${error.response?.data?.detail || error.message}`);
    }
  };

  const getPriorityBadge = (priority: number) => {
    const priorityMap: Record<number, { label: string; variant: 'info' | 'success' | 'warning' | 'error' }> = {
      [-2]: { label: 'Lowest', variant: 'info' },
      [-1]: { label: 'Low', variant: 'info' },
      [0]: { label: 'Normal', variant: 'success' },
      [1]: { label: 'High', variant: 'warning' },
      [2]: { label: 'Emergency', variant: 'error' },
    };

    const config = priorityMap[priority] || { label: 'Unknown', variant: 'info' };
    return <Badge variant={config.variant}>{config.label}</Badge>;
  };

  const getTypeBadge = (type: string) => {
    const typeMap: Record<string, 'info' | 'success' | 'warning' | 'error'> = {
      'order_filled': 'success',
      'position_opened': 'info',
      'position_closed': 'success',
      'critical_alert': 'error',
      'warning': 'warning',
      'info': 'info',
      'engine_started': 'success',
      'engine_stopped': 'warning',
      'optimization_complete': 'success',
      'optimization_failed': 'error',
      'backtest_complete': 'success',
      'backtest_failed': 'error',
    };

    return <Badge variant={typeMap[type] || 'info'}>{type}</Badge>;
  };

  const totalPages = Math.ceil(total / perPage);

  return (
    <div>
      <div className="mb-4 md:mb-6">
        <h1 className="text-2xl md:text-3xl font-bold text-gray-900">Notification History</h1>
        <p className="text-sm md:text-base text-gray-600 mt-1 md:mt-2">
          View and analyze all push notifications sent by the system
        </p>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200 mb-6">
        <nav className="-mb-px flex space-x-8">
          <button
            onClick={() => setSelectedTab('list')}
            className={`py-4 px-1 border-b-2 font-medium text-sm ${
              selectedTab === 'list'
                ? 'border-indigo-500 text-indigo-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            Notification List
          </button>
          <button
            onClick={() => setSelectedTab('stats')}
            className={`py-4 px-1 border-b-2 font-medium text-sm ${
              selectedTab === 'stats'
                ? 'border-indigo-500 text-indigo-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            Statistics
          </button>
        </nav>
      </div>

      {selectedTab === 'list' && (
        <>
          {/* Filters */}
          <Card className="mb-6">
            <div className="flex items-center gap-2 mb-4">
              <h3 className="text-lg font-semibold">Filters</h3>
              <InfoIcon content="Filter notification history by type and status" />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Notification Type
                </label>
                <select
                  value={selectedType}
                  onChange={(e) => {
                    setSelectedType(e.target.value);
                    setPage(1);
                  }}
                  className="w-full border border-gray-300 rounded-md p-2"
                >
                  <option value="">All Types</option>
                  {availableTypes.map((type) => (
                    <option key={type} value={type}>
                      {type}
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex items-end">
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={showOnlyErrors}
                    onChange={(e) => {
                      setShowOnlyErrors(e.target.checked);
                      setPage(1);
                    }}
                    className="mr-2"
                  />
                  <span className="text-sm text-gray-700">Show only failed notifications</span>
                </label>
              </div>

              <div className="flex items-end justify-end">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleCleanup}
                >
                  Cleanup Old (90+ days)
                </Button>
              </div>
            </div>
          </Card>

          {/* Notifications List */}
          <Card>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold">
                Notifications ({total} total)
              </h3>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => fetchNotifications()}
                disabled={loading}
              >
                {loading ? 'Loading...' : 'Refresh'}
              </Button>
            </div>

            {loading && notifications.length === 0 ? (
              <div className="text-center py-8 text-gray-500">Loading notifications...</div>
            ) : notifications.length === 0 ? (
              <div className="text-center py-8 text-gray-500">No notifications found</div>
            ) : (
              <div className="space-y-4">
                {notifications.map((notification) => (
                  <div
                    key={notification.notification_id}
                    className={`border rounded-lg p-4 ${
                      !notification.sent_successfully ? 'border-red-300 bg-red-50' : 'border-gray-200'
                    }`}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2">
                          <h4 className="font-semibold text-gray-900">
                            {notification.title || 'No title'}
                          </h4>
                          {getTypeBadge(notification.notification_type)}
                          {getPriorityBadge(notification.priority)}
                          {!notification.sent_successfully && (
                            <Badge variant="error">Failed</Badge>
                          )}
                        </div>

                        <p className="text-sm text-gray-700 mb-2 whitespace-pre-wrap">
                          {notification.message}
                        </p>

                        {notification.error_message && (
                          <div className="bg-red-100 border border-red-300 rounded p-2 mb-2">
                            <p className="text-xs text-red-800">
                              <strong>Error:</strong> {notification.error_message}
                            </p>
                          </div>
                        )}

                        <div className="flex items-center gap-4 text-xs text-gray-500">
                          <span>
                            {formatDistanceToNow(new Date(notification.sent_at), { addSuffix: true })}
                          </span>
                          {notification.device && <span>Device: {notification.device}</span>}
                          {notification.sound && <span>Sound: {notification.sound}</span>}
                        </div>

                        {notification.metadata && Object.keys(notification.metadata).length > 0 && (
                          <details className="mt-2">
                            <summary className="text-xs text-blue-600 cursor-pointer">
                              Show metadata
                            </summary>
                            <pre className="text-xs bg-gray-100 p-2 rounded mt-1 overflow-x-auto">
                              {JSON.stringify(notification.metadata, null, 2)}
                            </pre>
                          </details>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between mt-6 pt-4 border-t">
                <div className="text-sm text-gray-600">
                  Page {page} of {totalPages}
                </div>
                <div className="flex gap-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => setPage(Math.max(1, page - 1))}
                    disabled={page === 1}
                  >
                    Previous
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => setPage(Math.min(totalPages, page + 1))}
                    disabled={page === totalPages}
                  >
                    Next
                  </Button>
                </div>
              </div>
            )}
          </Card>
        </>
      )}

      {selectedTab === 'stats' && (
        <>
          {/* Stats Period Selector */}
          <Card className="mb-6">
            <div className="flex items-center gap-2 mb-4">
              <h3 className="text-lg font-semibold">Analysis Period</h3>
              <InfoIcon content="Select time period for statistics analysis" />
            </div>

            <div className="flex items-center gap-4">
              <label className="text-sm font-medium text-gray-700">
                Last
              </label>
              <select
                value={statsDays}
                onChange={(e) => setStatsDays(parseInt(e.target.value))}
                className="border border-gray-300 rounded-md p-2"
              >
                <option value="7">7 days</option>
                <option value="30">30 days</option>
                <option value="90">90 days</option>
                <option value="180">180 days</option>
                <option value="365">1 year</option>
              </select>
            </div>
          </Card>

          {/* Stats Table */}
          <Card>
            <h3 className="text-lg font-semibold mb-4">Notification Statistics</h3>

            {loading && stats.length === 0 ? (
              <div className="text-center py-8 text-gray-500">Loading statistics...</div>
            ) : stats.length === 0 ? (
              <div className="text-center py-8 text-gray-500">No notifications in this period</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Type
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Total
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Success
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Failed
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Success Rate
                      </th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {stats.map((stat) => (
                      <tr key={stat.notification_type}>
                        <td className="px-6 py-4 whitespace-nowrap">
                          {getTypeBadge(stat.notification_type)}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                          {stat.total_count}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-green-600">
                          {stat.success_count}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-red-600">
                          {stat.failure_count}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="flex items-center">
                            <div className="w-24 bg-gray-200 rounded-full h-4 mr-2">
                              <div
                                className={`h-4 rounded-full ${
                                  stat.success_rate >= 95 ? 'bg-green-500' :
                                  stat.success_rate >= 80 ? 'bg-yellow-500' :
                                  'bg-red-500'
                                }`}
                                style={{ width: `${stat.success_rate}%` }}
                              ></div>
                            </div>
                            <span className="text-sm text-gray-700">
                              {stat.success_rate.toFixed(1)}%
                            </span>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
