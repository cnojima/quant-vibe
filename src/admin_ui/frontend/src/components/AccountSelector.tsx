import { useState, useEffect } from 'react';
import { ChevronDownIcon, CheckIcon, ArrowPathIcon, LinkIcon } from '@heroicons/react/24/outline';
import { useBrokerAccounts, useSetDefaultAccount, useRefreshAccounts } from '../api/queries';
import { useToast } from '../contexts/ToastContext';

interface AccountSelectorProps {
  tradingMode: 'real' | 'paper';
  selectedAccount: string | null;
  onAccountChange: (accountHash: string) => void;
}

export function AccountSelector({ tradingMode, selectedAccount, onAccountChange }: AccountSelectorProps) {
  const [isOpen, setIsOpen] = useState(false);
  const { data: accountsData, isLoading, refetch } = useBrokerAccounts(tradingMode);
  const setDefaultMutation = useSetDefaultAccount();
  const refreshMutation = useRefreshAccounts();
  const { addToast } = useToast();

  const accounts = accountsData?.accounts || [];

  // Auto-select default account on load
  useEffect(() => {
    if (!selectedAccount && accounts.length > 0) {
      const defaultAccount = accounts.find(acc => acc.is_default) || accounts[0];
      if (defaultAccount) {
        onAccountChange(defaultAccount.account_hash);
      }
    }
  }, [accounts, selectedAccount, onAccountChange]);

  const selectedAccountData = accounts.find(acc => acc.account_hash === selectedAccount);

  const handleSetDefault = (accountHash: string) => {
    setDefaultMutation.mutate(
      { accountHash, tradingMode },
      {
        onSuccess: () => {
          addToast({
            type: 'success',
            title: 'Default Account Updated',
            message: 'Successfully set as default account',
            duration: 4000,
          });
          refetch();
        },
        onError: (error: any) => {
          addToast({
            type: 'error',
            title: 'Failed to Set Default',
            message: error.response?.data?.detail || error.message || 'Could not update default account',
            duration: 5000,
          });
        },
      }
    );
  };

  const handleRefresh = () => {
    refreshMutation.mutate(tradingMode, {
      onSuccess: (data) => {
        addToast({
          type: 'success',
          title: 'Accounts Refreshed',
          message: `Successfully refreshed ${data?.count || 0} account(s)`,
          duration: 3000,
        });
        refetch();
      },
      onError: (error: any) => {
        addToast({
          type: 'error',
          title: 'Refresh Failed',
          message: error.response?.data?.detail || error.message || 'Could not refresh accounts',
          duration: 5000,
        });
      },
    });
  };

  if (isLoading) {
    return (
      <div className="flex items-center space-x-2">
        <div className="animate-pulse bg-gray-200 h-10 w-48 rounded"></div>
      </div>
    );
  }

  if (accounts.length === 0 && tradingMode === 'paper') {
    // Paper trading doesn't require real accounts
    return (
      <div className="text-sm text-gray-500">
        Paper Trading Mode (No Account Required)
      </div>
    );
  }

  if (accounts.length === 0) {
    return (
      <div className="flex items-center space-x-2">
        <span className="text-sm text-red-500">No accounts found</span>
        <button
          onClick={handleRefresh}
          className="p-1 hover:bg-gray-100 rounded"
          title="Refresh accounts"
        >
          <ArrowPathIcon className="h-4 w-4" />
        </button>
      </div>
    );
  }

  return (
    <div className="flex items-center space-x-2">
      <div className="relative">
        <button
          onClick={() => setIsOpen(!isOpen)}
          className="flex items-center space-x-2 px-4 py-2 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <div className="text-left">
            <div className="text-sm font-medium text-gray-900">
              {selectedAccountData?.nickname || 'Select Account'}
            </div>
            {selectedAccountData && (
              <div className="text-xs text-gray-500">
                {selectedAccountData.account_number} • {selectedAccountData.account_type}
                {selectedAccountData.is_day_trader && ' • Day Trader'}
              </div>
            )}
          </div>
          <ChevronDownIcon className={`h-5 w-5 text-gray-400 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
        </button>

        {isOpen && (
          <div className="absolute z-50 mt-2 w-80 bg-white border border-gray-200 rounded-lg shadow-lg">
            <div className="py-1">
              {accounts.map((account) => (
                <button
                  key={account.account_hash}
                  onClick={() => {
                    onAccountChange(account.account_hash);
                    setIsOpen(false);
                  }}
                  className="w-full px-4 py-3 hover:bg-gray-50 text-left"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center space-x-2">
                        <span className="font-medium text-gray-900">
                          {account.nickname}
                        </span>
                        {account.is_default && (
                          <span className="px-2 py-0.5 text-xs bg-blue-100 text-blue-700 rounded">
                            Default
                          </span>
                        )}
                        {account.account_hash === selectedAccount && (
                          <CheckIcon className="h-4 w-4 text-green-600" />
                        )}
                      </div>
                      <div className="mt-1 text-xs text-gray-500">
                        {account.account_number} • {account.account_type}
                        {account.is_day_trader && ' • Day Trader'}
                        {account.round_trips > 0 && ` • ${account.round_trips} Round Trips`}
                      </div>
                      <div className="mt-1 text-xs text-gray-400">
                        Hash: {account.account_hash.substring(0, 8)}...
                      </div>
                    </div>
                    {!account.is_default && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleSetDefault(account.account_hash);
                        }}
                        className="ml-2 text-xs text-blue-600 hover:text-blue-800"
                      >
                        Set Default
                      </button>
                    )}
                  </div>
                </button>
              ))}
            </div>

            <div className="border-t border-gray-200 px-4 py-2">
              <button
                onClick={() => {
                  setIsOpen(false);
                  addToast({
                    type: 'info',
                    title: 'Coming Soon',
                    message: 'Account management features will be available in a future update',
                    duration: 4000,
                  });
                }}
                className="text-sm text-blue-600 hover:text-blue-800"
              >
                + Add Account
              </button>
            </div>
          </div>
        )}
      </div>

      <button
        onClick={handleRefresh}
        disabled={refreshMutation.isPending}
        className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
        title="Refresh accounts from broker"
      >
        <ArrowPathIcon className={`h-5 w-5 ${refreshMutation.isPending ? 'animate-spin' : ''}`} />
      </button>

      <button
        onClick={() => {
          addToast({
            type: 'info',
            title: 'Order Sync Coming Soon',
            message: `Order synchronization for ${selectedAccountData?.nickname || 'this account'} will be available in a future update`,
            duration: 4000,
          });
        }}
        className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
        title="Sync orders from broker"
      >
        <LinkIcon className="h-5 w-5" />
      </button>
    </div>
  );
}