"""
Sync Agentic Data Lake to Quant Project Data Lake
Bridges market_datalake.db -> C:/Users/jare0/Documents/Obsidian/04_Projects/Quant/Local_Cache/data_lake.db
"""

import os
import sys
import sqlite3
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SOURCE_DB = os.path.join(os.path.dirname(__file__), "market_datalake.db")
QUANT_DB = r"C:\Users\jare0\Documents\Obsidian\04_Projects\Quant\Local_Cache\data_lake.db"

def sync_datalakes():
    if not os.path.exists(SOURCE_DB):
        print(f"Source DB not found at: {SOURCE_DB}")
        return

    if not os.path.exists(os.path.dirname(QUANT_DB)):
        os.makedirs(os.path.dirname(QUANT_DB), exist_ok=True)

    src_conn = sqlite3.connect(SOURCE_DB)
    quotes_df = pd.read_sql_query("SELECT * FROM intraday_quotes", src_conn)
    scans_df = pd.read_sql_query("SELECT * FROM scanner_breakouts", src_conn)
    src_conn.close()

    dest_conn = sqlite3.connect(QUANT_DB)
    quotes_df.to_sql("agentic_intraday_quotes", dest_conn, if_exists="append", index=False)
    scans_df.to_sql("agentic_scanner_breakouts", dest_conn, if_exists="append", index=False)
    dest_conn.close()

    print(f"✅ Synced {len(quotes_df)} quotes and {len(scans_df)} scanner breakouts into Quant data lake: {QUANT_DB}")

if __name__ == "__main__":
    sync_datalakes()
