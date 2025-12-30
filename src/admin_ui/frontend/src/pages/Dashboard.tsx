import { useServices } from '../api/queries';
import { Card } from '../components/common/Card';
import { Badge } from '../components/common/Badge';
import { Button } from '../components/common/Button';
import { useServiceAction } from '../api/queries';
import { formatUptime } from '../utils/formatters';

export function Dashboard() {
  const { data: services, isLoading, error } = useServices();
  const serviceAction = useServiceAction();

  const handleAction = (serviceName: string, action: 'start' | 'stop' | 'restart') => {
    serviceAction.mutate({ serviceName, action });
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
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-gray-900">System Overview</h1>
        <p className="text-gray-600 mt-2">
          {runningCount === totalCount ? (
            <span className="text-green-600 font-medium">All Systems Operational</span>
          ) : (
            <span className="text-yellow-600 font-medium">
              {runningCount}/{totalCount} Services Running
            </span>
          )}
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {servicesList.map((service) => (
          <Card key={service.name}>
            <div className="flex justify-between items-start mb-4">
              <h3 className="text-lg font-semibold capitalize">
                {service.name.replace(/_/g, ' ')}
              </h3>
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

            <div className="flex gap-2">
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
                </>
              ) : (
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => handleAction(service.name, 'start')}
                  disabled={serviceAction.isPending}
                >
                  Start
                </Button>
              )}
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
