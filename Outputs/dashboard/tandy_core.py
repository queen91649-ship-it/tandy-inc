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
        query = f"'{folder_id}' in parents and name contains 'latest_newsletter' and trashed = false"
        results = self.service.files().list(q=query, fields='files(id, name)').execute()
        files = results.get('files', [])

        if not files:
            raise FileNotFoundError("latest_newsletter が見つかりません。")

        latest_id = files[0]['id']
        
        jst = datetime.timezone(datetime.timedelta(hours=9))
        archive_name = f"{datetime.datetime.now(jst).strftime('%Y%m%d')}_newsletter.md"
        local_dir = "Outputs/newsletters"
        os.makedirs(local_dir, exist_ok=True)
        local_path = os.path.join(local_dir, archive_name)
        with open(local_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"ローカルアーカイブにニュースレターを保存しました: {local_path}")

        print("最新ニュースレターを上書き更新 ＆ 知的フォーマット整形中...")
        self.write_and_format_google_doc(latest_id, content)
        return latest_id

    def write_and_format_google_doc(self, document_id, markdown_text):
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

    def empty_trash_and_show_quota(self):
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
        print(f"\n--- 古いアーカイブのクリーンアップ (過去 {keep_days} 日分を保持) ---")
        try:
            query = f"'{folder_id}' in parents and name contains '_newsletter' and trashed = false"
            results = self.service.files().list(q=query, orderBy="name desc", fields='files(id, name, createdTime)').execute()
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


def clean_emoji_and_symbols(text):
    emoji_pattern = re.compile(
        r'[\u2600-\u27BF]|[\uE000-\uF8FF]|\uD83C[\uDF00-\uDFFF]|\uD83D[\uDC00-\uDFFF]|[\u2011-\u26FF]|\uD83E[\uDD10-\uDDFF]',
        flags=re.UNICODE
    )
    return emoji_pattern.sub('', text)

def main():
    if not ROOT_FOLDER_ID or not GEMINI_API_KEY:
        print("エラー: 必要な環境変数が設定されていません。")
        sys.exit(1)

    drive = TandyDriveClient()
    drive.empty_trash_and_show_quota()
    
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    
    jst = datetime.timezone(datetime.timedelta(hours=9))
    today_str = datetime.datetime.now(jst).strftime("%Y年%m月%d日")

    # 1. watchlist.txt の確実な読み込み
    print("watchlist.txt を読み込み中...")
    watchlist_id = drive.find_file_id_by_path("02_情報リサーチ/watchlist.txt")
    if not watchlist_id:
        raise FileNotFoundError("02_情報リサーチ/watchlist.txt が見つかりません。")
    watchlist_content = drive.read_file_content(watchlist_id)
    print("watchlist.txt 読み込み完了。")

    # 2. 定義ファイルの読み込み
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
        fid = drive.find_file_id_by_path(path)
        reporter_instructions[name] = drive.read_file_content(fid) if fid else f"あなたは{name}担当の記者です。"
        print(f"{name} 記者定義ファイル読み込み完了。")

    editor_id = drive.find_file_id_by_path("08_出版事業部/editor_agent.md")
    editor_instruction = drive.read_file_content(editor_id) if editor_id else "あなたは総合編集長です。"

    auditor_id = drive.find_file_id_by_path("05_法務監査/auditor_agent.md")
    auditor_instruction = drive.read_file_content(auditor_id) if auditor_id else "あなたはコンプライアンス監査役です。"

    # 3. 8名の記者による執筆（CEO指示書「watchlist」をインプットに注入）
    articles = {}
    print("\n--- 8名の記者が執筆を開始します ---")
    for name, instruction in reporter_instructions.items():
        print(f"{name} 記者 執筆中...")
        prompt = (
            f"本日の日付は {today_str} です。\n\n"
            f"【最優先リサーチ・執筆対象（CEO関心キーワード）】:\n{watchlist_content}\n\n" # ←バグ修正：指示書を確実に注入
            "あなたの役割定義（system_instruction）に従い、上記キーワードおよび担当領域に関連する直近24時間の重要トピックを必ず3件以上選定し、"
            "詳細に執筆してください。各トピックには個別に 'Tandy's Insight' を記述してください。"
            "Google Searchで最新情報を収集してから執筆してください。"
            "【重要規約】: 本文および見出しにおいて、絵文字やシンボルマーク（✅や🚀など）は一切使用しないでください。"
            "また、毎朝読むCEOが今日一日前向きで知的なエネルギーに満ちあふれるよう、"
            "客観的かつ建設的で、自己肯定感の高まる高尚な文体で論述してください。"
        )
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
            articles[name] = clean_emoji_and_symbols(response.text)
            print(f"{name} 記者 執筆完了。")
        except Exception as ex:
            articles[name] = f"【エラー】{name}記者の執筆中にエラーが発生しました: {ex}"
            print(f"{name} 記者 エラー: {ex}")

    # 4. 編集長によるパッケージング（初稿作成）
    print("\n--- 編集長がパッケージング中 ---")
    editor_prompt = (
        f"本日の日付は {today_str} です。8名の記者から以下の原稿が届きました。\n\n"
        f"【国内政治・経済】\n{articles.get('japan','')}\n\n"
        f"【国際情勢・世界経済】\n{articles.get('global','')}\n\n"
        f"【AI・テクノロジー】\n{articles.get('ai','')}\n\n"
        f"【通信インフラ】\n{articles.get('infra','')}\n\n"
        f"【トッテナム・Spurs】\n{articles.get('spurs','')}\n\n"
        f"【プレミアリーグ】\n{articles.get('premier','')}\n\n"
        f"【欧州リーグ】\n{articles.get('europe','')}\n\n"
        f"【宇宙・深海・科学】\n{articles.get('serendipity','')}\n\n"
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

    # 5. システムによるURL生存チェック（プログラム監査）
    print("\n--- 掲載URLの生存チェックを実行中 ---")
    link_report = "### 生存リンクチェックログ\n"
    urls = set(re.findall(r'https?://[^\s)\]"\']+', draft))
    for url in urls:
        url = url.rstrip('.,;*')
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                status = response.getcode()
                link_report += f"- ✅ {url} (Status: {status})\n"
        except Exception as e:
            link_report += f"- ❌ {url} (Error: {e})\n"
    print("URL生存チェック完了。")

    # 6. バグ修正：法務監査役（Compliance）によるAIガチ監査の統合
    print("\n--- コンプライアンス監査役によるファクトチェック ＆ 修正中 ---")
    auditor_prompt = (
        "あなたはTandy.incの法務監査・コンプライアンス監査役です。あなたの役割定義（system_instruoregroundColor,fontSize,bold'
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
    watchlist_id = drive.find_file_id_by_path("02_情報リサーチ/watchlist.txt")
    if not watchlist_id:
        raise FileNotFoundError("02_情報リサーチ/watchlist.txt が見つかりません。")
    watchlist_content = drive.read_file_content(watchlist_id)
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
        fid = drive.find_file_id_by_path(path)
        reporter_instructions[name] = drive.read_file_content(fid) if fid else f"あなたは{name}担当の記者です。"
        print(f"{name} 記者定義ファイル読み込み完了。")

    editor_id = drive.find_file_id_by_path("08_出版事業部/editor_agent.md")
    editor_instruction = drive.read_file_content(editor_id) if editor_id else "あなたは総合編集長です。"

    auditor_id = drive.find_file_id_by_path("05_法務監査/auditor_agent.md")
    auditor_instruction = drive.read_file_content(auditor_id) if auditor_id else "あなたはコンプライアンス監査役です。"

    # 8名の記者による執筆
    articles = {}
    print("\n--- 8名の記者が執筆を開始します ---")
    for name, instruction in reporter_instructions.items():
        print(f"{name} 記者 執筆中...")
        prompt = (
            f"本日の日付は {today_str} です。"
            "あなたの役割定義に従い、直近24時間における重要トピックを必ず3件以上選定し、"
            "詳細に執筆してください。各トピックには個別に 'Tandy's Insight' を記述してください。"
            "Google Searchで最新情報を収集してから執筆してください。"
            "【重要規約】: 本文および見出しにおいて、絵文字やシンボルマーク（✅や🚀など）は一切使用しないでください。"
            "また、毎朝読むCEOが今日一日前向きで知的なエネルギーに満ちあふれるよう、"
            "客観的かつ建設的で、自己肯定感の高まる高尚な文体で論述してください。"
        )
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
            articles[name] = clean_emoji_and_symbols(response.text)
            print(f"{name} 記者 執筆完了。")
        except Exception as ex:
            articles[name] = f"【エラー】{name}記者の執筆中にエラーが発生しました: {ex}"
            print(f"{name} 記者 エラー: {ex}")

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

    # Compliance監査 (絵文字排除 ＆ 2026年日付 of 厳密化)
    print("\n--- Compliance監査中 ---")
    compliance_prompt = (
        f"編集長から朝刊ドラフトが届きました。\n【朝刊ドラフト】{draft}\n"
        f"本日の正確な日付は {today_str}（2026年）です。この日付を絶対的な基準として、記述されている各ニュースのファクトや年（2024年などの過去ニュースの混入）にハルシネーションがないかを検証してください。\n"
        f"また、以下のURL検証ログと合わせて監査レポートを作成してください。\n"
        f"【URLログ】{link_report}\n"
        "最後に朝刊ドラフトの末尾に監査レポートをドッキングした最終版を書き出してください。\n"
        "【重要規約】: 絵文字は一切使用しないでください。"
    )
    final = gemini_client.models.generate_content(
        model='gemini-2.5-pro', contents=compliance_prompt,
        config=types.GenerateContentConfig(system_instruction=auditor_instruction, temperature=0.7)
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
