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

        // Add Ribbon Icon
        this.addRibbonIcon('brain', 'Always-On Memory Agent', () => {
            this.showMenu();
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

        if (this.settings.autoStartOnLaunch) {
            this.startAgent();
        }
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

    showMenu() {
        const menu = new obsidian.Menu();
        if (this.agentProcess) {
            menu.addItem((item) => item.setTitle('Stop Memory Agent').setIcon('cross').onClick(() => this.stopAgent()));
        } else {
            menu.addItem((item) => item.setTitle('Start Memory Agent').setIcon('play').onClick(() => this.startAgent()));
        }
        menu.addItem((item) => item.setTitle('Crawl & Index Vault').setIcon('refresh-cw').onClick(() => this.runCrawl()));
        menu.addItem((item) => item.setTitle('Launch Dashboard').setIcon('layout-dashboard').onClick(() => this.launchDashboard()));
        menu.showAtPosition({ x: event?.clientX || 100, y: event?.clientY || 100 });
    }

    async loadSettings() {
        this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
    }

    async saveSettings() {
        await this.saveData(this.settings);
    }
}

module.exports = AlwaysOnMemoryAgentPlugin;
