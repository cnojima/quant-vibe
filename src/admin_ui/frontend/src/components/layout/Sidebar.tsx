import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  HomeIcon,
  CpuChipIcon,
  KeyIcon,
  ChartBarIcon,
  BeakerIcon,
} from '@heroicons/react/24/outline';

const navigation = [
  { name: 'Dashboard', href: '/', icon: HomeIcon },
  { name: 'Services', href: '/services', icon: CpuChipIcon },
  { name: 'Token Manager', href: '/tokens', icon: KeyIcon },
  { name: 'Live Trading', href: '/live', icon: ChartBarIcon },
  { name: 'Backtest', href: '/backtest', icon: BeakerIcon },
];

export function Sidebar() {
  return (
    <div className="w-64 bg-gray-800 min-h-screen">
      <nav className="mt-5 px-2">
        <div className="space-y-1">
          {navigation.map((item) => (
            <NavLink
              key={item.name}
              to={item.href}
              end={item.href === '/'}
              className={({ isActive }) =>
                `group flex items-center px-3 py-2 text-sm font-medium rounded-md transition-colors ${
                  isActive
                    ? 'bg-gray-900 text-white'
                    : 'text-gray-300 hover:bg-gray-700 hover:text-white'
                }`
              }
            >
              <item.icon className="mr-3 h-5 w-5 flex-shrink-0" aria-hidden="true" />
              {item.name}
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  );
}
