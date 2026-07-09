import os
import sys
import datetime
import traceback
import urllib.request
import json

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
        return current_parent

    def read_file_content(self, file_id):
        import io
        request = self.service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
        return fh.getvalue().decode('utf-8')

    def upload_new_file(self, folder_id, filename, content):
        import io
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(content)
        file_metadata = {'name': filename, 'parents': [folder_id]}
        media = MediaFileUpload(filename, mimetype='text/markdown')
        uploaded_file = self.service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        if os.path.exists(filename):
            os.remove(filename)
        return uploaded_file.get('id')

def main():
    if not ROOT_FOLDER_ID or not GEMINI_API_KEY:
        sys.exit(1)

    drive = TandyDriveClient()
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    
    watchlist_id = drive.find_file_id_by_path("02_Research/watchlist.txt")
    if not watchlist_id:
        raise FileNotFoundError("Could not find watchlist.txt")
    
    watchlist_content = drive.read_file_content(watchlist_id)

    reporters = {
        "japan": "08_Publishing/reporters/reporter_japan.md",
        "global": "08_Publishing/reporters/reporter_global.md",
        "ai": "08_Publishing/reporters/reporter_ai.md",
        "infra": "08_Publishing/reporters/reporter_infra.md",
        "spurs": "08_Publishing/reporters/reporter_spurs.md",
        "premier": "08_Publishing/reporters/reporter_premier.md",
        "europe": "08_Publishing/reporters/reporter_europe.md",
        "serendipity": "08_Publishing/reporters/reporter_serendipity.md"
    }
    
    reporter_instructions = {}
    for name, path in reporters.items():
        fid = drive.find_file_id_by_path(path)
        reporter_instructions[name] = drive.read_file_content(fid) if fid else f"You are {name} reporter."

    editor_id = drive.find_file_id_by_path("08_Publishing/editor_agent.md")
    editor_instruction = drive.read_file_content(editor_id) if editor_id else "You are Editor-in-Chief."

    auditor_id = drive.find_file_id_by_path("05_Compliance/auditor_agent.md")
    auditor_instruction = drive.read_file_content(auditor_id) if auditor_id else "You are Compliance Auditor."

    articles = {}
    today_str = datetime.date.today().strftime("%Y年%m月%d日")
    
    for name, instruction in reporter_instructions.items():
        prompt = f"本日の日付は {today_str} です。あなたの役割定義に従い、直近24時間における重要トピックを必ず3件以上選定し、詳細に執筆してください。各トピックには、個別に必ず 'Tandy's Insight' を記述してください。最新情報を取得するために、必ず内蔵 of 検索（Google Search）を実行し、最新のファクトに基づいて執筆してください。"
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
        except Exception as ex:
            articles[name] = f"【エラー】{name}記者の執筆プロセスでエラーが発生しました: {ex}"

    editor_prompt = f"本日の日付は {today_str} です。8名の各記者から以下の一次原稿が届きました。【国内政治・経済 (reporter_japan)】{articles.get('japan', '')}【国際情勢・世界経済 (reporter_global)】{articles.get('global', '')}【AI・テクノロジー (reporter_ai)】{articles.get('ai', '')}【通信インフラ・海底ケーブル (reporter_infra)】{articles.get('infra', '')}【トッテナム・Spurs (reporter_spurs)】{articles.get('spurs', '')}【プレミアリーグ (reporter_premier)】{articles.get('premier', '')}【欧州リーグ・カップ戦 (reporter_europe)】{articles.get('europe', '')}【宇宙・深海・科学 (reporter_serendipity)】{articles.get('serendipity', '')}。あなたの編集ルール（editor_agent.md）に従い、全体のトーン＆マナー（です・ます調への統制）を整え、表紙（今日のヘッドラインリード・目次）、および編集長社説（EIC Editorial）を追加して、1つの美しいMarkdown形式の朝刊（Tandy Times）を完成させてください。"
    
    tandy_times_draft = gemini_client.models.generate_content(
        model='gemini-2.5-pro', contents=editor_prompt,
        config=types.GenerateContentConfig(system_instruction=editor_instruction, temperature=0.7)
    ).text

    link_report = "### 生存リンクチェックログ\n"
    import re
    urls = re.findall(r'https?://[^\s\)\],`]+', tandy_times_draft)
    for url in set(urls):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as conn:
                status = conn.getcode()
            link_report += f"* {url} : **生存確認完了 ({status} OK)**\n"
        except Exception as ex:
            link_report += f"* {url} : **警告 - アクセス失敗 ({ex})**\n"

    compliance_prompt = f"編集長から完成した朝刊ドラフトが上がってきました。【朝刊ドラフト】{tandy_times_draft}。あなたのルール（auditor_agent.md）に従い、記述されている各トピックのファクト（数値や名称等）にハルシネーションがないかを検証してください。また、以下の自動URL検証ログをベースにして、リンク切れ生存チェック報告を含んだ「法務監査 ＆ 生存リンク二重検証レポート (Compliance 担当)」を作成してください。【自動URL検証ログ】{link_report}。最後に、朝刊ドラフトの末尾に、あなたの監査レポートをドッキングした最終版の「朝刊（Tandy Times）」を書き出してください。"
    
    final_newsletter_content = gemini_client.models.generate_content(
        model='gemini-2.5-pro', contents=compliance_prompt,
        config=types.GenerateContentConfig(system_instruction=auditor_instruction, temperature=0.7)
    ).text

    newsletters_folder_id = drive.get_or_create_folder_by_path("Outputs/newsletters")
    filename = f"{datetime.date.today().strftime('%Y%m%d')}_newsletter.md"
    drive.upload_new_file(newsletters_folder_id, filename, final_newsletter_content)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        tb = traceback.format_exc()
        print("\n!!! ERROR DETAILS IN CLOUD !!!")
        print(tb)  # 必ずGitHubの画面にエラーを表示させる
        try:
            drive_client = TandyDriveClient()
            errors_folder_id = drive_client.get_or_create_folder_by_path("Outputs/errors")
            err_filename = f"error_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            drive_client.upload_new_file(errors_folder_id, err_filename, tb)
            print("Uploaded error log to Google Drive.")
        except Exception as ex:
            print(f"Could not upload error log to Google Drive: {ex}")
        sys.exit(1)
