import { useTokenStatus, useRefreshToken } from '../api/queries';
import { Card } from '../components/common/Card';
import { Badge } from '../components/common/Badge';
import { Button } from '../components/common/Button';
import { formatDistanceToNow } from 'date-fns';

export function TokenManager() {
  const { data: tokenStatus, isLoading, error } = useTokenStatus();
  const refreshToken = useRefreshToken();

  const handleRefresh = () => {
    refreshToken.mutate();
  };

  if (isLoading) {
    return (
      <div className="flex justify-center items-center h-64">
        <div className="text-gray-600">Loading token status...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
        Failed to load token status
      </div>
    );
  }

  const getStatusBadge = () => {
    if (!tokenStatus?.access_token_valid) {
      return <Badge variant="error">Invalid/Expired</Badge>;
    }
    if (tokenStatus.expires_in && tokenStatus.expires_in < 300) {
      return <Badge variant="warning">Expiring Soon</Badge>;
    }
    return <Badge variant="success">Valid</Badge>;
  };

  const getTimeRemaining = () => {
    if (!tokenStatus?.expires_in) return 'Unknown';

    const seconds = tokenStatus.expires_in;
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;

    if (hours > 0) {
      return `${hours}h ${minutes}m ${secs}s`;
    }
    if (minutes > 0) {
      return `${minutes}m ${secs}s`;
    }
    return `${secs}s`;
  };

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-gray-900">Schwab API Token Manager</h1>
        <p className="text-gray-600 mt-2">
          Manage your Schwab API OAuth tokens
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <div className="flex justify-between items-start mb-4">
            <h3 className="text-lg font-semibold">Access Token</h3>
            {getStatusBadge()}
          </div>

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-gray-600">Status:</span>
              <span className="font-medium">
                {tokenStatus?.access_token_valid ? 'Valid' : 'Invalid/Expired'}
              </span>
            </div>

            {tokenStatus?.access_token_valid && (
              <div className="flex items-center justify-between">
                <span className="text-gray-600">Expires in:</span>
                <span className="font-medium font-mono">{getTimeRemaining()}</span>
              </div>
            )}

            {tokenStatus?.last_refreshed && (
              <div className="flex items-center justify-between">
                <span className="text-gray-600">Last Refreshed:</span>
                <span className="font-medium">
                  {formatDistanceToNow(new Date(tokenStatus.last_refreshed), { addSuffix: true })}
                </span>
              </div>
            )}

            {tokenStatus?.source && (
              <div className="flex items-center justify-between">
                <span className="text-gray-600">Source:</span>
                <span className="font-medium">{tokenStatus.source}</span>
              </div>
            )}
          </div>

          <div className="mt-6">
            <Button
              variant="primary"
              onClick={handleRefresh}
              disabled={refreshToken.isPending}
              className="w-full"
            >
              {refreshToken.isPending ? 'Refreshing...' : 'Refresh Token'}
            </Button>
          </div>

          {refreshToken.isSuccess && (
            <div className="mt-4 bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded">
              Token refreshed successfully!
            </div>
          )}

          {refreshToken.isError && (
            <div className="mt-4 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
              Failed to refresh token. Please check logs.
            </div>
          )}
        </Card>

        <Card>
          <h3 className="text-lg font-semibold mb-4">Token Information</h3>

          <div className="space-y-3 text-sm">
            <div className="bg-blue-50 border border-blue-200 rounded p-3">
              <p className="text-blue-900 font-medium mb-1">OAuth Token Lifecycle</p>
              <p className="text-blue-700">
                Schwab API access tokens expire after 30 minutes. The token service
                automatically refreshes them every 14 minutes to maintain uninterrupted
                access.
              </p>
            </div>

            <div className="bg-yellow-50 border border-yellow-200 rounded p-3">
              <p className="text-yellow-900 font-medium mb-1">Expiring Soon Warning</p>
              <p className="text-yellow-700">
                If the token expires in less than 5 minutes, you'll see a warning badge.
                Click "Refresh Token" to manually refresh it.
              </p>
            </div>

            <div className="bg-gray-50 border border-gray-200 rounded p-3">
              <p className="text-gray-900 font-medium mb-1">Token Service</p>
              <p className="text-gray-700">
                The centralized token service manages tokens for all services
                (streaming, live trading, admin UI). Manual refresh is rarely needed.
              </p>
            </div>
          </div>
        </Card>
      </div>

      {tokenStatus?.access_token_valid === false && (
        <Card className="mt-6 bg-red-50 border-red-200">
          <div className="flex items-start">
            <div className="flex-shrink-0">
              <svg className="h-6 w-6 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
            <div className="ml-3">
              <h3 className="text-red-800 font-medium">Token Invalid or Expired</h3>
              <p className="text-red-700 mt-2">
                Your Schwab API access token is invalid or has expired. This may affect:
              </p>
              <ul className="list-disc list-inside text-red-700 mt-2 space-y-1">
                <li>Real-time data streaming</li>
                <li>Live trading operations</li>
                <li>Order placement and management</li>
              </ul>
              <p className="text-red-700 mt-2">
                Click "Refresh Token" above to attempt automatic refresh. If that fails,
                you may need to re-authenticate through the Schwab OAuth flow.
              </p>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
