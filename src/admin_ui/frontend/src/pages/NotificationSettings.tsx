import { useState } from 'react';
import { Card } from '../components/common/Card';
import { Button } from '../components/common/Button';
import { InfoIcon } from '../components/common/InfoIcon';
import apiClient from '../api/client';

export function NotificationSettings() {
  const [testStatus, setTestStatus] = useState<'idle' | 'sending' | 'success' | 'error'>('idle');
  const [statusMessage, setStatusMessage] = useState<string>('');

  const handleTestNotification = async () => {
    setTestStatus('sending');
    setStatusMessage('Sending test notification...');

    try {
      const response = await apiClient.post('/optimization/test-notification');

      if (response.data.sent) {
        setTestStatus('success');
        setStatusMessage('✅ Test notification sent successfully! Check your Pushover app.');
      } else {
        setTestStatus('error');
        setStatusMessage(`❌ Failed to send notification: ${response.data.message || 'Unknown error'}`);
      }
    } catch (error: any) {
      setTestStatus('error');
      const errorMsg = error.response?.data?.detail || error.message || 'Unknown error';
      setStatusMessage(`❌ Error: ${errorMsg}`);
    }
  };

  return (
    <div>
      <div className="mb-4 md:mb-6">
        <h1 className="text-2xl md:text-3xl font-bold text-gray-900">Notification Settings</h1>
        <p className="text-sm md:text-base text-gray-600 mt-1 md:mt-2">
          Configure push notifications for long-running tasks
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Pushover Configuration */}
        <Card>
          <div className="flex items-center gap-2 mb-4">
            <h3 className="text-lg font-semibold">Pushover Configuration</h3>
            <InfoIcon
              content="Pushover sends push notifications to your mobile device when optimizations complete. Get API credentials from pushover.net"
              placement="right"
            />
          </div>

          <div className="space-y-4">
            <div className="p-4 bg-blue-50 border border-blue-200 rounded">
              <h4 className="font-medium text-blue-900 mb-2">Setup Instructions</h4>
              <ol className="text-sm text-blue-700 space-y-2 list-decimal list-inside">
                <li>Create account at <a href="https://pushover.net" target="_blank" rel="noopener noreferrer" className="underline">pushover.net</a></li>
                <li>Install Pushover app on your phone</li>
                <li>Get your User Key from the dashboard</li>
                <li>Create an API token for your application</li>
                <li>Add credentials to your <code className="bg-blue-100 px-1 rounded">.env</code> file</li>
              </ol>
            </div>

            <div className="p-4 bg-gray-50 border border-gray-200 rounded">
              <h4 className="font-medium text-gray-900 mb-2">Environment Variables</h4>
              <div className="space-y-2 text-sm font-mono">
                <div>
                  <div className="text-gray-600">PUSHOVER_API_TOKEN</div>
                  <div className="text-xs text-gray-500">Your application API token</div>
                </div>
                <div>
                  <div className="text-gray-600">PUSHOVER_USER_KEY</div>
                  <div className="text-xs text-gray-500">Your user/group key</div>
                </div>
                <div>
                  <div className="text-gray-600">PUSHOVER_ENABLED</div>
                  <div className="text-xs text-gray-500">true (enables notifications)</div>
                </div>
              </div>
            </div>

            <div className="p-4 bg-yellow-50 border border-yellow-200 rounded">
              <h4 className="font-medium text-yellow-900 mb-2">Notification Events</h4>
              <ul className="text-sm text-yellow-700 space-y-1">
                <li>✅ Optimization completed (with results)</li>
                <li>❌ Optimization failed (with error)</li>
                <li>⏱️ Optimization timeout (after 1 hour)</li>
                <li>📊 Includes runtime and performance metrics</li>
              </ul>
            </div>

            <Button
              variant="primary"
              className="w-full"
              onClick={handleTestNotification}
              disabled={testStatus === 'sending'}
            >
              {testStatus === 'sending' ? 'Sending...' : 'Send Test Notification'}
            </Button>

            {statusMessage && (
              <div className={`p-3 rounded border ${
                testStatus === 'success'
                  ? 'bg-green-50 border-green-200 text-green-800'
                  : testStatus === 'error'
                  ? 'bg-red-50 border-red-200 text-red-800'
                  : 'bg-blue-50 border-blue-200 text-blue-800'
              }`}>
                {statusMessage}
              </div>
            )}
          </div>
        </Card>

        {/* Notification Examples */}
        <Card>
          <div className="flex items-center gap-2 mb-4">
            <h3 className="text-lg font-semibold">Notification Examples</h3>
            <InfoIcon
              content="See what push notifications look like for different events"
              placement="right"
            />
          </div>

          <div className="space-y-4">
            {/* Success Example */}
            <div className="p-4 bg-white border border-gray-200 rounded shadow-sm">
              <div className="flex items-start gap-3">
                <div className="text-2xl">✅</div>
                <div className="flex-1">
                  <div className="font-semibold text-gray-900">Optimization Complete: bullish_vertical_put</div>
                  <div className="text-sm text-gray-600 mt-1 space-y-1">
                    <div>Optimization opt_20260101_143022 finished successfully.</div>
                    <div>Best Sharpe: 2.45</div>
                    <div>Best Return: +12.34%</div>
                    <div>Runtime: 23.5 min</div>
                  </div>
                  <div className="text-xs text-gray-500 mt-2">Sound: cashregister</div>
                </div>
              </div>
            </div>

            {/* Failure Example */}
            <div className="p-4 bg-white border border-gray-200 rounded shadow-sm">
              <div className="flex items-start gap-3">
                <div className="text-2xl">❌</div>
                <div className="flex-1">
                  <div className="font-semibold text-gray-900">Optimization Failed: bullish_vertical_put</div>
                  <div className="text-sm text-gray-600 mt-1 space-y-1">
                    <div>Optimization opt_20260101_143022 failed.</div>
                    <div>Error: Database connection timeout</div>
                    <div>Runtime: 5.2 min</div>
                  </div>
                  <div className="text-xs text-gray-500 mt-2">Sound: siren • Priority: High</div>
                </div>
              </div>
            </div>

            {/* Info Box */}
            <div className="p-4 bg-gray-50 border border-gray-200 rounded">
              <h4 className="font-medium text-gray-900 mb-2">Features</h4>
              <ul className="text-sm text-gray-700 space-y-1">
                <li>📱 Push to all devices or specific device</li>
                <li>🔊 Custom sounds for different events</li>
                <li>⚡ High priority for failures (overrides quiet hours)</li>
                <li>🔗 Deep links to result pages (future)</li>
                <li>📊 Quick metrics in notification</li>
              </ul>
            </div>

            {/* Cost Info */}
            <div className="p-4 bg-blue-50 border border-blue-200 rounded">
              <h4 className="font-medium text-blue-900 mb-2">Pushover Pricing</h4>
              <div className="text-sm text-blue-700 space-y-1">
                <div>• <strong>$5 one-time</strong> per platform (iOS, Android)</div>
                <div>• Unlimited apps and notifications</div>
                <div>• No monthly fees or limits</div>
                <div>• 10,000 messages/month included</div>
              </div>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
