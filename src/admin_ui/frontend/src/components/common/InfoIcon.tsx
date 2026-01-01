import { useState, useRef, useEffect } from 'react';

interface InfoIconProps {
  content: string;
  placement?: 'top' | 'bottom' | 'left' | 'right';
  size?: 'sm' | 'md' | 'lg';
}

export function InfoIcon({ content, placement = 'top', size = 'sm' }: InfoIconProps) {
  const [isVisible, setIsVisible] = useState(false);
  const [tooltipStyle, setTooltipStyle] = useState<React.CSSProperties>({});
  const iconRef = useRef<HTMLDivElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);

  const sizeClasses = {
    sm: 'w-4 h-4 text-xs',
    md: 'w-5 h-5 text-sm',
    lg: 'w-6 h-6 text-base',
  };

  useEffect(() => {
    if (isVisible && iconRef.current && tooltipRef.current) {
      const iconRect = iconRef.current.getBoundingClientRect();
      const tooltipRect = tooltipRef.current.getBoundingClientRect();
      const viewportWidth = window.innerWidth;
      const viewportHeight = window.innerHeight;

      let top = 0;
      let left = 0;

      switch (placement) {
        case 'top':
          top = -tooltipRect.height - 8;
          left = (iconRect.width - tooltipRect.width) / 2;
          break;
        case 'bottom':
          top = iconRect.height + 8;
          left = (iconRect.width - tooltipRect.width) / 2;
          break;
        case 'left':
          top = (iconRect.height - tooltipRect.height) / 2;
          left = -tooltipRect.width - 8;
          break;
        case 'right':
          top = (iconRect.height - tooltipRect.height) / 2;
          left = iconRect.width + 8;
          break;
      }

      // Adjust if tooltip would go off screen
      const absoluteLeft = iconRect.left + left;
      const absoluteTop = iconRect.top + top;

      if (absoluteLeft + tooltipRect.width > viewportWidth) {
        left = viewportWidth - iconRect.left - tooltipRect.width - 10;
      }
      if (absoluteLeft < 0) {
        left = -iconRect.left + 10;
      }
      if (absoluteTop + tooltipRect.height > viewportHeight) {
        top = viewportHeight - iconRect.top - tooltipRect.height - 10;
      }
      if (absoluteTop < 0) {
        top = -iconRect.top + 10;
      }

      setTooltipStyle({ top: `${top}px`, left: `${left}px` });
    }
  }, [isVisible, placement]);

  return (
    <div
      ref={iconRef}
      className="inline-block relative"
      onMouseEnter={() => setIsVisible(true)}
      onMouseLeave={() => setIsVisible(false)}
      onFocus={() => setIsVisible(true)}
      onBlur={() => setIsVisible(false)}
      tabIndex={0}
    >
      <div
        className={`${sizeClasses[size]} inline-flex items-center justify-center rounded-full bg-blue-100 text-blue-600 hover:bg-blue-200 cursor-help transition-colors`}
      >
        <svg
          className="w-full h-full p-0.5"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          xmlns="http://www.w3.org/2000/svg"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
      </div>

      {isVisible && (
        <div
          ref={tooltipRef}
          style={tooltipStyle}
          className="absolute z-50 px-3 py-2 text-sm text-white bg-gray-900 rounded-lg shadow-lg w-80 whitespace-normal pointer-events-none"
          role="tooltip"
        >
          {content}
          <div
            className={`absolute w-2 h-2 bg-gray-900 transform rotate-45 ${
              placement === 'top' ? 'bottom-[-4px] left-1/2 -translate-x-1/2' :
              placement === 'bottom' ? 'top-[-4px] left-1/2 -translate-x-1/2' :
              placement === 'left' ? 'right-[-4px] top-1/2 -translate-y-1/2' :
              'left-[-4px] top-1/2 -translate-y-1/2'
            }`}
          />
        </div>
      )}
    </div>
  );
}
