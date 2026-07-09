const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = 3000;
const DIRECTORY = __dirname;
const WORKSPACE_ROOT = path.dirname(path.dirname(DIRECTORY));

const MIME_TYPES = {
    '.html': 'text/html; charset=utf-8',
    '.css': 'text/css',
    '.js': 'application/javascript',
    '.json': 'application/json',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.gif': 'image/gif'
};

const server = http.createServer((req, res) => {
    // API 1: Inbox内の新規ファイルをリアルタイム実スキャンして返す
    if (req.url === '/api/inbox' && req.method === 'GET') {
        const inboxPath = path.join(WORKSPACE_ROOT, 'Inbox');
        const files = [];
        
        if (fs.existsSync(inboxPath)) {
            const list = fs.readdirSync(inboxPath);
            list.forEach(file => {
                const fullPath = path.join(inboxPath, file);
                if (file !== 'README.md' && fs.statSync(fullPath).isFile() && !file.startsWith('.')) {
                    files.push({ name: file });
                }
            });
        }
        
        res.writeHead(200, {
            'Content-Type': 'application/json; charset=utf-8',
            'Access-Control-Allow-Origin': '*'
        });
        res.end(JSON.stringify(files));
        return;
    }

    // API 2: Pending_Approval（要確認成果物）のファイルスキャン
    if (req.url === '/api/pending-approval' && req.method === 'GET') {
        const pendingPath = path.join(WORKSPACE_ROOT, 'Pending_Approval');
        const files = [];
        
        if (fs.existsSync(pendingPath)) {
            const list = fs.readdirSync(pendingPath);
            list.forEach(file => {
                const fullPath = path.join(pendingPath, file);
                if (file !== 'README.md' && !file.startsWith('.')) {
                    const stat = fs.statSync(fullPath);
                    if (stat.isFile()) {
                        files.push({ name: file, type: 'file' });
                    } else if (stat.isDirectory()) {
                        files.push({ name: file, type: 'directory' });
                    }
                }
            });
        }
        
        res.writeHead(200, {
            'Content-Type': 'application/json; charset=utf-8',
            'Access-Control-Allow-Origin': '*'
        });
        res.end(JSON.stringify(files));
        return;
    }

    // API 2.5: Outputs/proposals 内の提案一覧を取得
    if (req.url === '/api/proposals' && req.method === 'GET') {
        const proposalsPath = path.join(WORKSPACE_ROOT, 'Outputs', 'proposals');
        const files = [];
        
        if (fs.existsSync(proposalsPath)) {
            const list = fs.readdirSync(proposalsPath);
            list.sort().reverse(); // 最新順
            
            list.forEach(file => {
                const fullPath = path.join(proposalsPath, file);
                if (file !== 'README.md' && fs.statSync(fullPath).isFile() && !file.startsWith('.')) {
                    const stat = fs.statSync(fullPath);
                    files.push({ 
                        name: file, 
                        created: stat.mtime
                    });
                }
            });
        }
        
        res.writeHead(200, {
            'Content-Type': 'application/json; charset=utf-8',
            'Access-Control-Allow-Origin': '*'
        });
        res.end(JSON.stringify(files));
        return;
    }

    // API 2.6: 個別の提案書の内容を返す
    if (req.url.startsWith('/api/proposals/detail') && req.method === 'GET') {
        const urlObj = new URL(req.url, `http://${req.headers.host}`);
        const fileName = urlObj.searchParams.get('name');
        
        if (!fileName || fileName.includes('..') || path.isAbsolute(fileName)) {
            res.writeHead(400, { 'Content-Type': 'text/plain; charset=utf-8' });
            res.end('Bad Request');
            return;
        }
        
        const filePath = path.join(WORKSPACE_ROOT, 'Outputs', 'proposals', fileName);
        
        if (fs.existsSync(filePath) && fs.statSync(filePath).isFile()) {
            const content = fs.readFileSync(filePath, 'utf8');
            res.writeHead(200, {
                'Content-Type': 'text/markdown; charset=utf-8',
                'Access-Control-Allow-Origin': '*'
            });
            res.end(content);
        } else {
            res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
            res.end('Proposal not found');
        }
        return;
    }

    // API 3: クラウド監視ステータス (ロック、エラーカウンター、サーキットブレーカー)
    if (req.url === '/api/watcher-status' && req.method === 'GET') {
        const lockPath = path.join(WORKSPACE_ROOT, '.workflow_lock');
        const counterPath = path.join(WORKSPACE_ROOT, '04_運営総務', 'watcher_error_counter.json');
        
        let locked = fs.existsSync(lockPath);
        let consecutive_errors = 0;
        let circuit_broken = false;
        
        if (fs.existsSync(counterPath)) {
            try {
                const data = JSON.parse(fs.readFileSync(counterPath, 'utf8'));
                consecutive_errors = data.consecutive_errors || 0;
                circuit_broken = data.circuit_broken || false;
            } catch (e) {
                console.error("Error reading counter json: ", e);
            }
        }
        
        res.writeHead(200, {
            'Content-Type': 'application/json; charset=utf-8',
            'Access-Control-Allow-Origin': '*'
        });
        res.end(JSON.stringify({ locked, consecutive_errors, circuit_broken }));
        return;
    }

    // API 4: 監視ステータスの手動リセット (サーキットブレーカーの復旧)
    if (req.url === '/api/reset-watcher' && req.method === 'POST') {
        const lockPath = path.join(WORKSPACE_ROOT, '.workflow_lock');
        const counterPath = path.join(WORKSPACE_ROOT, '04_運営総務', 'watcher_error_counter.json');
        
        if (fs.existsSync(lockPath)) {
            fs.unlinkSync(lockPath);
        }
        
        const resetData = { consecutive_errors: 0, circuit_broken: false };
        fs.writeFileSync(counterPath, JSON.stringify(resetData, null, 2), 'utf8');
        
        res.writeHead(200, {
            'Content-Type': 'application/json; charset=utf-8',
            'Access-Control-Allow-Origin': '*'
        });
        res.end(JSON.stringify({ status: 'success', message: 'Watcher status reset successfully.' }));
        return;
    }

    // API 5: ワークフロー実行リクエスト (ローカル模擬実行用)
    if (req.url === '/api/run-workflow' && req.method === 'POST') {
        res.writeHead(200, {
            'Content-Type': 'application/json; charset=utf-8',
            'Access-Control-Allow-Origin': '*'
        });
        res.end(JSON.stringify({ status: 'success', message: 'Tandy.inc workflow triggered.' }));
        return;
    }

    // 静的ファイルの配信 (HTML/CSS/JS)
    let filePath = path.join(DIRECTORY, req.url === '/' ? 'index.html' : req.url);
    const extname = path.extname(filePath);
    const contentType = MIME_TYPES[extname] || 'application/octet-stream';

    fs.readFile(filePath, (error, content) => {
        if (error) {
            if (error.code === 'ENOENT') {
                res.writeHead(404, { 'Content-Type': 'text/html; charset=utf-8' });
                res.end('<h1>404 Not Found</h1>', 'utf-8');
            } else {
                res.writeHead(500);
                res.end(`Server Error: ${error.code}`);
            }
        } else {
            res.writeHead(200, { 'Content-Type': contentType });
            res.end(content, 'utf-8');
        }
    });
});

server.listen(PORT, () => {
    console.log(`==================================================`);
    console.log(` 🚀 Tandy.inc Control Dashboard (Node.js版サーバー)`);
    console.log(`    追加ライブラリ(Express)のインストール不要で即時起動します`);
    console.log(` 🔗 アドレス: http://localhost:${PORT}`);
    console.log(`==================================================`);
});
