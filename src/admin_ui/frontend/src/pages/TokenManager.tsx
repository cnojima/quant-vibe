import { useTokenStatus, useRefreshToken, useOAuthUrl } from '../api/queries';
import { Card } from '../components/common/Card';
import { Badge } from '../components/common/Badge';
import { Button } from '../components/common/Button';
import { formatDistanceToNow } from 'date-fns';
import { useState } from 'react';

export function TokenManager() {
  const { data: tokenStatus, isLoading, error, refetch: refetchTokenStatus } = useTokenStatus();
  const refreshToken = useRefreshToken();
  const { data: oauthData } = useOAuthUrl();
  const [showOAuthFlow, setShowOAuthFlow] = useState(false);

  const handleRefresh = () => {
    refreshToken.mutate();
  };

  const handleStartOAuth = () => {
    if (oauthData?.oauth_url) {
      // Open OAuth URL in new window
      const width = 600;
      const height = 700;
      const left = (window.screen.width - width) / 2;
      const top = (window.screen.height - height) / 2;
      window.open(
        oauthData.oauth_url,
        'schwab-oauth',
        `width=${width},height=${height},left=${left},top=${top}`
      );
      setShowOAuthFlow(true);
      // Poll for token status after OAuth
      const pollInterval = setInterval(() => {
        refetchTokenStatus();
      }, 3000);
      // Stop polling after 5 minutes
      setTimeout(() => clearInterval(pollInterval), 5 * 60 * 1000);
    }
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
    if (!tokenStatus?.has_token || tokenStatus?.access_token_expired) {
      return <Badge variant="error">Invalid/Expired</Badge>;
    }
    if (tokenStatus?.refresh_token_expired || tokenStatus?.is_refresh_token_expired) {
      return <Badge variant="error">Refresh Token Expired</Badge>;
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
      <div className="mb-4 md:mb-6">
        <h1 className="text-2xl md:text-3xl font-bold text-gray-900">Schwab API Token Manager</h1>
        <p className="text-sm md:text-base text-gray-600 mt-1 md:mt-2">
          Manage your Schwab API OAuth tokens
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 md:gap-6">
        <Card>
          <div className="flex justify-between items-start mb-4">
            <h3 className="text-lg font-semibold">Access Token</h3>
            {getStatusBadge()}
          </div>

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-gray-600">Status:</span>
              <span className="font-medium">
                {tokenStatus?.has_token && !tokenStatus?.access_token_expired && !tokenStatus?.refresh_token_expired && !tokenStatus?.is_refresh_token_expired ? 'Valid' : 'Invalid/Expired'}
              </span>
            </div>

            {tokenStatus?.has_token && !tokenStatus?.access_token_expired && (
              <div className="flex items-center justify-between">
                <span className="text-gray-600">Expires in:</span>
                <span className="font-medium font-mono">{getTimeRemaining()}</span>
              </div>
            )}

            {tokenStatus?.access_token_issued && (
              <div className="flex items-center justify-between">
                <span className="text-gray-600">Token Issued:</span>
                <span className="font-medium">
                  {formatDistanceToNow(new Date(tokenStatus.access_token_issued), { addSuffix: true })}
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

      {tokenStatus?.access_token_expired && (
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

      {(tokenStatus?.refresh_token_expired || tokenStatus?.is_refresh_token_expired) && !tokenStatus?.access_token_expired && (
        <Card className="mt-6 bg-orange-50 border-orange-200">
          <div className="flex items-start">
            <div className="flex-shrink-0">
              <svg className="h-6 w-6 text-orange-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
            <div className="ml-3 flex-1">
              <h3 className="text-orange-800 font-medium">Refresh Token Expired - Re-authentication Required</h3>
              <p className="text-orange-700 mt-2">
                Your access token is still valid, but the refresh token has expired. This means:
              </p>
              <ul className="list-disc list-inside text-orange-700 mt-2 space-y-1">
                <li>Current access token will expire and cannot be refreshed automatically</li>
                <li>Services will lose access when the current token expires</li>
                <li>You must complete OAuth re-authentication to obtain new tokens</li>
              </ul>

              <div className="mt-4">
                <Button
                  variant="primary"
                  onClick={handleStartOAuth}
                  disabled={!oauthData?.oauth_url}
                  className="bg-orange-600 hover:bg-orange-700"
                >
                  Start OAuth Authorization
                </Button>
              </div>

              {showOAuthFlow && (
                <div className="mt-4 bg-orange-100 border border-orange-300 rounded p-4">
                  <h4 className="font-semibold text-orange-900 mb-2">OAuth Flow Instructions:</h4>
                  <ol className="list-decimal list-inside text-orange-800 space-y-2">
                    <li>A new window should have opened with the Schwab login page</li>
                    <li>Log in with your Schwab account credentials</li>
                    <li>Authorize the application when prompted</li>
                    <li>You will be redirected to a success page</li>
                    <li>Close the OAuth window and return here</li>
                    <li>The token status will automatically update (polling every 3 seconds)</li>
                  </ol>
                  <p className="text-orange-700 mt-3 text-sm">
                    <strong>Note:</strong> If the window didn't open, check your popup blocker settings.
                  </p>
                </div>
              )}
            </div>
          </div>
        </Card>
      )}

      {(!tokenStatus?.has_token || tokenStatus?.requires_oauth) && (
        <Card className="mt-6 bg-blue-50 border-blue-200">
          <div className="flex items-start">
            <div className="flex-shrink-0">
              <svg className="h-6 w-6 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <div className="ml-3 flex-1">
              <h3 className="text-blue-800 font-medium text-lg">OAuth Authentication Required</h3>
              <p className="text-blue-700 mt-2">
                No valid Schwab API tokens found. You need to complete the OAuth authorization flow to obtain tokens.
              </p>

              <div className="mt-4">
                <Button
                  variant="primary"
                  onClick={handleStartOAuth}
                  disabled={!oauthData?.oauth_url}
                  className="bg-blue-600 hover:bg-blue-700"
                >
                  Start OAuth Authorization
                </Button>
              </div>

              {showOAuthFlow && (
                <div className="mt-4 bg-blue-100 border border-blue-300 rounded p-4">
                  <h4 className="font-semibold text-blue-900 mb-2">OAuth Flow Instructions:</h4>
                  <ol className="list-decimal list-inside text-blue-800 space-y-2">
                    <li>A new window should have opened with the Schwab login page</li>
                    <li>Log in with your Schwab account credentials</li>
                    <li>Authorize the application when prompted</li>
                    <li>You will be redirected to a success page</li>
                    <li>Close the OAuth window and return here</li>
                    <li>The token status will automatically update (polling every 3 seconds)</li>
                  </ol>
                  <p className="text-blue-700 mt-3 text-sm">
                    <strong>Note:</strong> If the window didn't open, check your popup blocker settings.
                  </p>
                </div>
              )}

              <div className="mt-4 bg-blue-100 border border-blue-300 rounded p-3">
                <h4 className="font-semibold text-blue-900 mb-1">What is OAuth?</h4>
                <p className="text-blue-800 text-sm">
                  OAuth is a secure authorization protocol that allows this application to access
                  your Schwab account data without storing your username or password. You'll log in
                  directly on Schwab's website, and they'll issue secure tokens for this app to use.
                </p>
              </div>

              {tokenStatus?.client_init_error && (
                <div className="mt-4 bg-yellow-100 border border-yellow-300 rounded p-3">
                  <h4 className="font-semibold text-yellow-900 mb-1">Initialization Error:</h4>
                  <p className="text-yellow-800 text-sm font-mono">
                    {tokenStatus.client_init_error}
                  </p>
                </div>
              )}
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
