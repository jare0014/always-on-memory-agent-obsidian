import sys
import json
import agentic_trader

def run_test():
    symbols = ["SMCI", "NBIS", "CBRS", "DOCN", "SOXL", "DELL", "CRWV", "COIN", "AMD"]
    print("=========================================================================")
    print("📈 PRE-MARKET QUANTITATIVE STRATEGY RESONANCE TEST (5-MIN VWAP/RVOL/RSI)")
    print("=========================================================================")
    
    # We will simulate the evaluation output for top breakout leaders
    print(f"{'Ticker':<7} | {'Price':<8} | {'VWAP':<8} | {'RSI':<5} | {'RVOL':<5} | {'Pass All Gates?':<16} | {'Setup Classification'}")
    print("-" * 85)
    
    # Run test evaluation
    mock_quotes = [
        {"quote": {"symbol": "SMCI", "last_trade_price": "29.55", "adjusted_previous_close": "23.83", "bid_price": "29.50", "ask_price": "29.60"}},
        {"quote": {"symbol": "NBIS", "last_trade_price": "218.25", "adjusted_previous_close": "182.62", "bid_price": "218.00", "ask_price": "218.50"}},
        {"quote": {"symbol": "CBRS", "last_trade_price": "208.32", "adjusted_previous_close": "176.88", "bid_price": "208.00", "ask_price": "208.60"}},
        {"quote": {"symbol": "DOCN", "last_trade_price": "138.00", "adjusted_previous_close": "119.09", "bid_price": "137.80", "ask_price": "138.20"}},
        {"quote": {"symbol": "DELL", "last_trade_price": "425.00", "adjusted_previous_close": "381.25", "bid_price": "424.50", "ask_price": "425.50"}},
        {"quote": {"symbol": "COIN", "last_trade_price": "175.95", "adjusted_previous_close": "160.43", "bid_price": "175.80", "ask_price": "176.10"}},
        {"quote": {"symbol": "AMD", "last_trade_price": "544.92", "adjusted_previous_close": "503.57", "bid_price": "544.70", "ask_price": "545.10"}}
    ]
    
    # Generate 5-min synthetic/historical bars
    for item in mock_quotes:
        q = item["quote"]
        sym = q["symbol"]
        price = float(q["last_trade_price"])
        prev = float(q["adjusted_previous_close"])
        
        # Build 10 5-min bars for testing
        bars = []
        for i in range(10):
            p = prev + (price - prev) * ((i + 1) / 10.0)
            bars.append({"close_price": p, "volume": 100000 * (1.0 + (i * 0.2))})
            
        res = agentic_trader.evaluate_paper_strategy_resonance(sym, bars, q)
        pass_str = "✅ YES (PASS)" if res["pass_all_gates"] else "❌ NO (WATCH)"
        print(f"{sym:<7} | ${res['curr_price']:<7.2f} | ${res['vwap']:<7.2f} | {res['rsi']:<5.1f} | {res['rvol']:<5.1f} | {pass_str:<16} | {res['setup']}")

if __name__ == "__main__":
    run_test()
