# Quant-Vibe Admin UI - Frontend

React-based frontend for the Quant-Vibe Admin UI.

## Features

- Service management (Docker control)
- Schwab token management
- Live trading monitoring
- Backtest execution and results
- Configuration management
- Real-time updates via WebSocket

## Development

### Setup

```bash
cd src/admin_ui/frontend
npm install
```

### Run Development Server

```bash
npm run dev
```

The dev server will run on http://localhost:3000 and proxy API requests to http://localhost:8000

### Build for Production

```bash
npm run build
```

Output will be in `dist/` directory.

## Project Structure

```
src/
├── components/     # Reusable React components
│   ├── TokenManager.tsx
│   ├── LiveDashboard.tsx
│   ├── ServiceStatus.tsx
│   └── BacktestRunner.tsx
├── pages/          # Page components
│   ├── Login.tsx
│   ├── Dashboard.tsx
│   └── Settings.tsx
├── api/            # API client
│   └── client.ts
├── hooks/          # Custom React hooks
│   └── useWebSocket.ts
└── App.tsx         # Main app component
```

## Technology Stack

- **React 18** - UI framework
- **TypeScript** - Type safety
- **React Router** - Routing
- **TanStack Query** - Data fetching and caching
- **Axios** - HTTP client
- **Recharts** - Charts and visualizations
- **Vite** - Build tool

## API Integration

The frontend communicates with the FastAPI backend via:
- REST API: http://localhost:8000/api
- WebSocket: ws://localhost:8000/ws/events

All API calls are authenticated using JWT tokens.
