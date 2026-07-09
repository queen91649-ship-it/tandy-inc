import os
import sys

try:
    from google.auth import default
    from googleapiclient.discovery import build
except ImportError as e:
    print(f"Error: Missing dependency. {e}")
    sys.exit(1)

ROOT_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_ROOT_FOLDER_ID")

def main():
    print(f"=== DEBUG MODE ===")
    print(f"ROOT_FOLDER_ID: {ROOT_FOLDER_ID}")
    
    credentials, project = default(scopes=['https://www.googleapis.com/auth/drive'])
    service = build('drive', 'v3', credentials=credentials)
    
    print(f"GCP Project: {project}")
    print(f"Credentials type: {type(credentials)}")

    # サービスアカウントが見えているファイル・フォルダをすべて表示
    print("\n=== サービスアカウントからアクセスできるファイル一覧 ===")
    results = service.files().list(
        pageSize=20,
        fields="files(id, name, mimeType, parents)"
    ).execute()
    
    files = results.get('files', [])
    if not files:
        print("【警告】アクセスできるファイルが1つもありません！共有設定が機能していない可能性があります。")
    else:
        for f in files:
            print(f"  名前: {f['name']}")
            print(f"  ID:   {f['id']}")
            print(f"  種類: {f['mimeType']}")
            print(f"  親:   {f.get('parents', '不明')}")
            print("  ---")
    
    # 指定のルートフォルダに直接アクセスを試みる
    print(f"\n=== ルートフォルダID ({ROOT_FOLDER_ID}) への直接アクセステスト ===")
    try:
        folder = service.files().get(fileId=ROOT_FOLDER_ID, fields='id, name, mimeType').execute()
        print(f"成功！フォルダ名: {folder['name']}, 種類: {folder['mimeType']}")
    except Exception as ex:
        print(f"失敗！エラー: {ex}")

if __name__ == "__main__":
    main()
