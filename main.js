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

class AlwaysOnMemoryAgentPlugin extends obsidian.Plugin {
    async onload() {
        console.log('[Always-On Memory Agent] Loading plugin...');
        await this.loadSettings();

        // Create Status Bar Item
        this.statusBarItem = this.addStatusBarItem();
        this.updateStatus('Stopped');

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
                geminiApiKey = await this.app.secretStorage.getSecret('always-on-memory-gemini-api-key') || 
                               await this.app.secretStorage.getSecret('schedule-assistant-gemini-api-key') || 
                               await this.app.secretStorage.getSecret('timeblocker-gemini-api-key') || '';
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
        new obsidian.Notice('Opening Memory Dashboard in Side Panel...');

        const dashboardNotePath = '03_Knowledge/🧠 Memory Agent Dashboard.md';
        const templateFile = this.getScriptPath('obsidian_dashboard_template.md');
        let templateContent = '';

        if (fs.existsSync(templateFile)) {
            const raw = fs.readFileSync(templateFile, 'utf-8');
            const match = raw.match(/```dataviewjs[\s\S]*?```/);
            if (match) {
                templateContent = `# 🧠 Always-On Memory Agent Dashboard\n\n${match[0]}`;
            }
        }

        if (!templateContent) {
            templateContent = `# 🧠 Always-On Memory Agent Dashboard\n\n\`\`\`dataviewjs\nconst agentUrl = "http://localhost:8888";\nconst statsRes = await requestUrl({ url: \`\${agentUrl}/status\`, method: "GET" }).catch(() => null);\nif (!statsRes) {\n    dv.paragraph("❌ **Always-On Memory Agent is offline**.<br>Please start the agent backend (\`python agent.py\`) first.");\n} else {\n    const stats = JSON.parse(statsRes.text);\n    dv.paragraph(\`🟢 **Memory Agent Online** | Total Memories: **\${stats.total_memories}** | Pending Consolidation: **\${stats.unconsolidated}** | Consolidations: **\${stats.consolidations}**\`);\n}\n\`\`\``;
        }

        let tFile = this.app.vault.getAbstractFileByPath(dashboardNotePath);
        if (!tFile) {
            tFile = await this.app.vault.create(dashboardNotePath, templateContent);
        } else {
            await this.app.vault.modify(tFile, templateContent);
        }

        let leaf = this.app.workspace.getRightLeaf(false);
        if (!leaf) {
            leaf = this.app.workspace.getLeaf('split', 'vertical');
        }

        await leaf.openFile(tFile);
        this.app.workspace.revealLeaf(leaf);

        new obsidian.Notice('Memory Agent Dashboard active in Side Panel!');
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

        new obsidian.Setting(containerEl)
            .setName('Agent Service Status')
            .setDesc(this.plugin.agentProcess ? 'Status: Active (Process running in background)' : 'Status: Stopped')
            .addButton(btn => btn
                .setButtonText(this.plugin.agentProcess ? 'Stop Agent' : 'Start Agent')
                .setWarning(!!this.plugin.agentProcess)
                .setCta(!this.plugin.agentProcess)
                .onClick(() => {
                    if (this.plugin.agentProcess) {
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

module.exports = AlwaysOnMemoryAgentPlugin;
