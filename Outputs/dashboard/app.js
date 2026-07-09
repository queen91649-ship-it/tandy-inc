// 各モードの日本語説明定義
const workflowDescriptions = {
    auto: "【自動判定モード (推奨)】<br>Inboxに置かれている新規ファイルをAIが自動で検知し、内容や拡張子から最も適切なモード（ブログ/開発/バグ修正/UI更新/市場調査）を自動で判断して実行します。ファイルを置いて実行するだけの簡単モードです。",
    blog: "【ブログ記事モード】<br>指定されたトピックから、リサーチ → 記事＆SNSドラフト生成 → Complianceによるハルシネーション（事実誤認）およびリンク生存監査を行い、完成版パッケージを出力します。",
    dev: "【開発コード生成モード】<br>設計要件から、必要な仕様調査 → 例外処理を徹底したソースコード自動生成 → UIUX_Designによる美観・レスポンシブ監査 → QA_Engineeringによるテストコード実行確認を行い、完成版を出力します。",
    bugfix: "【バグ修正モード】<br>Inboxに投入されたコードとエラーログを元に、原因調査 → 修正コード＆根本原因と対策の解説生成 → UIUXデザイン監査 → QAによる回帰テストを通過させて出力します。",
    research: "【市場調査モード】<br>調べたいテーマについてWebや事例を検索し、競合比較テーブルや導入ROI・コスト試算、リンク生存確認をすべてクリアした一次ソース付きの調査報告書を作成します。",
    ui_update: "【UIデザイン更新モード】<br>既存のダッシュボードやWebUIの改善指示から、画面レイアウト・CSS・JSの更新箇所を分析 → 制作・自動バックアップ作成 → UIUX_Design監査 → QA動作検証を行い、直接上書き更新します。",
    newsletter: "【朝のニュースレターモード】<br>毎日朝6:00に自動実行されるモードです。監視リスト（watchlist.txt）の情報源から最新情報を収集し、全トピックに個別ビジネス影響（Tandy's Insight）を付加して出力します。",
    design_audit: "【UIデザイン定期監査 (アイデアD)】<br>現在の自社UIダッシュボード（Outputs/dashboard/）のソースコードや美観を、最新のUIUXトレンドや事例と比較分析。フォント・色彩・レスポンシブ性・アクセシビリティの観点から改善点をまとめた「デザイン改善ロードマップ」を自動生成します。"
};

const workflowNames = {
    auto: "自動判定ワークフロー",
    blog: "ブログ記事モード",
    dev: "開発コード生成",
    bugfix: "バグ修正モード",
    research: "市場調査モード",
    ui_update: "UIデザイン更新",
    newsletter: "朝のニュースレター",
    design_audit: "UIデザイン定期監査 (アイデアD)"
};

// 状態管理
let selectedMode = 'auto';
let draggedProposalName = null;
let currentSelectedProposal = null;

// クロック表示
function updateClock() {
    const timeDisplay = document.getElementById('time-display');
    const now = new Date();
    timeDisplay.textContent = now.toTimeString().split(' ')[0];
}
setInterval(updateClock, 1000);
updateClock();

// タブ切り替え制御
function initTabs() {
    const navItems = document.querySelectorAll('.nav-menu .nav-item');
    const tabContents = document.querySelectorAll('.tab-content');
    
    navItems.forEach(item => {
        item.addEventListener('click', () => {
            const targetTab = item.getAttribute('data-tab');
            
            // 組織マニュアルなどの外部リンクタブはスキップ
            if (targetTab === 'docs') return;
            
            // 全ナビゲーションのactiveを解除
            navItems.forEach(nav => nav.classList.remove('active'));
            // クリックしたナビゲーションをactiveに
            item.classList.add('active');
            
            // 全コンテンツを非表示に
            tabContents.forEach(content => {
                content.style.display = 'none';
                content.classList.remove('active');
            });
            
            // 対象コンテンツを表示
            const activeTab = document.getElementById(`${targetTab}-tab`);
            if (activeTab) {
                activeTab.style.display = 'block';
                activeTab.classList.add('active');
            }
            
            // 提案タブが開かれた場合は、提案データを読み込み
            if (targetTab === 'proposals') {
                loadProposals();
            }
        });
    });
}

// Drag & Drop API 初期化
function initDragAndDrop() {
    const dropzone = document.getElementById('proposal-dropzone');
    if (!dropzone) return;
    
    dropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropzone.classList.add('dragover');
    });
    
    dropzone.addEventListener('dragleave', () => {
        dropzone.classList.remove('dragover');
    });
    
    dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.classList.remove('dragover');
        
        if (draggedProposalName) {
            openApproveModal(draggedProposalName);
        }
    });
    
    // ドロップゾーンをクリックしても採用フローに入れるようにする
    dropzone.addEventListener('click', () => {
        if (currentSelectedProposal) {
            openApproveModal(currentSelectedProposal);
        } else {
            alert("まず、左側のリストから採用したい提案を選択するか、直接ドラッグ＆ドロップしてください。");
        }
    });
}

// Inboxスキャン
async function scanInbox() {
    const listElement = document.getElementById('inbox-list');
    try {
        const response = await fetch('/api/inbox');
        const files = await response.json();
        
        listElement.innerHTML = '';
        if (files.length === 0) {
            listElement.innerHTML = '<li class="file-item loading">現在、Inboxには処理すべきファイルはありません。</li>';
            return;
        }
        
        files.forEach(file => {
            const li = document.createElement('li');
            li.className = 'file-item';
            
            let badgeBg = 'rgba(0, 240, 255, 0.15)';
            let badgeColor = '#00f0ff';
            let label = '新規検知';
            
            if (file.name.startsWith('【実行要求】')) {
                badgeBg = 'rgba(157, 0, 255, 0.15)';
                badgeColor = '#9d00ff';
                label = '実行要求';
            }
            
            li.innerHTML = `<span>📄 ${file.name}</span><span class="status-badge" style="background-color:${badgeBg};color:${badgeColor};">${label}</span>`;
            listElement.appendChild(li);
        });
    } catch (error) {
        listElement.innerHTML = '<li class="file-item loading">Inbox フォルダのスキャンに失敗しました。</li>';
    }
}

// Pending Approval スキャン
async function scanPendingApproval() {
    const listElement = document.getElementById('pending-list');
    try {
        const response = await fetch('/api/pending-approval');
        const files = await response.json();
        
        listElement.innerHTML = '';
        if (files.length === 0) {
            listElement.innerHTML = '<li class="file-item loading">現在、承認待ちの成果物はありません。</li>';
            return;
        }
        
        files.forEach(file => {
            const li = document.createElement('li');
            li.className = 'file-item';
            li.style.borderLeftColor = '#f59e0b';
            
            const icon = file.type === 'directory' ? '📁' : '📄';
            li.innerHTML = `<span>${icon} ${file.name}</span><span class="status-badge" style="background-color:rgba(245, 158, 11, 0.15);color:#f59e0b;">承認待ち</span>`;
            listElement.appendChild(li);
        });
    } catch (error) {
        listElement.innerHTML = '<li class="file-item loading">承認待ちフォルダのスキャンに失敗しました。</li>';
    }
}

// 提案書リストの取得
async function loadProposals() {
    const listElement = document.getElementById('proposal-list-items');
    try {
        const response = await fetch('/api/proposals');
        const proposals = await response.json();
        
        listElement.innerHTML = '';
        if (proposals.length === 0) {
            listElement.innerHTML = '<li class="file-item loading">現在、AIからの提案はありません。</li>';
            return;
        }
        
        proposals.forEach(p => {
            const li = document.createElement('li');
            li.className = 'file-item';
            li.style.borderLeftColor = '#9d00ff'; // パープル
            
            // ドラッグ可能属性とイベントの設定
            li.setAttribute('draggable', 'true');
            
            li.addEventListener('dragstart', () => {
                draggedProposalName = p.name;
                li.classList.add('dragging');
            });
            
            li.addEventListener('dragend', () => {
                draggedProposalName = null;
                li.classList.remove('dragging');
            });
            
            const date = new Date(p.created);
            const dateStr = `${date.getMonth()+1}/${date.getDate()} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
            
            li.innerHTML = `<span>💡 ${p.name}</span><span class="status-badge" style="background-color:rgba(157, 0, 255, 0.15);color:#9d00ff;">${dateStr}</span>`;
            
            li.onclick = () => {
                currentSelectedProposal = p.name;
                viewProposalDetail(p.name);
            };
            
            listElement.appendChild(li);
        });
    } catch (error) {
        listElement.innerHTML = '<li class="file-item loading">提案書のロードに失敗しました。</li>';
    }
}

// 個別提案書詳細の取得・描画
async function viewProposalDetail(name) {
    const titleElement = document.getElementById('proposal-detail-title');
    const contentElement = document.getElementById('proposal-detail-content');
    const actionArea = document.getElementById('proposal-action-area');
    
    titleElement.textContent = name;
    contentElement.innerHTML = '<p class="preview-placeholder">提案書を読み込んでいます...</p>';
    if (actionArea) actionArea.style.display = 'none';
    
    try {
        const response = await fetch(`/api/proposals/detail?name=${encodeURIComponent(name)}`);
        if (!response.ok) throw new Error("Failed to fetch detail");
        const markdown = await response.text();
        
        // 簡易Markdown HTMLコンバータ
        let html = markdown
            .replace(/^#\s+(.+)$/gm, '<h1 style="color:#00f0ff;font-family:\'Outfit\';font-size:22px;margin:24px 0 12px 0;">$1</h1>')
            .replace(/^##\s+(.+)$/gm, '<h2 style="color:#9d00ff;font-family:\'Outfit\';font-size:18px;margin:20px 0 8px 0;border-bottom:1px solid rgba(255,255,255,0.06);padding-bottom:6px;">$1</h2>')
            .replace(/^###\s+(.+)$/gm, '<h3 style="color:#f3f4f6;font-family:\'Outfit\';font-size:14px;margin:14px 0 6px 0;">$1</h3>')
            .replace(/^\*\s+(.+)$/gm, '<li style="margin-left:18px;margin-bottom:6px;list-style-type:square;color:#f3f4f6;font-size:13px;">$1</li>')
            .replace(/^- \s*(.+)$/gm, '<li style="margin-left:18px;margin-bottom:6px;list-style-type:square;color:#f3f4f6;font-size:13px;">$1</li>')
            .replace(/\*\*(.*?)\*\*/g, '<strong style="color:#00f0ff;">$1</strong>')
            .replace(/\n\n/g, '<br><br>')
            .replace(/\n/g, '<br>');
            
        contentElement.innerHTML = `<div style="font-family:'Inter';font-size:14px;line-height:1.6;color:#e5e7eb;padding:10px;">${html}</div>`;
        
        // 詳細ロードに成功したら、採用アクションエリアを表示する
        if (actionArea) {
            actionArea.style.display = 'block';
            const btn = document.getElementById('btn-adopt-proposal');
            if (btn) {
                btn.onclick = () => openApproveModal(name);
            }
        }
        
    } catch (error) {
        contentElement.innerHTML = '<p class="preview-placeholder" style="color:#ef4444;">詳細の取得に失敗しました。</p>';
    }
}

// 採用ボタン（詳細プレビュー上のボタン）のクリックハンドラ
function adoptSelectedProposal() {
    if (currentSelectedProposal) {
        openApproveModal(currentSelectedProposal);
    }
}

// 採用・承認モーダルを開く
function openApproveModal(name) {
    const modal = document.getElementById('approve-modal');
    const title = document.getElementById('approve-modal-title');
    const msg = document.getElementById('approve-modal-msg');
    const submitBtn = document.getElementById('approve-modal-submit-btn');
    const commentField = document.getElementById('approve-comment');
    
    if (!modal) return;
    
    // 初期化
    title.textContent = "提案を採用しますか？";
    msg.innerHTML = `選択された <strong>${name}</strong> を採用し、コメントを添えて Inbox フォルダ（採用棚）へ投入します。`;
    commentField.value = '';
    
    // 送信処理のバインド
    submitBtn.onclick = async () => {
        const comment = commentField.value;
        submitBtn.disabled = true;
        submitBtn.textContent = '送信中...';
        
        try {
            const response = await fetch('/api/proposals/approve', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ name, comment })
            });
            
            const result = await response.json();
            closeApproveModal();
            
            if (result.status === 'success') {
                // 成功アラートを表示
                showAdoptSuccessModal(result.targetFile);
            } else {
                alert("採用処理に失敗しました: " + result.message);
            }
        } catch (err) {
            alert("エラーが発生しました。");
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = '採用してInboxへ投入';
        }
    };
    
    modal.classList.add('active');
}

// 採用モーダルを閉じる
function closeApproveModal() {
    const modal = document.getElementById('approve-modal');
    if (modal) modal.classList.remove('active');
}

// 採用成功モーダルの表示（既存のconfirm-modalを再利用）
function showAdoptSuccessModal(targetFile) {
    const modal = document.getElementById('confirm-modal');
    const msg = document.getElementById('modal-msg');
    
    msg.innerHTML = `提案が正常に承認され、Inbox へ投入されました！<br><br>- 作成された指示書: <span style="color:#00f0ff; font-weight:600;">${targetFile}</span><br><br>毎日9:00および17:00の自動スキャン監視、または手動操作によって、AIエージェント達が自動で実行（開発・執筆）を開始します。`;
    
    modal.classList.add('active');
    
    // リストの更新
    scanInbox();
}

// クラウド定期監視ステータスの取得
async function updateWatcherStatus() {
    const lockBadge = document.getElementById('watcher-lock-status');
    const errorCountSpan = document.getElementById('watcher-error-count');
    const circuitBadge = document.getElementById('watcher-circuit-status');
    const resetBtn = document.getElementById('btn-reset-watcher');
    
    try {
        const response = await fetch('/api/watcher-status');
        const status = await response.json();
        
        // ロック状況
        if (status.locked) {
            lockBadge.textContent = 'ロック中 (実行中)';
            lockBadge.className = 'status-badge danger';
            lockBadge.style.backgroundColor = 'rgba(239, 68, 68, 0.15)';
            lockBadge.style.color = '#ef4444';
        } else {
            lockBadge.textContent = '未ロック (待機中)';
            lockBadge.className = 'status-badge normal';
            lockBadge.style.backgroundColor = 'rgba(16, 185, 129, 0.15)';
            lockBadge.style.color = '#10b981';
        }
        
        // エラー数
        errorCountSpan.textContent = `${status.consecutive_errors} / 3`;
        if (status.consecutive_errors > 0) {
            errorCountSpan.style.color = '#f59e0b';
        } else {
            errorCountSpan.style.color = '';
        }
        
        // サーキットブレーカー
        if (status.circuit_broken) {
            circuitBadge.textContent = '停止中 (要確認)';
            circuitBadge.className = 'status-badge danger';
            circuitBadge.style.backgroundColor = 'rgba(239, 68, 68, 0.15)';
            circuitBadge.style.color = '#ef4444';
            resetBtn.style.display = 'block';
        } else {
            circuitBadge.textContent = '正常稼働中';
            circuitBadge.className = 'status-badge normal';
            circuitBadge.style.backgroundColor = 'rgba(16, 185, 129, 0.15)';
            circuitBadge.style.color = '#10b981';
            resetBtn.style.display = 'none';
        }
        
    } catch (error) {
        console.error("Failed to fetch watcher status: ", error);
    }
}

// 監視ステータスの手動リセット
async function resetWatcherStatus() {
    if (!confirm("安全装置（サーキットブレーカー）を解除し、多重起動ロックを強制リセットしますか？")) {
        return;
    }
    
    try {
        const response = await fetch('/api/reset-watcher', { method: 'POST' });
        const result = await response.json();
        
        if (result.status === 'success') {
            alert("リセットに成功しました。監視を再開します。");
            updateWatcherStatus();
        } else {
            alert("リセットに失敗しました: " + result.message);
        }
    } catch (error) {
        alert("リセット処理でエラーが発生しました。");
    }
}

// 1. ボタンを押した時は「説明の切り替えと選択状態の保持」のみを行う
function selectWorkflowMode(mode) {
    selectedMode = mode;
    
    // 全ボタンのスタイルを一旦非選択にリセット
    const individualButtons = document.querySelectorAll('#mode-btn-container button');
    individualButtons.forEach(btn => {
        btn.className = 'btn btn-secondary';
    });

    const autoBtn = document.getElementById('btn-auto');
    if (autoBtn) {
        autoBtn.classList.remove('active');
    }

    // 選択されたボタンをアクティブ（ハイライト）にする
    if (mode === 'auto') {
        if (autoBtn) autoBtn.classList.add('active');
    } else {
        const activeBtn = document.getElementById(`btn-${mode}`);
        if (activeBtn) {
            activeBtn.className = 'btn btn-primary';
        }
    }

    // 説明文のアップデート
    const descBox = document.getElementById('workflow-desc');
    descBox.innerHTML = workflowDescriptions[mode] || "カスタム指示を実行します。";
    descBox.classList.add('active');
}

// 2. 下部の「実行する」を押した時に確認画面をポップアップ
function triggerConfirmModal() {
    const modal = document.getElementById('start-modal');
    const title = document.getElementById('start-modal-title');
    const msg = document.getElementById('start-modal-msg');
    const executeBtn = document.getElementById('start-modal-execute-btn');

    const modeName = workflowNames[selectedMode] || "カスタムモード";
    const inputVal = document.getElementById('workflow-input').value;

    title.textContent = `${modeName} を開始しますか？`;
    
    if (inputVal) {
        msg.innerHTML = `選択された <strong>${modeName}</strong> を、以下の追加指示を添えて開始します。<br><br><span style="color:#00f0ff; font-style:italic;">「${inputVal}」</span>`;
    } else {
        msg.innerHTML = `選択された <strong>${modeName}</strong> を開始してよろしいですか？<br>各部門（エージェント）が連携して自律処理を起動します。`;
    }
    
    // 実行ボタンに実際の処理をバインド
    executeBtn.onclick = () => {
        closeStartModal();
        runWorkflow(selectedMode);
    };

    modal.classList.add('active');
}

// 実行前モーダルを閉じる
function closeStartModal() {
    const modal = document.getElementById('start-modal');
    modal.classList.remove('active');
}

// 3. 実際のワークフロー実行処理（進行シミュレーション）
async function runWorkflow(mode) {
    resetProgress();
    setAgentStatus('agent-ops', 50, '判定・初期化中...', true);
    
    setTimeout(() => {
        setAgentStatus('agent-ops', 100, '処理プロセス開始', false);
        simulateWorkflowRun(mode);
    }, 1000);
}

// 進捗リセット
function resetProgress() {
    const bars = document.querySelectorAll('.progress-bar');
    const labels = document.querySelectorAll('.agent-label');
    const rows = document.querySelectorAll('.agent-row');
    
    bars.forEach(bar => bar.style.width = '0%');
    labels.forEach(label => label.textContent = '待機中');
    rows.forEach(row => row.classList.remove('active'));
}

// エージェント進捗セット
function setAgentStatus(elementId, percentage, label, isActive) {
    const row = document.getElementById(elementId);
    const bar = row.querySelector('.progress-bar');
    const labelSpan = row.querySelector('.agent-label');
    
    bar.style.width = `${percentage}%`;
    labelSpan.textContent = label;
    if (isActive) {
        row.classList.add('active');
    } else {
        row.classList.remove('active');
    }
}

// ワークフローのシミュレーション表示 (デモ用)
function simulateWorkflowRun(mode) {
    const previewArea = document.getElementById('preview-content');
    previewArea.innerHTML = '<p class="preview-placeholder">AIエージェントが連携して処理を実行中...</p>';
    
    let resolvedMode = mode;
    // 自動判定時のダミーシミュレーション用
    if (mode === 'auto') {
        resolvedMode = 'research'; // デモでは市場調査モードが自動で選ばれたことにする
    }

    // Research
    setTimeout(() => {
        if (mode === 'auto') {
            setAgentStatus('agent-ops', 100, '自動判定完了：市場調査モード', false);
        }
        setAgentStatus('agent-research', 80, '情報調査・競合比較分析中...', true);
    }, 1500);
    
    // Creative
    setTimeout(() => {
        setAgentStatus('agent-research', 100, '調査完了', false);
        setAgentStatus('agent-creative', 70, 'コンテンツ・ロードマップ執筆中...', true);
    }, 3500);
    
    // Design
    setTimeout(() => {
        setAgentStatus('agent-creative', 100, '執筆完了', false);
        setAgentStatus('agent-design', 90, 'レイアウト・色彩美的監査中...', true);
    }, 6000);
    
    // QA
    setTimeout(() => {
        setAgentStatus('agent-design', 100, 'デザイン監査合格', false);
        setAgentStatus('agent-qa', 90, '検証・ファクト二重検証中...', true);
    }, 8000);
    
    // Complete
    setTimeout(() => {
        setAgentStatus('agent-qa', 100, '検証・監査合格', false);
        
        let modeName = "自動判定モード";
        let folderName = "Outputs/";
        if (resolvedMode === 'blog') { modeName = "ブログ記事モード"; folderName += "blog_post_result.md"; }
        else if (resolvedMode === 'dev') { modeName = "開発コード生成モード"; folderName += "dashboard/"; }
        else if (resolvedMode === 'bugfix') { modeName = "バグ修正モード"; folderName += "bugfixes/"; }
        else if (resolvedMode === 'research') { modeName = "市場調査モード"; folderName += "research/"; }
        else if (resolvedMode === 'ui_update') { modeName = "UIデザイン更新モード"; folderName += "dashboard/"; }
        else if (resolvedMode === 'newsletter') { modeName = "ニュースレターモード"; folderName += "newsletters/"; }
        else if (resolvedMode === 'design_audit') { modeName = "UIデザイン定期監査モード"; folderName += "design_audit_roadmap.md"; }

        // プレビュー表示
        previewArea.innerHTML = `
            <div style="font-family: 'Inter'; font-size:14px; line-height:1.6;">
                <h3 style="color:#00f0ff;font-family:'Outfit';margin-bottom:12px;display:flex;align-items:center;gap:8px;">
                    🎉 成果物の生成に成功しました
                </h3>
                <p style="margin-bottom:14px;color:#9ca3af;font-size:12px;">実行されたモード: ${modeName}</p>
                <div style="background-color:rgba(255,255,255,0.03);padding:16px;border-radius:10px;border:1px solid rgba(255,255,255,0.06);margin-bottom:12px;">
                    <h4 style="color:#9d00ff;font-size:13px;margin-bottom:8px;font-family:'Outfit';">【保存された成果物】</h4>
                    <p style="font-size:12px;color:#f3f4f6;">
                        - 保存先: <span style="color:#00f0ff;">${folderName}</span><br>
                        - AIが自律的に要求を満たし、品質チェックと監査を通して成果物を書き出しました。<br>
                        - 処理が終了し、安全ロックは正常に解除されました。
                    </p>
                </div>
            </div>
        `;
        
        // 完了モーダル表示
        showConfirmModal(`${modeName}`);
        
        // リストの即時更新
        scanInbox();
        scanPendingApproval();
        updateWatcherStatus();
    }, 10000);
}

// 完了モーダル表示
function showConfirmModal(modeName) {
    const modal = document.getElementById('confirm-modal');
    const msg = document.getElementById('modal-msg');
    msg.innerHTML = `<strong>【${modeName}】</strong> の自動処理がすべて完了しました。<br>各監査・品質テストをすべて通過し、完成版アセットが保存されました。`;
    modal.classList.add('active');
}

// 完了モーダル閉じる
function closeModal() {
    const modal = document.getElementById('confirm-modal');
    modal.classList.remove('active');
}

// 起動時処理
window.onload = () => {
    updateClock();
    initTabs(); // タブ初期化
    initDragAndDrop(); // Drag & Drop 初期化
    
    // 初回読み込み
    scanInbox();
    scanPendingApproval();
    updateWatcherStatus();
    
    // 定期フェッチの開始 (5秒ごと)
    setInterval(() => {
        scanInbox();
        scanPendingApproval();
        updateWatcherStatus();
    }, 5000);
    
    // デフォルトで「自動判定モード」を選択状態にし、ハイライトする
    selectWorkflowMode('auto');
};
