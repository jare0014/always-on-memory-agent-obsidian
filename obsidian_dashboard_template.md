# Always-On Memory Agent Obsidian Dashboard

This note serves as your control center for the Always-On Memory Agent. To use this dashboard, you must have the **Dataview** community plugin installed in Obsidian, and **Enable JavaScript Queries** must be toggled ON in Dataview settings.

Create a new note in Obsidian (e.g., `🧠 Memory Agent.md`) and copy-paste the entire block below:

```dataviewjs
const agentUrl = "http://localhost:8888";

// 1. Fetch current status & statistics
const statsRes = await requestUrl({ url: `${agentUrl}/status`, method: "GET" }).catch(() => null);

if (!statsRes) {
    dv.paragraph("❌ **Always-On Memory Agent is offline**.<br>Please start the agent backend (`python agent.py`) first.");
} else {
    const stats = JSON.parse(statsRes.text);
    
    // Status & Header
    dv.paragraph(`🟢 **Memory Agent Online** | Total Memories: **${stats.total_memories}** | Pending Consolidation: **${stats.unconsolidated}** | Consolidations: **${stats.consolidations}**`);

    const container = this.container;
    
    // UI Styling
    const styleEl = document.createElement("style");
    styleEl.innerHTML = `
        .memory-dashboard {
            font-family: var(--font-interface);
            color: var(--text-normal);
            margin: 15px 0;
        }
        .memory-section {
            border: 1px solid var(--background-modifier-border);
            border-radius: 8px;
            padding: 16px;
            background: var(--background-primary);
            margin-bottom: 15px;
        }
        .memory-btn {
            background-color: var(--interactive-accent);
            color: var(--text-on-accent);
            border: none;
            padding: 8px 16px;
            border-radius: 5px;
            cursor: pointer;
            font-weight: bold;
            transition: opacity 0.2s;
        }
        .memory-btn:hover {
            opacity: 0.9;
        }
        .memory-btn-sec {
            background-color: var(--background-modifier-border);
            color: var(--text-normal);
            border: 1px solid var(--border-color);
            padding: 8px 16px;
            border-radius: 5px;
            cursor: pointer;
            margin-left: 10px;
        }
        .memory-btn-sec:hover {
            background-color: var(--background-modifier-hover);
        }
        .memory-input {
            width: 70%;
            padding: 8px;
            border-radius: 5px;
            border: 1px solid var(--background-modifier-border);
            background: var(--background-secondary);
            color: var(--text-normal);
            margin-right: 10px;
        }
        .memory-result {
            margin-top: 15px;
            padding: 15px;
            border-radius: 6px;
            background: var(--background-secondary);
            border-left: 4px solid var(--interactive-accent);
            line-height: 1.6;
        }
        .memory-card {
            border-left: 3px solid var(--interactive-accent);
            padding: 8px 12px;
            margin: 10px 0;
            background: var(--background-secondary-alt);
            border-radius: 0 6px 6px 0;
        }
        .memory-tag {
            background: var(--background-modifier-border);
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 11px;
            margin-right: 4px;
            display: inline-block;
        }
    `;
    container.appendChild(styleEl);

    // Section 1: Ingest Current Note
    const ingestSection = container.createEl("div", { cls: "memory-section" });
    ingestSection.createEl("h4", { text: "📥 Ingest Active Note" });
    ingestSection.createEl("p", { 
        text: "Directly process your currently open note into the memory bank.",
        style: "color: var(--text-muted); font-size: 13px; margin-bottom: 12px;" 
    });
    
    const ingestBtn = ingestSection.createEl("button", { text: "⚡ Ingest Active Note", cls: "memory-btn" });
    const ingestStatus = ingestSection.createEl("div", { style: "margin-top: 10px; font-weight: 500;" });
    
    ingestBtn.addEventListener("click", async () => {
        const activeFile = app.workspace.getActiveFile();
        if (!activeFile) {
            ingestStatus.setText("❌ No active note open.");
            return;
        }
        ingestStatus.setText(`⏳ Processing "${activeFile.basename}"...`);
        try {
            const content = await app.vault.read(activeFile);
            const response = await requestUrl({
                url: `${agentUrl}/ingest`,
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ text: content, source: activeFile.name })
            });
            const data = JSON.parse(response.text);
            ingestStatus.setText(`✅ Successfully ingested "${activeFile.basename}"!`);
        } catch (e) {
            ingestStatus.setText(`❌ Error: ${e.message}`);
        }
    });

    // Section 2: Query Memory
    const querySection = container.createEl("div", { cls: "memory-section" });
    querySection.createEl("h4", { text: "🔍 Query Memory Bank" });
    
    const inputEl = querySection.createEl("input", { 
        type: "text", 
        placeholder: "Ask your memory anything...",
        cls: "memory-input"
    });
    
    const queryBtn = querySection.createEl("button", { text: "Ask Agent", cls: "memory-btn" });
    const consolidateBtn = querySection.createEl("button", { text: "🔄 Trigger Consolidation", cls: "memory-btn-sec" });
    
    const resultEl = querySection.createEl("div", { cls: "memory-result", style: "display: none;" });
    
    queryBtn.addEventListener("click", async () => {
        const query = inputEl.value.trim();
        if (!query) return;
        resultEl.style.display = "block";
        resultEl.setText("Searching memory...");
        try {
            const response = await requestUrl({
                url: `${agentUrl}/query?q=${encodeURIComponent(query)}`,
                method: "GET"
            });
            const data = JSON.parse(response.text);
            let answerText = data.answer || "";

            try {
                if (answerText.trim().startsWith('{')) {
                    const parsed = JSON.parse(answerText);
                    const items = parsed.results || parsed.memories || (Array.isArray(parsed) ? parsed : null);
                    if (items && Array.isArray(items)) {
                        let html = parsed.query ? `<p style="margin-bottom:8px;"><strong>🔍 Query:</strong> ${parsed.query}</p>` : '';
                        items.forEach(m => {
                            html += `<div class="memory-card">`;
                            html += `<div style="display:flex; justify-content:space-between; font-size: 11px; color: var(--text-muted);"><span>Memory #${m.id || '?'}</span><span>${m.source || 'Unknown'}</span></div>`;
                            html += `<p style="margin: 6px 0; font-size: 13px;">${m.summary || m.raw_text || 'No summary'}</p>`;
                            if (m.topics && Array.isArray(m.topics)) {
                                html += `<div>${m.topics.map(t => `<span class="memory-tag">${t}</span>`).join('')}</div>`;
                            }
                            html += `</div>`;
                        });
                        resultEl.innerHTML = html;
                        return;
                    }
                }
            } catch(err) {}

            // Clean markdown structure rendering
            resultEl.innerHTML = answerText.replace(/\n/g, "<br>");
        } catch (e) {
            resultEl.setText("Error querying memory agent: " + e.message);
        }
    });
    
    consolidateBtn.addEventListener("click", async () => {
        resultEl.style.display = "block";
        resultEl.setText("⏳ Triggering consolidation process...");
        try {
            const response = await requestUrl({
                url: `${agentUrl}/consolidate`,
                method: "POST"
            });
            const data = JSON.parse(response.text);
            resultEl.innerHTML = `<strong>Consolidation Complete:</strong><br>${data.response.replace(/\n/g, "<br>")}`;
        } catch (e) {
            resultEl.setText("Error running consolidation: " + e.message);
        }
    });

    // Section 3: Recent Memories
    const memoriesSection = container.createEl("div", { cls: "memory-section" });
    memoriesSection.createEl("h4", { text: "🧠 Recent Memories" });
    
    const listContainer = memoriesSection.createEl("div");
    listContainer.setText("Loading recent memories...");
    
    try {
        const response = await requestUrl({
            url: `${agentUrl}/memories`,
            method: "GET"
        });
        const data = JSON.parse(response.text);
        listContainer.setText("");
        
        if (data.memories && data.memories.length > 0) {
            // Show up to 5 memories
            data.memories.slice(0, 5).forEach(m => {
                const card = listContainer.createEl("div", { cls: "memory-card" });
                
                const header = card.createEl("div", { style: "display:flex; justify-content:space-between; font-size: 11px; color: var(--text-muted);" });
                header.createEl("span", { text: `Memory #${m.id}` });
                header.createEl("span", { text: `${m.source || "Unknown"} | ${m.created_at.substring(0,10)}` });
                
                card.createEl("p", { text: m.summary, style: "margin: 6px 0; font-size: 13px;" });
                
                const tagsDiv = card.createEl("div");
                if (m.topics) {
                    m.topics.forEach(t => tagsDiv.createEl("span", { text: t, cls: "memory-tag" }));
                }
            });
        } else {
            listContainer.setText("No memories stored yet.");
        }
    } catch (e) {
        listContainer.setText("Error loading recent memories: " + e.message);
    }
}
```
