import React, { useState } from 'react';
import { Header } from './Header';
import { Sidebar } from './Sidebar';

interface LayoutProps {
  children: React.ReactNode;
}

export function Layout({ children }: LayoutProps) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const toggleSidebar = () => {
    // On mobile, toggle open/close
    // On desktop, toggle collapsed/expanded
    if (window.innerWidth < 768) {
      setSidebarOpen(!sidebarOpen);
    } else {
      setSidebarCollapsed(!sidebarCollapsed);
    }
  };

  const closeMobileSidebar = () => {
    setSidebarOpen(false);
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <Header onToggleSidebar={toggleSidebar} sidebarCollapsed={sidebarCollapsed} />

      <div className="flex">
        {/* Backdrop overlay (mobile only) */}
        {sidebarOpen && (
          <div
            className="fixed inset-0 bg-black bg-opacity-50 z-40 md:hidden"
            onClick={closeMobileSidebar}
          />
        )}

        {/* Sidebar */}
        <Sidebar
          collapsed={sidebarCollapsed}
          mobileOpen={sidebarOpen}
          onClose={closeMobileSidebar}
          onToggleSidebar={toggleSidebar}
        />

        {/* Main content - add left margin to account for fixed sidebar on desktop */}
        <main className={`flex-1 p-4 md:p-6 transition-all duration-300 ${
          sidebarCollapsed ? 'md:ml-16' : 'md:ml-64'
        }`}>
          {children}
        </main>
      </div>
    </div>
  );
}
