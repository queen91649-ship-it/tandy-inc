import os
import sys
import datetime
import traceback
import urllib.request
import re
import xml.etree.ElementTree as ET

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
        credentials, project = default(scopes=[
            'https://www.googleapis.com/auth/drive',
            'https://www.googleapis.com/auth/documents'
        ])
        self.credentials = credentials
        self.service = build('drive', 'v3', credentials=credentials)
        self.docs_service = build('docs', 'v1', credentials=credentials)
        self.root_id = ROOT_FOLDER_ID
        print(f"Google Drive & Docs 接続成功。ルートID: {self.root_id}")

    def find_file_id_by_path(self, relative_path, parent_id=None):
        if parent_id is None:
            parent_id = self.root_id
        parts = relative_path.strip("/").split("/")
        current_parent = parent_id
        for i, part in enumerate(parts):
            is_last = (i == len(parts) - 1)
            if is_last:
                query = f"'{current_parent}' in parents and name = '{part}' and trashed = false"
            else:
                query = f"'{current_parent}' in parents and name = '{part}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            results = self.service.files().list(q=query, fields='files(id, name)').execute()
            files = results.get('files', [])
            if not files:
                print(f"警告: パス '{relative_path}' の '{part}' が見つかりません。")
                return None
            current_parent = files[0]['id']
        return current_parent

    def get_folder_id_by_path(self, relative_path, parent_id=None):
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
                print(f"フォルダが見つかりません: {part}")
                return None
        return current_parent

    def read_file_content(self, file_id):
        import io
        file_metadata = self.service.files().get(fileId=file_id, fields='mimeType').execute()
        mime_type = file_metadata.get('mimeType', '')

        if 'application/vnd.google-apps.document' in mime_type:
            request = self.service.files().export_media(fileId=file_id, mimeType='text/plain')
        else:
            request = self.service.files().get_media(fileId=file_id)

        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        return fh.getvalue().decode('utf-8')

    def archive_and_update_newsletter(self, folder_id, content):
        """
        前回の 'latest_newsletter' の複製コピーはサービスアカウントの容量制限（上限0バイト）を回避するため行わず、
        代わりにローカルの Outputs/newsletters/ 内にMarkdownとしてアーカイブを出力し、
        Google Docs（latest_newsletter）はDocs APIで上書き更新する。
        """
        # 1. 既存の latest_newsletter を検索
        query = f"'{folder_id}' in parents and name contains 'latest_newsletter' and trashed = false"
        results = self.service.files().list(q=query, fields='files(id, name)').execute()
        files = results.get('files', [])

        if not files:
            raise FileNotFoundError("latest_newsletter が見つかりません。")

        latest_id = files[0]['id']
        
        # 2. ローカルに日付付きMarkdownでアーカイブを保存（GitHub Actionsがこれをコミットして履歴保存する - 日本時間基準）
        jst = datetime.timezone(datetime.timedelta(hours=9))
        archive_name = f"{datetime.datetime.now(jst).strftime('%Y%m%d')}_newsletter.md"
        local_dir = "Outputs/newsletters"
        os.makedirs(local_dir, exist_ok=True)
        local_path = os.path.join(local_dir, archive_name)
        with open(local_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"ローカルアーカイブにニュースレターを保存しました: {local_path}")

        # 3. Google Docs API を用いた本番上書き ＆ 自己肯定感が上がる美麗フォーマットの適用
        print("最新ニュースレターを上書き更新 ＆ 知的フォーマット整形中...")
        self.write_and_format_google_doc(latest_id, content)
        return latest_id

    def write_and_format_google_doc(self, document_id, markdown_text):
        """
        Google Docs API を使用して、Markdownテキストを美しい段落・見出し・装飾付きドキュメントに変換して上書きする。
        """
        doc = self.docs_service.documents().get(documentId=document_id).execute()
        end_index = doc.get('body').get('content')[-1].get('endIndex')
        
        requests = []
        if end_index > 2:
            requests.append({
                'deleteContentRange': {
                    'range': {
                        'startIndex': 1,
                        'endIndex': end_index - 1
                    }
                }
            })
            self.docs_service.documents().batchUpdate(documentId=document_id, body={'requests': requests}).execute()

        requests = []
        current_index = 1
        lines = markdown_text.split('\n')
        
        formatting_actions = []

        for line in lines:
            if line.startswith('# '):
                clean_text = line[2:].strip() + '\n'
                requests.append({'insertText': {'location': {'index': current_index}, 'text': clean_text}})
                formatting_actions.append(('HEADING_1', current_index, current_index + len(clean_text)))
                current_index += len(clean_text)
            elif line.startswith('## '):
                clean_text = line[3:].strip() + '\n'
                requests.append({'insertText': {'location': {'index': current_index}, 'text': clean_text}})
                formatting_actions.append(('HEADING_2', current_index, current_index + len(clean_text)))
                current_index += len(clean_text)
            elif line.startswith('### '):
                clean_text = line[4:].strip() + '\n'
                requests.append({'insertText': {'location': {'index': current_index}, 'text': clean_text}})
                formatting_actions.append(('HEADING_3', current_index, current_index + len(clean_text)))
                current_index += len(clean_text)
            elif line.strip() == '---':
                divider = "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                requests.append({'insertText': {'location': {'index': current_index}, 'text': divider}})
                formatting_actions.append(('DIVIDER', current_index, current_index + len(divider)))
                current_index += len(divider)
            else:
                clean_text = line + '\n'
                requests.append({'insertText': {'location': {'index': current_index}, 'text': clean_text}})
                
                if "Tandy's Insight" in clean_text:
                    start_offset = clean_text.find("Tandy's Insight")
                    formatting_actions.append(('INSIGHT_HIGHLIGHT', current_index + start_offset, current_index + start_offset + len("Tandy's Insight")))
                
                bold_matches = list(re.finditer(r'\*\*(.*?)\*\*', clean_text))
                for match in bold_matches:
                    b_start = current_index + match.start()
                    b_end = current_index + match.end()
                    formatting_actions.append(('BOLD_TEXT', b_start, b_end))

                current_index += len(clean_text)

        if requests:
            self.docs_service.documents().batchUpdate(documentId=document_id, body={'requests': requests}).execute()

        style_requests = []
        for action, start, end in formatting_actions:
            if start < 1:
                continue
            
            if action == 'HEADING_1':
                style_requests.append({
                    'updateParagraphStyle': {
                        'range': {'startIndex': start, 'endIndex': end},
                        'paragraphStyle': {'namedStyleType': 'TITLE'},
                        'fields': 'namedStyleType'
                    }
                })
                style_requests.append({
                    'updateTextStyle': {
                        'range': {'startIndex': start, 'endIndex': end - 1},
                        'textStyle': {
                            'foregroundColor': {'color': {'rgbColor': {'blue': 0.35, 'green': 0.15, 'red': 0.12}}},
                            'fontSize': {'magnitude': 22, 'unit': 'PT'},
                            'bold': True
                        },
                        'fields': 'foregroundColor,fontSize,bold'
                    }
                })
            elif action == 'HEADING_2':
                style_requests.append({
                    'updateParagraphStyle': {
                        'range': {'startIndex': start, 'endIndex': end},
                        'paragraphStyle': {'namedStyleType': 'HEADING_1'},
                        'fields': 'namedStyleType'
                    }
                })
                style_requests.append({
                    'updateTextStyle': {
                        'range': {'startIndex': start, 'endIndex': end - 1},
                        'textStyle': {
                            'foregroundColor': {'color': {'rgbColor': {'blue': 0.55, 'green': 0.28, 'red': 0.18}}},
                            'fontSize': {'magnitude': 15, 'unit': 'PT'},
                            'bold': True
                        },
                        'fields': 'foregroundColor,fontSize,bold'
                    }
                })
            elif action == 'HEADING_3':
                style_requests.append({
                    'updateParagraphStyle': {
                        'range': {'startIndex': start, 'endIndex': end},
                        'paragraphStyle': {'namedStyleType': 'HEADING_2'},
                        'fields': 'namedStyleType'
                    }
                })
                style_requests.append({
                    'updateTextStyle': {
                        'range': {'startIndex': start, 'endIndex': end - 1},
                        'textStyle': {
                            'foregroundColor': {'color': {'rgbColor': {'blue': 0.3, 'green': 0.3, 'red': 0.3}}},
                            'fontSize': {'magnitude': 12, 'unit': 'PT'},
                            'bold': True
                        },
                        'fields': 'foregroundColor,fontSize,bold'
                    }
                })
            elif action == 'INSIGHT_HIGHLIGHT':
                style_requests.append({
                    'updateTextStyle': {
                        'range': {'startIndex': start, 'endIndex': end},
                        'textStyle': {
                            'foregroundColor': {'color': {'rgbColor': {'blue': 0.5, 'green': 0.1, 'red': 0.1}}},
                            'bold': True
                        },
                        'fields': 'foregroundColor,bold'
                    }
                })
            elif action == 'BOLD_TEXT':
                style_requests.append({
                    'updateTextStyle': {
                        'range': {'startIndex': start, 'endIndex': end},
                        'textStyle': {'bold': True},
                        'fields': 'bold'
                    }
                })
            elif action == 'DIVIDER':
                style_requests.append({
                    'updateTextStyle': {
                        'range': {'startIndex': start, 'endIndex': end},
                        'textStyle': {
                            'foregroundColor': {'color': {'rgbColor': {'blue': 0.8, 'green': 0.8, 'red': 0.8}}}
                        },
                        'fields': 'foregroundColor'
                    }
                })

        if style_requests:
            try:
                self.docs_service.documents().batchUpdate(documentId=document_id, body={'requests': style_requests}).execute()
            except Exception as ex:
                print(f"書式適用で一部スキップが発生しました: {ex}")

        replace_requests = [
            {
                'replaceAllText': {
                    'containsText': {'matchCase': True, 'text': '**'},
                    'replaceText': ''
                }
            }
        ]
        self.docs_service.documents().batchUpdate(documentId=document_id, body={'requests': replace_requests}).execute()

    def list_files(self, folder_id):
        """指定したフォルダ内のファイル一覧を取得する (mimeType, modifiedTime, size を含む)"""
        query = f"'{folder_id}' in parents and trashed = false"
        results = self.service.files().list(
            q=query, 
            fields='files(id, name, mimeType, modifiedTime, size)'
        ).execute()
        return results.get('files', [])

    def rename_file(self, file_id, new_name):
        """ファイル名をリネームする"""
        file_metadata = {'name': new_name}
        return self.service.files().update(
            fileId=file_id, 
            body=file_metadata, 
            fields='id, name'
        ).execute()

    def empty_trash_and_show_quota(self):
        """
        サービスアカウントのストレージ容量（クォータ）を表示し、
        ゴミ箱（Trash）を空にして容量を解放する。
        """
        print("\n--- サービスアカウント ストレージ確認 ＆ ゴミ箱クリア ---")
        try:
            about = self.service.about().get(fields="storageQuota").execute()
            quota = about.get('storageQuota', {})
            limit = int(quota.get('limit', 0)) / (1024**3) if 'limit' in quota else 0
            usage = int(quota.get('usage', 0)) / (1024**3) if 'usage' in quota else 0
            print(f"ストレージ使用状況: {usage:.4f} GB / 上限: {limit:.4f} GB")
        except Exception as e:
            print(f"ストレージ情報の取得に失敗しました: {e}")

        try:
            print("ゴミ箱を空にしています...")
            self.service.files().emptyTrash().execute()
            print("ゴミ箱のクリアが完了しました。")
            
            about = self.service.about().get(fields="storageQuota").execute()
            quota = about.get('storageQuota', {})
            usage = int(quota.get('usage', 0)) / (1024**3) if 'usage' in quota else 0
            print(f"クリア後のストレージ使用状況: {usage:.4f} GB")
        except Exception as e:
            print(f"ゴミ箱のクリアに失敗しました: {e}")

    def cleanup_old_archives(self, folder_id, keep_days=30):
        """
        アーカイブフォルダ内の古いファイルを削除する（デフォルト30日間保持）
        """
        print(f"\n--- 古いアーカイブのクリーンアップ (過去 {keep_days} 日分を保持) ---")
        try:
            query = f"'{folder_id}' in parents and name contains '_newsletter' and trashed = false"
            results = self.service.files().list(
                q=query, 
                orderBy="name desc", 
                fields='files(id, name, createdTime)'
            ).execute()
            files = results.get('files', [])
            
            archive_files = []
            for f in files:
                if re.match(r'^\d{8}_newsletter', f['name']):
                    archive_files.append(f)
            
            print(f"見つかったアーカイブ数: {len(archive_files)} 件")
            if len(archive_files) > keep_days:
                to_delete = archive_files[keep_days:]
                print(f"保持上限 ({keep_days} 件) を超えたため、{len(to_delete)} 件の古いファイルを削除します。")
                for f in to_delete:
                    print(f"削除中: {f['name']} (ID: {f['id']})")
                    self.service.files().delete(fileId=f['id']).execute()
                print("古いアーカイブの削除が完了しました。")
            else:
                print("削除対象の古いアーカイブはありません。")
        except Exception as e:
            print(f"古いアーカイブのクリーンアップに失敗しました: {e}")


def read_file_with_local_fallback(drive_client, relative_path, default_content=None):
    """
    Google Drive API を介してファイルを読み込むことを試み、
    見つからない場合はローカルリポジトリ内の同パスのファイルから読み込むフォールバック処理を行います。
    """
    try:
        file_id = drive_client.find_file_id_by_path(relative_path)
        if file_id:
            content = drive_client.read_file_content(file_id)
            print(f"Drive から読み込み成功: {relative_path}")
            return content
    except Exception as e:
        print(f"Drive からの読み込み中にエラーが発生しました ({relative_path}): {e}。ローカルからの読み込みを試みます。")

    # ローカルからの読み込み
    try:
        local_path = relative_path.replace("/", os.sep)
        # Windowsの絶対パスに展開するためのローカルパス解決
        # 親ディレクトリなどが存在するか確認して安全に開く
        if os.path.exists(local_path):
            with open(local_path, "r", encoding="utf-8") as f:
                content = f.read()
            print(f"ローカルから読み込み成功: {local_path}")
            return content
    except Exception as e:
        print(f"ローカルからの読み込みにも失敗しました ({relative_path}): {e}")

    return default_content


def fetch_rss_feeds_by_category(category_name, drive_client):
    """
    指定されたカテゴリー（分野名）に対応するRSSフィードを 02_情報リサーチ/rss_feeds.txt から読み込み、
    最新記事をパースして文字列として返します。
    """
    try:
        # ローカル・フォールバック付きで rss_feeds.txt を読み込む
        rss_content = read_file_with_local_fallback(
            drive_client, 
            "02_情報リサーチ/rss_feeds.txt", 
            default_content=""
        )
        if not rss_content:
            print(f"警告: rss_feeds.txt の中身が空か存在しません。RSSリサーチをスキップします。")
            return "直近で取得可能なRSS記事はありませんでした。"
        
        urls = []
        for line in rss_content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                cat, url = line.split("=", 1)
                if cat.strip() == category_name:
                    urls.append(url.strip())
                    
        if not urls:
            print(f"[{category_name}] カテゴリーに対応するRSSフィードURLが定義されていません。")
            return "直近で取得可能なRSS記事はありませんでした。"
            
        print(f"[{category_name}] RSSフィードから収集を開始します: {len(urls)} 件")
        
        articles = []
        for url in urls:
            try:
                req = urllib.request.Request(
                    url, 
                    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                )
                with urllib.request.urlopen(req, timeout=10) as response:
                    xml_data = response.read()
                    
                root = ET.fromstring(xml_data)
                
                # RSS 2.0 (channel -> item) のパース
                channel = root.find('channel')
                if channel is not None:
                    for item in channel.findall('item'):
                        title = item.findtext('title', '').strip()
                        link = item.findtext('link', '').strip()
                        desc = item.findtext('description', '').strip()
                        pub_date = item.findtext('pubDate', '').strip()
                        
                        desc = re.sub(r'<[^>]*>', '', desc)
                        if len(desc) > 200:
                            desc = desc[:200] + "..."
                            
                        articles.append({
                            'title': title,
                            'link': link,
                            'description': desc,
                            'pubDate': pub_date
                        })
                else:
                    # Atom (feed -> entry) のパース
                    entries = root.findall('.//{http://www.w3.org/2005/Atom}entry')
                    if not entries:
                        entries = root.findall('.//entry')
                        
                    for entry in entries:
                        title_elem = entry.find('{http://www.w3.org/2005/Atom}title') or entry.find('title')
                        title = title_elem.text.strip() if title_elem is not None else ""
                        
                        link_elem = entry.find('{http://www.w3.org/2005/Atom}link') or entry.find('link')
                        link = ""
                        if link_elem is not None:
                            link = link_elem.attrib.get('href', '').strip()
                            
                        summary_elem = entry.find('{http://www.w3.org/2005/Atom}summary') or entry.find('{http://www.w3.org/2005/Atom}content') or entry.find('summary') or entry.find('content')
                        desc = summary_elem.text.strip() if summary_elem is not None else ""
                        desc = re.sub(r'<[^>]*>', '', desc)
                        if len(desc) > 200:
                            desc = desc[:200] + "..."
                            
                        pub_elem = entry.find('{http://www.w3.org/2005/Atom}published') or entry.find('{http://www.w3.org/2005/Atom}updated') or entry.find('published') or entry.find('updated')
                        pub_date = pub_elem.text.strip() if pub_elem is not None else ""
                        
                        articles.append({
                            'title': title,
                            'link': link,
                            'description': desc,
                            'pubDate': pub_date
                        })
            except Exception as ex:
                print(f"[{category_name}] RSS取得・パースエラー ({url}): {ex}")
                
        if not articles:
            return "直近で取得可能なRSS記事はありませんでした。"
            
        rss_text = ""
        for idx, art in enumerate(articles[:10]):  # 最大10件
            rss_text += f"[{idx+1}] タイトル: {art['title']}\n"
            rss_text += f"    ソースURL: {art['link']}\n"
            rss_text += f"    公開日時: {art['pubDate']}\n"
            rss_text += f"    要約: {art['description']}\n\n"
            
        return rss_text
    except Exception as e:
        print(f"[{category_name}] fetch_rss_feeds_by_category で想定外のエラー: {e}")
        return "直近で取得可能なRSS記事はありませんでした。"


def clean_emoji_and_symbols(text):
    """テキストから絵文字および装飾絵文字記号を完全に排除する"""
    emoji_pattern = re.compile(
        r'[\u2600-\u27BF]|'  
        r'[\uE000-\uF8FF]|'  
        r'\uD83C[\uDF00-\uDFFF]|'  
        r'\uD83D[\uDC00-\uDFFF]|'  
        r'[\u2011-\u26FF]|'  
        r'\uD83E[\uDD10-\uDDFF]',  
        flags=re.UNICODE
    )
    return emoji_pattern.sub('', text)

def main():
    if not ROOT_FOLDER_ID or not GEMINI_API_KEY:
        print("エラー: 必要な環境変数が設定されていません。")
        sys.exit(1)

    drive = TandyDriveClient()
    
    # サービスアカウントのゴミ箱クリア＆容量確認
    drive.empty_trash_and_show_quota()
    
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    
    # 日本時間 (UTC+9) の日付を明示的に取得して使用
    jst = datetime.timezone(datetime.timedelta(hours=9))
    today_str = datetime.datetime.now(jst).strftime("%Y年%m月%d日")

    # watchlist.txt 読み込み
    print("watchlist.txt を読み込み中...")
    watchlist_content = read_file_with_local_fallback(drive, "02_情報リサーチ/watchlist.txt")
    if not watchlist_content:
        raise FileNotFoundError("02_情報リサーチ/watchlist.txt が見つかりません。")
    print("watchlist.txt 読み込み完了。")

    # 記者・編集長・監査役の定義ファイル読み込み
    reporters = {
        "japan":       "08_出版事業部/専属記者/reporter_japan.md",
        "global":      "08_出版事業部/専属記者/reporter_global.md",
        "ai":          "08_出版事業部/専属記者/reporter_ai.md",
        "infra":       "08_出版事業部/専属記者/reporter_infra.md",
        "spurs":       "08_出版事業部/専属記者/reporter_spurs.md",
        "premier":     "08_出版事業部/専属記者/reporter_premier.md",
        "europe":      "08_出版事業部/専属記者/reporter_europe.md",
        "serendipity": "08_出版事業部/専属記者/reporter_serendipity.md"
    }
    reporter_instructions = {}
    for name, path in reporters.items():
        reporter_instructions[name] = read_file_with_local_fallback(
            drive, 
            path, 
            default_content=f"あなたは{name}担当の記者です。"
        )
        print(f"{name} 記者定義ファイル読み込み完了。")

    editor_instruction = read_file_with_local_fallback(
        drive, 
        "08_出版事業部/editor_agent.md", 
        default_content="あなたは総合編集長です。"
    )

    auditor_instruction = read_file_with_local_fallback(
        drive, 
        "05_法務監査/auditor_agent.md", 
        default_content="あなたはコンプライアンス監査役です。"
    )

    # リサーチ部門の指示書読み込み
    research_instruction = read_file_with_local_fallback(
        drive, 
        "02_情報リサーチ/research_agent.md", 
        default_content="あなたは優秀なリサーチ・エージェントです。"
    )
    print("research_agent.md 読み込み完了。")

    # 8名の記者による執筆 (リサーチエージェントとのバトンリレー構造)
    articles = {}
    print("\n--- ニュースレター作成プロセス（リサーチ ➔ 執筆 のバトンリレー）を開始します ---")
    for name, instruction in reporter_instructions.items():
        print(f"\n[{name} 分野] リサーチエージェントがファクト調査中...")
        
        # RSSフィードから事実データを取得
        rss_data = fetch_rss_feeds_by_category(name, drive)
        
        research_prompt = (
            f"本日の日付は {today_str} です。\n"
            f"【最優先リサーチ対象キーワード】:\n{watchlist_content}\n"
            f"担当分野: {name}\n\n"
            f"【RSSフィードから収集された確実な事実ソース】:\n{rss_data}\n\n"
            "あなたの役割定義に従い、この分野および最優先キーワードに関する最新重要ニュースや事実データを調査し、"
            "客観的な事実と情報ソースURL（Sources）および記事タイトルのみを詳細にまとめた『リサーチレポート』を作成してください。\n"
            "【優先リサーチ指示】:\n"
            "1. 上記の『RSSフィードから収集された確実な事実ソース』の中に該当分野に関連するニュースがある場合は、その情報を最優先してレポートを作成してください。\n"
            "2. レポート内の各事実に対し、必ずRSSフィードから提供されたソースURL（元のリンク）および記事のタイトルを明記してください。\n"
            "3. Google Searchは、RSSフィードに関連ニュースが不足している場合の補助調査（またはRSSソースの裏付け・詳細化）として使用してください。\n"
            "4. 推測やハルシネーション（事実の捏造）は一切含めないでください。\n"
            "【重要規約】: レポート内において、絵文字やシンボルマーク（✅や🚀など）は一切使用しないでください。"
        )
        
        research_report = ""
        try:
            research_response = gemini_client.models.generate_content(
                model='gemini-2.5-pro',
                contents=research_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=research_instruction,
                    temperature=0.2,  # ファクト調査のため低めのTemperatureで堅実に
                    tools=[{"google_search": {}}]
                ),
            )
            research_report = clean_emoji_and_symbols(research_response.text)
            print(f"[{name} 分野] リサーチレポート作成完了。")
        except Exception as ex:
            research_report = f"【エラー】リサーチ中にエラーが発生しました: {ex}"
            print(f"[{name} 分野] リサーチエラー: {ex}")

        print(f"[{name} 分野] 記者が執筆中...")
        reporter_prompt = (
            f"本日の日付は {today_str} です。\n"
            f"【最優先リサーチ対象キーワード】:\n{watchlist_content}\n\n"
            f"【リサーチ部門からの確定事実レポート】:\n{research_report}\n\n"
            "上記の確定事実レポートおよび最優先キーワードに基づき、あなたの役割定義に従って、"
            "詳細に記事を執筆してください。\n"
            "【最重要指示（情報量の増強）】:\n"
            "1. 1つのトピック（見出し）あたりの情報量を大幅に増やし、背景、詳細な事実、将来的な影響、およびリサーチレポートで明記されたソースURL（Sources）と記事タイトルを、読者が納得できるよう詳しく長文で記述してください。\n"
            "2. 単なる要約で終わらせず、非常に読み応えのある知的なオピニオン記事として深く論述してください。\n"
            "3. 各トピックには、個別に 'Tandy's Insight' を記述してください。インサイトの構成やトーンは従来通り（1〜2行のビジネス影響分析）で問題ありません。\n"
            "4. 必ずリサーチレポートに記載されている事実に基づき、ハルシネーション（事実の捏造）を決して行わないでください。\n"
            "【重要規約】: 本文および見出しにおいて、絵文字やシンボルマーク（✅や🚀など）は一切使用しないでください。"
            "また、毎朝読むCEOが今日一日前向きで知的なエネルギーに満ちあふれるよう、"
            "客観的かつ建設的で、自己肯定感の高まる高尚な文体で論述してください。"
        )
        try:
            response = gemini_client.models.generate_content(
                model='gemini-2.5-pro',
                contents=reporter_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=instruction,
                    temperature=0.7,  # 表現を豊かにするため執筆は高めのTemperature
                ),
            )
            articles[name] = clean_emoji_and_symbols(response.text)
            print(f"[{name} 分野] 記者 執筆完了。")
        except Exception as ex:
            articles[name] = f"【エラー】{name}記者の執筆中にエラーが発生しました: {ex}"
            print(f"[{name} 分野] 記者 執筆エラー: {ex}")

    # 編集長によるパッケージング
    print("\n--- 編集長がパッケージング中 ---")
    editor_prompt = (
        f"本日の日付は {today_str} です。8名の記者から以下の原稿が届きました。\n"
        f"【国内政治・経済】{articles.get('japan','')}\n"
        f"【国際情勢・世界経済】{articles.get('global','')}\n"
        f"【AI・テクノロジー】{articles.get('ai','')}\n"
        f"【通信インフラ】{articles.get('infra','')}\n"
        f"【トッテナム・Spurs】{articles.get('spurs','')}\n"
        f"{articles.get('premier','')}\n"
        f"【欧州リーグ】{articles.get('europe','')}\n"
        f"【宇宙・深海・科学】{articles.get('serendipity','')}\n"
        "全体のトーンを統一し、表紙（ヘッドラインリード・目次）と編集長社説を追加して、"
        "美しいMarkdown形式の朝刊（Tandy Times）を完成させてください。"
        "【重要規約】: 絵文字や装飾記号は一切使用しないでください。"
        "知的な高揚感と、読者（CEO）のモチベーション・自己肯定感を大きく高める社説と見出しを構成してください。"
    )
    draft = gemini_client.models.generate_content(
        model='gemini-2.5-pro', contents=editor_prompt,
        config=types.GenerateContentConfig(system_instruction=editor_instruction, temperature=0.7)
    ).text
    draft = clean_emoji_and_symbols(draft)
    print("編集長パッケージング完了。")

    # URL生存チェック
    link_report = "### 生存リンクチェックログ\n"
    for url in set(re.findall(r'https?://[^\s\)\],`"]+', draft)):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as conn:
                link_report += f"* {url} : 生存確認完了 ({conn.getcode()} OK)\n"
        except Exception as ex:
            link_report += f"* {url} : 警告 - アクセス失敗 ({ex})\n"

    # Compliance監査 (絵文字排除 ＆ 2026年日付 of 厳密化 ＆ ガチ監査)
    print("\n--- Compliance監査中 ---")
    auditor_prompt = (
        "あなたはTandy.incの法務監査・コンプライアンス監査役です。\n"
        f"本日の正確な日付は {today_str}（2026年）です。この日付を絶対的な基準として、以下の朝刊（初稿）の内容に、事実誤認や不確かな情報（ハルシネーション）がないか、"
        "また過去のニュースの混入がないかを、あなたの監査基準に従って厳格にチェックし、必要であれば修正した最終稿を出力してください。\n"
        f"また、以下のURL検証ログを監査し、リンク切れなどの警告があれば、必要に応じて修正または注記を追加してください。\n"
        f"【URL検証ログ】:\n{link_report}\n\n"
        f"【朝刊初稿】:\n{draft}\n\n"
        "最後に、朝刊ドラフトの末尾にあなたの監査レポートをドッキングした最終版を出力してください。\n"
        "【重要規約】: 本文および見出し、監査レポートを含め、絵文字やシンボルマークは一切使用しないでください。"
    )
    final = gemini_client.models.generate_content(
        model='gemini-2.5-pro', contents=auditor_prompt,
        config=types.GenerateContentConfig(system_instruction=auditor_instruction, temperature=0.2)
    ).text
    final = clean_emoji_and_symbols(final)
    print("Compliance監査完了。")

    # Googleドライブへ自動アーカイブ ＆ 上書き美装納品
    print("\n--- Googleドライブへ朝刊をアーカイブ ＆ 納品中 ---")
    newsletters_folder_id = drive.get_folder_id_by_path("Outputs/newsletters")
    if not newsletters_folder_id:
        raise FileNotFoundError("Outputs/newsletters フォルダが見つかりません。")

    file_id = drive.archive_and_update_newsletter(newsletters_folder_id, final)
    print(f"✅ 朝刊の納品完了！ (ID: {file_id})")
    print(f"   本日付: {today_str}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        tb = traceback.format_exc()
        print("\n!!! ERROR DETAILS IN CLOUD !!!")
        print(tb)
        sys.exit(1)
