import os
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import sqlite3
import requests
from pathlib import Path
from dotenv import load_dotenv

# Load env configuration
load_dotenv()

VAULT_PATH = os.getenv("OBSIDIAN_VAULT", r"C:\Users\jare0\Documents\Obsidian")
AGENT_URL = "http://localhost:8888"
DB_PATH = os.getenv("MEMORY_DB", "memory.db")
COOLDOWN_SECONDS = 3.0  # Time to sleep between notes to let Ollama cool down
CONSOLIDATE_EVERY = 10  # Run consolidation every 10 new notes

def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db

def is_processed(db, path):
    row = db.execute("SELECT 1 FROM processed_files WHERE path = ?", (str(path),)).fetchone()
    return row is not None

def mark_processed(db, path):
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    db.execute("INSERT OR REPLACE INTO processed_files (path, processed_at) VALUES (?, ?)", (str(path), now))
    db.commit()

def crawl_and_ingest():
    vault = Path(VAULT_PATH)
    if not vault.is_dir():
        print(f"Error: Obsidian vault directory not found at {VAULT_PATH}")
        sys.exit(1)
        
    print(f"🔍 Starting crawl of Obsidian Vault: {VAULT_PATH}")
    print(f"🔗 Target Memory Agent: {AGENT_URL}")
    print(f"📦 SQLite DB Tracker: {DB_PATH}")
    print(f"⏱️  Rate Limit: {COOLDOWN_SECONDS}s delay, Consolidate every {CONSOLIDATE_EVERY} notes\n")

    db = get_db()
    
    # Exclude system and hidden folders
    exclude_dirs = {'.git', '.obsidian', '.trash', 'node_modules', '.venv', 'venv', '__pycache__'}
    
    markdown_files = []
    for root, dirs, files in os.walk(vault):
        # Modify dirs in-place to skip excluded directories
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for f in files:
            if f.endswith('.md'):
                markdown_files.append(Path(root) / f)

    total_files = len(markdown_files)
    print(f"📂 Found {total_files} total Markdown (.md) notes.")

    new_notes_count = 0
    skipped_count = 0

    for i, file_path in enumerate(markdown_files):
        # Get path relative to the vault root for clean source representation
        rel_path = file_path.relative_to(vault)
        
        # Check if already processed
        if is_processed(db, rel_path):
            skipped_count += 1
            continue
            
        print(f"[{i+1}/{total_files}] Ingesting: {rel_path} ...")
        
        try:
            # Read note contents
            content = file_path.read_text(encoding="utf-8", errors="replace")
            
            # Skip empty files
            if not content.strip():
                print(f"  ⚠️ Skipped (empty file)")
                mark_processed(db, rel_path)
                continue
                
            # Post to agent
            t0 = time.time()
            res = requests.post(
                f"{AGENT_URL}/ingest",
                json={"text": content, "source": str(rel_path)},
                timeout=120
            )
            elapsed = time.time() - t0
            
            if res.status_code == 200:
                res_data = res.json()
                status = res_data.get("status")
                print(f"  ✅ Ingested successfully in {elapsed:.1f}s (Status: {status})")
                
                # Mark as processed in database
                mark_processed(db, rel_path)
                new_notes_count += 1
                
                # Cooldown delay
                if COOLDOWN_SECONDS > 0:
                    time.sleep(COOLDOWN_SECONDS)
                    
                # Periodic consolidation
                if new_notes_count > 0 and new_notes_count % CONSOLIDATE_EVERY == 0:
                    print(f"\n🔄 Running periodic consolidation for the last {CONSOLIDATE_EVERY} memories...")
                    t_cons = time.time()
                    cons_res = requests.post(f"{AGENT_URL}/consolidate", json={}, timeout=180)
                    if cons_res.status_code == 200:
                        print(f"  ✅ Consolidation complete in {time.time() - t_cons:.1f}s!\n")
                    else:
                        print(f"  ❌ Consolidation failed: {cons_res.status_code}\n")
            else:
                print(f"  ❌ Server error: {res.status_code} - {res.text}")
                
        except Exception as e:
            print(f"  ❌ Error processing file: {e}")
            
    db.close()
    
    print("\n🏁 Crawl finished!")
    print(f"   Stored: {new_notes_count} new memories")
    print(f"   Skipped: {skipped_count} already processed notes")
    
    # Final consolidation if we stored anything new
    if new_notes_count > 0:
        print("\n🔄 Running final consolidation cycle...")
        requests.post(f"{AGENT_URL}/consolidate", json={}, timeout=180)
        print("  ✅ Final consolidation complete!")

if __name__ == "__main__":
    crawl_and_ingest()
