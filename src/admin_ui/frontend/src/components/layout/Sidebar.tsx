import { NavLink } from 'react-router-dom';
import {
  HomeIcon,
  CpuChipIcon,
  KeyIcon,
  ChartBarIcon,
  BeakerIcon,
  Cog6ToothIcon,
  PuzzlePieceIcon,
} from '@heroicons/react/24/outline';

const navigation = [
  { name: 'Dashboard', href: '/', icon: HomeIcon },
  { name: 'Services', href: '/services', icon: CpuChipIcon },
  { name: 'Token Manager', href: '/tokens', icon: KeyIcon },
  { name: 'Live Trading', href: '/live', icon: ChartBarIcon },
  { name: 'Strategies', href: '/strategies', icon: PuzzlePieceIcon },
  { name: 'Backtest', href: '/backtest', icon: BeakerIcon },
  { name: 'Configuration', href: '/config', icon: Cog6ToothIcon },
];

interface SidebarProps {
  collapsed: boolean;
  mobileOpen: boolean;
  onClose: () => void;
}

export function Sidebar({ collapsed, mobileOpen, onClose }: SidebarProps) {
  return (
    <div
      className={`
        bg-gray-800 transition-all duration-300 z-50

        /* Always fixed position */
        fixed inset-y-0 left-0 h-screen overflow-y-auto

        /* Mobile: slides in from left when open */
        ${mobileOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}

        /* Width: responsive based on collapsed state */
        ${collapsed ? 'w-16' : 'w-64'}
      `}
    >
      <nav className="mt-5 px-2">
        <div className="space-y-1">
          {navigation.map((item) => (
            <NavLink
              key={item.name}
              to={item.href}
              end={item.href === '/'}
              onClick={onClose}
              className={({ isActive }) =>
                `group flex items-center px-3 py-3 md:py-2 text-sm font-medium rounded-md transition-colors min-h-[44px] ${
                  isActive
                    ? 'bg-gray-900 text-white'
                    : 'text-gray-300 hover:bg-gray-700 hover:text-white'
                }`
              }
              title={collapsed ? item.name : undefined}
            >
              <item.icon
                className={`h-6 w-6 md:h-5 md:w-5 flex-shrink-0 ${
                  collapsed ? 'md:mr-0' : 'mr-3'
                }`}
                aria-hidden="true"
              />
              <span className={collapsed ? 'md:hidden' : ''}>{item.name}</span>
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  );
}
