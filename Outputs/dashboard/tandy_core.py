import os
import sys
import datetime
import traceback
import urllib.request
import re
import xml.etree.ElementTree as ET
import email.utils
import asyncio
import io

if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

try:
    from google.auth import default
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    from google.antigravity import Agent, LocalAgentConfig, CapabilitiesConfig
except ImportError as e:
    print(f"Error: Missing dependency. {e}")
    sys.exit(1)

ROOT_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_ROOT_FOLDER_ID", "1YM7t5t-1XOo2Pi_wX7JUEaROxjJ6wl6M")

class TandyDriveClient:
    def __init__(self):
        self.service = None
        self.docs_service = None
        self.root_id = ROOT_FOLDER_ID
        try:
            credentials, project = default(scopes=[
                'https://www.googleapis.com/auth/drive',
                'https://www.googleapis.com/auth/documents'
            ])
            self.credentials = credentials
            self.service = build('drive', 'v3', credentials=credentials)
            self.docs_service = build('docs', 'v1', credentials=credentials)
            print(f"Google Drive & Docs Web API 接続成功。ルートID: {self.root_id}")
        except Exception as e:
            print(f"【お知らせ】Google Cloud Web API 認証情報が見つからないため、ローカル同期モード（Markdown直接書き出し）で稼働します。({e})")

    def find_file_id_by_path(self, relative_path, parent_id=None):
        if not self.service:
            return None
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
        if not self.service:
            return None
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
        if not self.service:
            return ""
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
        ローカルの Outputs/newsletters/ 内にMarkdownとしてアーカイブを出力し、
        Web API接続が有効な場合のみ Google Docs (latest_newsletter) を Docs API で上書き更新する。
        """
        # 1. ローカルに日付付きMarkdownでアーカイブを保存（Google Drive デスクトップアプリが自動でクラウドに同期します）
        jst = datetime.timezone(datetime.timedelta(hours=9))
        archive_name = f"{datetime.datetime.now(jst).strftime('%Y%m%d')}_newsletter.md"
        local_dir = "Outputs/newsletters"
        os.makedirs(local_dir, exist_ok=True)
        local_path = os.path.join(local_dir, archive_name)
        with open(local_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"ローカルアーカイブにニュースレターを保存しました: {local_path}")

        # 2. Web API が接続されている場合のみ Docs 側も上書き美装更新
        if self.service and self.docs_service:
            try:
                # 既存の latest_newsletter を検索
                query = f"'{folder_id}' in parents and name contains 'latest_newsletter' and trashed = false"
                results = self.service.files().list(q=query, fields='files(id, name)').execute()
                files = results.get('files', [])

                if files:
                    latest_id = files[0]['id']
                    print("最新ニュースレターを上書き更新 ＆ 知的フォーマット整形中...")
                    self.write_and_format_google_doc(latest_id, content)
                    return latest_id
            except Exception as e:
                print(f"警告: Google Docs (latest_newsletter) の更新に失敗しました: {e}")
        else:
            print("Google Docs (latest_newsletter) の更新はローカル同期モードのためスキップされました。")
        return None

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
                        'paragraphStyle': {'namedStyleType': 'HEADING_2'},
                        'fields': 'namedStyleType'
                    }
                })
                style_requests.append({
                    'updateTextStyle': {
                        'range': {'startIndex': start, 'endIndex': end - 1},
                        'textStyle': {
                            'foregroundColor': {'color': {'rgbColor': {'blue': 0.25, 'green': 0.25, 'red': 0.25}}},
                            'fontSize': {'magnitude': 16, 'unit': 'PT'},
                            'bold': True
                        },
                        'fields': 'foregroundColor,fontSize,bold'
                    }
                })
            elif action == 'HEADING_3':
                style_requests.append({
                    'updateParagraphStyle': {
                        'range': {'startIndex': start, 'endIndex': end},
                        'paragraphStyle': {'namedStyleType': 'HEADING_3'},
                        'fields': 'namedStyleType'
                    }
                })
                style_requests.append({
                    'updateTextStyle': {
                        'range': {'startIndex': start, 'endIndex': end - 1},
                        'textStyle': {
                            'foregroundColor': {'color': {'rgbColor': {'blue': 0.38, 'green': 0.38, 'red': 0.38}}},
                            'fontSize': {'magnitude': 13, 'unit': 'PT'},
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
                            'foregroundColor': {'color': {'rgbColor': {'blue': 0.1, 'green': 0.5, 'red': 0.1}}},
                            'bold': True,
                            'italic': True
                        },
                        'fields': 'foregroundColor,bold,italic'
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
                            'foregroundColor': {'color': {'rgbColor': {'blue': 0.7, 'green': 0.7, 'red': 0.7}}},
                            'fontSize': {'magnitude': 10, 'unit': 'PT'}
                        },
                        'fields': 'foregroundColor,fontSize'
                    }
                })

        if style_requests:
            self.docs_service.documents().batchUpdate(documentId=document_id, body={'requests': style_requests}).execute()

    def empty_trash_and_show_quota(self):
        """サービスアカウントのゴミ箱クリアまたはローカルアーカイブの30日クリーンアップを行う"""
        if not self.service:
            print("ローカル同期モードのため、GCP容量チェックはスキップされました。")
            # ローカルの30日クリーンアップのみ実行
            try:
                local_dir = "Outputs/newsletters"
                if os.path.exists(local_dir):
                    now = datetime.datetime.now(datetime.timezone.utc)
                    deleted_count = 0
                    for f in os.listdir(local_dir):
                        if f.endswith("_newsletter.md"):
                            f_path = os.path.join(local_dir, f)
                            created_time = datetime.datetime.fromtimestamp(os.path.getctime(f_path), datetime.timezone.utc)
                            if (now - created_time).days > 30:
                                os.remove(f_path)
                                deleted_count += 1
                    if deleted_count > 0:
                        print(f"ローカルの30日以上古いアーカイブを {deleted_count} 件削除しました。")
            except Exception as e:
                print(f"ローカルクリーンアップエラー: {e}")
            return

        try:
            print("=== GCP容量チェック・ゴミ箱クリーンアップ ===")
            about = self.service.about().get(fields="storageQuota").execute()
            quota = about.get('storageQuota', {})
            limit = int(quota.get('limit', 0))
            usage = int(quota.get('usage', 0))
            
            pct = (usage / limit * 100) if limit > 0 else 0
            print(f"ストレージ使用状況: {usage / (1024*1024):.2f} MB / {limit / (1024*1024):.2f} MB ({pct:.2f}%)")
            
            self.service.files().emptyTrash().execute()
            print("Google Drive ゴミ箱をクリアしました。")
            
            # 30日クリーンアップ
            newsletters_folder_id = self.get_folder_id_by_path("Outputs/newsletters")
            if newsletters_folder_id:
                query = f"'{newsletters_folder_id}' in parents and name contains '_newsletter.md' and trashed = false"
                results = self.service.files().list(q=query, fields='files(id, name, createdTime)').execute()
                files = results.get('files', [])
                
                now = datetime.datetime.now(datetime.timezone.utc)
                deleted_count = 0
                for f in files:
                    created_time_str = f.get('createdTime', '')
                    if created_time_str:
                        created_time = datetime.datetime.fromisoformat(created_time_str.replace('Z', '+00:00'))
                        if (now - created_time).days > 30:
                            self.service.files().delete(fileId=f['id']).execute()
                            deleted_count += 1
                if deleted_count > 0:
                    print(f"Drive上の30日以上古いアーカイブを {deleted_count} 件削除しました。")
        except Exception as e:
            print(f"容量チェックまたはクリーンアップに失敗しました: {e}")


def read_file_with_local_fallback(drive_client, relative_path, default_content=None):
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
        if os.path.exists(local_path):
            with open(local_path, "r", encoding="utf-8") as f:
                content = f.read()
            print(f"ローカルから読み込み成功: {local_path}")
            return content
    except Exception as e:
        print(f"ローカルからの読み込みにも失敗しました ({relative_path}): {e}")

    return default_content


def parse_rss_date(date_str):
    if not date_str:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt
    except Exception:
        pass
    try:
        clean_str = date_str.replace('Z', '+00:00')
        dt = datetime.datetime.fromisoformat(clean_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt
    except Exception:
        pass
    return None


def fetch_rss_feeds_by_category(category_name, drive_client):
    """
    指定されたカテゴリー（分野名）に対応するRSSフィードを 02_情報リサーチ/rss_feeds.txt から読み込み、
    過去24時間（最大48時間）の最新記事をパースして文字列として返します。
    """
    try:
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
        
        now = datetime.datetime.now(datetime.timezone.utc)
        limit_hours = 48
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
                
                channel = root.find('channel')
                if channel is not None:
                    for item in channel.findall('item'):
                        title = item.findtext('title', '').strip()
                        link = item.findtext('link', '').strip()
                        desc = item.findtext('description', '').strip()
                        pub_date = item.findtext('pubDate', '').strip()
                        
                        dt = parse_rss_date(pub_date)
                        if dt:
                            diff = now - dt
                            if diff.total_seconds() > limit_hours * 3600:
                                continue
                                
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
                            
                        pub_elem = entry.find('{http://www.w3.org/2005/Atom}published') or entry.find('{http://www.w3.org/2005/Atom}updated') or entry.find('published') or entry.find('updated')
                        pub_date = pub_elem.text.strip() if pub_elem is not None else ""
                        
                        dt = parse_rss_date(pub_date)
                        if dt:
                            diff = now - dt
                            if diff.total_seconds() > limit_hours * 3600:
                                continue
                                
                        summary_elem = entry.find('{http://www.w3.org/2005/Atom}summary') or entry.find('{http://www.w3.org/2005/Atom}content') or entry.find('summary') or entry.find('content')
                        desc = summary_elem.text.strip() if summary_elem is not None else ""
                        desc = re.sub(r'<[^>]*>', '', desc)
                        if len(desc) > 200:
                            desc = desc[:200] + "..."
                            
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
        for idx, art in enumerate(articles[:10]):
            rss_text += f"[{idx+1}] タイトル: {art['title']}\n"
            rss_text += f"    ソースURL: {art['link']}\n"
            rss_text += f"    公開日時: {art['pubDate']}\n"
            rss_text += f"    要約: {art['description']}\n\n"
            
        return rss_text
    except Exception as e:
        print(f"[{category_name}] fetch_rss_feeds_by_category で想定外のエラー: {e}")
        return "直近で取得可能なRSS記事はありませんでした。"


def clean_emoji_and_symbols(text):
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


async def run_agent(system_instruction, prompt, enable_search=False):
    """
    Antigravity SDK (google-antigravity) を介して、
    ローカルアプリセッション経由の完全無料（0円）でGeminiを非同期実行します。
    """
    capabilities = CapabilitiesConfig()
    config = LocalAgentConfig(
        system_instructions=system_instruction,
        capabilities=capabilities
    )
    async with Agent(config) as agent:
        response = await agent.chat(prompt)
        content = ""
        async for token in response:
            content += token
        return content


async def main():
    drive = TandyDriveClient()
    
    # ゴミ箱クリア＆容量確認
    drive.empty_trash_and_show_quota()
    
    # 日本時間 (UTC+9) の日付を取得
    jst = datetime.timezone(datetime.timedelta(hours=9))
    today_str = datetime.datetime.now(jst).strftime("%Y年%m月%d日")

    # watchlist.txt 読み込み
    print("watchlist.txt を読み込み中...")
    watchlist_content = read_file_with_local_fallback(drive, "02_情報リサーチ/watchlist.txt")
    if not watchlist_content:
        raise FileNotFoundError("02_情報リサーチ/watchlist.txt が見つかりません。")
    print("watchlist.txt 読み込み完了。")

    # 4つの統合された記者定義ファイルの読み込みとマージ
    reporter_groups = {
        "politics_economy": [
            "08_出版事業部/専属記者/reporter_japan.md", 
            "08_出版事業部/専属記者/reporter_global.md"
        ],
        "ai_tech": [
            "08_出版事業部/専属記者/reporter_ai.md", 
            "08_出版事業部/専属記者/reporter_infra.md"
        ],
        "sports": [
            "08_出版事業部/専属記者/reporter_spurs.md", 
            "08_出版事業部/専属記者/reporter_premier.md", 
            "08_出版事業部/専属記者/reporter_europe.md"
        ],
        "serendipity": [
            "08_出版事業部/専属記者/reporter_serendipity.md"
        ]
    }
    
    reporter_instructions = {}
    for name, paths in reporter_groups.items():
        combined_text = ""
        for path in paths:
            content = read_file_with_local_fallback(drive, path, default_content="")
            if content:
                combined_text += content + "\n\n"
        if not combined_text:
            combined_text = f"あなたは{name}分野担当の記者です。"
        reporter_instructions[name] = combined_text
        print(f"[{name}] 記者定義マージ完了。")

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

    # 4名の記者による執筆
    articles = {}
    print("\n--- ニュースレター作成プロセス（RSS -> 執筆 のバトンリレー）を開始します ---")
    for name, instruction in reporter_instructions.items():
        print(f"\n[{name} 分野] RSSフィードから最新ニュースを収集中...")
        rss_data = fetch_rss_feeds_by_category(name, drive)
        
        reporter_prompt = (
            f"本日の正確な日付は {today_str} です。\n"
            f"【最優先キーワード】:\n{watchlist_content}\n\n"
            f"【RSSフィードから収集された過去24時間以内の確実な事実ソース】:\n{rss_data}\n\n"
            "あなたの役割定義（マージされた記者魂）に従って、上記の最新ニュースから最も重要なトピックを厳選し、執筆を行ってください。\n"
            "【執筆ガイドライン】:\n"
            "1. 各トピック（見出し）ごとに詳細な長文で背景、事実、将来的な影響、および引用したRSSのタイトルとソースURL（Sources）を明記してください。\n"
            "2. 単なる事実要約に留まらず、知的な価値を提供するオピニオンを含めて論述してください。\n"
            "3. 各トピックには、個別に 'Tandy's Insight'（1〜2行のビジネス視点インサイト）を必ず記述してください。\n"
            "4. 提供されたRSSソース内の事実だけを基に記述し、ハルシネーション（事実の捏造や過去の古い情報の混入）は一切行わないでください。\n"
            "【重要規約】: 本文および見出しにおいて、絵文字やシンボルマーク（✅や🚀など）は一切使用しないでください。高尚で自己肯定感の高まる文体で執筆してください。"
        )
        
        try:
            print(f"[{name} 分野] 記者が執筆中（Antigravity SDK経由）...")
            response_text = await run_agent(instruction, reporter_prompt)
            articles[name] = clean_emoji_and_symbols(response_text)
            print(f"[{name} 分野] 記者 執筆完了。")
        except Exception as ex:
            articles[name] = f"【エラー】{name}記者の執筆中にエラーが発生しました: {ex}"
            print(f"[{name} 分野] 記者 執筆エラー: {ex}")

    # 編集長によるパッケージング
    print("\n--- 編集長がパッケージング中 ---")
    editor_prompt = (
        f"本日の日付は {today_str} です。4名の記者から以下の原稿が届きました。\n"
        f"【国内外時事（政治・経済）】\n{articles.get('politics_economy','')}\n\n"
        f"【AI・テクノロジー】\n{articles.get('ai_tech','')}\n\n"
        f"【スポーツ・エンタメ】\n{articles.get('sports','')}\n\n"
        f"【サイエンス・セレンディピティ】\n{articles.get('serendipity','')}\n\n"
        "全体のトーンを統一し、表紙（ヘッドラインリード・目次）と編集長社説を追加して、"
        "美しいMarkdown形式の朝刊（Tandy Times）を完成させてください。\n"
        "【重要規約】: 絵文字や装飾記号は一切使用しないでください。"
        "知的な高揚感と、読者（CEO）のモチベーション・自己肯定感を大きく高める社説と見出しを構成してください。"
    )
    draft = await run_agent(editor_instruction, editor_prompt)
    draft = clean_emoji_and_symbols(draft)
    print("編集長パッケージング完了.")

    # URL生存チェック
    print("\n--- リンク切れチェック中 ---")
    link_report = "### 生存リンクチェックログ\n"
    for url in set(re.findall(r'https?://[^\s\)\],`"]+', draft)):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as conn:
                link_report += f"* {url} : 生存確認完了 ({conn.getcode()} OK)\n"
        except Exception as ex:
            link_report += f"* {url} : 警告 - アクセス失敗 ({ex})\n"

    # Compliance監査
    print("\n--- Compliance監査中（検索ツール付き） ---")
    auditor_prompt = (
        "あなたはTandy.incの法務監査・コンプライアンス監査役です。\n"
        f"本日の正確な日付は {today_str}（2026年）です。この日付を絶対的な基準として、以下の朝刊（初稿）の内容に、事実誤認や不確かな情報（ハルシネーション）がないか、"
        "また過去のニュースの混入がないかを、あなたの監査基準に従って厳格にチェックしてください。\n"
        "【重要】: 記載された最新ニュースや新技術について、自身の過去の知識だけに頼らず、必ずgoogle_searchツールを積極的に用いてWeb検索を行い、裏付けのある正しい事実であるか二重検証を行ってください。ソースが実在するものは誤ってハルシネーションと判定しないでください。\n"
        f"また、以下のURL検証ログを監査し、リンク切れなどの警告があれば、必要に応じて修正または注記を追加してください。\n"
        f"【URL検証ログ】:\n{link_report}\n\n"
        f"【朝刊初稿】:\n{draft}\n\n"
        "監査を行い、あなたの【監査レポート】（監査結果サマリー、ファクトチェック二重検証ログ、生存リンクチェック結果、最終判定）のみを出力してください。元の朝刊原稿を含める必要はありません。\n"
        "【重要規約】: 監査レポート内を含め、絵文字やシンボルマークは一切使用しないでください。"
    )
    audit_report = await run_agent(auditor_instruction, auditor_prompt, enable_search=True)
    audit_report = clean_emoji_and_symbols(audit_report)
    print("Compliance監査完了。")

    # 朝刊原稿と監査レポートを安全にドッキング
    final_output = (
        f"{draft}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"## 法務・信頼性監査レポート\n\n"
        f"{audit_report}"
    )

    # Googleドライブへ自動アーカイブ ＆ 上書き美装納品
    print("\n--- Googleドライブへ朝刊をアーカイブ ＆ 納品中 ---")
    newsletters_folder_id = None
    try:
        newsletters_folder_id = drive.get_folder_id_by_path("Outputs/newsletters")
    except Exception:
        pass

    file_id = drive.archive_and_update_newsletter(newsletters_folder_id, final_output)
    print(f"\n朝刊の納品完了！")
    print(f"本日付: {today_str}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        tb = traceback.format_exc()
        print("\n!!! ERROR DETAILS IN CORE !!!")
        print(tb)
        sys.exit(1)
