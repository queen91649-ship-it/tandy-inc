import os
import sys
import datetime
import traceback
import re

# Drive クライアントの読み込み
from tandy_watcher import TandyWatcherDriveClient

ROOT_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_ROOT_FOLDER_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

def clean_newsletters(drive):
    """Outputs/newsletters 内の古いニュースレターを月別フォルダに分類整理し、日付の表記揺れを補正"""
    print("\n--- ニュースレターフォルダの整理整頓を開始します ---")
    
    newsletters_dir_id = drive.get_folder_id_by_path("Outputs/newsletters")
    if not newsletters_dir_id:
        print("Outputs/newsletters フォルダが存在しないため、スキップします。")
        return
        
    files = drive.list_files(newsletters_dir_id)
    
    for f in files:
        name = f['name']
        file_id = f['id']
        mime_type = f['mimeType']
        
        # フォルダはスキップ
        if mime_type == 'application/vnd.google-apps.folder':
            continue
            
        # 表記揺れの検出用パターン
        # 期待する標準形式: Tandy_Times_YYYYMMDD.md
        # 揺れ形式1: Tandy_Times_YYYY_MM_DD.md
        # 揺れ形式2: Tandy_Times_YYYY-MM-DD.md
        
        standard_match = re.search(r'Tandy_Times_(\d{8})\.md', name)
        
        new_name = name
        date_str = None
        
        if standard_match:
            date_str = standard_match.group(1)
        else:
            # 揺れ形式 2026_07_10
            underscore_match = re.search(r'Tandy_Times_(\d{4})_(\d{2})_(\d{2})\.md', name)
            # 揺れ形式 2026-07-10
            dash_match = re.search(r'Tandy_Times_(\d{4})-(\d{2})-(\d{2})\.md', name)
            
            if underscore_match:
                date_str = underscore_match.group(1) + underscore_match.group(2) + underscore_match.group(3)
                new_name = f"Tandy_Times_{date_str}.md"
            elif dash_match:
                date_str = dash_match.group(1) + dash_match.group(2) + dash_match.group(3)
                new_name = f"Tandy_Times_{date_str}.md"
                
        if date_str:
            # YYYYMMDD から年と月を取得 (20260710 -> 2026_07)
            year = date_str[:4]
            month = date_str[4:6]
            month_folder_name = f"{year}_{month}"
            
            # 月別フォルダを取得または作成
            month_folder_id = drive.get_or_create_folder_by_path(f"Outputs/newsletters/{month_folder_name}", drive.root_id)
            
            # リネームが必要なら実行
            if new_name != name:
                print(f"表記揺れ補正リネーム: {name} -> {new_name}")
                drive.rename_file(file_id, new_name)
                
            # 月別フォルダに移動
            print(f"ニュースレターをアーカイブ: {new_name} -> Outputs/newsletters/{month_folder_name}/")
            drive.move_file(file_id, newsletters_dir_id, month_folder_id)

def clean_proposals(drive):
    """adopted, rethinking, rejected フォルダ内の7日以上古い提案書をアーカイブへ移動"""
    print("\n--- 意思決定済み提案書フォルダの整理整頓を開始します ---")
    
    proposals_path = "Outputs/proposals"
    proposals_id = drive.get_folder_id_by_path(proposals_path)
    if not proposals_id:
        print("Outputs/proposals フォルダが存在しません。")
        return
        
    subdirs = ["adopted", "rethinking", "rejected"]
    
    # 提案全体のアーカイブフォルダ
    archive_id = drive.get_or_create_folder_by_path(f"{proposals_path}/archive", drive.root_id)
    
    today = datetime.datetime.now(datetime.timezone.utc)
    
    for subdir in subdirs:
        subdir_id = drive.get_folder_id_by_path(f"{proposals_path}/{subdir}")
        if not subdir_id:
            continue
            
        files = drive.list_files(subdir_id)
        
        for f in files:
            name = f['name']
            file_id = f['id']
            mime_type = f['mimeType']
            
            if mime_type == 'application/vnd.google-apps.folder' or name == '.gitkeep':
                continue
                
            # 作成または更新日時を取得
            # ドライブの modifiedTime (ISO形式) をパース
            modified_time_str = f.get('modifiedTime')
            if not modified_time_str:
                continue
                
            # ISO 8601 形式の文字列を datetime オブジェクトに変換 (タイムゾーン対応)
            # 末尾の Z を +00:00 に置換してパースしやすくする
            clean_time_str = modified_time_str.replace('Z', '+00:00')
            modified_time = datetime.datetime.fromisoformat(clean_time_str)
            
            age = (today - modified_time).days
            
            # 7日以上経過したものをアーカイブへ移動
            if age >= 7:
                print(f"7日以上経過した提案をアーカイブ移動 ({subdir}): {name} (最終更新から {age} 日経過)")
                
                # サブディレクトリ内のアーカイブ先フォルダ (例: Outputs/proposals/archive/adopted/)
                dest_sub_archive_id = drive.get_or_create_folder_by_path(f"{proposals_path}/archive/{subdir}", drive.root_id)
                drive.move_file(file_id, subdir_id, dest_sub_archive_id)

def clean_inbox(drive):
    """Inbox フォルダに残ったままになっている古い処理済みファイルを整理"""
    print("\n--- Inboxフォルダの点検・整理整頓を開始します ---")
    
    inbox_id = drive.get_folder_id_by_path("Inbox")
    if not inbox_id:
        print("Inbox フォルダが存在しません。")
        return
        
    files = drive.list_files(inbox_id)
    today = datetime.datetime.now(datetime.timezone.utc)
    
    # 成果物アーカイブフォルダ
    global_archive_id = drive.get_or_create_folder_by_path("Outputs/archive", drive.root_id)
    
    for f in files:
        name = f['name']
        file_id = f['id']
        mime_type = f['mimeType']
        
        if mime_type == 'application/vnd.google-apps.folder' or name == 'README.md' or name == '.gitkeep':
            continue
            
        modified_time_str = f.get('modifiedTime')
        if not modified_time_str:
            continue
            
        clean_time_str = modified_time_str.replace('Z', '+00:00')
        modified_time = datetime.datetime.fromisoformat(clean_time_str)
        
        age = (today - modified_time).days
        
        # 処理済みプレフィックス（【実行要求】や【再考依頼】）が付いていて、3日以上放置されているファイルをアーカイブに移動
        if (name.startswith("【実行要求】") or name.startswith("【再考依頼】")) and age >= 3:
            print(f"Inbox内で処理完了し放置された指示書をアーカイブへ退避: {name} ({age} 日前)")
            drive.move_file(file_id, inbox_id, global_archive_id)

def main():
    if not ROOT_FOLDER_ID or not GEMINI_API_KEY:
        print(f"エラー: 必要な環境変数が設定されていません。")
        print(f"  GOOGLE_DRIVE_ROOT_FOLDER_ID: {'設定あり' if ROOT_FOLDER_ID else '未設定'}")
        print(f"  GEMINI_API_KEY: {'設定あり' if GEMINI_API_KEY else '未設定'}")
        sys.exit(1)

    print("Google Drive API に接続中...")
    try:
        drive = TandyWatcherDriveClient()
    except Exception as e:
        print(f"エラー: Google Driveへの接続に失敗しました: {e}")
        traceback.print_exc()
        sys.exit(1)
    
    # ロックファイルチェック
    lock_id = drive.find_file_id_by_path(".workflow_lock", parent_id=drive.root_id)
    if lock_id:
        print("【処理スキップ】ロックファイル (.workflow_lock) が存在するため、整理整頓フローをスキップします。")
        sys.exit(0)

    # ロックの確保
    print("ロックファイル (.workflow_lock) を作成します。")
    lock_time_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    lock_id = drive.create_file(".workflow_lock", f"Locked by Housekeeping Agent at {lock_time_str}", drive.root_id, mime_type='text/plain')

    try:
        # 各クリーンアップルールの実行
        clean_newsletters(drive)
        clean_proposals(drive)
        clean_inbox(drive)
        
        print("\n✅ 週次自動整理整頓（Housekeeping）が正常に完了しました！")
        
    except Exception as e:
        print(f"❌ 整理整頓プロセス中にエラーが発生しました: {e}")
        traceback.print_exc()
        sys.exit(1)
        
    finally:
        # ロックファイルの削除
        try:
            drive.delete_file(lock_id)
            print("ロックファイル (.workflow_lock) を削除しました。")
        except Exception as e:
            print(f"警告: ロックファイルの削除に失敗しました: {e}")

if __name__ == "__main__":
    main()
