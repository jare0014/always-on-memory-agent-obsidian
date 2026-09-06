import asyncio
from datetime import datetime, timezone
from pathlib import Path

from memory_layer.config import ALL_SUPPORTED, TEXT_EXTENSIONS, log
from memory_layer.db import get_db
from memory_layer.runner import MemoryAgent


async def watch_folder(agent: MemoryAgent, folder: Path, poll_interval: int = 5):
    """Watch a folder for new files and ingest them (text, images, audio, video, PDFs)."""
    folder.mkdir(parents=True, exist_ok=True)
    log.info(f"👁️  Watching: {folder}/  (supports: text, images, audio, video, PDFs)")

    while True:
        try:
            db = get_db()
            try:
                for f in sorted(folder.iterdir()):
                    if f.name.startswith("."):
                        continue
                    suffix = f.suffix.lower()
                    if suffix not in ALL_SUPPORTED:
                        continue
                    row = db.execute("SELECT 1 FROM processed_files WHERE path = ?", (str(f),)).fetchone()
                    if row:
                        continue

                    try:
                        if suffix in TEXT_EXTENSIONS:
                            log.info(f"📄 New text file: {f.name}")
                            text = f.read_text(encoding="utf-8", errors="replace")[:10000]
                            if text.strip():
                                await agent.ingest(text, source=f.name)
                        else:
                            log.info(f"🖼️  New media file: {f.name}")
                            await agent.ingest_file(f)
                    except Exception as file_err:
                        log.error(f"Error ingesting {f.name}: {file_err}")

                    db.execute(
                        "INSERT INTO processed_files (path, processed_at) VALUES (?, ?)",
                        (str(f), datetime.now(timezone.utc).isoformat()),
                    )
                    db.commit()
            finally:
                db.close()
        except Exception as e:
            log.error(f"Watch error: {e}")

        await asyncio.sleep(poll_interval)


async def consolidation_loop(agent: MemoryAgent, interval_minutes: int = 30):
    """Run consolidation periodically, like sleep cycles."""
    log.info(f"🔄 Consolidation: every {interval_minutes} minutes")
    while True:
        await asyncio.sleep(interval_minutes * 60)
        try:
            db = get_db()
            count = db.execute("SELECT COUNT(*) as c FROM memories WHERE consolidated = 0").fetchone()["c"]
            db.close()
            if count >= 2:
                log.info(f"🔄 Running consolidation ({count} unconsolidated memories)...")
                result = await agent.consolidate()
                log.info(f"🔄 {result[:100]}")
            else:
                log.info(f"🔄 Skipping consolidation ({count} unconsolidated memories)")
        except Exception as e:
            log.error(f"Consolidation error: {e}")
