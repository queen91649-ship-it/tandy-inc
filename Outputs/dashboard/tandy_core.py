import os
import sys
import datetime
import traceback
import urllib.request
import re

try:
    from google.auth import default
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
    from google import genai
    from google.genai import types
except ImportError as e:
    print(f"Error: Missing dependency. {e}")
    sys.exit(1)

ROOT_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_ROOT_FOLDER_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

class TandyDriveClient:
    def __init__(self):
        credentials, project = default(scopes=['https://www.googleapis.com/auth/drive'])
        self.service = build('drive', 'v3', credentials=credentials)
        self.root_id = ROOT_FOLDER_ID
        print(f"Google Drive接続成功。ルートフォルダID: {self.root_id}")

    def find_file_id_by_path(self, relative_path, parent_id=None):
        if parent_id is None:
            parent_id = self.root_id
        parts = relative_path.strip("/").split("/")
        current_parent = parent_id
        for i, part in enumerate(parts):
            is_last = (i == len(parts) - 1)
            mime_type_query = "and mimeType != 'application/vnd.google-apps.folder'" if is_last else "and mimeType = 'application/vnd.google-apps.folder'"
            query = f"'{current_parent}' in parents and name = '{part}' and trashed = false {mime_type_query}"
            results = self.service.files().list(q=query, fields='files(id, name)').execute()
            files = results.get('files', [])
            if not files:
                print(f"警告: パス '{relative_path}' の '{part}' が見つかりません。")
                return None
            current_parent = files[0]['id']
        return current_parent

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
                folder_metadata = {'name': part, 'mimeType': 'application/vnd.google-apps.folder', 'parents': [current_parent]}
                folder = self.service.files().create(body=folder_metadata, fields='id').execute()
                current_parent = folder.get('id')
                print(f"フォルダ作成: {part}")
        return current_parent

    def read_file_content(self, file_id):
        import io
        request = self.service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        return fh.getvalue().decode('utf-8')

    def upload_new_file(self, folder_id, filename, content):
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(content)
        file_metadata = {'name': filename, 'parents': [folder_id]}
        media = MediaFileUpload(filename, mimetype='text/markdown')
        uploaded = self.service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        if os.path.exists(filename):
            os.remove(filename)
        return uploaded.get('id')

def main():
    if not ROOT_FOLDER_ID or not GEMINI_API_KEY:
        print("エラー: 必要な環境変数が設定されていません。")
        sys.exit(1)

    drive = TandyDriveClient()
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    today_str = datetime.date.today().strftime("%Y年%m月%d日")

    # watchlist.txt 読み込み
    print("watchlist.txt を読み込み中...")
    watchlist_id = drive.find_file_id_by_path("02_Research/watchlist.txt")
    if not watchlist_id:
        raise FileNotFoundError("02_Research/watchlist.txt が見つかりません。")
    watchlist_content = drive.read_file_content(watchlist_id)
    print("watchlist.txt 読み込み完了。")

    # 記者定義ファイル読み込み
    reporters = {
        "japan":      "08_Publishing/reporters/reporter_japan.md",
        "global":     "08_Publishing/reporters/reporter_global.md",
        "ai":         "08_Publishing/reporters/reporter_ai.md",
        "infra":      "08_Publishing/reporters/reporter_infra.md",
        "spurs":      "08_Publishing/reporters/reporter_spurs.md",
        "premier":    "08_Publishing/reporters/reporter_premier.md",
        "europe":     "08_Publishing/reporters/reporter_europe.md",
        "serendipity":"08_Publishing/reporters/reporter_serendipity.md"
    }
    reporter_instructions = {}
    for name, path in reporters.items():
        fid = drive.find_file_id_by_path(path)
        reporter_instructions[name] = drive.read_file_content(fid) if fid else f"あなたは{name}担当の記者です。"
        print(f"{name} 記者定義ファイル読み込み完了。")

    editor_id = drive.find_file_id_by_path("08_Publishing/editor_agent.md")
    editor_instruction = drive.read_file_content(editor_id) if editor_id else "あなたは総合編集長です。"

    auditor_id = drive.find_file_id_by_path("05_Compliance/auditor_agent.md")
    auditor_instruction = drive.read_file_content(auditor_id) if auditor_id else "あなたはコンプライアンス監査役です。"

    # 8名の記者による執筆
    articles = {}
    print("\n--- 8名の記者が執筆を開始します ---")
    for name, instruction in reporter_instructions.items():
        print(f"{name} 記者 執筆中...")
        prompt = f"本日の日付は {today_str} です。あなたの役割定義に従い、直近24時間における重要トピックを必ず3件以上選定し、詳細に執筆してください。各トピックには個別に 'Tandy's Insight' を記述してください。Google Searchで最新情報を収集してから執筆してください。"
        try:
            response = gemini_client.models.generate_content(
                model='gemini-2.5-pro',
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=instruction,
                    temperature=0.7,
                    tools=[{"google_search": {}}]
                ),
            )
            articles[name] = response.text
            print(f"{name} 記者 執筆完了。")
        except Exception as ex:
            articles[name] = f"【エラー】{name}記者の執筆中にエラーが発生しました: {ex}"
            print(f"{name} 記者 エラー: {ex}")

    # 編集長によるパッケージング
    print("\n--- 編集長がパッケージング中 ---")
    editor_prompt = f"""本日の日付は {today_str} です。8名の記者から以下の原稿が届きました。
【国内政治・経済】{articles.get('japan','')}
【国際情勢・世界経済】{articles.get('global','')}
【AI・テクノロジー】{articles.get('ai','')}
【通信インフラ】{articles.get('infra','')}
【トッテナム・Spurs】{articles.get('spurs','')}
【プレミアリーグ】{articles.get('premier','')}
【欧州リーグ】{articles.get('europe','')}
【宇宙・深海・科学】{articles.get('serendipity','')}
全体のトーンを統一し、表紙（ヘッドラインリード・目次）と編集長社説を追加して、美しいMarkdown形式の朝刊（Tandy Times）を完成させてください。"""

    draft = gemini_client.models.generate_content(
        model='gemini-2.5-pro', contents=editor_prompt,
        config=types.GenerateContentConfig(system_instruction=editor_instruction, temperature=0.7)
    ).text
    print("編集長パッケージング完了。")

    # URL生存チェック
    link_report = "### 生存リンクチェックログ\n"
    for url in set(re.findall(r'https?://[^\s\)\],`"]+', draft)):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as conn:
                link_report += f"* {url} : ✅ 生存確認 ({conn.getcode()} OK)\n"
        except Exception as ex:
            link_report += f"* {url} : ⚠️ アクセス失敗 ({ex})\n"

    # Compliance監査
    print("\n--- Compliance監査中 ---")
    compliance_prompt = f"""編集長から朝刊ドラフトが届きました。
【朝刊ドラフト】{draft}
ハルシネーションがないかを検証し、以下のURL検証ログと合わせて監査レポートを作成してください。
【URLログ】{link_report}
最後に朝刊ドラフトの末尾に監査レポートをドッキングした最終版を書き出してください。"""

    final = gemini_client.models.generate_content(
        model='gemini-2.5-pro', contents=compliance_prompt,
        config=types.GenerateContentConfig(system_instruction=auditor_instruction, temperature=0.7)
    ).text
    print("Compliance監査完了。")

    # Googleドライブへ納品
    print("\n--- Googleドライブへ朝刊を納品中 ---")
    newsletters_folder_id = drive.get_or_create_folder_by_path("Outputs/newsletters")
    filename = f"{datetime.date.today().strftime('%Y%m%d')}_newsletter.md"
    file_id = drive.upload_new_file(newsletters_folder_id, filename, final)
    print(f"✅ 朝刊の納品完了！ファイル名: {filename} (ID: {file_id})")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        tb = traceback.format_exc()
        print("\n!!! ERROR DETAILS IN CLOUD !!!")
        print(tb)
        try:
            drive_client = TandyDriveClient()
            errors_folder_id = drive_client.get_or_create_folder_by_path("Outputs/errors")
            err_filename = f"error_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            drive_client.upload_new_file(errors_folder_id, err_filename, tb)
            print(f"エラーログをGoogleドライブに保存しました: {err_filename}")
        except Exception as ex:
            print(f"エラーログのアップロードに失敗: {ex}")
        sys.exit(1)
