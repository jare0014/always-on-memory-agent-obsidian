from aiohttp import web
from memory_layer.config import log
from memory_layer.db import (
    get_memory_stats,
    delete_memory,
    clear_all_memories
)
from memory_layer.search import read_all_memories, search_memories
from memory_layer.runner import MemoryAgent


def build_http(agent: MemoryAgent, watch_path: str = "./inbox") -> web.Application:
    """Build the aiohttp web application with CORS middleware and all API routes."""
    @web.middleware
    async def cors_middleware(request, handler):
        if request.method == "OPTIONS":
            response = web.Response(status=204)
        else:
            response = await handler(request)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, DELETE"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response

    app = web.Application(middlewares=[cors_middleware])

    async def handle_query(request: web.Request):
        q = request.query.get("q", "").strip()
        if not q:
            return web.json_response({"error": "missing ?q= parameter"}, status=400)
        try:
            answer = await agent.query(q)
            return web.json_response({"question": q, "answer": answer})
        except Exception as e:
            err_msg = str(e)
            log.error(f"Error handling query: {err_msg}")
            if "401" in err_msg or "UNAUTHENTICATED" in err_msg or "No API key" in err_msg:
                return web.json_response({
                    "error": "Gemini API key invalid or unauthenticated (401). Please enter your valid Gemini API key in Always-On Memory Agent settings in Obsidian."
                }, status=401)
            try:
                search_res = search_memories(q, limit=5)
                mems = search_res.get("memories", [])
                if mems:
                    fallback_text = f"**Search Excerpts for:** *{q}*\n\n"
                    for m in mems:
                        fallback_text += f"- **[Memory #{m['id']}]** (*{m.get('source', 'Vault')}*): {m.get('summary') or m.get('raw_text', '')[:200]}\n"
                    return web.json_response({"question": q, "answer": fallback_text, "fallback": True})
            except Exception:
                pass
            return web.json_response({"error": err_msg}, status=500)

    async def handle_ingest(request: web.Request):
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)
        text = data.get("text", "").strip()
        if not text:
            return web.json_response({"error": "missing 'text' field"}, status=400)
        source = data.get("source", "api")
        try:
            result = await agent.ingest(text, source=source)
            return web.json_response({"status": "ingested", "response": result})
        except Exception as e:
            log.error(f"Error handling ingest: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def handle_consolidate(request: web.Request):
        try:
            result = await agent.consolidate()
            return web.json_response({"status": "done", "response": result})
        except Exception as e:
            log.error(f"Error handling consolidate: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def handle_status(request: web.Request):
        stats = get_memory_stats()
        return web.json_response(stats)

    async def handle_memories(request: web.Request):
        data = read_all_memories()
        return web.json_response(data)

    async def handle_delete(request: web.Request):
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)
        memory_id = data.get("memory_id")
        if not memory_id:
            return web.json_response({"error": "missing 'memory_id' field"}, status=400)
        result = delete_memory(int(memory_id))
        return web.json_response(result)

    async def handle_semantic_query(request: web.Request):
        q = request.query.get("q", "").strip()
        top_k = int(request.query.get("top_k", 8))
        if not q:
            return web.json_response({"error": "missing ?q= parameter"}, status=400)
        try:
            results = search_memories(q, limit=top_k)
            return web.json_response(results)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def handle_ping(request: web.Request):
        return web.json_response({"ok": True, "status": "healthy", "service": "always-on-memory-agent"})

    async def handle_clear(request: web.Request):
        result = clear_all_memories(inbox_path=watch_path)
        return web.json_response(result)

    app.router.add_get("/ping", handle_ping)
    app.router.add_get("/query", handle_query)
    app.router.add_get("/semantic-query", handle_semantic_query)
    app.router.add_post("/ingest", handle_ingest)
    app.router.add_post("/consolidate", handle_consolidate)
    app.router.add_get("/status", handle_status)
    app.router.add_get("/memories", handle_memories)
    app.router.add_post("/delete", handle_delete)
    app.router.add_post("/clear", handle_clear)

    return app
