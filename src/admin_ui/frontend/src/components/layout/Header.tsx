import { useAuth } from '../../hooks/useAuth';
import { Button } from '../common/Button';
import { Bars3Icon, ArrowRightStartOnRectangleIcon } from '@heroicons/react/24/outline';
import logo from '../../assets/quant_vibe_icon_white_bg.svg';

interface HeaderProps {
  onToggleSidebar: () => void;
  sidebarCollapsed: boolean;
}

export function Header({ onToggleSidebar, sidebarCollapsed }: HeaderProps) {
  const { logout } = useAuth();

  return (
    <header className={`bg-white shadow sticky top-0 z-30 transition-all duration-300 ${
      sidebarCollapsed ? 'md:ml-16' : 'md:ml-64'
    }`}>
      <div className="mx-auto px-3 md:px-4 lg:px-8 py-2 md:py-4 flex justify-between items-center">
        <div className="flex items-center gap-2 md:gap-3">
          <Button
            variant="ghost"
            size="sm"
            onClick={onToggleSidebar}
            className="p-2 min-w-[44px] min-h-[44px]"
            aria-label="Toggle sidebar"
          >
            <Bars3Icon className="h-6 w-6" />
          </Button>
          <img src={logo} alt="QuantVibe" className="h-10 md:h-16 w-auto" />
          <h1 className="hidden sm:block text-xl md:text-2xl font-bold text-gray-900">Admin</h1>
        </div>
        <div className="flex items-center gap-2 md:gap-4">
          <Button
            variant="secondary"
            size="sm"
            onClick={logout}
            className="min-w-[44px] min-h-[44px]"
            aria-label="Logout"
          >
            <span className="hidden sm:inline">Logout</span>
            <ArrowRightStartOnRectangleIcon className="h-5 w-5 sm:hidden" />
          </Button>
        </div>
      </div>
    </header>
  );
}
