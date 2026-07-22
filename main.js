const obsidian = require('obsidian');
const child_process = require('child_process');
const path = require('path');
const fs = require('fs');

const DEFAULT_SETTINGS = {
    autoStartOnLaunch: false,
    llmProvider: 'gemini', // 'gemini' or 'ollama'
    geminiModel: 'gemini-3.1-flash-lite',
    ollamaModel: 'qwen2.5:7b',
    ollamaUrl: 'http://100.93.91.76:11434',
    geminiApiKey: ''
};

const MEMORY_VIEW_TYPE = 'always-on-memory-agent-view';

class AlwaysOnMemoryAgentPlugin extends obsidian.Plugin {
    async onload() {
        console.log('[Always-On Memory Agent] Loading plugin...');
        await this.loadSettings();

        // Register Native Sidebar View
        this.registerView(MEMORY_VIEW_TYPE, (leaf) => new MemoryAgentView(leaf, this));

        // Create Status Bar Item
        this.statusBarItem = this.addStatusBarItem();
        this.checkServiceHealth();
        this.registerInterval(
            window.setInterval(() => this.checkServiceHealth(), 15 * 1000)
        );

        // Add Settings Tab (Renders in Settings Sidebar)
        this.addSettingTab(new AlwaysOnMemoryAgentSettingTab(this.app, this));

        // Add Ribbon Icon
        this.addRibbonIcon('brain', 'Always-On Memory Agent', (evt) => {
            this.showMenu(evt);
        });

        // Command Palette Commands
        this.addCommand({
            id: 'start-memory-agent',
            name: 'Start Memory Service',
            callback: () => this.startAgent()
        });

        this.addCommand({
            id: 'stop-memory-agent',
            name: 'Stop Memory Service',
            callback: () => this.stopAgent()
        });

        this.addCommand({
            id: 'crawl-vault-memory',
            name: 'Crawl & Index Vault Memory',
            callback: () => this.runCrawl()
        });

        this.addCommand({
            id: 'launch-memory-dashboard',
            name: 'Launch Memory Dashboard',
            callback: () => this.launchDashboard()
        });

        this.registerEvent(
            this.app.workspace.on('layout-change', () => {
                setTimeout(() => this.organizeCustomPluginsSidebar(), 200);
            })
        );

        if (this.settings.autoStartOnLaunch) {
            this.startAgent();
        }
    }

    organizeCustomPluginsSidebar() {
        const settingModal = document.querySelector('.modal.mod-settings');
        if (!settingModal) return;
        
        const sidebar = settingModal.querySelector('.vertical-tab-header');
        if (!sidebar) return;
        
        const communitySection = sidebar.querySelector('.vertical-tab-header-group-items[data-section="community-plugins"]');
        if (!communitySection) return;
        
        let folderContainer = communitySection.querySelector('.custom-plugins-folder-container');
        
        const targetPluginIds = [
            'always-on-memory-agent',
            'schedule-assistant-focus-timer',
            'omni-logger',
            'google-keep-sync',
            'grind-manager',
            'knowledge-pipeline',
            'git-logger'
        ];
        
        const targetElements = [];
        const navItems = communitySection.querySelectorAll('.vertical-tab-nav-item');
        navItems.forEach(item => {
            const id = item.getAttribute('data-setting-id');
            if (targetPluginIds.includes(id)) {
                targetElements.push(item);
            }
        });
        
        if (targetElements.length === 0) return;
        
        if (!folderContainer) {
            const folderHeader = document.createElement('div');
            folderHeader.className = 'vertical-tab-nav-item custom-plugins-folder-header';
            folderHeader.style.fontWeight = '600';
            folderHeader.style.cursor = 'pointer';
            folderHeader.style.display = 'flex';
            folderHeader.style.alignItems = 'center';
            folderHeader.style.justifyContent = 'space-between';
            folderHeader.style.padding = '8px 12px';
            folderHeader.style.marginTop = '8px';
            folderHeader.style.borderTop = '1px solid var(--background-modifier-border)';
            
            const headerTitle = document.createElement('span');
            headerTitle.textContent = '📁 Custom Plugins';
            folderHeader.appendChild(headerTitle);
            
            const chevron = document.createElement('span');
            chevron.textContent = '▼';
            chevron.style.fontSize = '0.75rem';
            chevron.style.transition = 'transform 0.2s ease';
            folderHeader.appendChild(chevron);
            
            folderContainer = document.createElement('div');
            folderContainer.className = 'custom-plugins-folder-container';
            folderContainer.style.transition = 'max-height 0.25s ease-out, opacity 0.2s ease';
            folderContainer.style.overflow = 'hidden';
            
            let isCollapsed = localStorage.getItem('custom-plugins-settings-collapsed') === 'true';
            if (isCollapsed) {
                folderContainer.style.maxHeight = '0px';
                folderContainer.style.opacity = '0';
                chevron.style.transform = 'rotate(-90deg)';
            } else {
                folderContainer.style.maxHeight = '500px';
                folderContainer.style.opacity = '1';
            }
            
            folderHeader.onclick = (e) => {
                e.stopPropagation();
                isCollapsed = !isCollapsed;
                localStorage.setItem('custom-plugins-settings-collapsed', isCollapsed);
                if (isCollapsed) {
                    folderContainer.style.maxHeight = '0px';
                    folderContainer.style.opacity = '0';
                    chevron.style.transform = 'rotate(-90deg)';
                } else {
                    folderContainer.style.maxHeight = '500px';
                    folderContainer.style.opacity = '1';
                    chevron.style.transform = 'rotate(0deg)';
                }
            };
            
            const firstTarget = targetElements[0];
            try {
                communitySection.insertBefore(folderHeader, firstTarget);
                communitySection.insertBefore(folderContainer, firstTarget);
            } catch(e) {}
        }
        
        targetElements.forEach(item => {
            if (item.parentElement !== folderContainer) {
                item.style.paddingLeft = '24px';
                folderContainer.appendChild(item);
            }
        });
    }

    onunload() {
        console.log('[Always-On Memory Agent] Unloading plugin...');
        this.stopAgent();
    }

    getPythonCmd() {
        const vaultPath = this.app.vault.adapter.getBasePath();
        const venvPython = path.join(vaultPath, '04_Projects', 'always-on-memory-agent', '.venv', 'Scripts', 'python.exe');
        if (fs.existsSync(venvPython)) {
            return venvPython;
        }
        const pluginVenvPython = path.join(vaultPath, '.obsidian', 'plugins', 'always-on-memory-agent', '.venv', 'Scripts', 'python.exe');
        if (fs.existsSync(pluginVenvPython)) {
            return pluginVenvPython;
        }
        return 'python';
    }

    getScriptPath(scriptName) {
        const vaultPath = this.app.vault.adapter.getBasePath();
        const projectScript = path.join(vaultPath, '04_Projects', 'always-on-memory-agent', scriptName);
        if (fs.existsSync(projectScript)) {
            return projectScript;
        }
        return path.join(vaultPath, '.obsidian', 'plugins', 'always-on-memory-agent', scriptName);
    }

    updateStatus(statusText, isBusy = false) {
        if (!this.statusBarItem) return;
        const icon = isBusy ? '⏳' : (statusText === 'Running' ? '🧠' : '💤');
        this.statusBarItem.setText(`${icon} Memory Agent: ${statusText}`);
    }

    async checkServiceHealth() {
        try {
            const res = await obsidian.requestUrl({ url: 'http://localhost:8888/status', method: 'GET' });
            if (res.status === 200) {
                this.isServiceRunning = true;
                this.updateStatus('Running');
            } else {
                this.isServiceRunning = !!this.agentProcess;
                this.updateStatus(this.isServiceRunning ? 'Running' : 'Stopped');
            }
        } catch(e) {
            this.isServiceRunning = !!this.agentProcess;
            this.updateStatus(this.isServiceRunning ? 'Running' : 'Stopped');
        }
    }

    async startAgent() {
        if (this.agentProcess) {
            new obsidian.Notice('Always-On Memory Agent is already running.');
            return;
        }

        const pythonCmd = this.getPythonCmd();
        const scriptPath = this.getScriptPath('agent.py');
        const projectDir = path.dirname(scriptPath);

        // Retrieve API key securely from Obsidian SecretStorage / System Keychain
        let geminiApiKey = '';
        if (this.app.secretStorage) {
            try {
                geminiApiKey = await this.app.secretStorage.getSecret('always-on-memory-gemini-api-key');
                if (!geminiApiKey) {
                    geminiApiKey = await this.app.secretStorage.getSecret('schedule-assistant-gemini-api-key') || 
                                   await this.app.secretStorage.getSecret('timeblocker-gemini-api-key') || '';
                    if (geminiApiKey) {
                        await this.app.secretStorage.setSecret('always-on-memory-gemini-api-key', geminiApiKey);
                    }
                }
            } catch(e) {}
        }
        if (!geminiApiKey) {
            geminiApiKey = this.settings.geminiApiKey || '';
        }

        new obsidian.Notice('Starting Always-On Memory Agent...');
        this.updateStatus('Starting...', true);

        try {
            this.agentProcess = child_process.spawn(pythonCmd, [scriptPath], {
                cwd: projectDir,
                detached: false,
                env: { 
                    ...process.env, 
                    PYTHONIOENCODING: 'utf-8',
                    GEMINI_API_KEY: geminiApiKey,
                    MODEL: this.settings.llmProvider === 'ollama' 
                        ? `litellm:ollama/${this.settings.ollamaModel || 'gemma3:4b'}` 
                        : (this.settings.geminiModel || 'gemini-3.5-flash-lite'),
                    OLLAMA_API_BASE: this.settings.ollamaUrl || 'http://100.93.91.76:11434'
                }
            });

            this.agentProcess.stdout.on('data', (data) => {
                console.log(`[Memory Agent] ${data.toString().trim()}`);
            });

            this.agentProcess.stderr.on('data', (data) => {
                console.error(`[Memory Agent Error] ${data.toString().trim()}`);
            });

            this.agentProcess.on('close', (code) => {
                console.log(`[Memory Agent] Process exited with code ${code}`);
                this.agentProcess = null;
                this.updateStatus('Stopped');
            });

            this.updateStatus('Running');
            new obsidian.Notice('Always-On Memory Agent background process active.');
        } catch (err) {
            console.error('[Memory Agent] Failed to launch agent:', err);
            new obsidian.Notice(`Failed to start Memory Agent: ${err.message}`);
            this.updateStatus('Error');
        }
    }

    stopAgent() {
        if (this.agentProcess) {
            this.agentProcess.kill();
            this.agentProcess = null;
            this.updateStatus('Stopped');
            new obsidian.Notice('Always-On Memory Agent stopped.');
        } else {
            new obsidian.Notice('Always-On Memory Agent is not running.');
        }
    }

    runCrawl() {
        const pythonCmd = this.getPythonCmd();
        const scriptPath = this.getScriptPath('crawl_vault.py');
        const projectDir = path.dirname(scriptPath);

        new obsidian.Notice('Crawling and indexing Vault memory...');
        this.updateStatus('Indexing...', true);

        child_process.execFile(pythonCmd, [scriptPath], { cwd: projectDir, env: { ...process.env, PYTHONIOENCODING: 'utf-8' } }, (error, stdout, stderr) => {
            if (error) {
                console.error('[Memory Agent Crawl Error]', stderr || error.message);
                new obsidian.Notice(`Vault Crawl Error: ${error.message}`);
                this.updateStatus(this.agentProcess ? 'Running' : 'Stopped');
                return;
            }
            console.log('[Memory Agent Crawl Output]', stdout);
            new obsidian.Notice('Vault Memory indexing complete!');
            this.updateStatus(this.agentProcess ? 'Running' : 'Stopped');
        });
    }

    async launchDashboard() {
        let leaf = this.app.workspace.getLeavesOfType(MEMORY_VIEW_TYPE)[0];
        if (!leaf) {
            leaf = this.app.workspace.getRightLeaf(false) || this.app.workspace.getLeaf('split', 'vertical');
            await leaf.setViewState({ type: MEMORY_VIEW_TYPE, active: true });
        }
        this.app.workspace.revealLeaf(leaf);
        new obsidian.Notice('Memory Agent Side Panel active!');
    }

    showMenu(evt) {
        const menu = new obsidian.Menu();
        if (this.agentProcess) {
            menu.addItem((item) => item.setTitle('Stop Memory Agent').setIcon('cross').onClick(() => this.stopAgent()));
        } else {
            menu.addItem((item) => item.setTitle('Start Memory Agent').setIcon('play').onClick(() => this.startAgent()));
        }
        menu.addItem((item) => item.setTitle('Crawl & Index Vault').setIcon('refresh-cw').onClick(() => this.runCrawl()));
        menu.addItem((item) => item.setTitle('Launch Dashboard').setIcon('layout-dashboard').onClick(() => this.launchDashboard()));
        menu.showAtPosition({ x: evt?.clientX || 100, y: evt?.clientY || 100 });
    }

    async loadSettings() {
        this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
        this.syncEnvFile();
    }

    async saveSettings() {
        await this.saveData(this.settings);
        this.syncEnvFile();
    }

    syncEnvFile() {
        try {
            const vaultPath = this.app.vault.adapter.getBasePath();
            const activeModel = this.settings.llmProvider === 'ollama'
                ? `litellm:ollama/${this.settings.ollamaModel || 'gemma3:4b'}`
                : (this.settings.geminiModel || 'gemini-3.1-flash-lite');

            const ollamaBase = this.settings.ollamaUrl || 'http://127.0.0.1:11434';
            const apiKey = this.settings.geminiApiKey || '';

            const envContent = `GEMINI_API_KEY=${apiKey}\nMODEL=${activeModel}\nOLLAMA_API_BASE=${ollamaBase}\nMEMORY_DB=memory.db\n`;

            const envPaths = [
                path.join(vaultPath, '04_Projects', 'always-on-memory-agent', '.env'),
                path.join(vaultPath, '.obsidian', 'plugins', 'always-on-memory-agent', '.env')
            ];

            envPaths.forEach(p => {
                try {
                    fs.writeFileSync(p, envContent, 'utf-8');
                } catch(e) {}
            });
        } catch(e) {
            console.error('[Memory Agent] Failed to sync .env file:', e);
        }
    }
}

class AlwaysOnMemoryAgentSettingTab extends obsidian.PluginSettingTab {
    constructor(app, plugin) {
        super(app, plugin);
        this.plugin = plugin;
    }

    display() {
        const { containerEl } = this;
        containerEl.empty();
        containerEl.createEl('h2', { text: '🧠 Always-On Memory Agent Settings' });

        // Service Controls Section
        containerEl.createEl('h3', { text: '⚙️ Agent Service Controls' });

        new obsidian.Setting(containerEl)
            .setName('Auto-Start on Launch')
            .setDesc('Automatically start the memory agent background process when Obsidian launches.')
            .addToggle(toggle => toggle
                .setValue(this.plugin.settings.autoStartOnLaunch)
                .onChange(async (value) => {
                    this.plugin.settings.autoStartOnLaunch = value;
                    await this.plugin.saveSettings();
                }));

        const isActive = this.plugin.isServiceRunning || !!this.plugin.agentProcess;
        new obsidian.Setting(containerEl)
            .setName('Agent Service Status')
            .setDesc(isActive ? 'Status: Active (Service online on port 8888)' : 'Status: Stopped')
            .addButton(btn => btn
                .setButtonText(isActive ? 'Stop Agent' : 'Start Agent')
                .setWarning(isActive)
                .setCta(!isActive)
                .onClick(() => {
                    if (isActive) {
                        this.plugin.stopAgent();
                    } else {
                        this.plugin.startAgent();
                    }
                    this.display();
                }));

        new obsidian.Setting(containerEl)
            .setName('Crawl & Index Vault')
            .setDesc('Trigger an immediate re-index of vault notes into memory.db.')
            .addButton(btn => btn
                .setButtonText('Run Indexer Now')
                .onClick(() => {
                    this.plugin.runCrawl();
                }));

        // LLM Provider & Model Configuration Section
        containerEl.createEl('h3', { text: '🤖 LLM Provider & Model Configuration' });

        new obsidian.Setting(containerEl)
            .setName('LLM Provider')
            .setDesc('Choose whether to run on hosted Gemini API or local Ollama.')
            .addDropdown(dropdown => dropdown
                .addOption('gemini', 'Google Gemini API (Cloud)')
                .addOption('ollama', 'Ollama (Local Instance)')
                .setValue(this.plugin.settings.llmProvider)
                .onChange(async (value) => {
                    this.plugin.settings.llmProvider = value;
                    await this.plugin.saveSettings();
                    new obsidian.Notice(`LLM Provider set to: ${value.toUpperCase()}. If agent is running, restart agent to apply.`);
                    this.display();
                }));

        if (this.plugin.settings.llmProvider === 'gemini') {
            const geminiPresetOptions = ['gemini-3.5-flash-lite', 'gemini-3.5-flash', 'gemini-3.1-flash-lite', 'gemini-2.5-flash', 'gemini-2.5-pro'];
            let currentGeminiVal = this.plugin.settings.geminiModel || 'gemini-3.5-flash-lite';
            let isGeminiCustom = (!geminiPresetOptions.includes(currentGeminiVal) && currentGeminiVal !== '') || currentGeminiVal === 'custom';

            new obsidian.Setting(containerEl)
                .setName('Gemini Model')
                .setDesc('Select Gemini model variant.')
                .addDropdown(dropdown => {
                    dropdown
                        .addOption('gemini-3.5-flash-lite', 'Gemini 3.5 Flash-Lite (Fast & Ultra-Light)')
                        .addOption('gemini-3.5-flash', 'Gemini 3.5 Flash')
                        .addOption('gemini-3.1-flash-lite', 'Gemini 3.1 Flash-Lite')
                        .addOption('gemini-2.5-flash', 'Gemini 2.5 Flash')
                        .addOption('gemini-2.5-pro', 'Gemini 2.5 Pro')
                        .addOption('custom', 'Custom...');
                    dropdown.setValue(isGeminiCustom ? 'custom' : currentGeminiVal)
                        .onChange(async (value) => {
                            if (value === 'custom') {
                                this.plugin.settings.geminiModel = this.plugin.settings.customGeminiModel || 'custom';
                            } else {
                                this.plugin.settings.geminiModel = value;
                            }
                            await this.plugin.saveSettings();
                            this.display();
                        });
                });

            if (isGeminiCustom || this.plugin.settings.geminiModel === 'custom') {
                new obsidian.Setting(containerEl)
                    .setName('Custom Gemini Model Name')
                    .setDesc('Enter custom model identifier (e.g. gemini-2.5-flash-preview).')
                    .addText(text => text
                        .setPlaceholder('Custom Gemini model name...')
                        .setValue(this.plugin.settings.customGeminiModel || (isGeminiCustom ? currentGeminiVal : ''))
                        .onChange(async (value) => {
                            this.plugin.settings.customGeminiModel = value.trim();
                            this.plugin.settings.geminiModel = value.trim();
                            await this.plugin.saveSettings();
                        }));
            }

            const geminiKeySetting = new obsidian.Setting(containerEl)
                .setName('Gemini API Key')
                .setDesc('Stored securely in Windows Keychain / OS SecretStorage.')
                .addText(text => {
                    text.inputEl.type = 'password';
                    text.setPlaceholder('Enter Gemini API key...');
                    if (this.app.secretStorage) {
                        this.app.secretStorage.getSecret('always-on-memory-gemini-api-key').then(secret => {
                            if (!secret) {
                                this.app.secretStorage.getSecret('schedule-assistant-gemini-api-key').then(sec => text.setValue(sec || ''));
                            } else {
                                text.setValue(secret || '');
                            }
                        });
                    } else {
                        text.setValue(this.plugin.settings.geminiApiKey || '');
                    }
                    text.onChange(async (value) => {
                        const trimmed = value.trim();
                        if (this.app.secretStorage) {
                            await this.app.secretStorage.setSecret('always-on-memory-gemini-api-key', trimmed);
                        }
                        this.plugin.settings.geminiApiKey = ''; // Never save plain-text to data.json
                        await this.plugin.saveSettings();
                    });
                });
            
            const geminiBadge = createStatusBadge(geminiKeySetting.nameEl);
            (async () => {
                let key = '';
                if (this.app.secretStorage) {
                    key = await this.app.secretStorage.getSecret('always-on-memory-gemini-api-key') || 
                          await this.app.secretStorage.getSecret('schedule-assistant-gemini-api-key') || '';
                }
                updateBadge(geminiBadge, !!key, key ? 'Keychain: Connected' : 'Keychain: Key Missing');
            })();
        } else {
            new obsidian.Setting(containerEl)
                .setName('Ollama Local Model')
                .setDesc('Select or enter local Ollama model identifier.')
                .addDropdown(dropdown => dropdown
                    .addOption('qwen2.5:7b', 'qwen2.5:7b (Recommended Local Model)')
                    .addOption('qwen2.5-coder:7b', 'qwen2.5-coder:7b')
                    .addOption('gemma3:4b', 'gemma3:4b')
                    .addOption('llama3.2', 'llama3.2')
                    .setValue(this.plugin.settings.ollamaModel || 'qwen2.5:7b')
                    .onChange(async (value) => {
                        this.plugin.settings.ollamaModel = value;
                        await this.plugin.saveSettings();
                    }))
                .addText(text => text
                    .setPlaceholder('Or type custom model tag (e.g. gemma3:4b)...')
                    .setValue(this.plugin.settings.ollamaModel)
                    .onChange(async (value) => {
                        if (value.trim()) {
                            this.plugin.settings.ollamaModel = value.trim();
                            await this.plugin.saveSettings();
                        }
                    }));

            new obsidian.Setting(containerEl)
                .setName('Ollama Server Base URL (VPN / Custom Endpoint)')
                .setDesc('Base URL and VPN port for your Ollama instance (e.g. http://100.x.y.z:11434, http://vpn-host:11434, or http://127.0.0.1:11434).')
                .addText(text => text
                    .setPlaceholder('e.g. http://100.64.0.1:11434 or http://127.0.0.1:11434')
                    .setValue(this.plugin.settings.ollamaUrl || 'http://127.0.0.1:11434')
                    .onChange(async (value) => {
                        this.plugin.settings.ollamaUrl = value.trim();
                        await this.plugin.saveSettings();
                    }));
        }

        // Active Configuration Display
        const activeModelStr = this.plugin.settings.llmProvider === 'ollama'
            ? `litellm:ollama/${this.plugin.settings.ollamaModel || 'gemma3:4b'}`
            : (this.plugin.settings.geminiModel || 'gemini-3.1-flash-lite');

        const activeEndpointStr = this.plugin.settings.llmProvider === 'ollama'
            ? (this.plugin.settings.ollamaUrl || 'http://127.0.0.1:11434')
            : 'Google Gemini Cloud API';

        new obsidian.Setting(containerEl)
            .setName('Active Environment Summary')
            .setDesc(`Model: ${activeModelStr} | Endpoint: ${activeEndpointStr} | .env Synced ✅`);
    }
}

class MemoryAgentView extends obsidian.ItemView {
    constructor(leaf, plugin) {
        super(leaf);
        this.plugin = plugin;
    }

    getViewType() {
        return MEMORY_VIEW_TYPE;
    }

    getDisplayText() {
        return 'Always-On Memory Agent';
    }

    getIcon() {
        return 'brain';
    }

    async onOpen() {
        const container = this.containerEl.children[1];
        container.empty();
        container.classList.add('always-on-memory-view');
        container.style.padding = '15px';
        container.style.overflowY = 'auto';

        // Inject Card CSS Styles
        const styleEl = container.createEl('style');
        styleEl.innerHTML = `
            .always-on-memory-card {
                border: 1px solid var(--background-modifier-border, rgba(255, 255, 255, 0.15)) !important;
                border-left: 4px solid var(--interactive-accent, #7b61ff) !important;
                padding: 12px 14px !important;
                background: var(--background-secondary-alt, var(--background-secondary, rgba(255, 255, 255, 0.04))) !important;
                border-radius: 8px !important;
                box-shadow: 0 3px 10px rgba(0, 0, 0, 0.25) !important;
                margin-bottom: 12px !important;
                transition: transform 0.15s ease, box-shadow 0.15s ease;
            }
            .always-on-memory-card:hover {
                box-shadow: 0 5px 14px rgba(0, 0, 0, 0.35) !important;
                border-color: var(--interactive-accent, #7b61ff) !important;
            }
            .always-on-memory-tag {
                background: rgba(123, 97, 255, 0.18) !important;
                color: var(--text-accent, #aa99ff) !important;
                border: 1px solid rgba(123, 97, 255, 0.35) !important;
                padding: 2px 8px !important;
                border-radius: 12px !important;
                font-size: 0.75em !important;
                font-weight: 500 !important;
                display: inline-block !important;
            }
        `;

        // Header
        const header = container.createDiv({ style: 'margin-bottom:15px; border-bottom:1px solid var(--background-modifier-border); padding-bottom:10px;' });
        header.createEl('h3', { text: '🧠 Memory Agent Side Panel', style: 'margin:0 0 5px 0;' });
        const statusSpan = header.createEl('span', { text: 'Checking connection...', style: 'font-size:0.85em; color:var(--text-muted);' });

        // Memory Stats Card
        const statsCard = container.createDiv({ style: 'background:var(--background-secondary); padding:10px 12px; border-radius:8px; margin-bottom:15px; border:1px solid var(--background-modifier-border);' });
        const statsText = statsCard.createEl('div', { text: 'Loading stats...', style: 'font-size:0.9em;' });

        const refreshStats = async () => {
            try {
                const res = await obsidian.requestUrl({ url: 'http://localhost:8888/status', method: 'GET' });
                if (res.status === 200) {
                    const stats = JSON.parse(res.text);
                    statusSpan.setText('🟢 Memory Service Online');
                    statusSpan.style.color = '#30d158';
                    statsText.innerHTML = `Memories: <b>${stats.total_memories || 0}</b> | Pending: <b>${stats.unconsolidated || 0}</b> | Consolidations: <b>${stats.consolidations || 0}</b>`;
                } else {
                    statusSpan.setText('❌ Service Offline');
                    statusSpan.style.color = '#ff453a';
                    statsText.setText('Service offline. Please start the background agent service in settings or ribbon menu.');
                }
            } catch (e) {
                statusSpan.setText('❌ Service Offline');
                statusSpan.style.color = '#ff453a';
                statsText.setText('Service offline. Please start the background agent service in settings or ribbon menu.');
            }
        };
        refreshStats();

        // Section: Search & Query Memory
        const querySection = container.createDiv({ style: 'margin-bottom:15px; border:1px solid var(--background-modifier-border); border-radius:8px; padding:12px; background:var(--background-primary);' });
        querySection.createEl('h4', { text: '🔍 Search & Query Memory', style: 'margin:0 0 8px 0;' });
        
        const queryRow = querySection.createDiv({ style: 'display:flex; gap:6px; margin-bottom:8px;' });
        const queryInput = queryRow.createEl('input', { type: 'text', placeholder: 'Ask your memory agent...', style: 'flex:1; padding:6px 10px; border-radius:6px; border:1px solid var(--background-modifier-border); background:var(--background-secondary); color:var(--text-normal);' });
        const queryBtn = queryRow.createEl('button', { text: 'Ask', cls: 'mod-cta' });
        
        const resultBox = querySection.createDiv({ style: 'display:none; margin-top:10px; padding:10px; border-radius:6px; background:var(--background-secondary); border-left:3px solid var(--interactive-accent); font-size:0.9em; line-height:1.5; white-space:pre-wrap;' });

        const executeQuery = async () => {
            const q = queryInput.value.trim();
            if (!q) return;
            queryBtn.setText('Querying...');
            resultBox.style.display = 'block';
            resultBox.setText('Thinking...');
            try {
                const res = await obsidian.requestUrl({ url: `http://localhost:8888/query?q=${encodeURIComponent(q)}`, method: 'GET' });
                if (res.status === 200) {
                    const data = JSON.parse(res.text);
                    resultBox.setText(data.answer || 'No answer returned.');
                } else if (res.status === 401) {
                    resultBox.setText('⚠️ API Key Error: Please enter a valid Gemini API key in Always-On Memory Agent settings.');
                } else {
                    resultBox.setText(`❌ Error: ${res.text}`);
                }
            } catch (e) {
                resultBox.setText(`❌ Query Failed: ${e.message}`);
            } finally {
                queryBtn.setText('Ask');
            }
        };

        queryBtn.onclick = executeQuery;
        queryInput.onkeydown = (e) => {
            if (e.key === 'Enter') executeQuery();
        };

        // Section: Recent Memories & Consolidated Insights Cards
        const recentSection = container.createDiv({ style: 'margin-top:15px; border:1px solid var(--background-modifier-border); border-radius:8px; padding:12px; background:var(--background-primary);' });
        const recentHeader = recentSection.createDiv({ style: 'display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;' });
        recentHeader.createEl('h4', { text: '🧠 Recent Memories & Insights', style: 'margin:0;' });
        const refreshMemoriesBtn = recentHeader.createEl('button', { text: '↻ Refresh', style: 'font-size:0.8em; padding:2px 8px;' });

        const cardsContainer = recentSection.createDiv({ style: 'display:flex; flex-direction:column; gap:12px; margin-top:8px;' });

        const loadRecentMemories = async () => {
            cardsContainer.empty();
            const loadingMsg = cardsContainer.createDiv({ text: 'Loading recent memories...', style: 'font-size:0.85em; color:var(--text-muted);' });
            try {
                const res = await obsidian.requestUrl({ url: 'http://localhost:8888/memories', method: 'GET' });
                if (res.status === 200) {
                    loadingMsg.remove();
                    const data = JSON.parse(res.text);
                    const memories = data.memories || [];
                    if (memories.length === 0) {
                        cardsContainer.createDiv({ text: 'No memories stored in database yet.', style: 'font-size:0.85em; color:var(--text-muted);' });
                        return;
                    }
                    memories.slice(0, 6).forEach(m => {
                        const card = cardsContainer.createDiv();
                        card.style.cssText = 'display:block !important; border:1px solid var(--background-modifier-border, #3a3a3c) !important; border-left:4px solid var(--interactive-accent, #7b61ff) !important; padding:12px 14px !important; background:var(--background-secondary-alt, var(--background-secondary, #242426)) !important; border-radius:8px !important; font-size:0.85em; box-shadow:0 4px 10px rgba(0,0,0,0.25) !important; margin-bottom:12px !important;';
                        
                        const cardMeta = card.createDiv({ style: 'display:flex; justify-content:space-between; align-items:center; font-size:0.8em; color:var(--text-muted, #8e8e93); margin-bottom:6px; font-weight:600;' });
                        cardMeta.createSpan({ text: `Memory #${m.id}`, style: 'color:var(--interactive-accent, #7b61ff); font-weight:bold;' });
                        cardMeta.createSpan({ text: `${m.source || 'Vault'} • ${(m.created_at || '').substring(0, 10)}` });

                        card.createEl('p', { text: m.summary || m.raw_text || 'No summary available.', style: 'margin:0 0 8px 0; line-height:1.45; color:var(--text-normal, #dcddde); font-size:0.95em;' });

                        if (m.topics && Array.isArray(m.topics) && m.topics.length > 0) {
                            const tagsDiv = card.createDiv({ style: 'display:flex; flex-wrap:wrap; gap:5px; margin-top:4px;' });
                            m.topics.forEach(tag => {
                                const tagSpan = tagsDiv.createSpan({ text: `#${tag}` });
                                tagSpan.style.cssText = 'display:inline-block !important; background:rgba(123, 97, 255, 0.2) !important; color:var(--text-accent, #a792ff) !important; border:1px solid rgba(123, 97, 255, 0.4) !important; padding:2px 8px !important; border-radius:12px !important; font-size:0.75em !important; font-weight:500 !important;';
                            });
                        }
                    });
                } else {
                    loadingMsg.setText('Unable to fetch memories (Service Offline)');
                }
            } catch (e) {
                loadingMsg.setText('Memory service offline. Start backend to view cards.');
            }
        };

        refreshMemoriesBtn.onclick = loadRecentMemories;
        loadRecentMemories();

        // Section: Agent Controls
        const actionsSection = container.createDiv({ style: 'margin-top:15px; display:flex; flex-direction:column; gap:8px;' });
        const crawlBtn = actionsSection.createEl('button', { text: '🔄 Crawl & Index Vault Now' });
        crawlBtn.onclick = () => {
            this.plugin.runCrawl();
            setTimeout(() => {
                refreshStats();
                loadRecentMemories();
            }, 3500);
        };

        const consolidateBtn = actionsSection.createEl('button', { text: '🧩 Consolidate Memories Now' });
        consolidateBtn.onclick = async () => {
            consolidateBtn.setText('Consolidating...');
            try {
                const res = await obsidian.requestUrl({ url: 'http://localhost:8888/consolidate', method: 'POST' });
                new obsidian.Notice('Consolidation complete!');
            } catch(e) {
                new obsidian.Notice(`Consolidation failed: ${e.message}`);
            } finally {
                consolidateBtn.setText('🧩 Consolidate Memories Now');
                refreshStats();
                loadRecentMemories();
            }
        };
    }
}

module.exports = AlwaysOnMemoryAgentPlugin;
