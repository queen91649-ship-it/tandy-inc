# ⏱️ Tandy.inc Inbox監視フロー手順書 (inbox_watcher_flow.md)

このファイルは、毎日 AM 9:00 および PM 17:00 にクラウド（GitHub Actions）上で自動起動し、Google Drive の `Inbox/` フォルダを安全に巡回・自動処理するフローの実行手順です。

## 📁 関連ファイルパス
* **監視スクリプト**: `g:/マイドライブ/02_AI Campany/Tandy.inc/Outputs/dashboard/tandy_watcher.py`
* **GitHubワークフロー**: `g:/マイドライブ/02_AI Campany/Tandy.inc/.github/workflows/tandy_watcher.yml`
* **ロックファイル**: `g:/マイドライブ/02_AI Campany/Tandy.inc/.workflow_lock`
* **エラーカウンタ**: `g:/マイドライブ/02_AI Campany/Tandy.inc/04_運営総務/watcher_error_counter.json`

---

## 🔄 処理手順（クラウド動作仕様）

### 1. 安全チェック ＆ サーキットブレーカー判定
GitHub Actions から `tandy_watcher.py` が起動されると、まず以下のステータスを確認します。

1. **エラーカウンタの確認**:
   - `watcher_error_counter.json` を読み込みます。ファイルがない場合は自動作成され、`{"consecutive_errors": 0, "circuit_broken": false}` となります。
   - `circuit_broken` が `true` の場合、処理を実行せず、**「【サーキットブレーカー作動中】連続エラー数が上限に達したため、定期監視フローは一時停止しています」**とログを出力して終了します。
2. **多重起動の確認 (ロック制御)**:
   - `.workflow_lock` が存在するか確認します。
   - 存在する場合、既に別プロセスが処理を実行中のため、何もせず処理をスキップして終了します（多重起動防止）。

### 2. 処理対象ファイルの検出 (書き込み完了安定判定)
安全チェックを通過した場合、`Inbox/` をスキャンします。

1. **対象ファイルリストの取得**:
   - `Inbox/` 配下のファイル（`README.md` や隠しファイルを除く）をリストアップします。
2. **安定判定（書き込み中ファイルの除外）**:
   - ファイルの `modifiedTime`（更新日時）を確認し、**最終更新から30秒以上経過していないファイル**は、現在マイドライブ同期中または書き込み中である可能性が高いため、今回の処理対象から除外します。
3. **処理対象がない場合の終了**:
   - 対象ファイルが1つもない場合は、サイレントに処理を終了します。

### 3. ロックの獲得
処理対象ファイルが存在する場合、処理を開始する前にロックを獲得します。

1. `.workflow_lock` ファイルを作成し、内容に `Locked by Cloud Agent at [現在の時刻]` を書き込みます。

### 4. ワークフローの実行
`workflow_guide.md` に従い、ファイル名や内容からモードを自動判定し、Gemini API (2.5-pro / 2.5-flash) を用いて処理を順次実行します。

### 5. 成果物の保存と隔離
* **高リスク成果物の隔離**: 監査 (Auditor) で高リスク（ハルシネーションやセキュリティの懸念）と判定された成果物は、`Outputs/` ではなく `Pending_Approval/` に保存され、人間（CEO）の確認・承認待ちとします。

### 6. 処理結果に応じた後処理

#### A. 正常終了時 (Success)
1. **ロックの解除**: `.workflow_lock` ファイルを削除します。
2. **エラーカウンタのリセット**: `watcher_error_counter.json` の内容を `{"consecutive_errors": 0, "circuit_broken": false}` に更新します。
3. **元ファイルの退避**: 処理が完了した元のインプットファイルを `Archive/` に移動します。

#### B. 異常終了時 (Fail)
1. **ロックの解除**: `.workflow_lock` ファイルを削除します。
2. **エラーカウンタのインクリメント**:
   - `watcher_error_counter.json` の `consecutive_errors` を `+1` します。
   - `consecutive_errors` が `3` 以上になった場合、`circuit_broken` を `true` に設定してサーキットブレーカーを作動させます。

---

## 🛠️ 管理者による手動復旧手順

サーキットブレーカーが作動した場合、以下のファイルを Google Drive 上で直接、修正・削除して復旧を行ってください。

1. **ロックの解除**: `g:/マイドライブ/02_AI Campany/Tandy.inc/.workflow_lock` が残っている場合は削除します。
2. **カウンターのリセット**: `watcher_error_counter.json` の内容を `{"consecutive_errors": 0, "circuit_broken": false}` に書き換えて保存します。
