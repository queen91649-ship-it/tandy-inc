# Tandy.inc インフラ構成 ＆ 復旧マニュアル (INFRASTRUCTURE.md)

このマニュアルは、Tandy.inc の 24時間完全自動朝刊発行システム（GitHub Actions ➔ GCP ➔ Googleドライブ ➔ Gemini API）の接続設定、認証合鍵（Workload Identity 連携）、およびシステム再起動時の「復旧手順」を記録した標準手順書です。

今後、パソコンの買い替えやシステムトラブルが発生した際は、**このファイルをAIに読ませることで、すべてのインフラ情報をAIが自動理解し、復旧作業を先導します。**

---

## 1. 全体インフラ構成（Workload Identity 連携）

Tandy.inc は、漏洩リスクのある「秘密鍵JSONファイル」を一切使用せず、GitHub ActionsのOIDCトークンを用いて一時的な合鍵を動的に取得するセキュアな仕組みを採用しています。

*   **実行環境**: GitHub Actions (無料枠)
*   **認証方式**: Workload Identity 連携 (OIDC)
*   **保管庫（リポジトリ）**: `queen91649-ship-it/tandy-inc`

---

## 2. 登録されている認証情報・環境変数

### ① GitHub Variables (公開されてもよい環境変数)
GitHubリポジトリの `Settings -> Secrets and variables -> Actions` の「Variables」タブに以下の3つが登録されています。

*   **`GCP_SERVICE_ACCOUNT`**
    *   **値**: `tandy-inc@tandy-inc.iam.gserviceaccount.com`
    *   **役割**: GCPのサービスアカウント名。このアカウントに対してGoogleドライブの編集権限を付与しています。
*   **`GCP_WORKLOAD_IDENTITY_PROVIDER`**
    *   **値**: `projects/606204392426/locations/global/workloadIdentityPools/tandy-pool/providers/github-provider`
    *   **役割**: GCPで作成したプロバイダのフルリソースID。GitHubがログインする際の窓口となります。
*   **`GOOGLE_DRIVE_ROOT_FOLDER_ID`**
    *   **値**: `1YM7t5t-1XOo2Pi_wX7JUEaROxjJ6wl6M`
    *   **役割**: Googleドライブ上の「02_AI Company / Tandy.inc」のルートフォルダID。

### ② GitHub Secrets (暗号化された秘密鍵)
GitHubリポジトリの「Secrets」タブに登録されています。

*   **`GEMINI_API_KEY`**
    *   **値**: *(CEO所有の Gemini API キー)*

---

## 3. トラブル時の復旧・再起動手順

### Q. 朝刊が自動で届かなくなった場合（サーバー再起動などで停止した場合）
1.  **GitHub Actions のログを確認する**:
    GitHubリポジトリの `Actions` タブを開き、動いているタスクのログで「どこでエラーが出ているか」を確認します。
2.  **エラーログ（Googleドライブ側）を確認する**:
    もしプログラムの実行中にエラーが発生した場合は、Googleドライブの **`Outputs/errors/`** フォルダに自動で `error_YYYYMMDD_HHMMSS.log` がアップロードされます。その中身をAIに見せて原因を尋ねてください。
3.  **手動で再起動テストを行う**:
    `Actions` ➔ `Tandy.inc Daily Newsletter Automation` ➔ **「Run workflow」**（手動起動）をクリックして、再度テスト実行をトリガーします。

### Q. ストレージ容量超過エラー（storageQuotaExceeded）が発生した場合
*   **原因**: Googleドライブ、またはサービスアカウントの容量制限に達したため、アーカイブ作成（コピー）が失敗しています。
*   **対策（自動）**: `tandy_core.py` は自動的に **「起動時にサービスアカウントのゴミ箱を完全に空にする」** 処理と、**「過去30日分より古いアーカイブを自動的にクリーンアップ（削除）する」** 処理を行います。
*   **対策（手動）**: 
    1. 自動でクリアされない場合、CEO自身のGoogleドライブ容量（ https://drive.google.com/drive/quota ）が上限に達していないか確認し、不要な大容量ファイルやゴミ箱をクリアしてください。
    2. アーカイブの保持期間（デフォルト30日）を短くしたい場合は、`tandy_core.py` の `self.cleanup_old_archives(folder_id, keep_days=30)` の `keep_days` を変更してください。
