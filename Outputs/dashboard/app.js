// 各モードの日本語説明定義
const workflowDescriptions = {
    auto: "【自動判定モード (推奨)】<br>Inboxに置かれている新規ファイルをAIが自動で検知し、内容や拡張子から最も適切なモード（ブログ/開発/バグ修正/UI更新/市場調査）を自動で判断して実行します。ファイルを置いて実行するだけの簡単モードです。",
    blog: "【ブログ記事モード】<br>指定されたトピックから、リサーチ → 記事＆SNSドラフト生成 → Complianceによるハルシネーション（事実誤認）およびリンク生存監査を行い、完成版パッケージを出力します。",
    dev: "【開発コード生成モード】<br>設計要件から、必要な仕様調査 → 例外処理を徹底したソースコード自動生成 → UIUX_Designによる美観・レスポンシブ監査 → QA_Engineeringによるテストコード実行確認を行い、完成版を出力します。",
    bugfix: "【バグ修正モード】<br>Inboxに投入されたコードとエラーログを元に、原因調査 → 修正コード＆根本原因と対策の解説生成 → UIUXデザイン監査 → QAによる回帰テストを通過させて出力します。",
    research: "【市場調査モード】<br>調べたいテーマについてWebや事例を検索し、競合比較テーブルや導入ROI・コスト試算、リンク生存確認をすべてクリアした一次ソース付きの調査報告書を作成します。",
    ui_update: "【UIデザイン更新モード】<br>既存 of ダッシュボードやWebUIの改善指示から、画面レイアウト・CSS・JSの更新箇所を分析 → 制作・自動バックアップ作成 → UIUX_Design監査 → QA動作検証を行い、直接上書き更新します。",
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
let currentSelectedPending = null;

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
            
            // タブ遷移に応じた初回読み込み処理
            if (targetTab === 'ceo-office') {
                scanInbox();
                scanPendingApproval();
            } else if (targetTab === 'proposals') {
                loadProposals();
            } else if (targetTab === 'scheduler') {
                loadSchedules();
                updateWatcherStatus();
            } else if (targetTab === 'workflows') {
                scanInbox();
            } else if (targetTab === 'evolution') {
                resetProgress();
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
            openActionModal(draggedProposalName, 'adopt');
        }
    });
    
    // ドロップゾーンをクリックしても採用フローに入れるようにする
    dropzone.addEventListener('click', () => {
        if (currentSelectedProposal) {
            openActionModal(currentSelectedProposal, 'adopt');
        } else {
            alert("まず、左側のリストから採用したい提案を選択するか、直接ドラッグ＆ドロップしてください。");
        }
    });
}

// Inboxスキャン (インプット監視モニター)
async function scanInbox() {
    const listElement = document.getElementById('inbox-list');
    if (!listElement) return;
    
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
            } else if (file.name.startsWith('【再考依頼】')) {
                badgeBg = 'rgba(245, 158, 11, 0.15)';
                badgeColor = '#f59e0b';
                label = '再考依頼';
            } else if (file.name.startsWith('CEO指示_') || file.name.endsWith('.txt')) {
                badgeBg = 'rgba(0, 240, 255, 0.15)';
                badgeColor = '#00f0ff';
                label = 'CEO指示';
            }
            
            li.innerHTML = `<span>${file.name}</span><span class="status-badge" style="background-color:${badgeBg};color:${badgeColor};">${label}</span>`;
            listElement.appendChild(li);
        });
    } catch (error) {
        listElement.innerHTML = '<li class="file-item loading">Inbox フォルダのスキャンに失敗しました。</li>';
    }
}

// Pending Approval スキャン (承認待ちリスト)
async function scanPendingApproval() {
    const listElement = document.getElementById('pending-list');
    if (!listElement) return;
    
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
            li.style.cursor = 'pointer';
            
            const icon = file.type === 'directory' ? '[フォルダ]' : '[ファイル]';
            li.innerHTML = `<span>${icon} ${file.name}</span><span class="status-badge" style="background-color:rgba(245, 158, 11, 0.15);color:#f59e0b;">承認待ち</span>`;
            
            // クリック時に監査プレビューを開く
            li.onclick = () => {
                currentSelectedPending = file.name;
                viewPendingDetail(file.name);
            };
            
            listElement.appendChild(li);
        });
    } catch (error) {
        listElement.innerHTML = '<li class="file-item loading">承認待ちフォルダのスキャンに失敗しました。</li>';
    }
}

// 承認待ち成果物の監査プレビュー取得・描画
async function viewPendingDetail(name) {
    const titleElement = document.getElementById('pending-detail-title');
    const contentElement = document.getElementById('pending-detail-content');
    const actionArea = document.getElementById('pending-action-area');
    
    titleElement.textContent = `成果物監査: ${name}`;
    contentElement.innerHTML = '<p class="preview-placeholder">成果物のテキストデータを読み込んでいます...</p>';
    if (actionArea) actionArea.style.display = 'none';
    
    try {
        const response = await fetch(`/api/pending/detail?name=${encodeURIComponent(name)}`);
        if (!response.ok) throw new Error("Failed to fetch detail");
        const text = await response.text();
        
        // 簡易Markdown HTMLコンバータ
        let html = text
            .replace(/^#\s+(.+)$/gm, '<h1 style="color:#00f0ff;font-family:\'Outfit\';font-size:22px;margin:24px 0 12px 0;">$1</h1>')
            .replace(/^##\s+(.+)$/gm, '<h2 style="color:#9d00ff;font-family:\'Outfit\';font-size:18px;margin:20px 0 8px 0;border-bottom:1px solid rgba(255,255,255,0.06);padding-bottom:6px;">$1</h2>')
            .replace(/^###\s+(.+)$/gm, '<h3 style="color:#f3f4f6;font-family:\'Outfit\';font-size:14px;margin:14px 0 6px 0;">$1</h3>')
            .replace(/^\*\s+(.+)$/gm, '<li style="margin-left:18px;margin-bottom:6px;list-style-type:square;color:#f3f4f6;font-size:13px;">$1</li>')
            .replace(/^- \s*(.+)$/gm, '<li style="margin-left:18px;margin-bottom:6px;list-style-type:square;color:#f3f4f6;font-size:13px;">$1</li>')
            .replace(/\*\*(.*?)\*\*/g, '<strong style="color:#00f0ff;">$1</strong>')
            .replace(/\n\n/g, '<br><br>')
            .replace(/\n/g, '<br>');
            
        contentElement.innerHTML = `<div style="font-family:'Inter';font-size:14px;line-height:1.6;color:#e5e7eb;padding:10px;">${html}</div>`;
        
        // アクションエリアを表示し、承認・却下ボタンにハンドリングをバインド
        if (actionArea) {
            actionArea.style.display = 'block';
            
            document.getElementById('btn-approve-pending').onclick = () => executePendingAction(name, 'approve');
            document.getElementById('btn-reject-pending').onclick = () => executePendingAction(name, 'reject');
        }
        
    } catch (error) {
        contentElement.innerHTML = '<p class="preview-placeholder" style="color:#ef4444;">詳細テキストの取得に失敗しました。バイナリまたはフォルダ構造のみの可能性があります。</p>';
    }
}

// 成果物承認・却下アクション実行
async function executePendingAction(name, action) {
    const actionLabel = action === 'approve' ? '承認' : '却下';
    const confirmMsg = action === 'approve'
        ? `この成果物「${name}」を承認し、本番リリース（Outputs/archive/ へ移動）してよろしいですか？`
        : `この成果物「${name}」を却下（アーカイブ退避）し、修正・再起案を要求しますか？`;
        
    if (!confirm(confirmMsg)) return;
    
    try {
        const response = await fetch('/api/pending/action', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, action })
        });
        
        const result = await response.json();
        
        if (result.status === 'success') {
            // 成功メッセージモーダルの起動
            const modal = document.getElementById('confirm-modal');
            const msg = document.getElementById('modal-msg');
            const modalTitle = modal.querySelector('.modal-title');
            
            modalTitle.textContent = "成果物監査完了";
            if (action === 'approve') {
                msg.innerHTML = `成果物「<strong>${name}</strong>」を承認しました！<br><br>- 移動先: <span style="color:#10b981; font-weight:600;">Outputs/archive/${name}</span><br><br>リリース処理が完了し、成果物は安全に保管されました。`;
            } else {
                msg.innerHTML = `成果物「<strong>${name}</strong>」を却下しました。<br><br>- 移動先: <span style="color:#ef4444; font-weight:600;">Outputs/archive/rejected_assets/${name}</span><br><br>修正が必要な場合は、新規指示として再投函を行ってください。`;
            }
            
            modal.classList.add('active');
            
            // 画面表示のリセット
            document.getElementById('pending-detail-title').textContent = '🔍 成果物の監査プレビュー';
            document.getElementById('pending-detail-content').innerHTML = '<p class="preview-placeholder">左側の「承認待ちの成果物」リストから監査したいファイルを選択してください。</p>';
            document.getElementById('pending-action-area').style.display = 'none';
            currentSelectedPending = null;
            
            // リスト更新
            scanPendingApproval();
        } else {
            alert(`${actionLabel}処理に失敗しました: ` + result.message);
        }
    } catch (err) {
        alert("通信エラーが発生しました。");
    }
}

// スケジュール設定情報の取得 ＆ テーブル描画
async function loadSchedules() {
    const listElement = document.getElementById('schedule-table-body');
    if (!listElement) return;

    try {
        const response = await fetch('/api/schedules');
        const schedules = await response.json();

        listElement.innerHTML = '';
        if (schedules.length === 0) {
            listElement.innerHTML = '<tr><td colspan="4" style="padding: 20px; text-align: center; color: var(--text-muted);">定期スケジュールタスクは見つかりませんでした。</td></tr>';
            return;
        }

        schedules.forEach(s => {
            const tr = document.createElement('tr');
            
            // 部門に応じたバッジ色の設定
            let deptBadgeClass = 'status-badge';
            if (s.department === '運営・総務部門') {
                deptBadgeClass += ' dept-creative';
            } else if (s.department === '経営・統括部門 (審査会)') {
                deptBadgeClass += ' dept-ceo';
            } else if (s.department === '出版事業部') {
                deptBadgeClass += ' dept-auditor';
            }

            tr.innerHTML = `
                <td style="padding: 14px 10px; font-weight: 600; color: #f3f4f6;">${s.name}</td>
                <td style="padding: 14px 10px;">
                    <span class="status-badge" style="background-color: rgba(157, 0, 255, 0.12); color: #9d00ff; font-weight: 600;">${s.scheduleJST}</span>
                    <span class="status-badge sched-cron" style="margin-left: 8px;">${s.cron}</span>
                </td>
                <td style="padding: 14px 10px; font-family: monospace; color: #00f0ff;">${s.script}</td>
                <td style="padding: 14px 10px;"><span class="${deptBadgeClass}">${s.department}</span></td>
            `;
            listElement.appendChild(tr);
        });

    } catch (error) {
        listElement.innerHTML = '<tr><td colspan="4" style="padding: 20px; text-align: center; color: #ef4444;">スケジュールの取得に失敗しました。</td></tr>';
    }
}

// 提案書リストの取得 (部門別のカラーバッジ表示)
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
            
            let badgeClass = 'status-badge';
            let labelStr = p.department;
            
            if (p.status === 'pending') {
                badgeClass += ' hold';
                labelStr = '保留: ' + p.department;
                li.style.borderLeftColor = '#f59e0b'; // オレンジ
            } else {
                // 部門に応じたカラーリング設定
                if (p.department === '経営統括部門') {
                    badgeClass += ' dept-ceo';
                    li.style.borderLeftColor = '#00f0ff';
                } else if (p.department === 'リサーチ部門') {
                    badgeClass += ' dept-research';
                    li.style.borderLeftColor = '#9d00ff';
                } else if (p.department === '制作・開発部門') {
                    badgeClass += ' dept-creative';
                    li.style.borderLeftColor = '#3b82f6';
                } else if (p.department === 'デザイン監査部門') {
                    badgeClass += ' dept-design';
                    li.style.borderLeftColor = '#ff007a';
                } else if (p.department === '品質保証部門') {
                    badgeClass += ' dept-qa';
                    li.style.borderLeftColor = '#10b981';
                } else if (p.department === '法務・広報監査') {
                    badgeClass += ' dept-auditor';
                    li.style.borderLeftColor = '#eab308';
                } else {
                    badgeClass += ' new';
                    li.style.borderLeftColor = '#9d00ff';
                }
            }
            
            li.innerHTML = `<span>${p.name}</span><span class="${badgeClass}">${labelStr}</span>`;
            
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
        
        // 詳細ロードに成功したら、採用アクションエリア（4つのボタン）を表示・バインド
        if (actionArea) {
            actionArea.style.display = 'block';
            
            document.getElementById('btn-adopt-proposal').onclick = () => openActionModal(name, 'adopt');
            document.getElementById('btn-rethink-proposal').onclick = () => openActionModal(name, 'rethink');
            document.getElementById('btn-hold-proposal').onclick = () => executeImmediateAction(name, 'hold');
            document.getElementById('btn-reject-proposal').onclick = () => executeImmediateAction(name, 'reject');
        }
        
    } catch (error) {
        contentElement.innerHTML = '<p class="preview-placeholder" style="color:#ef4444;">詳細の取得に失敗しました。</p>';
    }
}

// 採用ボタン（詳細プレビュー上のボタン）のクリックハンドラ
function adoptSelectedProposal() {
    if (currentSelectedProposal) {
        openActionModal(currentSelectedProposal, 'adopt');
    }
}

// 採用 / 再考依頼モーダル（コメント入力あり）の起動制御
function openActionModal(name, action) {
    const modal = document.getElementById('approve-modal');
    const title = document.getElementById('approve-modal-title');
    const msg = document.getElementById('approve-modal-msg');
    const submitBtn = document.getElementById('approve-modal-submit-btn');
    const commentField = document.getElementById('approve-comment');
    
    if (!modal) return;
    
    // アクションに応じたテキスト切替
    if (action === 'adopt') {
        title.textContent = "提案を採用しますか？";
        msg.innerHTML = `選択された <strong>${name}</strong> を採用し、追加指示を添えて Inbox （採用棚）へ投入します。`;
        commentField.placeholder = "例:『このデザインをベースに、フォントをInterに変更して進めてください』『提案A of コスト最適化から実装を開始してください』";
        submitBtn.textContent = "採用してInboxへ投入";
        submitBtn.style.background = "linear-gradient(135deg, #00f0ff 0%, #9d00ff 100%)";
        submitBtn.style.color = "#ffffff";
    } else if (action === 'rethink') {
        title.textContent = "提案の再考を依頼しますか？";
        msg.innerHTML = `選択された <strong>${name}</strong> を再検討するため、CEOフィードバックを添えて Inbox （再考棚）へ差し戻します。`;
        commentField.placeholder = "例:『コスト試算について、より低価格なAPI（Gemini 2.5 Flash）をベースに再見積もりを行ってください』";
        submitBtn.textContent = "再考を依頼する";
        submitBtn.style.background = "#f59e0b";
        submitBtn.style.color = "#0a0f1d";
    }
    
    commentField.value = '';
    
    // 送信ボタンのハンドリング
    submitBtn.onclick = async () => {
        const comment = commentField.value;
        submitBtn.disabled = true;
        
        try {
            const response = await fetch('/api/proposals/action', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, action, comment })
            });
            const result = await response.json();
            closeApproveModal();
            
            if (result.status === 'success') {
                showActionResultModal(action, result.targetFile);
            } else {
                alert("処理に失敗しました: " + result.message);
            }
        } catch (err) {
            alert("エラーが発生しました。");
        } finally {
            submitBtn.disabled = false;
        }
    };
    
    modal.classList.add('active');
}

// モーダルクローズ
function closeApproveModal() {
    const modal = document.getElementById('approve-modal');
    if (modal) modal.classList.remove('active');
}

// コメント不要アクション（保留・却下）の即時実行
async function executeImmediateAction(name, action) {
    let actionLabel = action === 'hold' ? '保留' : '却下';
    let confirmMsg = action === 'hold' 
        ? `この提案「${name}」を一時保留にしますか？（保留フォルダへ移動し、リストにオレンジ色のバッジで維持されます）`
        : `この提案「${name}」を却下しますか？（不採用フォルダへ移動し、リストから非表示になります）`;
        
    if (!confirm(confirmMsg)) return;
    
    try {
        const response = await fetch('/api/proposals/action', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, action })
        });
        const result = await response.json();
        
        if (result.status === 'success') {
            showActionResultModal(action);
        } else {
            alert(`${actionLabel}処理に失敗しました: ` + result.message);
        }
    } catch (err) {
        alert("通信エラーが発生しました。");
    }
}

// 決定処理完了時の成功ダイアログ表示
function showActionResultModal(action, targetFile) {
    const modal = document.getElementById('confirm-modal');
    const msg = document.getElementById('modal-msg');
    const title = modal.querySelector('.modal-title');
    
    title.textContent = "意思決定を処理しました";
    
    if (action === 'adopt') {
        msg.innerHTML = `提案が正常に承認され、採用されました！<br><br>- 作成された指示書: <span style="color:#00f0ff; font-weight:600;">${targetFile}</span><br><br>定期監視フローまたは手動指示により、AIエージェント達が自動で実行プロセス（開発・執筆）を開始します。`;
    } else if (action === 'rethink') {
        msg.innerHTML = `再考依頼が送信され、Inbox へ投函されました。<br><br>- 再考要求書: <span style="color:#f59e0b; font-weight:600;">${targetFile}</span><br><br>次回定期監視スキャン時に、AIがCEOの指示を取り入れた「修正提案書(v2)」を自動で再生成してデリバリーします。`;
    } else if (action === 'hold') {
        msg.innerHTML = `提案を保留にしました。<br><br>リスト上には「保留中」としてオレンジ色のバッジで維持され、いつでも後から採用・却下を再判断できます。`;
    } else if (action === 'reject') {
        msg.innerHTML = `提案を不採用（却下）にしました。<br><br>この提案書は非表示フォルダへ移動し、一覧リストから除外されました。`;
    }
    
    modal.classList.add('active');
    
    // 一覧・Inboxリロード
    scanInbox();
    loadProposals();
    
    // 詳細エリアのリセット
    document.getElementById('proposal-detail-title').textContent = '提案書のプレビュー';
    document.getElementById('proposal-detail-content').innerHTML = '<p class="preview-placeholder">左側の提案一覧から確認したい提案を選択してください。</p>';
    document.getElementById('proposal-action-area').style.display = 'none';
    currentSelectedProposal = null;
}

// CEOからの新規指示の直接投函（Inbox保存）処理
async function submitNewInstructionToInbox() {
    const titleField = document.getElementById('new-instruction-title');
    const bodyField = document.getElementById('new-instruction-body');
    
    const title = titleField.value.trim();
    const body = bodyField.value.trim();
    
    if (body === '') {
        alert("指示内容（本文）を入力してください。");
        return;
    }
    
    try {
        const response = await fetch('/api/inbox/create', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ title, body })
        });
        
        const result = await response.json();
        
        if (result.status === 'success') {
            // フォームをクリア
            titleField.value = '';
            bodyField.value = '';
            
            // 成功モーダルの表示
            const modal = document.getElementById('confirm-modal');
            const msg = document.getElementById('modal-msg');
            const modalTitle = modal.querySelector('.modal-title');
            
            modalTitle.textContent = "インボックスに投函完了";
            msg.innerHTML = `CEOからの新規指示が正常に投函されました！<br><br>- 作成されたファイル: <span style="color:#00f0ff; font-weight:600;">${result.filename}</span><br><br>毎日9:00および17:00の定期監視スキャンで自動検出され、適切なエージェント部門が実行に入ります。`;
            
            modal.classList.add('active');
            
            // リストの即時スキャン
            scanInbox();
        } else {
            alert("投函に失敗しました: " + result.message);
        }
    } catch (error) {
        alert("投函処理中にエラーが発生しました。");
    }
}

// 自己進化メタ開発の実行リクエスト (多重監査のシミュレータ可視化対応)
async function triggerMetaWorkflowCreation() {
    const requirementField = document.getElementById('meta-workflow-requirement');
    const requirement = requirementField.value.trim();
    
    if (requirement === '') {
        alert("どのようなワークフローを作成したいか（要件）を入力してください。");
        return;
    }
    
    if (!confirm("AIエージェント達（Creative, Design, QA, Auditor）による自動開発・多重監査・Git自動デプロイプロセスを開始してよろしいですか？\n(これには1〜2分程度かかります)")) {
        return;
    }
    
    // 進捗バーのリセットと開始シミュレーション
    resetProgress();
    setAgentStatus('agent-ops-evo', 30, '自己進化プロセス初期化中...', true);
    
    // 擬似的にエージェント間監査連携進捗を描画 (1分強のタイムライン)
    setTimeout(() => {
        setAgentStatus('agent-ops-evo', 100, '起案準備完了', false);
        setAgentStatus('agent-creative-evo', 40, 'コード・YAML起案(ドラフト生成)中...', true);
    }, 3000);
    
    setTimeout(() => {
        setAgentStatus('agent-creative-evo', 100, '起案完了', false);
        setAgentStatus('agent-design-evo', 50, 'UIレイアウト・配色調和監査中...', true);
    }, 15000);
    
    setTimeout(() => {
        setAgentStatus('agent-design-evo', 100, 'デザイン監査合格', false);
        setAgentStatus('agent-qa-evo', 60, 'Pythonコード構文・エラートラップ検証中...', true);
    }, 28000);
    
    setTimeout(() => {
        setAgentStatus('agent-qa-evo', 100, 'QA監査合格', false);
        setAgentStatus('agent-auditor-evo', 70, 'セキュリティ・環境変数監査中...', true);
    }, 42000);
    
    setTimeout(() => {
        setAgentStatus('agent-auditor-evo', 100, '全監査合格・デプロイ準備中', false);
        setAgentStatus('agent-ops-evo', 90, 'Gitコミット・デプロイ(Push)実行中...', true);
    }, 55000);

    const previewArea = document.getElementById('preview-content-evo');
    previewArea.innerHTML = '<p class="preview-placeholder">AIエージェント達が新ワークフローの自動開発・多重監査・デプロイを実行中です。これには約1〜2分かかります。進行状況は上の稼働状況バーをご確認ください...</p>';
    
    requirementField.value = '';
    
    try {
        const response = await fetch('/api/workflow/create', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ requirement })
        });
        
        const result = await response.json();
        
        // 進捗バーを100%に強制完了
        setAgentStatus('agent-ops-evo', 100, '開発・デプロイ完了', false);
        
        if (result.status === 'success') {
            // 成功ポップアップ
            const modal = document.getElementById('confirm-modal');
            const msg = document.getElementById('modal-msg');
            const modalTitle = modal.querySelector('.modal-title');
            
            modalTitle.textContent = "自己進化デプロイ成功！";
            msg.innerHTML = `新ワークフローが正常に自動開発され、多重監査を通過してデプロイされました！<br><br>ダッシュボード（ index.html / app.js ）およびマニュアル（ ORGANIZATION.md ）への登録も完了しています。<br><br>ブラウザを再読み込み（F5）すると、システム統括タブに新しい実行ボタンが追加されます。`;
            
            modal.classList.add('active');
            
            previewArea.innerHTML = `
                <div style="font-family: 'Inter'; font-size:13px; line-height:1.5;">
                    <h3 style="color:#00f0ff;font-family:'Outfit';font-size:15px;">🛠️ 自動開発・多重監査完了ログ</h3>
                    <pre style="background: rgba(0,0,0,0.3); padding:10px; border-radius:8px; max-height:200px; overflow-y:auto; font-family:monospace; font-size:11px; margin-top:8px; border:1px solid var(--card-border); color:#10b981;">${result.log}</pre>
                </div>
            `;
        } else {
            alert("自動開発に失敗しました: " + result.message + "\n詳細: " + (result.detail || ""));
            previewArea.innerHTML = '<p class="preview-placeholder" style="color:#ef4444;">開発プロセスでエラーが発生しました。</p>';
            resetProgress();
        }
    } catch (error) {
        alert("通信エラーが発生しました。");
        previewArea.innerHTML = '<p class="preview-placeholder" style="color:#ef4444;">通信エラーによりプロセスが中断されました。</p>';
        resetProgress();
    }
}

// クラウド定期監視ステータスの取得
async function updateWatcherStatus() {
    const lockBadge = document.getElementById('watcher-lock-status');
    const errorCountSpan = document.getElementById('watcher-error-count');
    const circuitBadge = document.getElementById('watcher-circuit-status');
    const resetBtn = document.getElementById('btn-reset-watcher');
    
    if (!lockBadge) return;
    
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
    if (!row) return;
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
    if (!previewArea) return;
    
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
                    成果物の生成に成功しました
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
        
        // リストの即時更新
        scanInbox();
        scanPendingApproval();
    }, 10000);
}

// 完了モーダル表示
function showConfirmModal(modeName) {
    const modal = document.getElementById('confirm-modal');
    modal.classList.remove('active');
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
    
    // 初回読み込み (CEO室がデフォルトアクティブなのでCEO室用データ取得)
    scanInbox();
    scanPendingApproval();
    
    // 定期フェッチの開始 (5秒ごと)
    setInterval(() => {
        const activeTab = document.querySelector('.nav-item.active');
        if (activeTab) {
            const tabName = activeTab.getAttribute('data-tab');
            if (tabName === 'ceo-office') {
                scanInbox();
                scanPendingApproval();
            } else if (tabName === 'scheduler') {
                updateWatcherStatus();
            } else if (tabName === 'workflows') {
                scanInbox();
            }
        }
    }, 5000);
    
    // デフォルト選択状態の設定 (自動ワークフロー実行用)
    selectWorkflowMode('auto');
};
