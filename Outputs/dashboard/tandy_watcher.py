import os
import sys
import datetime
import traceback
import json
import re
import argparse

try:
    from google.auth import default
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload, MediaInMemoryUpload
    from google import genai
    from google.genai import types
except ImportError as e:
    print(f"Error: Missing dependency. {e}")
    sys.exit(1)

# tandy_core から接続クライアントとクリーンユーティリティをインポート
from tandy_core import TandyDriveClient, clean_emoji_and_symbols

ROOT_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_ROOT_FOLDER_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

class TandyWatcherDriveClient(TandyDriveClient):
    def create_file(self, name, content, parent_id, mime_type='text/markdown'):
        file_metadata = {
            'name': name,
            'parents': [parent_id]
        }
        media = MediaInMemoryUpload(content.encode('utf-8'), mimetype=mime_type, resumable=True)
        file = self.service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        return file.get('id')

    def move_file(self, file_id, source_parent_id, target_parent_id):
        file = self.service.files().get(fileId=file_id, fields='parents').execute()
        previous_parents = ",".join(file.get('parents', [source_parent_id]))
        file = self.service.files().update(
            fileId=file_id,
            addParents=target_parent_id,
            removeParents=previous_parents,
            fields='id, parents'
        ).execute()
        return file

    def delete_file(self, file_id):
        self.service.files().delete(fileId=file_id).execute()

    def list_files_in_folder(self, folder_id):
        query = f"'{folder_id}' in parents and trashed = false"
        results = self.service.files().list(q=query, fields='files(id, name, modifiedTime, size)').execute()
        return results.get('files', [])

    def create_folder(self, name, parent_id):
        file_metadata = {
            'name': name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parent_id]
        }
        file = self.service.files().create(body=file_metadata, fields='id').execute()
        return file.get('id')

    def get_or_create_folder_by_path(self, relative_path, parent_id=None):
        if parent_id is None:
            parent_id = self.root_id
        parts = relative_path.strip("/").split("/")
        current_parent = parent_id
        for part in parts:
            query = f"'{current_parent}' in parents and name = '{part}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            results = self.service.files().list(q=query, fields='files(id, name)').execute()
            files = results.get('files', [])
            if files:
                current_parent = files[0]['id']
            else:
                current_parent = self.create_folder(part, current_parent)
                print(f"フォルダを作成しました: {part} (ID: {current_parent})")
        return current_parent


def get_error_data(drive, ops_folder_id):
    counter_id = drive.find_file_id_by_path("04_運営総務/watcher_error_counter.json", parent_id=drive.root_id)
    if counter_id:
        try:
            content = drive.read_file_content(counter_id)
            return json.loads(content), counter_id
        except Exception as e:
            print(f"警告: エラーカウンタファイルの読み込みに失敗しました: {e}")
    return {"consecutive_errors": 0, "circuit_broken": False}, None


def save_error_data(drive, ops_folder_id, data, counter_id=None):
    content = json.dumps(data, ensure_ascii=False, indent=2)
    if counter_id:
        # 既存ファイルを更新
        media = MediaInMemoryUpload(content.encode('utf-8'), mimetype='application/json')
        drive.service.files().update(fileId=counter_id, media_body=media).execute()
    else:
        # 新規ファイルを作成
        drive.create_file("watcher_error_counter.json", content, ops_folder_id, mime_type='application/json')


def is_stable(file_meta):
    # ドライブの modifiedTime (例: "2026-07-09T14:06:41.000Z")
    mtime_str = file_meta.get('modifiedTime', '')
    if not mtime_str:
        return False
    
    # 簡単なパース (UTC)
    try:
        # 簡易正規表現パース
        m = re.match(r'(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})', mtime_str)
        if m:
            dt = datetime.datetime(
                int(m.group(1)), int(m.group(2)), int(m.group(3)),
                int(m.group(4)), int(m.group(5)), int(m.group(6)),
                tzinfo=datetime.timezone.utc
            )
            now = datetime.datetime.now(datetime.timezone.utc)
            diff = (now - dt).total_seconds()
            return diff >= 30  # 30秒以上経っていれば安定とみなす
    except Exception as e:
        print(f"安定判定中に例外: {e}")
    return True


def determine_mode(gemini_client, filename, content):
    """ファイル名と内容から適切な処理モードをGeminiで判定"""
    prompt = (
        f"ファイル名: {filename}\n"
        f"ファイル内容:\n{content[:2000]}\n\n"
        "このファイルの役割や指示内容を分析し、Tandy.inc の以下の自動化モードのいずれかに分類してください。\n"
        "1. BLOG_MODE (ブログ記事作成、SNS投稿ドラフト、SEO等)\n"
        "2. DEV_MODE (新規プログラムコード、テストコード、README等の開発要求)\n"
        "3. UI_UPDATE_MODE (既存のUIダッシュボードのデザイン・スタイル更新、app.js等の更新)\n"
        "4. BUG_FIX_MODE (エラーログや不具合メモとコードのセット、バグ修正要求)\n"
        "5. RESEARCH_MODE (市場調査、事例調査、トレンド、競合分析等、調査・調べ事を求めるテキスト)\n\n"
        "返答は、以下のJSONフォーマットのみとし、余計な説明やmarkdownコードブロックの記号は一切含めないでください:\n"
        "{\"mode\": \"BLOG_MODE\" | \"DEV_MODE\" | \"UI_UPDATE_MODE\" | \"BUG_FIX_MODE\" | \"RESEARCH_MODE\", \"reason\": \"判定の簡潔な理由\"}"
    )
    
    response = gemini_client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.1)
    )
    
    cleaned_res = response.text.strip().strip('`').strip()
    if cleaned_res.startswith('json'):
        cleaned_res = cleaned_res[4:].strip()
        
    try:
        data = json.loads(cleaned_res)
        return data.get('mode', 'BLOG_MODE'), data.get('reason', '')
    except Exception as e:
        print(f"モードのJSON判定に失敗しました: {e}. デフォルトで BLOG_MODE を適用します。結果: {response.text}")
        return "BLOG_MODE", "Fallback"


def process_workflow(gemini_client, mode, filename, content):
    """各モードに応じたGeminiでの生成処理（エージェント思考のシミュレーション）"""
    today_str = datetime.date.today().strftime("%Y年%m月%d日")
    
    # 共通のベースプロンプト
    system_instruction = (
        "あなたは Tandy.inc の専門エージェントチーム（Research, Creative, Compliance, QA）を統括するAIディレクターです。"
        "入力された要求に対し、各部門の役割をシミュレートしながら、最終的な高品質な成果物を組み立ててください。"
        "毎朝読むCEOが今日一日前向きで知的なエネルギーに満ちあふれるよう、客観的かつ建設的で、自己肯定感の高まる高尚な文体で論述してください。"
        "【重要規約】: 成果物本文および見出しにおいて、絵文字やシンボルマーク（✅や🚀など）は一切使用しないでください。"
    )

    if mode == "BLOG_MODE":
        prompt = (
            f"本日の日付は {today_str} です。\n"
            f"ファイル名: {filename}\n"
            f"入力要求:\n{content}\n\n"
            "以下の手順でブログ記事の成果物を生成してください:\n"
            "1. 【読者ターゲットペルソナ】の定義 (1〜2行で明確に)\n"
            "2. 【リサーチ結果】テーマについてWeb検索や事実をベースにした知的な情報収集サマリー\n"
            "3. 【ブログ本文 ＆ SNS投稿ドラフト】結論ファースト（PREP法）の構成で執筆された知的な記事\n"
            "4. 【SEOメタデータ】32文字以内のSEO推奨タイトル、120文字以内のDescription、3〜5個の推奨キーワード\n"
            "5. 【アイキャッチ画像プロンプト】画像生成AI用のプロンプト（日本語 ＆ 英語）\n"
            "6. 【法務監査レポート】事実誤認リスクや剽窃リスクがないかを自己監査したレポート\n\n"
            "これらを1つの美しいMarkdownファイルとして組み立ててください。絵文字は厳禁です。"
        )
    elif mode == "RESEARCH_MODE":
        prompt = (
            f"本日の日付は {today_str} です。\n"
            f"ファイル名: {filename}\n"
            f"調査要求:\n{content}\n\n"
            "以下の手順で市場調査報告書の成果物を生成してください:\n"
            "1. 【調査報告書】要求されたトピックについての詳細なトレンド・事例調査（一次ソースURLを明記すること）\n"
            "2. 【競合比較マトリクス】対象サービスやツールを視覚的に比較したMarkdown表\n"
            "3. 【費用対効果（ROI）試算 ＆ 導入ロードマップ】導入にかかる料金や、削減される作業時間・人件費などの費用対効果（ROI）シミュレーションを含んだアクションプラン\n"
            "4. 【二重検証監査レポート】事実や数値の正確性を厳格にクロスチェックし、掲載URLが有効か自己検証した監査報告\n\n"
            "これらを統合した美しいMarkdownファイルとして組み立ててください。絵文字は厳禁です。"
        )
    elif mode == "DEV_MODE":
        prompt = (
            f"本日の日付は {today_str} です。\n"
            f"ファイル名: {filename}\n"
            f"開発要求:\n{content}\n\n"
            "以下の手順で開発プログラムパッケージの成果物を生成してください:\n"
            "1. 【設計・仕様調査】必要なPythonライブラリやAPI仕様のアプローチ整理\n"
            "2. 【ソースコード本体】try-except例外処理が徹底された、安全で防衛的なPython等のコード\n"
            "3. 【ユニットテストコード】正常動作を自動検証するための test_*.py テストコード\n"
            "4. 【説明書 README.md】使い方、および 依存ライブラリ requirements.txt\n"
            "5. 【デザイン・UIUX品質監査レポート】レスポンシブ対応や美的余白の検証結果\n"
            "6. 【品質保証レポート】セキュリティ脆弱性の有無、ハードコード値の排除、テスト結果のQA報告\n\n"
            "これら全てのセクション（コード、テスト、README、レポート）を含んだ、1つの美しいMarkdownパッケージファイルとして組み立ててください。絵文字は厳禁です。"
        )
    elif mode == "BUG_FIX_MODE":
        prompt = (
            f"本日の日付は {today_str} です。\n"
            f"ファイル名: {filename}\n"
            f"バグ報告内容:\n{content}\n\n"
            "以下の手順でバグ修正パッケージの成果物を生成してください:\n"
            "1. 【エラー原因調査】エラーログとソースコードを照合した原因分析\n"
            "2. 【修正ソースコード】修正を施した安全なソースコード本体\n"
            "3. 【原因・対策解説 README_fix.md】エラーの根本原因と今後の再発防止策\n"
            "4. 【回帰テスト ＆ 品質QAレポート】今回の修正によって他の既存機能が壊れていないかを検証したレポート\n\n"
            "これらすべてのセクションを含んだ1つの美しいMarkdownファイルとして組み立ててください。絵文字は厳禁です。"
        )
    else:  # UI_UPDATE_MODE
        prompt = (
            f"本日の日付は {today_str} です。\n"
            f"ファイル名: {filename}\n"
            f"UI改善指示:\n{content}\n\n"
            "以下の手順でUI改善・更新パッケージの成果物を生成してください:\n"
            "1. 【変更箇所分析】現在のダッシュボードUIコード（index.html, style.css等）の修正点特定\n"
            "2. 【更新コード】改善されたHTML, CSS, JSコードのコードブロック\n"
            "3. 【デザイン・UIUX監査レポート】美的美観、レスポンシブ性、余白・フォントの監査結果\n"
            "4. 【構文監査・動作テストQAレポート】HTML/CSS/JSの文法エラーや動作上の不具合検証レポート\n\n"
            "これらを1つの美しいMarkdownファイルとして組み立ててください。絵文字は厳禁です。"
        )

    # Gemini-2.5-pro にて思考プロセスとWeb検索ツールを最大限活用して生成
    response = gemini_client.models.generate_content(
        model='gemini-2.5-pro',
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.7,
            tools=[{"google_search": {}}]
        ),
    )
    
    return clean_emoji_and_symbols(response.text)


def check_for_high_risk(content):
    """簡易的な監査判定：ハルシネーションの警告やセキュリティ懸念などのキーワードが含まれるかをチェック"""
    # 監査レポートセクションで「警告」「リスクあり」「高リスク」などの判定があるか判定
    # (※本番ではより厳密な判定が可能ですが、ここではキーワード検知とします)
    lower_content = content.lower()
    risk_keywords = ["ハルシネーションの疑い", "セキュリティ脆弱性", "高リスク判定", "事実誤認の疑い", "警告: リンク切れ"]
    for kw in risk_keywords:
        if kw in lower_content:
            return True
    return False


def main():
    parser = argparse.ArgumentParser(description="Tandy.inc Cloud Inbox Watcher Core")
    parser.add_argument('--dry-run', action='store_true', help="Check files and logs without generating content or moving files")
    args = parser.parse_args()

    if not ROOT_FOLDER_ID or not GEMINI_API_KEY:
        print("エラー: 必要な環境変数が設定されていません。")
        sys.exit(1)

    print("Google Drive API に接続中...")
    drive = TandyWatcherDriveClient()
    
    # 1. 各フォルダのIDを取得
    inbox_id = drive.get_folder_id_by_path("Inbox")
    archive_id = drive.get_folder_id_by_path("Archive")
    outputs_id = drive.get_folder_id_by_path("Outputs")
    ops_folder_id = drive.get_folder_id_by_path("04_運営総務")
    pending_approval_id = drive.get_folder_id_by_path("Pending_Approval")

    if not inbox_id or not archive_id or not outputs_id or not ops_folder_id:
        print("エラー: 必要なフォルダ構造が見つかりません。")
        sys.exit(1)

    # 2. 安全確認（サーキットブレーカー ＆ ロック）
    error_data, counter_id = get_error_data(drive, ops_folder_id)
    if error_data.get("circuit_broken", False):
        print(f"【安全停止】サーキットブレーカーが作動中です (連続エラー: {error_data.get('consecutive_errors')})。処理をスキップします。")
        sys.exit(0)

    lock_id = drive.find_file_id_by_path(".workflow_lock", parent_id=drive.root_id)
    if lock_id:
        print("【処理スキップ】ロックファイル (.workflow_lock) が存在します。現在別プロセスが処理中です。")
        sys.exit(0)

    # 3. Inbox内のファイルリスト取得
    files = drive.list_files_in_folder(inbox_id)
    target_files = []
    for f in files:
        if f['name'].lower() == 'readme.md' or f['name'].startswith('.'):
            continue
        if is_stable(f):
            target_files.append(f)

    print(f"Inbox内のファイル数: {len(files)} 件, 処理対象ファイル数: {len(target_files)} 件")
    if not target_files:
        print("処理対象の新規ファイルはありません。正常終了します。")
        sys.exit(0)

    if args.dry_run:
        print("\n--- DRY-RUN MODE ---")
        print("検出された処理対象ファイル:")
        for tf in target_files:
            print(f"- {tf['name']} (ID: {tf['id']}, 更新日時: {tf['modifiedTime']})")
        print("ドライラン終了。ファイル操作やAPI処理はスキップされました。")
        sys.exit(0)

    # 4. ロックの獲得
    print("ロックファイル (.workflow_lock) を作成します。")
    lock_time_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    lock_id = drive.create_file(".workflow_lock", f"Locked by Cloud Agent at {lock_time_str}", drive.root_id, mime_type='text/plain')

    gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    
    # 5. 各ファイルを処理
    has_global_error = False
    for tf in target_files:
        filename = tf['name']
        file_id = tf['id']
        print(f"\n=== ファイル処理開始: {filename} ===")
        
        try:
            # A. ファイル内容読み込み
            content = drive.read_file_content(file_id)
            
            # B. 処理モード判定
            mode, reason = determine_mode(gemini_client, filename, content)
            print(f"判定されたモード: {mode} (理由: {reason})")
            
            # C. ワークフローコンテンツの生成
            result_content = process_workflow(gemini_client, mode, filename, content)
            print(f"成果物コンテンツの生成が完了しました (文字数: {len(result_content)} 文字)")
            
            # D. 高リスク判定と保存先フォルダの切り替え
            is_high_risk = check_for_high_risk(result_content)
            target_save_folder_id = outputs_id
            save_name_prefix = ""
            
            if is_high_risk:
                print("⚠️ 監査にて高リスク（ハルシネーションまたはセキュリティ懸念）が検知されたため、成果物は Pending_Approval/ に隔離されます。")
                target_save_folder_id = pending_approval_id
                save_name_prefix = "[RISK_PENDING]_"
            
            # E. 成果物の保存
            # 各モードごとの保存名のルールに準拠
            base_name, _ = os.path.splitext(filename)
            if mode == "BLOG_MODE":
                save_name = f"{save_name_prefix}{base_name}_result.md"
                drive.create_file(save_name, result_content, target_save_folder_id)
            elif mode == "RESEARCH_MODE":
                folder_id = drive.get_or_create_folder_by_path(f"Outputs/research/{base_name}" if not is_high_risk else f"Pending_Approval/research_{base_name}", drive.root_id)
                drive.create_file("README.md", result_content, folder_id)
            elif mode == "DEV_MODE":
                folder_id = drive.get_or_create_folder_by_path(f"Outputs/{base_name}" if not is_high_risk else f"Pending_Approval/dev_{base_name}", drive.root_id)
                drive.create_file("README.md", result_content, folder_id)
            elif mode == "BUG_FIX_MODE":
                folder_id = drive.get_or_create_folder_by_path(f"Outputs/bugfixes/{base_name}" if not is_high_risk else f"Pending_Approval/bugfix_{base_name}", drive.root_id)
                drive.create_file("README.md", result_content, folder_id)
            else: # UI_UPDATE_MODE
                # クラウド側では直接上書きせずに、結果パッケージを Outputs/ に入れるか、
                # あるいは Pending_Approval/ での承認待ちにします。
                save_name = f"{save_name_prefix}{base_name}_ui_update.md"
                drive.create_file(save_name, result_content, target_save_folder_id)
            
            print(f"成果物の保存完了！")
            
            # F. 元ファイルを Archive/ へ移動
            print("ファイルを Archive/ へ退避します。")
            drive.move_file(file_id, inbox_id, archive_id)
            print(f"=== ファイル処理成功: {filename} ===")
            
        except Exception as e:
            print(f"❌ ファイル {filename} の処理中にエラーが発生しました: {e}")
            traceback.print_exc()
            has_global_error = True

    # 6. 後処理
    print("\n--- 後処理を実行中 ---")
    try:
        drive.delete_file(lock_id)
        print("ロックファイル (.workflow_lock) を削除しました。")
    except Exception as e:
        print(f"警告: ロックファイルの削除に失敗しました: {e}")

    # エラー状態の記録
    if has_global_error:
        error_data["consecutive_errors"] += 1
        if error_data["consecutive_errors"] >= 3:
            error_data["circuit_broken"] = True
            print(f"🚨 【サーキットブレーカー発動】連続エラーが3回に達したため、定期監視を停止します。")
        else:
            print(f"警告: 処理中にエラーが発生しました。現在の連続エラー回数: {error_data['consecutive_errors']}")
    else:
        error_data["consecutive_errors"] = 0
        error_data["circuit_broken"] = False
        print("すべてのファイルが正常に処理されました。エラーカウンタをリセットしました。")

    save_error_data(drive, ops_folder_id, error_data, counter_id)
    print("定期監視フロー処理完了。")


if __name__ == "__main__":
    main()
