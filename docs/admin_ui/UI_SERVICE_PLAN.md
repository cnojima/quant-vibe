# UI Service Plan - QuantVibe Admin Dashboard

**Created**: 2025-12-25
**Status**: Planning Complete - Ready for Implementation

---

## Executive Summary

This document outlines the comprehensive plan for building the QuantVibe Admin UI, a web-based dashboard for real-time monitoring and control of the quantitative trading platform.

**Current State**:
- ✅ Backend FastAPI application is production-ready with complete REST API
- ✅ WebSocket event streaming implemented
- ✅ JWT authentication configured
- ⚠️ Frontend React application is scaffolded but completely empty

**Goal**: Build a modern React TypeScript frontend that leverages all existing backend APIs to provide real-time monitoring, control, and analysis capabilities.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│  Admin UI Service (Port 8000)                           │
│  ├─ FastAPI Backend (READY ✓)                           │
│  │  ├─ REST API (/api)                                  │
│  │  ├─ WebSocket (/ws/events)                           │
│  │  ├─ JWT Authentication                               │
│  │  └─ Redis/TimescaleDB clients                        │
│  │                                                       │
│  └─ React Frontend (TO BUILD)                           │
│     ├─ Service Dashboard                                │
│     ├─ Token Manager                                    │
│     ├─ Live Trading Monitor                             │
│     ├─ Backtest Runner                                  │
│     └─ Chart Visualizations                             │
└─────────────────────────────────────────────────────────┘
```

---

## Backend API Reference

The following REST API endpoints and WebSocket connections are **already implemented** and ready to use:

### Authentication (`/api/auth`)
- `POST /api/auth/login` - JWT token authentication
- Default credentials: `admin / changeme` (configurable via `.env`)

### Service Management (`/api/services`)
- `GET /api/services/` - List all services with status
- `GET /api/services/{service_name}` - Get specific service status
- `POST /api/services/{service_name}/start` - Start service
- `POST /api/services/{service_name}/stop` - Stop service
- `POST /api/services/{service_name}/restart` - Restart service
- `GET /api/services/{service_name}/logs?tail=100` - Get service logs

### Schwab Token Management (`/api/tokens`)
- `GET /api/tokens/status` - Get token status (expiration, age)
- `POST /api/tokens/refresh` - Manually refresh access token
- ⚠️ `GET /api/tokens/oauth-url` - Get OAuth URL (TODO)
- ⚠️ `POST /api/tokens/oauth-callback` - Handle OAuth callback (TODO)

### Live Trading Monitoring (`/api/live`)
- `GET /api/live/status` - Engine status
- `GET /api/live/positions?status=open|closed|all&limit=100` - Get positions
- `GET /api/live/orders?limit=100` - Get open orders
- `GET /api/live/events?limit=100&event_type=...&severity=...` - Get events
- `GET /api/live/stats?start_time=...&end_time=...` - Trading statistics

### Backtest Execution (`/api/backtests`)
- `GET /api/backtests/strategies` - List available strategies
- `POST /api/backtests/run` - Run backtest asynchronously
- `GET /api/backtests/{backtest_id}/status` - Get backtest status
- `GET /api/backtests/{backtest_id}/results` - Get backtest results
- `GET /api/backtests/history?limit=50` - Backtest history

### WebSocket (`/ws/events`)
- Real-time event streaming from Redis pub/sub
- Broadcasts to all connected clients
- Supports ping/pong keepalive

---

## MVP Feature Specifications

### 1. Schwab API Token Management 🔑

**Purpose**: Monitor and manage Schwab API OAuth tokens to prevent service disruptions.

**Backend Status**: ✅ Partial (status and refresh ready, OAuth callback missing)

**Frontend Components**:
```
src/pages/TokenManager.tsx
  └─ TokenStatus.tsx        - Display token validity and expiration
  └─ RefreshButton.tsx      - Manual refresh trigger
  └─ TokenTimeline.tsx      - Visual countdown timer
  └─ OAuthFlow.tsx          - Re-authentication flow (needs backend)
```

**UI Features**:
- Real-time token status (valid/expired/expiring soon)
- Countdown timer with visual indicators
  - Green: >1 hour remaining
  - Yellow: <1 hour, >30 minutes
  - Red: <30 minutes or expired
- One-click manual refresh
- Auto-refresh indicator (shows "Auto-refresh: Enabled")
- OAuth re-authentication button (redirects to Schwab)

**Data Flow**:
```
Frontend → GET /api/tokens/status (every 60s)
         → Display status + countdown
         → User clicks "Refresh"
         → POST /api/tokens/refresh
         → Update status display
```

**Mock UI**:
```
┌─────────────────────────────────────────────────┐
│ Schwab API Token Status                         │
├─────────────────────────────────────────────────┤
│ Access Token:  ✓ Valid (expires in 18m 32s)    │
│ [██████████████████░░] 65% remaining            │
│                                                 │
│ Refresh Token: ✓ Valid (expires in 5d 3h)      │
│ [████████████████████] 100% remaining           │
│                                                 │
│ [Refresh Token Now]  [Re-authenticate]         │
│                                                 │
│ Last Refreshed: 2025-12-25 10:15:32            │
│ Auto-refresh: ✓ Enabled (every 25 minutes)     │
└─────────────────────────────────────────────────┘
```

---

### 2. Service Status Dashboard 🚦

**Purpose**: Monitor and control all QuantVibe services from a single interface.

**Backend Status**: ✅ Ready

**Frontend Components**:
```
src/pages/Dashboard.tsx
  └─ ServiceGrid.tsx        - Grid layout of service cards
  └─ ServiceCard.tsx        - Individual service status + controls
  └─ ServiceLogs.tsx        - Expandable log viewer
  └─ SystemHealth.tsx       - Overall health indicators
```

**Services to Monitor**:
1. Streaming Service (`streaming_service`)
2. Live Trading Engine (`live_trading_service`)
3. Redis (`redis`)
4. TimescaleDB (`timescaledb`)
5. Admin UI (`admin_ui`) - self-monitoring

**UI Features**:
- Service status indicators (running/stopped/error)
- Uptime display (hours/days)
- Control buttons (Start/Stop/Restart)
- Log viewer (last 100 lines, searchable)
- Health status icons
- Container resource usage (if available from Docker API)

**Data Flow**:
```
Frontend → GET /api/services/ (every 5s)
         → Display all services in grid
         → User clicks "Stop" on service
         → POST /api/services/{name}/stop
         → Wait 2s
         → Refresh service list
```

**Mock UI**:
```
┌─────────────────────────────────────────────────────────────┐
│ System Overview                                             │
├─────────────────────────────────────────────────────────────┤
│ Overall Health: ✓ All Systems Operational                  │
│                                                             │
│ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐        │
│ │ Streaming    │ │ Live Trading │ │ Redis        │        │
│ │ ● Running    │ │ ● Running    │ │ ● Running    │        │
│ │ Uptime: 3h   │ │ Uptime: 2h   │ │ Uptime: 5h   │        │
│ │ [Stop] [⟳]   │ │ [Stop] [⟳]   │ │ [Stop] [⟳]   │        │
│ │ [View Logs]  │ │ [View Logs]  │ │ [View Logs]  │        │
│ └──────────────┘ └──────────────┘ └──────────────┘        │
│                                                             │
│ ┌──────────────┐ ┌──────────────┐                         │
│ │ TimescaleDB  │ │ Admin UI     │                         │
│ │ ● Running    │ │ ● Running    │                         │
│ │ Uptime: 5h   │ │ Uptime: 3h   │                         │
│ │ [Stop] [⟳]   │ │ [Stop] [⟳]   │                         │
│ │ [View Logs]  │ │ [View Logs]  │                         │
│ └──────────────┘ └──────────────┘                         │
│                                                             │
│ Recent System Logs:                                         │
│ [2025-12-25 10:30:15][streaming][INFO] Bar aggregated...   │
│ [2025-12-25 10:30:20][live][INFO] Signal generated...      │
│ [Filter] [Export]                                          │
└─────────────────────────────────────────────────────────────┘
```

---

### 3. Live Trading Monitor 📊

**Purpose**: Real-time monitoring of live trading engine with position tracking and event streaming.

**Backend Status**: ✅ Ready (REST API + WebSocket)

**Frontend Components**:
```
src/pages/LiveTrading.tsx
  └─ EngineStatus.tsx       - Engine state, mode, stats
  └─ PositionsTable.tsx     - Active positions with real-time P&L
  └─ OrdersTable.tsx        - Order history and status
  └─ EventLog.tsx           - Live event stream (WebSocket)
  └─ TradingStats.tsx       - Win rate, Sharpe, total P&L
  └─ EquityCurve.tsx        - Real-time equity chart
  └─ RiskMetrics.tsx        - Daily loss limit, position limits
```

**UI Features**:
- Engine status badge (Running/Stopped, Paper/Live mode)
- Real-time statistics:
  - Total P&L (color-coded green/red)
  - Active positions count (X/max)
  - Total bars processed
  - Total signals generated
- Positions table with columns:
  - Position ID
  - Strategy name
  - Entry cost
  - Current value
  - Unrealized P&L (color-coded)
  - Entry time
  - Actions (Close position button)
- Orders table with filters (All/Pending/Filled/Cancelled)
- Live event stream (auto-scrolling, severity color-coding)
- Trading statistics panel
- Real-time equity curve chart (Recharts)

**Data Flow**:
```
Frontend → GET /api/live/status (every 5s)
         → GET /api/live/positions?status=open (every 5s)
         → GET /api/live/orders (every 5s)
         → WebSocket /ws/events (real-time)
         → Display all data in unified view
```

**Mock UI**:
```
┌─────────────────────────────────────────────────────────────┐
│ Live Trading Engine                                         │
├─────────────────────────────────────────────────────────────┤
│ Status: ● Running (Paper Mode)    Total P&L: +$2,345.67    │
│ Positions: 3/5    Bars: 1,234    Signals: 45               │
│                                                             │
│ ┌─────────────────────────────────────────────────────┐    │
│ │ Equity Curve (Real-time)                            │    │
│ │ [Recharts line chart showing equity over time]      │    │
│ └─────────────────────────────────────────────────────┘    │
│                                                             │
│ Active Positions:                                           │
│ ┌──────────────────────────────────────────────────────┐   │
│ │ID       │Strategy   │Entry      │Current  │P&L      │   │
│ ├─────────┼───────────┼───────────┼─────────┼─────────┤   │
│ │pos_001  │BullVertPut│-$500.00   │-$350.00 │+$150.00 │   │
│ │pos_002  │BullVertPut│-$480.00   │-$520.00 │-$40.00  │   │
│ │pos_003  │BullVertPut│-$510.00   │-$450.00 │+$60.00  │   │
│ └──────────────────────────────────────────────────────┘   │
│                                                             │
│ Recent Events (Live):                                       │
│ 10:30:25 [INFO   ] Signal: ENTER bullish_vertical_put      │
│ 10:30:30 [INFO   ] Order submitted: SPX 251227P5900        │
│ 10:30:35 [WARNING] Position approaching stop loss          │
└─────────────────────────────────────────────────────────────┘
```

---

### 4. Backtest Runner & Analyzer 📈

**Purpose**: Run backtests with custom parameters and visualize results.

**Backend Status**: ✅ Ready (async execution)

**Frontend Components**:
```
src/pages/Backtest.tsx
  └─ StrategySelector.tsx   - Dropdown of available strategies
  └─ ParameterForm.tsx      - Dynamic form for strategy params
  └─ DateRangePicker.tsx    - Start/end date selection
  └─ BacktestRunner.tsx     - Run button + progress indicator
  └─ ResultsViewer.tsx      - Trades table, equity curve, metrics
  └─ BacktestHistory.tsx    - List of past backtests
  └─ ComparisonView.tsx     - Compare multiple results
```

**UI Features**:
- Strategy selection dropdown (populated from API)
- Dynamic parameter form (changes based on strategy)
  - Spread width (number input)
  - Profit target (percentage)
  - Min/Max DTE (number inputs)
  - Other strategy-specific params
- Date range picker with presets:
  - Today
  - This week
  - This month
  - Custom range
- Run backtest button (disabled during execution)
- Progress indicator (polling status endpoint)
- Results display:
  - Summary metrics (Total trades, Win rate, Total P&L, Sharpe ratio)
  - Equity curve chart
  - Trades table (expandable rows for trade details)
  - CSV export button
- Backtest history sidebar (past runs)
- Comparison mode (select multiple backtests to compare)

**Data Flow**:
```
Frontend → GET /api/backtests/strategies
         → Display strategy selector
         → User selects strategy + params
         → POST /api/backtests/run → returns backtest_id
         → Poll GET /api/backtests/{id}/status every 2s
         → When complete, GET /api/backtests/{id}/results
         → Display results with charts
```

**Mock UI**:
```
┌─────────────────────────────────────────────────────────────┐
│ Backtest Runner                                             │
├─────────────────────────────────────────────────────────────┤
│ Strategy: [Bullish Vertical Put ▼]                         │
│                                                             │
│ Parameters:                                                 │
│   Spread Width:        [10.0]                              │
│   Profit Target (min): [0.50]                              │
│   Min DTE:             [0]                                 │
│   Max DTE:             [45]                                │
│                                                             │
│ Date Range: [2025-12-01] to [2025-12-25] [Presets ▼]      │
│                                                             │
│ [Run Backtest]                                             │
│                                                             │
│ ┌─────────────────────────────────────────────────────┐    │
│ │ Results: backtest_20251225_103015                   │    │
│ │ Total Trades: 23    Win Rate: 65.2%                │    │
│ │ Total P&L: +$3,456.78    Sharpe: 1.85             │    │
│ │                                                     │    │
│ │ [Equity Curve Chart - Recharts line chart]         │    │
│ │                                                     │    │
│ │ Trades:                                             │    │
│ │ ┌─────┬──────────┬──────────┬─────────┬─────────┐  │    │
│ │ │ID   │Entry Time│Exit Time │P&L      │Reason   │  │    │
│ │ ├─────┼──────────┼──────────┼─────────┼─────────┤  │    │
│ │ │T001 │10:30:00  │11:45:00  │+$150.00 │Profit   │  │    │
│ │ │T002 │11:00:00  │12:30:00  │-$50.00  │Stop Loss│  │    │
│ │ └─────┴──────────┴──────────┴─────────┴─────────┘  │    │
│ │                                                     │    │
│ │ [View Full Report] [Export CSV] [Compare]          │    │
│ └─────────────────────────────────────────────────────┘    │
│                                                             │
│ History:                                                    │
│ • backtest_20251225_103015 (Bullish Vertical Put)          │
│ • backtest_20251224_145030 (Bullish Vertical Put)          │
└─────────────────────────────────────────────────────────────┘
```

---

### 5. Chart Visualizations 📉

**Purpose**: Provide rich visual analytics for backtests and live trading.

**Backend Status**: ⚠️ Data available via API (no dedicated chart endpoints)

**Frontend Components**:
```
src/components/charts/
  └─ EquityCurveChart.tsx   - Line chart for equity/P&L over time
  └─ TradeHistogram.tsx     - Bar chart for trade P&L distribution
  └─ DrawdownChart.tsx      - Area chart for drawdown visualization
  └─ IndicatorOverlay.tsx   - Candlestick + indicators (SMA/RSI/MACD)
  └─ CandlestickChart.tsx   - OHLCV candlestick chart
```

**Chart Types**:

1. **Equity Curve** (Line Chart)
   - X-axis: Time
   - Y-axis: Portfolio value ($)
   - Data: `equity_curve` from backtest results
   - Features: Tooltip with exact values, zoom, pan

2. **Trade P&L Distribution** (Histogram)
   - X-axis: P&L bins (-$500, -$400, ..., $500)
   - Y-axis: Trade count
   - Data: Individual trade P&L from `trades` table
   - Features: Color-coded (green for profit, red for loss)

3. **Drawdown Chart** (Area Chart)
   - X-axis: Time
   - Y-axis: Drawdown from peak (%)
   - Data: Calculated from equity curve
   - Features: Highlight max drawdown period

4. **Price + Indicators** (Composite Chart)
   - Primary: Candlestick chart (OHLCV)
   - Overlays: SMA (moving average lines), Bollinger Bands
   - Sub-chart: RSI (oscillator below)
   - Data: Options OHLCV from TimescaleDB (future feature)

5. **Position P&L** (Bar Chart)
   - X-axis: Position ID
   - Y-axis: Current P&L
   - Data: Active positions from live trading
   - Features: Real-time updates, color-coded

**Technology**: **Recharts** (already in package.json)

**Recharts Components to Use**:
- `LineChart` - Equity curve, indicators
- `BarChart` - Trade distribution, position P&L
- `AreaChart` - Drawdown
- `ComposedChart` - Price + indicators overlay
- `Tooltip`, `Legend`, `XAxis`, `YAxis`, `CartesianGrid` - common

**Mock UI**:
```
┌─────────────────────────────────────────────────────────────┐
│ Strategy Performance Analysis                               │
├─────────────────────────────────────────────────────────────┤
│ Equity Curve:                                               │
│ ┌─────────────────────────────────────────────────────┐    │
│ │     $105k ┤                              ╱          │    │
│ │     $102k ┤                   ╱──────╱              │    │
│ │     $100k ┤─────╱────╱───────╱                      │    │
│ │      $98k ┤  ╱                                      │    │
│ │      $95k ┤╱                                        │    │
│ │           └──────────────────────────────────────   │    │
│ │            Dec 1   Dec 8   Dec 15   Dec 22         │    │
│ └─────────────────────────────────────────────────────┘    │
│                                                             │
│ Trade P&L Distribution:                                     │
│ ┌─────────────────────────────────────────────────────┐    │
│ │ Count                                               │    │
│ │   8 ┤     ▇▇▇                                      │    │
│ │   6 ┤  ▇▇▇▇▇▇▇                                     │    │
│ │   4 ┤▇▇▇▇▇▇▇▇▇▇                                    │    │
│ │   2 ┤▇▇▇▇▇▇▇▇▇▇▇▇                                  │    │
│ │   0 ┤────────────────────────────────────────      │    │
│ │     -$500  -$200    $0    $200   $500             │    │
│ └─────────────────────────────────────────────────────┘    │
│                                                             │
│ Drawdown:                                                   │
│ ┌─────────────────────────────────────────────────────┐    │
│ │    0% ┤────────────────────────────────────────     │    │
│ │   -2% ┤     ▁▁                     ▁               │    │
│ │   -4% ┤  ▁▁▁  ▁▁                ▁▁▁ ▁              │    │
│ │   -6% ┤▁▁       ▁▁▁          ▁▁▁     ▁             │    │
│ │   -8% ┤           ▁▁▁▁▁▁▁▁▁▁▁                      │    │
│ │       └──────────────────────────────────────────  │    │
│ │            Dec 1   Dec 8   Dec 15   Dec 22        │    │
│ └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

---

## Technical Implementation Details

### Frontend Project Structure

```
src/admin_ui/frontend/
├── src/
│   ├── api/                    # API client layer
│   │   ├── client.ts           # Axios instance with auth interceptor
│   │   ├── queries.ts          # TanStack Query hooks
│   │   └── websocket.ts        # WebSocket client
│   │
│   ├── components/             # Reusable UI components
│   │   ├── common/             # Generic components
│   │   │   ├── Button.tsx
│   │   │   ├── Card.tsx
│   │   │   ├── Table.tsx
│   │   │   ├── Badge.tsx
│   │   │   └── Modal.tsx
│   │   ├── charts/             # Chart components
│   │   │   ├── EquityCurveChart.tsx
│   │   │   ├── TradeHistogram.tsx
│   │   │   ├── DrawdownChart.tsx
│   │   │   └── IndicatorOverlay.tsx
│   │   └── layout/             # Layout components
│   │       ├── Header.tsx
│   │       ├── Sidebar.tsx
│   │       ├── Layout.tsx
│   │       └── Navigation.tsx
│   │
│   ├── pages/                  # Page components (React Router)
│   │   ├── Dashboard.tsx       # Main dashboard
│   │   ├── TokenManager.tsx    # Token management page
│   │   ├── LiveTrading.tsx     # Live trading monitor
│   │   ├── Backtest.tsx        # Backtest runner
│   │   └── Login.tsx           # Login page
│   │
│   ├── hooks/                  # Custom React hooks
│   │   ├── useWebSocket.ts     # WebSocket connection hook
│   │   ├── useAuth.ts          # Authentication hook
│   │   ├── usePolling.ts       # Polling hook for status updates
│   │   └── useLocalStorage.ts  # LocalStorage hook
│   │
│   ├── types/                  # TypeScript type definitions
│   │   ├── api.ts              # API response types
│   │   ├── backtest.ts         # Backtest types
│   │   ├── trading.ts          # Trading types
│   │   └── service.ts          # Service types
│   │
│   ├── utils/                  # Utility functions
│   │   ├── formatters.ts       # Number/date formatting
│   │   ├── validators.ts       # Form validation
│   │   └── constants.ts        # App constants
│   │
│   ├── App.tsx                 # Root component
│   ├── main.tsx                # Entry point
│   ├── router.tsx              # React Router setup
│   └── index.css               # Global styles (Tailwind)
│
├── public/                     # Static assets
│   └── vite.svg                # Favicon
├── index.html                  # HTML template
├── package.json                # Dependencies
├── tsconfig.json               # TypeScript config
├── vite.config.ts              # Vite config
├── tailwind.config.js          # Tailwind CSS config
└── postcss.config.js           # PostCSS config
```

### Core Dependencies

```json
{
  "name": "quantvibe-admin-ui",
  "version": "1.0.0",
  "type": "module",
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-router-dom": "^6.20.0",
    "@tanstack/react-query": "^5.15.0",
    "axios": "^1.6.2",
    "recharts": "^2.10.3",
    "date-fns": "^3.0.0",
    "@headlessui/react": "^1.7.17",
    "@heroicons/react": "^2.1.0"
  },
  "devDependencies": {
    "@types/react": "^18.2.43",
    "@types/react-dom": "^18.2.17",
    "@vitejs/plugin-react": "^4.2.1",
    "typescript": "^5.3.3",
    "vite": "^5.0.8",
    "tailwindcss": "^3.3.6",
    "autoprefixer": "^10.4.16",
    "postcss": "^8.4.32"
  }
}
```

### Key Implementation Examples

#### API Client with Auth Interceptor

```typescript
// src/api/client.ts
import axios from 'axios';

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000/api',
  timeout: 30000,
});

// Add JWT token to all requests
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('auth_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle 401 errors (token expired)
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('auth_token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default apiClient;
```

#### WebSocket Hook

```typescript
// src/hooks/useWebSocket.ts
import { useEffect, useRef, useState } from 'react';

export function useWebSocket<T>(url: string) {
  const [data, setData] = useState<T | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const ws = useRef<WebSocket | null>(null);

  useEffect(() => {
    const token = localStorage.getItem('auth_token');
    const wsUrl = `ws://localhost:8000${url}?token=${token}`;

    ws.current = new WebSocket(wsUrl);

    ws.current.onopen = () => {
      console.log('WebSocket connected');
      setIsConnected(true);
    };

    ws.current.onclose = () => {
      console.log('WebSocket disconnected');
      setIsConnected(false);
    };

    ws.current.onmessage = (event) => {
      const message = JSON.parse(event.data);
      setData(message);
    };

    ws.current.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    return () => {
      ws.current?.close();
    };
  }, [url]);

  return { data, isConnected };
}
```

#### TanStack Query Hooks

```typescript
// src/api/queries.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from './client';

// Service status query
export function useServices() {
  return useQuery({
    queryKey: ['services'],
    queryFn: async () => {
      const response = await apiClient.get('/services/');
      return response.data;
    },
    refetchInterval: 5000, // Poll every 5 seconds
  });
}

// Token status query
export function useTokenStatus() {
  return useQuery({
    queryKey: ['token-status'],
    queryFn: async () => {
      const response = await apiClient.get('/tokens/status');
      return response.data;
    },
    refetchInterval: 60000, // Refresh every minute
  });
}

// Refresh token mutation
export function useRefreshToken() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      await apiClient.post('/tokens/refresh');
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['token-status'] });
    },
  });
}

// Live trading status query
export function useLiveStatus() {
  return useQuery({
    queryKey: ['live-status'],
    queryFn: async () => {
      const response = await apiClient.get('/live/status');
      return response.data;
    },
    refetchInterval: 5000,
  });
}

// Live positions query
export function useLivePositions(status: 'open' | 'closed' | 'all' = 'open') {
  return useQuery({
    queryKey: ['live-positions', status],
    queryFn: async () => {
      const response = await apiClient.get(`/live/positions?status=${status}`);
      return response.data;
    },
    refetchInterval: 5000,
  });
}

// Run backtest mutation
export function useRunBacktest() {
  return useMutation({
    mutationFn: async (payload: any) => {
      const response = await apiClient.post('/backtests/run', payload);
      return response.data;
    },
  });
}
```

#### TypeScript Types

```typescript
// src/types/api.ts
export interface Service {
  name: string;
  status: 'running' | 'stopped' | 'error';
  uptime_seconds: number;
}

export interface TokenStatus {
  access_token_valid: boolean;
  access_token_expiry: string;
  refresh_token_valid: boolean;
  refresh_token_expiry: string;
}

export interface LiveEngineStatus {
  is_running: boolean;
  paper_trading: boolean;
  total_pnl: number;
  total_bars_processed: number;
  total_signals_generated: number;
  active_positions_count: number;
}

export interface Position {
  position_id: string;
  strategy_name: string;
  status: 'open' | 'closed';
  entry_time: string;
  entry_cost: number;
  current_value: number | null;
  exit_time: string | null;
  exit_value: number | null;
  exit_reason: string | null;
  unrealized_pnl: number | null;
  realized_pnl: number | null;
  legs: OptionLeg[];
}

export interface OptionLeg {
  contract_symbol: string;
  quantity: number;
  side: 'buy' | 'sell';
  entry_price: number;
  current_price: number | null;
}

export interface BacktestResult {
  backtest_id: string;
  strategy_name: string;
  start_date: string;
  end_date: string;
  total_trades: number;
  win_rate: number;
  total_pnl: number;
  sharpe_ratio: number;
  max_drawdown: number;
  equity_curve: EquityPoint[];
  trades: Trade[];
}

export interface EquityPoint {
  timestamp: string;
  portfolio_value: number;
}

export interface Trade {
  trade_id: string;
  entry_time: string;
  exit_time: string;
  pnl: number;
  exit_reason: string;
}
```

---

## Development Workflow

### Local Development Setup

```bash
# Terminal 1: Start backend
cd src/admin_ui/backend
source ../../../venv/bin/activate
python -m uvicorn main:app --reload --port 8000

# Terminal 2: Start frontend dev server
cd src/admin_ui/frontend
npm install
npm run dev  # Vite dev server on port 3000

# Terminal 3: Start supporting services (optional for testing)
docker-compose up redis timescaledb
python scripts/stream_spxw_schwabdev.py
python scripts/run_live_trading.py
```

### Production Build

```bash
cd src/admin_ui/frontend
npm run build  # Outputs to dist/

# Backend serves static files from dist/
cd src/admin_ui/backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

### Docker Deployment

Already configured in `docker-compose.yml`:

```yaml
admin_ui:
  build: ./src/admin_ui
  ports:
    - "8000:8000"
  environment:
    - SCHWAB_API_KEY
    - REDIS_HOST=redis
    - TIMESCALE_HOST=timescaledb
    - ADMIN_USERNAME=admin
    - ADMIN_PASSWORD=changeme
    - JWT_SECRET_KEY
  depends_on:
    - redis
    - timescaledb
  volumes:
    - ./config:/app/config:ro
    - ./logs:/app/logs
```

---

## Implementation Phases

### Phase 1: Foundation (2-3 days)

**Goal**: Set up frontend project with core infrastructure.

**Tasks**:
1. Initialize frontend project structure
2. Install dependencies (React, TanStack Query, Recharts, Tailwind)
3. Configure TypeScript, Vite, Tailwind
4. Create API client with auth interceptors
5. Implement WebSocket hook
6. Define TypeScript types for all API responses
7. Set up React Router with routes
8. Create basic Layout component (Header, Sidebar, Content)

**Deliverables**:
- Working Vite dev server
- API client connected to backend
- TypeScript types defined
- Basic routing structure

---

### Phase 2: MVP Features (5-7 days)

**Goal**: Implement all 5 MVP features.

#### 2.1 Authentication (1 day)
- Login page (`Login.tsx`)
- Auth hook (`useAuth.ts`)
- Protected route wrapper
- Token storage in localStorage

#### 2.2 Service Dashboard (1 day)
- Dashboard page (`Dashboard.tsx`)
- Service card component (`ServiceCard.tsx`)
- Service grid layout
- Start/stop/restart actions
- Log viewer modal

#### 2.3 Token Manager (1 day)
- Token manager page (`TokenManager.tsx`)
- Token status display with countdown
- Refresh button with loading state
- Timeline visualization

#### 2.4 Live Trading Monitor (1.5 days)
- Live trading page (`LiveTrading.tsx`)
- Engine status component
- Positions table with real-time updates
- Orders table
- Event log with WebSocket integration
- Trading statistics panel

#### 2.5 Backtest Runner (1.5 days)
- Backtest page (`Backtest.tsx`)
- Strategy selector
- Dynamic parameter form
- Date range picker
- Run backtest button with progress
- Results viewer

#### 2.6 Chart Components (1 day)
- Equity curve chart (`EquityCurveChart.tsx`)
- Trade histogram (`TradeHistogram.tsx`)
- Drawdown chart (`DrawdownChart.tsx`)
- Integrate charts into backtest and live trading pages

**Deliverables**:
- Fully functional UI with all 5 features
- Real-time data updates
- WebSocket integration
- Charts rendering correctly

---

### Phase 3: Backend Gaps (2-3 days)

**Goal**: Fill missing backend functionality.

#### 3.1 OAuth Callback Handler (1 day)
```python
# src/admin_ui/backend/routers/tokens.py

@router.get("/oauth-url")
async def get_oauth_url():
    """Generate Schwab OAuth URL for re-authentication"""
    from schwabdev import Client

    client = Client(
        app_key=os.getenv("SCHWAB_API_KEY"),
        app_secret=os.getenv("SCHWAB_API_SECRET"),
    )

    auth_url = client.get_authorization_url()
    return {"oauth_url": auth_url}

@router.post("/oauth-callback")
async def handle_oauth_callback(code: str):
    """Handle OAuth callback and exchange code for tokens"""
    from schwabdev import Client

    client = Client(
        app_key=os.getenv("SCHWAB_API_KEY"),
        app_secret=os.getenv("SCHWAB_API_SECRET"),
    )

    client.exchange_code_for_token(code)
    return {"status": "success"}
```

#### 3.2 Configuration Editor (1-2 days, optional)
```python
# src/admin_ui/backend/routers/config.py

@router.get("/config/{config_name}")
async def get_config(config_name: str):
    """Get YAML configuration"""
    config_path = f"config/{config_name}.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)
    return config

@router.put("/config/{config_name}")
async def update_config(config_name: str, config: dict):
    """Update YAML configuration"""
    config_path = f"config/{config_name}.yaml"
    with open(config_path, 'w') as f:
        yaml.dump(config, f)
    return {"status": "success"}
```

**Deliverables**:
- OAuth re-authentication flow working
- Configuration editor (optional)

---

## Testing Strategy

### Unit Tests
- Component rendering tests (React Testing Library)
- Hook tests (useWebSocket, useAuth)
- Utility function tests (formatters, validators)

### Integration Tests
- API client tests (mocked axios)
- TanStack Query hooks (mocked responses)
- Full page rendering tests

### E2E Tests (Optional)
- Playwright or Cypress
- Login flow
- Service control
- Backtest execution

---

## Deployment Checklist

### Pre-deployment
- [ ] All TypeScript errors resolved
- [ ] Build passes (`npm run build`)
- [ ] Environment variables configured
- [ ] Backend API accessible
- [ ] Docker image builds successfully

### Deployment
- [ ] Build frontend: `npm run build`
- [ ] Copy `dist/` to backend static directory
- [ ] Build Docker image: `docker-compose build admin_ui`
- [ ] Start container: `docker-compose up -d admin_ui`
- [ ] Verify health: `curl http://localhost:8000/health`

### Post-deployment
- [ ] Test login flow
- [ ] Verify WebSocket connection
- [ ] Test all CRUD operations
- [ ] Monitor logs for errors
- [ ] Set up monitoring/alerts

---

## Future Enhancements (Beyond MVP)

1. **Advanced Charting**
   - Candlestick charts with technical indicators
   - Multi-timeframe analysis
   - Drawing tools (trendlines, support/resistance)

2. **Strategy Optimizer**
   - Parameter sweep (grid search)
   - Genetic algorithm optimization
   - Walk-forward analysis

3. **Alerts & Notifications**
   - Email/SMS alerts for trades
   - Slack/Discord integration
   - Custom alert rules

4. **Risk Management**
   - Portfolio heat map
   - Correlation analysis
   - VaR (Value at Risk) calculation

5. **Multi-user Support**
   - User roles (admin, trader, viewer)
   - Per-user configurations
   - Audit logging

6. **Mobile App**
   - React Native version
   - Push notifications
   - Simplified mobile interface

---

## Summary

**Backend**: ✅ Production-ready (REST API, WebSocket, Auth, Database)

**Frontend**: 🚧 To build (React TypeScript SPA)

**Estimated Timeline**: 2 weeks for MVP

**Next Actions**:
1. Set up frontend project structure (Phase 1)
2. Implement authentication (Phase 2.1)
3. Build service dashboard (Phase 2.2)
4. Implement remaining MVP features (Phase 2.3-2.6)
5. Fill backend OAuth gaps (Phase 3.1)
6. Testing and deployment

**Key Technologies**:
- React 18 + TypeScript
- TanStack Query (data fetching)
- Recharts (charting)
- Tailwind CSS (styling)
- Vite (build tool)
- FastAPI (backend)
- WebSocket (real-time)

---

**Document Status**: Planning Complete
**Ready for Implementation**: Yes
**Created**: 2025-12-25
