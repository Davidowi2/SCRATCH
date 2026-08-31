# SCRATCH Dashboard

Real-time monitoring dashboard for the SCRATCH trading bot.

## Local Development

1. Install dependencies:
```bash
npm install
```

2. Create `.env.local` file:
```
API_URL=http://localhost:5000
API_KEY=your-secret-api-key-change-this
```

3. Run development server:
```bash
npm run dev
```

4. Open [http://localhost:3000](http://localhost:3000)

## Deploy to Vercel

1. Push code to GitHub

2. Import project to Vercel

3. Add environment variables in Vercel dashboard:
   - `API_URL`: Your VPS API URL (e.g., `http://your-vps-ip:5000`)
   - `API_KEY`: Your API key (must match the one on VPS)

4. Deploy!

## Features

- **Real-time status**: Bot running/stopped indicator
- **Live position**: See current open trade with SL/TP
- **Performance metrics**: Win rate, total P&L, average trade stats
- **Trade history**: Recent closed trades with full details
- **Auto-refresh**: Updates every 5 seconds

## Security

- API key authentication required for all endpoints
- CORS enabled for dashboard access
- Environment variables for sensitive config
