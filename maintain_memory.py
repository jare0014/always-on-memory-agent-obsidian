import sqlite3
import os
import sys
import json
import urllib.request
import urllib.parse
from pathlib import Path
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

DB_PATH = os.getenv("MEMORY_DB", r"c:\Users\jare0\Documents\Obsidian\04_Projects\always-on-memory-agent\memory.db")
AGENT_URL = os.getenv("AGENT_URL", "http://localhost:8888")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def audit_and_prune_archives():
    """Remove memories originating from archive, trash, or temp directories."""
    conn = get_db()
    cursor = conn.cursor()
    
    archive_patterns = [
        '%99_Archive%',
        '%.trash%',
        '%00_Imports%',
        '%scratch%',
        '%.gemini%'
    ]
    
    total_pruned = 0
    for pattern in archive_patterns:
        cursor.execute("DELETE FROM memories WHERE source LIKE ?", (pattern,))
        pruned = cursor.rowcount
        total_pruned += pruned
        cursor.execute("DELETE FROM processed_files WHERE path LIKE ?", (pattern,))
        
    conn.commit()
    conn.close()
    print(f"🧹 Pruned {total_pruned} archived/temp memories from memory.db.")
    return total_pruned

def deduplicate_memories():
    """Remove duplicate memory entries based on identical raw_text or summary."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        DELETE FROM memories 
        WHERE id NOT IN (
            SELECT MIN(id) 
            FROM memories 
            GROUP BY summary
        )
    """)
    dups_removed = cursor.rowcount
    conn.commit()
    conn.close()
    print(f"✂️ Removed {dups_removed} duplicate memories.")
    return dups_removed

def vacuum_database():
    """Compact SQLite database and optimize indices."""
    conn = get_db()
    conn.execute("VACUUM")
    conn.execute("ANALYZE")
    conn.close()
    print("⚡ Database vacuumed and optimized.")

def trigger_consolidation():
    """Trigger the memory agent server to consolidate raw memories into high-level insights."""
    url = f"{AGENT_URL.rstrip('/')}/consolidate"
    try:
        req = urllib.request.Request(url, data=b"{}", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            print(f"🧠 Consolidation trigger complete: {data}")
    except Exception as e:
        print(f"⚠️ Consolidation trigger failed (is agent running on {AGENT_URL}?): {e}")

def run_full_maintenance():
    print("=== 🛠️ Memory Agent Bank Maintenance ===")
    audit_and_prune_archives()
    deduplicate_memories()
    vacuum_database()
    trigger_consolidation()
    print("=== ✅ Maintenance Complete ===")

if __name__ == "__main__":
    run_full_maintenance()
