const obsidian = require('obsidian');
const child_process = require('child_process');
const path = require('path');
const fs = require('fs');

const DEFAULT_SETTINGS = {
    autoStartOnLaunch: false,
    crawlIntervalMinutes: 60,
    agentMode: 'autonomous'
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

    startAgent() {
        if (this.agentProcess) {
            new obsidian.Notice('Always-On Memory Agent is already running.');
            return;
        }

        const pythonCmd = this.getPythonCmd();
        const scriptPath = this.getScriptPath('agent.py');
        const projectDir = path.dirname(scriptPath);

        new obsidian.Notice('Starting Always-On Memory Agent...');
        this.updateStatus('Starting...', true);

        try {
            this.agentProcess = child_process.spawn(pythonCmd, [scriptPath], {
                cwd: projectDir,
                detached: false,
                env: { ...process.env, PYTHONIOENCODING: 'utf-8' }
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

    launchDashboard() {
        const pythonCmd = this.getPythonCmd();
        const scriptPath = this.getScriptPath('dashboard.py');
        const projectDir = path.dirname(scriptPath);

        new obsidian.Notice('Launching Memory Dashboard...');

        child_process.execFile(pythonCmd, [scriptPath], { cwd: projectDir, env: { ...process.env, PYTHONIOENCODING: 'utf-8' } }, (error, stdout, stderr) => {
            if (error) {
                console.error('[Memory Dashboard Error]', stderr || error.message);
                new obsidian.Notice(`Dashboard Launch Error: ${error.message}`);
                return;
            }
            console.log('[Memory Dashboard Output]', stdout);
            new obsidian.Notice('Memory Dashboard generated!');
        });
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
    }

    async saveSettings() {
        await this.saveData(this.settings);
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
        containerEl.createEl('h2', { text: 'Always-On Memory Agent Settings' });

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
            .setName('Crawl & Index Vault')
            .setDesc('Trigger an immediate re-index of vault notes into memory.db.')
            .addButton(btn => btn
                .setButtonText('Run Indexer Now')
                .setCta()
                .onClick(() => {
                    this.plugin.runCrawl();
                }));

        new obsidian.Setting(containerEl)
            .setName('Memory Dashboard')
            .setDesc('Generate or refresh the visual Memory Agent dashboard note.')
            .addButton(btn => btn
                .setButtonText('Launch Dashboard')
                .onClick(() => {
                    this.plugin.launchDashboard();
                }));

        new obsidian.Setting(containerEl)
            .setName('Agent Service Control')
            .setDesc('Start or stop the Python memory agent background service.')
            .addButton(btn => btn
                .setButtonText(this.plugin.agentProcess ? 'Stop Agent' : 'Start Agent')
                .setWarning(!!this.plugin.agentProcess)
                .onClick(() => {
                    if (this.plugin.agentProcess) {
                        this.plugin.stopAgent();
                    } else {
                        this.plugin.startAgent();
                    }
                    this.display();
                }));
    }
}

module.exports = AlwaysOnMemoryAgentPlugin;
