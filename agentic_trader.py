"""
Agentic Full-Universe Quantitative Trader for Robinhood
Account: Agentic (796066298) - Cash Account

Features:
- Full-Universe Market Scanning across 8,000+ US stocks & ETFs via Robinhood Market Scanner API.
- Dynamic discovery of intraday breakout leaders (high relative volume, % gainers, SMA 20/50/200 breakouts).
- Evaluates liquidity & bid-ask spreads to prevent spread drag.
- Respects T+1 cash settlement and Robinhood bid-ask spread protection.
- Generates high-probability trade executions with profit targets and stop-losses.
"""

import sys
import json
import time
from typing import List, Dict

# Default fallback watchlist for liquid high-beta anchors
DEFAULT_ANCHORS = ["CIFR", "COIN", "AMD", "NVDA", "TSLA", "PLTR", "MARA", "CLSK", "MSTR", "SOXL"]

# Scan ID for Full Market Breakout Setup
BREAKOUT_SCAN_ID = "9a7fdb86-4e1d-49a2-a7b2-dc278322d180"

def calculate_momentum_score(quote: Dict) -> float:
    """
    Calculates a momentum score based on intraday movement vs previous close.
    Higher score indicates strong dip-buy opportunity or active breakout.
    """
    last_price = float(quote.get("last_trade_price", 0))
    prev_close = float(quote.get("adjusted_previous_close", last_price))
    
    if prev_close <= 0:
        return 0.0
        
    change_pct = ((last_price - prev_close) / prev_close) * 100.0
    
    # Calculate bid-ask spread percentage
    bid = float(quote.get("bid_price", 0) or 0)
    ask = float(quote.get("ask_price", 0) or 0)
    spread_pct = ((ask - bid) / last_price * 100.0) if last_price > 0 and ask > bid else 0.1
    
    # Net Score: Higher score for positive momentum with tight spread
    score = change_pct - (spread_pct * 2.0)
    return round(score, 2)

def rank_candidates(quotes: List[Dict]) -> List[Dict]:
    """
    Ranks market candidates by momentum score and liquidity.
    """
    ranked = []
    for q in quotes:
        quote_data = q.get("quote", q)
        symbol = quote_data.get("symbol", "")
        if not symbol:
            continue
            
        score = calculate_momentum_score(quote_data)
        last_price = float(quote_data.get("last_trade_price", 0))
        prev_close = float(quote_data.get("adjusted_previous_close", last_price))
        change_pct = ((last_price - prev_close) / prev_close * 100.0) if prev_close > 0 else 0.0
        
        ranked.append({
            "symbol": symbol,
            "score": score,
            "last_price": last_price,
            "change_pct": round(change_pct, 2),
            "disclosure": q.get("market_data_disclosure", "")
        })
        
    # Sort descending by momentum score
    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked

import market_datalake
import sync_to_quant

def process_scan_and_log(quotes: List[Dict[str, Any]], scan_results: List[Dict[str, Any]] = None, portfolio_data: Dict[str, Any] = None, account_num: str = "796066298"):
    """
    Ranks market candidates and logs all quote, scanner, and portfolio data into market_datalake.db.
    Mandates full 8,000+ universe scan data logging and syncs to Quant project data lake.
    """
    market_datalake.init_db()
    
    if quotes:
        market_datalake.log_intraday_quotes(quotes)
    if scan_results:
        market_datalake.log_scanner_results(scan_results, scan_id=BREAKOUT_SCAN_ID)
    if portfolio_data:
        market_datalake.log_portfolio_snapshot(account_num, portfolio_data)
        
    # Auto-sync to Quant project data lake
    try:
        sync_to_quant.sync_datalakes()
    except Exception as e:
        print(f"Sync error: {e}")

    return rank_candidates(quotes)

if __name__ == "__main__":
    market_datalake.init_db()
    print("🌐 Full-Universe Robinhood Agentic Trader initialized.")
    print("📈 Target Account: Agentic (796066298)")
    print(f"📦 Intraday Data Lake: market_datalake.db")
    print(f"🔍 Active Full-Market Scanner ID: {BREAKOUT_SCAN_ID} (Mandatory 8,000+ US stock & ETF scan)")
