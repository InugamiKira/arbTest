# CodexLOFarb - Agents Guide

## What This System Does
LOF基金套利监控系统 - Real-time arbitrage monitoring for Listed Open-Ended Funds (LOF). Tracks A-shares, US ETFs, and futures to detect premium/discount opportunities.

## Tech Stack
- Python 3.11+
- Flask/Dash for web UI
- yfinance, requests, pandas for data
- IB Gateway for real-time market data

## Core Scripts (run order matters)
1. **LOF011_generate_basic_data.py** - Fetches FX rates and ETF history → `data/GLD_USO_basic_data.csv`
2. **LOF012_generate_lof_data.py** - Fetches LOF NAV, calculates static valuations → `data/LOF_{code}_history.csv`
3. **LOF013_woody_web_crawler.py** - Web scraper fallback for missing API data
4. **LOF02_fetch_trade_data.py** - **Core service (Port 5000)** - REST, WebSocket, SSE
5. **LOF03_generate_monitor_html.py** - Generates `lof_monitor.html` monitoring dashboard
6. **LOF00_input_LOF_info.py** - Web config editor (Port 5001)
7. **LOF01_admin_launcher.py** - Admin panel (Port 5002)

## Start the System
```bash
# Option 1: Use the batch script
LOF_start_lof_system.bat

# Option 2: Manual startup order
python -X utf8 LOF011_generate_basic_data.py
python -X utf8 LOF012_generate_lof_data.py
python -X utf8 LOF02_fetch_trade_data.py  # Port 5000
# Then in separate terminals:
python -X utf8 LOF01_admin_launcher.py  # Port 5002
python -X utf8 LOF03_generate_monitor_html.py
```

## Important Paths
- **Config**: `lof_config.yaml`
- **Data**: `data/*.csv`
- **Logs**: `logs/*.log`
- **Core Logic**: `readers/data_fetcher.py`, `readers/trade_manager.py`

## Adding/Updating a Fund
1. Edit `lof_config.yaml` directly or use LOF00 UI (Port 5001)
2. Run: `python -X utf8 LOF011_generate_basic_data.py`
3. Run: `python -X utf8 LOF012_generate_lof_data.py`
4. Restart LOF02 to reload config
5. Run: `python -X utf8 LOF03_generate_monitor_html.py`

## Ports
- **5000**: Main service (LOF02) - MUST be free
- **5001**: Config UI (LOF00)
- **5002**: Admin panel (LOF01)

## Port Conflict Resolution
```powershell
netstat -ano | findstr :5000
taskkill /PID <pid> /F
```

## Three Valuation Methods
1. **Static Official**: T-1 NAV + current ETF/FX changes
2. **Futures Calibration**: Dynamic calibration value (Future/ETF) mapping
3. **Futures Native**: Direct futures price with Beta adjustment

## Data Sources
- **A股**: 新浪/东财 SSE API via `readers/data_fetcher.py`
- **美股**: IB Gateway, Sina fallback
- **期货**: CME via IB
- **汇率**: LOF011 fetches from public APIs

## Troubleshooting
- **IB Data Missing**: Check IB Gateway running + market data subscriptions
- **QMT Not Connecting**: Enable "Expert Mode" in QMT, socket server enabled
- **Data Gaps**: Check `data/access_status.json` for fetch history
- **HTML Not Updating**: Run LOF03 manually after data fixes