import { useState } from 'react';
import { useServices, useServiceAction } from '../api/queries';
import { Card } from '../components/common/Card';
import { Badge } from '../components/common/Badge';
import { Button } from '../components/common/Button';
import { formatUptime } from '../utils/formatters';
import { LogViewer } from '../components/services/LogViewer';

interface ServiceCardProps {
  service: any;
  onAction: (name: string, action: 'start' | 'stop' | 'restart') => void;
  onViewLogs: (name: string) => void;
  isActionPending: boolean;
}

function ServiceCard({ service, onAction, onViewLogs, isActionPending }: ServiceCardProps) {
  const isLiveTradingReal = service.name === 'live_trading_real';
  const isLiveTradingPaper = service.name === 'live_trading_paper';
  const isTradingService = isLiveTradingReal || isLiveTradingPaper;
  const isRunning = service.status === 'running';

  function getStatusVariant(): 'success' | 'error' | 'default' {
    if (service.status === 'running') return 'success';
    if (service.status === 'error') return 'error';
    return 'default';
  }

  return (
    <Card className={isTradingService ? 'border-2 border-blue-200 dark:border-blue-800' : ''}>
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
        <Badge variant={getStatusVariant()}>
          {service.status}
        </Badge>
      </div>

      <div className="space-y-2 mb-4">
        <div className="flex items-center text-sm">
          <span className="text-gray-600">Uptime:</span>
          <span className="ml-2 font-medium">
            {isRunning ? formatUptime(service.uptime_seconds) : 'N/A'}
          </span>
        </div>
      </div>

      <div className="flex gap-2 flex-wrap">
        {isRunning ? (
          <>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => onAction(service.name, 'stop')}
              disabled={isActionPending}
            >
              Stop
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => onAction(service.name, 'restart')}
              disabled={isActionPending}
            >
              Restart
            </Button>
          </>
        ) : (
          <Button
            variant="primary"
            size="sm"
            onClick={() => onAction(service.name, 'start')}
            disabled={isActionPending}
          >
            Start
          </Button>
        )}
        <Button
          variant="secondary"
          size="sm"
          onClick={() => onViewLogs(service.name)}
        >
          Logs
        </Button>
      </div>
    </Card>
  );
}

export function Dashboard() {
  const { data: services, isLoading, error } = useServices();
  const serviceAction = useServiceAction();
  const [logViewer, setLogViewer] = useState<{
    isOpen: boolean;
    serviceName: string | null;
  }>({ isOpen: false, serviceName: null });

  const servicesList = Array.isArray(services) ? services : [];
  const runningCount = servicesList.filter((s) => s.status === 'running').length;
  const totalCount = servicesList.length;

  function handleAction(serviceName: string, action: 'start' | 'stop' | 'restart'): void {
    serviceAction.mutate({ serviceName, action });
  }

  function openLogViewer(serviceName: string): void {
    setLogViewer({ isOpen: true, serviceName });
  }

  function closeLogViewer(): void {
    setLogViewer({ isOpen: false, serviceName: null });
  }

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
        {servicesList.map((service) => (
          <ServiceCard
            key={service.name}
            service={service}
            onAction={handleAction}
            onViewLogs={openLogViewer}
            isActionPending={serviceAction.isPending}
          />
        ))}
      </div>

      {logViewer.serviceName && (
        <LogViewer
          serviceName={logViewer.serviceName}
          isOpen={logViewer.isOpen}
          onClose={closeLogViewer}
        />
      )}
    </div>
  );
}