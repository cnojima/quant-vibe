import { useState } from 'react';
import { useServices } from '../api/queries';
import { Card } from '../components/common/Card';
import { Badge } from '../components/common/Badge';
import { Button } from '../components/common/Button';
import { useServiceAction } from '../api/queries';
import { formatUptime } from '../utils/formatters';
import { LogViewer } from '../components/services/LogViewer';

export function Dashboard() {
  const { data: services, isLoading, error } = useServices();
  const serviceAction = useServiceAction();
  const [logViewerState, setLogViewerState] = useState<{
    isOpen: boolean;
    serviceName: string | null;
  }>({ isOpen: false, serviceName: null });

  const handleAction = (serviceName: string, action: 'start' | 'stop' | 'restart') => {
    serviceAction.mutate({ serviceName, action });
  };

  const openLogViewer = (serviceName: string) => {
    setLogViewerState({ isOpen: true, serviceName });
  };

  const closeLogViewer = () => {
    setLogViewerState({ isOpen: false, serviceName: null });
  };

  if (isLoading) {
    return (
      <div className="flex justify-center items-center h-64">
        <div className="text-gray-600">Loading services...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
        Failed to load services
      </div>
    );
  }

  // Ensure services is always an array
  const servicesList = Array.isArray(services) ? services : [];
  const runningCount = servicesList.filter((s) => s.status === 'running').length;
  const totalCount = servicesList.length;

  return (
    <div>
      <div className="mb-4 md:mb-6">
        <h1 className="text-2xl md:text-3xl font-bold text-gray-900">System Overview</h1>
        <p className="text-sm md:text-base text-gray-600 mt-1 md:mt-2">
          {runningCount === totalCount ? (
            <span className="text-green-600 font-medium">All Systems Operational</span>
          ) : (
            <span className="text-yellow-600 font-medium">
              {runningCount}/{totalCount} Services Running
            </span>
          )}
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-6">
        {servicesList.map((service) => {
          // Determine if this is a trading service
          const isLiveTradingReal = service.name === 'live_trading_real';
          const isLiveTradingPaper = service.name === 'live_trading_paper';
          const isTradingService = isLiveTradingReal || isLiveTradingPaper;

          return (
            <Card key={service.name} className={isTradingService ? 'border-2 border-blue-200 dark:border-blue-800' : ''}>
              <div className="flex justify-between items-start mb-4">
                <div className="flex flex-col gap-1">
                  <h3 className="text-lg font-semibold capitalize">
                    {service.name.replace(/_/g, ' ')}
                  </h3>
                  {isLiveTradingReal && (
                    <Badge variant="error" className="text-xs">
                      LIVE TRADING
                    </Badge>
                  )}
                  {isLiveTradingPaper && (
                    <Badge variant="default" className="text-xs">
                      PAPER TRADING
                    </Badge>
                  )}
                </div>
                <Badge
                  variant={
                    service.status === 'running'
                      ? 'success'
                      : service.status === 'error'
                      ? 'error'
                      : 'default'
                  }
                >
                  {service.status}
                </Badge>
              </div>

            <div className="space-y-2 mb-4">
              <div className="flex items-center text-sm">
                <span className="text-gray-600">Uptime:</span>
                <span className="ml-2 font-medium">
                  {service.status === 'running'
                    ? formatUptime(service.uptime_seconds)
                    : 'N/A'}
                </span>
              </div>
            </div>

            <div className="flex gap-2 flex-wrap">
              {service.status === 'running' ? (
                <>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => handleAction(service.name, 'stop')}
                    disabled={serviceAction.isPending}
                  >
                    Stop
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => handleAction(service.name, 'restart')}
                    disabled={serviceAction.isPending}
                  >
                    Restart
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => openLogViewer(service.name)}
                  >
                    Logs
                  </Button>
                </>
              ) : (
                <>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() => handleAction(service.name, 'start')}
                    disabled={serviceAction.isPending}
                  >
                    Start
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => openLogViewer(service.name)}
                  >
                    Logs
                  </Button>
                </>
              )}
            </div>
          </Card>
          );
        })}
      </div>

      {/* Log Viewer Modal */}
      {logViewerState.serviceName && (
        <LogViewer
          serviceName={logViewerState.serviceName}
          isOpen={logViewerState.isOpen}
          onClose={closeLogViewer}
        />
      )}
    </div>
  );
}
