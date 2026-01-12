import { useState, useEffect, useRef } from 'react';
import { useServiceLogs } from '../../api/queries';
import { Button } from '../common/Button';
import { Card } from '../common/Card';

interface LogViewerProps {
  serviceName: string;
  isOpen: boolean;
  onClose: () => void;
}

export function LogViewer({ serviceName, isOpen, onClose }: LogViewerProps) {
  const [tail, setTail] = useState(100);
  const [isFollowing, setIsFollowing] = useState(false);
  const logsEndRef = useRef<HTMLDivElement>(null);

  const { data, isLoading, error, refetch } = useServiceLogs(serviceName, tail);

  // Auto-scroll to bottom when following
  useEffect(() => {
    if (isFollowing && logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [data, isFollowing]);

  // Auto-refresh when following (every 2 seconds)
  useEffect(() => {
    if (!isFollowing) return;

    const interval = setInterval(() => {
      refetch();
    }, 2000);

    return () => clearInterval(interval);
  }, [isFollowing, refetch]);

  if (!isOpen) return null;

  const handleRefresh = () => {
    refetch();
  };

  const toggleFollow = () => {
    setIsFollowing(!isFollowing);
  };

  const handleTailChange = (newTail: number) => {
    setTail(newTail);
    setIsFollowing(false); // Stop following when changing tail
  };

  // Strip Docker timestamps (ISO 8601 format) from log lines
  const cleanLogs = (logs: string) => {
    // Remove Docker timestamps like "2026-01-12T16:57:49.552072964Z "
    return logs.replace(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z\s+/gm, '');
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 p-4">
      <div className="w-full max-w-6xl h-[90vh] flex flex-col">
        <Card className="flex flex-col h-full overflow-hidden">
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4 pb-4 border-b border-gray-200 flex-shrink-0">
            <div className="flex items-center gap-3 flex-wrap">
              <h2 className="text-xl font-bold">
                {serviceName.replace(/_/g, ' ').replace(/-/g, ' ')} Logs
              </h2>
              <div className="flex gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleRefresh}
                  disabled={isLoading || isFollowing}
                >
                  {isLoading ? 'Loading...' : 'Refresh'}
                </Button>
                <Button
                  variant={isFollowing ? 'primary' : 'secondary'}
                  size="sm"
                  onClick={toggleFollow}
                >
                  {isFollowing ? 'Stop Following' : 'Follow Logs'}
                </Button>
              </div>
            </div>

            <div className="flex items-center gap-3">
              {/* Tail selector */}
              <select
                value={tail}
                onChange={(e) => handleTailChange(Number(e.target.value))}
                className="px-3 py-1 border border-gray-300 rounded-md text-sm"
                disabled={isFollowing}
              >
                <option value={50}>Last 50 lines</option>
                <option value={100}>Last 100 lines</option>
                <option value={200}>Last 200 lines</option>
                <option value={500}>Last 500 lines</option>
                <option value={1000}>Last 1000 lines</option>
              </select>

              <Button
                variant="secondary"
                size="sm"
                onClick={onClose}
              >
                Close
              </Button>
            </div>
          </div>

          {/* Logs Content */}
          <div className="flex-1 overflow-y-auto bg-gray-900 rounded-lg p-4">
            {isLoading && !data && (
              <div className="text-gray-400 text-center py-8">
                Loading logs...
              </div>
            )}

            {error && (
              <div className="text-red-400 text-center py-8">
                Failed to load logs: {(error as Error).message}
              </div>
            )}

            {data && data.logs && (
              <pre className="text-xs text-gray-100 font-mono whitespace-pre-wrap break-words">
                {cleanLogs(data.logs)}
              </pre>
            )}

            {data && !data.logs && (
              <div className="text-gray-400 text-center py-8">
                No logs available
              </div>
            )}

            <div ref={logsEndRef} />
          </div>

          {/* Footer info */}
          {data && (
            <div className="mt-4 pt-4 border-t border-gray-200 text-sm text-gray-600 flex-shrink-0">
              Showing {data.lines || 0} lines
              {isFollowing && (
                <span className="ml-2 text-green-600 font-medium">
                  • Live (refreshing every 2s)
                </span>
              )}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
