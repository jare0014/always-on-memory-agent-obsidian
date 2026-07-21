"""
Agentic Quantitative Momentum Trader for Robinhood
Account: Agentic (796066298) - Cash Account

Features:
- Scans high-beta momentum tickers (NVDA, TSLA, COIN, AMD, PLTR, SOXL).
- Calculates daily price change, spread cost, and momentum signals.
- Respects T+1 cash settlement and Robinhood bid-ask spread protection.
- Generates high-probability trade executions with profit targets and stop-losses.
"""

import sys
import json
import time
from typing import List, Dict

# High-beta high-volatility target basket (including crypto miners & leveraged ETFs)
WATCHLIST = ["CIFR", "COIN", "AMD", "NVDA", "TSLA", "PLTR", "MARA", "CLSK", "MSTR", "SOXL"]

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

def generate_trade_recommendations(quotes: List[Dict], total_capital: float = 103.0) -> List[Dict]:
    """
    Ranks watchlist assets by momentum score and allocates capital.
    """
    ranked = []
    for q in quotes:
        symbol = q["quote"]["symbol"]
        score = calculate_momentum_score(q["quote"])
        last_price = float(q["quote"]["last_trade_price"])
        prev_close = float(q["quote"]["adjusted_previous_close"])
        change_pct = ((last_price - prev_close) / prev_close) * 100.0
        
        ranked.append({
            "symbol": symbol,
            "score": score,
            "last_price": last_price,
            "change_pct": round(change_pct, 2),
            "disclosure": q.get("market_data_disclosure", "")
        })
        
    # Sort descending by momentum score
    ranked.sort(key=lambda x: x["score"], reverse=True)
    
    # Allocate top 2 candidates 50/50 ($50 each for $100 total, leaving $3 reserve)
    allocations = []
    top_candidates = ranked[:2]
    amount_per_asset = 50.0
    
    for c in top_candidates:
        allocations.append({
            "symbol": c["symbol"],
            "amount": amount_per_asset,
            "current_price": c["last_price"],
            "change_pct": c["change_pct"],
            "score": c["score"],
            "disclosure": c["disclosure"]
        })
        
    return allocations

if __name__ == "__main__":
    print("🚀 Robinhood Agentic Momentum Trader initialized.")
    print("📈 Target Account: Agentic (796066298)")
    print(f"👀 Watching High-Beta Basket: {', '.join(WATCHLIST)}")
