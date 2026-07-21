"""
Robinhood Intraday Market Data Lake & Time-Series Logger
Database: market_datalake.db (SQLite Time-Series Data Lake)

Accumulates:
1. intraday_quotes: Real-time 5-minute quotes, bid-ask spreads, and price movement.
2. scanner_breakouts: Full-market scanner breakout candidates, relative volume surges, and SMAs.
3. portfolio_snapshots: Portfolio equity, cash reserves, and unrealized P&L snapshots over time.
4. agent_trades: Execution logs, order IDs, fill prices, and trade performance.
"""

import os
import sys
import sqlite3
import datetime
from typing import List, Dict, Any

DB_PATH = os.path.join(os.path.dirname(__file__), "market_datalake.db")

def init_db(db_path: str = DB_PATH):
    """Creates the data lake SQLite tables and indexes if they do not exist."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 1. Intraday Ticker Quotes
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS intraday_quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            symbol TEXT NOT NULL,
            last_price REAL,
            bid_price REAL,
            ask_price REAL,
            previous_close REAL,
            change_pct REAL,
            spread_pct REAL
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_quotes_sym_ts ON intraday_quotes(symbol, timestamp)")

    # 2. Market Scanner Breakout Snapshots
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scanner_breakouts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            scan_id TEXT,
            symbol TEXT NOT NULL,
            name TEXT,
            last_price REAL,
            change_pct REAL,
            relative_volume REAL,
            volume REAL,
            sma_20 REAL,
            sma_50 REAL,
            sma_200 REAL,
            high_50d REAL
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_scan_ts ON scanner_breakouts(timestamp)")

    # 3. Portfolio Snapshots
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS portfolio_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            account_number TEXT NOT NULL,
            total_value REAL,
            equity_value REAL,
            cash REAL,
            buying_power REAL
        )
    """)

    # 4. Agent Executed Trades
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            order_id TEXT UNIQUE,
            account_number TEXT,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            dollar_amount REAL,
            quantity REAL,
            fill_price REAL,
            status TEXT
        )
    """)

    conn.commit()
    conn.close()

def log_intraday_quotes(quotes: List[Dict[str, Any]], db_path: str = DB_PATH):
    """Logs real-time quote snapshots into the data lake."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    for q in quotes:
        quote_data = q.get("quote", q)
        symbol = quote_data.get("symbol", "")
        if not symbol:
            continue

        last_price = float(quote_data.get("last_trade_price", 0) or 0)
        bid = float(quote_data.get("bid_price", 0) or 0)
        ask = float(quote_data.get("ask_price", 0) or 0)
        prev_close = float(quote_data.get("adjusted_previous_close", last_price) or last_price)

        change_pct = ((last_price - prev_close) / prev_close * 100.0) if prev_close > 0 else 0.0
        spread_pct = ((ask - bid) / last_price * 100.0) if last_price > 0 and ask > bid else 0.0

        cursor.execute("""
            INSERT INTO intraday_quotes 
            (timestamp, symbol, last_price, bid_price, ask_price, previous_close, change_pct, spread_pct)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (now_iso, symbol, last_price, bid, ask, prev_close, round(change_pct, 4), round(spread_pct, 4)))

    conn.commit()
    conn.close()

def log_scanner_results(results: List[Dict[str, Any]], scan_id: str = "", db_path: str = DB_PATH):
    """Logs full-universe market scanner breakout discoveries into the data lake."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    for item in results:
        ticker = item.get("ticker", "")
        cols = item.get("columns", {})
        if not ticker and "Symbol" in cols:
            ticker = cols["Symbol"]
        if not ticker:
            continue

        name = cols.get("Name", "")
        last_price = float(cols.get("Last", 0) or 0)
        change_pct = float(cols.get("% Change", 0) or 0)
        rel_vol = float(cols.get("Relative volume", 0) or 0)
        volume = float(cols.get("Volume", 0) or 0)
        sma_20 = float(cols.get("SMA (20)", 0) or 0)
        sma_50 = float(cols.get("SMA (50)", 0) or 0)
        sma_200 = float(cols.get("SMA (200)", 0) or 0)
        high_50d = float(cols.get("High (50D)", 0) or 0)

        cursor.execute("""
            INSERT INTO scanner_breakouts
            (timestamp, scan_id, symbol, name, last_price, change_pct, relative_volume, volume, sma_20, sma_50, sma_200, high_50d)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (now_iso, scan_id, ticker, name, last_price, round(change_pct, 4), round(rel_vol, 4), volume, sma_20, sma_50, sma_200, high_50d))

    conn.commit()
    conn.close()

def log_portfolio_snapshot(account_num: str, portfolio_data: Dict[str, Any], db_path: str = DB_PATH):
    """Logs portfolio valuation and cash reserves into the data lake."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    total = float(portfolio_data.get("total_value", 0) or 0)
    equity = float(portfolio_data.get("equity_value", 0) or 0)
    cash = float(portfolio_data.get("cash", 0) or 0)
    buying_power = float(portfolio_data.get("buying_power", {}).get("buying_power", cash) or cash)

    cursor.execute("""
        INSERT INTO portfolio_snapshots
        (timestamp, account_number, total_value, equity_value, cash, buying_power)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (now_iso, account_num, total, equity, cash, buying_power))

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print(f"📦 Robinhood Intraday Market Data Lake initialized: {DB_PATH}")
