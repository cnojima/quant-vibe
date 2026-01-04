import { NavLink } from 'react-router-dom';
import {
  CpuChipIcon,
  KeyIcon,
  ChartBarIcon,
  BeakerIcon,
  Cog6ToothIcon,
  PuzzlePieceIcon,
  Bars3Icon,
  SparklesIcon,
  BellIcon,
} from '@heroicons/react/24/outline';
import { Button } from '../common/Button';

const navigation = [
  // { name: 'Dashboard', href: '/', icon: HomeIcon },
  { name: 'Live Trading', href: '/live', icon: ChartBarIcon },
  { name: 'Strategies', href: '/strategies', icon: PuzzlePieceIcon },
  { name: 'Configuration', href: '/config', icon: Cog6ToothIcon },
  { name: 'Backtest', href: '/backtest', icon: BeakerIcon },
  { name: 'Optimize', href: '/optimize', icon: SparklesIcon },
  { name: 'Notification Settings', href: '/notifications', icon: BellIcon },
  { name: 'Notification History', href: '/notification-history', icon: BellIcon },
  { name: 'Token Manager', href: '/tokens', icon: KeyIcon },
  { name: 'Services', href: '/services', icon: CpuChipIcon },
];

interface SidebarProps {
  collapsed: boolean;
  mobileOpen: boolean;
  onClose: () => void;
  onToggleSidebar: () => void;
}

export function Sidebar({ collapsed, mobileOpen, onClose, onToggleSidebar }: SidebarProps) {
  return (
    <div
      className={`
        bg-gray-800 transition-all duration-300 z-50

        /* Always fixed position */
        fixed inset-y-0 left-0 h-screen overflow-y-auto

        /* Mobile: slides in from left when open */
        ${mobileOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}

        /* Width: full on mobile, responsive on desktop based on collapsed state */
        w-64 ${collapsed ? 'md:w-16' : 'md:w-64'}
      `}
    >
      {/* Hamburger Button at Top - only visible on desktop */}
      <div className="hidden md:block px-2 pt-3 pb-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={onToggleSidebar}
          className="w-full p-2 min-w-[44px] min-h-[44px] text-gray-300 hover:text-white hover:bg-gray-700 rounded-md transition-colors"
          aria-label="Toggle sidebar"
        >
          <Bars3Icon className="h-6 w-6 mx-auto" />
        </Button>
      </div>

      <nav className="px-2">
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
