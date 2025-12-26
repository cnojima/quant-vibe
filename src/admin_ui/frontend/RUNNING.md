# QuantVibe Admin UI - Getting Started

## Current Status

**Phase 1 Complete** ✅

The following has been implemented:
- ✅ Project structure and configuration
- ✅ TypeScript, Vite, and Tailwind CSS setup
- ✅ API client with JWT authentication
- ✅ WebSocket hook for real-time updates
- ✅ TypeScript type definitions
- ✅ React Router with protected routes
- ✅ Login page with authentication
- ✅ Service Dashboard (view and control services)
- ✅ Layout with header and sidebar navigation

**Still To Build**:
- ⏳ Token Manager page
- ⏳ Live Trading Monitor
- ⏳ Backtest Runner
- ⏳ Chart components

## Running the Application

### Prerequisites
- Node.js 18+ and npm
- Backend API running on port 8000

### Development

1. **Install dependencies** (already done):
   ```bash
   npm install
   ```

2. **Start the backend API** (in a separate terminal):
   ```bash
   cd src/admin_ui/backend
   source ../../../venv/bin/activate
   python -m uvicorn main:app --reload --port 8000
   ```

3. **Start the frontend dev server**:
   ```bash
   npm run dev
   ```

4. **Open your browser**:
   - Frontend: http://localhost:3000
   - Login with default credentials: `admin` / `changeme`

### Production Build

```bash
npm run build
```

This outputs to `dist/` directory, which the backend serves as static files.

## Available Features

### Login Page
- JWT-based authentication
- Redirects to dashboard on successful login
- Shows error messages for invalid credentials

### Dashboard (Service Overview)
- View all QuantVibe services (streaming, live_trading, redis, timescaledb, admin_ui)
- See service status (running/stopped/error)
- View uptime for running services
- Start/Stop/Restart services via Docker API
- Auto-refreshes every 5 seconds

### Navigation
- Sidebar navigation with icons
- Protected routes (redirects to login if not authenticated)
- Logout button in header

## Project Structure

```
src/
├── api/                    # API client and React Query hooks
│   ├── client.ts           # Axios instance with auth interceptors
│   └── queries.ts          # TanStack Query hooks
│
├── components/
│   ├── common/             # Reusable components
│   │   ├── Button.tsx
│   │   ├── Card.tsx
│   │   └── Badge.tsx
│   └── layout/             # Layout components
│       ├── Header.tsx
│       ├── Sidebar.tsx
│       └── Layout.tsx
│
├── hooks/                  # Custom React hooks
│   ├── useAuth.ts
│   └── useWebSocket.ts
│
├── pages/                  # Page components
│   ├── Login.tsx
│   └── Dashboard.tsx
│
├── types/                  # TypeScript types
│   └── api.ts
│
├── utils/                  # Utility functions
│   └── formatters.ts
│
├── App.tsx                 # Root component with routing
├── main.tsx                # Entry point
└── index.css               # Tailwind CSS + custom styles
```

## Tech Stack

- **React 18** - UI framework
- **TypeScript** - Type safety
- **Vite** - Build tool and dev server
- **TanStack Query** - Data fetching and caching
- **Axios** - HTTP client
- **React Router** - Client-side routing
- **Tailwind CSS** - Styling
- **Heroicons** - Icons
- **Recharts** - Charts (ready for future use)

## API Integration

The frontend connects to the backend API at `http://localhost:8000/api`.

**Proxy Configuration** (in vite.config.ts):
- `/api` → proxied to backend
- `/ws` → WebSocket proxied to backend

This allows development without CORS issues.

## Next Steps

To continue implementation:

1. **Token Manager Page** (`src/pages/TokenManager.tsx`)
   - Display Schwab API token status
   - Show countdown timer
   - Refresh token button
   - OAuth re-authentication flow

2. **Live Trading Monitor** (`src/pages/LiveTrading.tsx`)
   - Engine status display
   - Positions table with real-time P&L
   - Orders table
   - Event log with WebSocket
   - Trading statistics
   - Equity curve chart

3. **Backtest Runner** (`src/pages/Backtest.tsx`)
   - Strategy selector
   - Parameter form
   - Date range picker
   - Run backtest button
   - Results viewer with charts

4. **Chart Components** (`src/components/charts/`)
   - Equity curve chart (Recharts)
   - Trade histogram
   - Drawdown chart

## Troubleshooting

### Backend not accessible
Ensure the FastAPI backend is running on port 8000:
```bash
cd src/admin_ui/backend
python -m uvicorn main:app --reload --port 8000
```

### Login fails
- Check that backend API is running
- Default credentials: `admin` / `changeme`
- Check browser console for errors

### Services not loading
- Ensure Redis and TimescaleDB are running
- Check Docker containers: `docker ps`
- Verify backend can access Docker API

## Development Tips

- Hot module replacement (HMR) is enabled - changes reflect instantly
- Use React DevTools for debugging
- Check Network tab for API requests
- TanStack Query DevTools can be added for debugging queries

## Environment Variables

Create `.env.local` file if needed:
```bash
VITE_API_URL=http://localhost:8000/api
```

Default is to use the proxy configuration, so this is optional.
