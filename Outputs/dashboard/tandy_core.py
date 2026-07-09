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
        """
        前回の 'latest_newsletter' を日付付きで複製コピーしてアーカイブ保存し、
        元の 'latest_newsletter' の内容を Google Docs API で上書き更新＆フォーマット整形する。
        """
        # 1. 既存の latest_newsletter を検索
        query = f"'{folder_id}' in parents and name contains 'latest_newsletter' and trashed = false"
        results = self.service.files().list(q=query, fields='files(id, name)').execute()
        files = results.get('files', [])

        if not files:
            raise FileNotFoundError("latest_newsletter が見つかりません。")

        latest_id = files[0]['id']
        
        # 2. 前日の内容を日付付きファイル名でコピー（アーカイブ）
        archive_name = f"{datetime.date.today().strftime('%Y%m%d')}_newsletter"
        print(f"前日のニュースレターをコピーアーカイブ中: {archive_name}")
        self.service.files().copy(
            fileId=latest_id,
            body={'name': archive_name}
        ).execute()

        # 3. Google Docs API を用いた本番上書き ＆ 自己肯定感が上がる美麗フォーマットの適用
        print("最新ニュースレターを上書き更新 ＆ 知的フォーマット整形中...")
        self.write_and_format_google_doc(latest_id, content)
        return latest_id

    def write_and_format_google_doc(self, document_id, markdown_text):
        """
        Google Docs API を使用して、Markdownテキストを美しい段落・見出し・装飾付きドキュメントに変換して上書きする。
        """
        # 3-A. ドキュメントの全コンテンツをクリアする
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

        # 3-B. テキストをパースし、挿入リクエストを作成する
        requests = []
        current_index = 1
        lines = markdown_text.split('\n')
        
        # フォーマット適用予定の範囲情報を格納するリスト
        formatting_actions = []

        for line in lines:
            # 見出し・区切り・箇条書きなどの解析
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
                # 美麗な水平線の代替
                divider = "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                requests.append({'insertText': {'location': {'index': current_index}, 'text': divider}})
                formatting_actions.append(('DIVIDER', current_index, current_index + len(divider)))
                current_index += len(divider)
            else:
                clean_text = line + '\n'
                requests.append({'insertText': {'location': {'index': current_index}, 'text': clean_text}})
                
                # 特定のキーワード（Tandy's Insight など）に太字や色付けを適用
                if "Tandy's Insight" in clean_text:
                    start_offset = clean_text.find("Tandy's Insight")
                    formatting_actions.append(('INSIGHT_HIGHLIGHT', current_index + start_offset, current_index + start_offset + len("Tandy's Insight")))
                
                # ボールド表記 ( **text** ) をDocsのボールド書式にパース
                bold_matches = list(re.finditer(r'\*\*(.*?)\*\*', clean_text))
                for match in bold_matches:
                    b_start = current_index + match.start()
                    b_end = current_index + match.end()
                    formatting_actions.append(('BOLD_TEXT', b_start, b_end))

                current_index += len(clean_text)

        # 3-C. テキストの挿入を実行
        if requests:
            self.docs_service.documents().batchUpdate(documentId=document_id, body={'requests': requests}).execute()

        # 挿入後の最新ドキュメントのインデックスで書式適用リクエストを再ビルド
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
                # タイトルの文字色（ダークネイビー）とサイズ
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
                # 大見出しの文字色（スチールブルー）とサイズ
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

        # 3-D. 書式の適用を実行
        if style_requests:
            try:
                self.docs_service.documents().batchUpdate(documentId=document_id, body={'requests': style_requests}).execute()
            except Exception as ex:
                print(f"書式適用で一部スキップが発生しました: {ex}")

        # 3-E. マークダウンの不要な「**」記号を消去
        replace_requests = [
            {
                'replaceAllText': {
                    'containsText': {'matchCase': True, 'text': '**'},
                    'replaceText': ''
                }
            }
        ]
        self.docs_service.documents().batchUpdate(documentId=document_id, body={'requests': replace_requests}).execute()


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
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    today_str = datetime.date.today().strftime("%Y年%m月%d日")

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
        f"【プレミアリーグ】{articles.get('premier','')}\n"
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

    # Compliance監査
    print("\n--- Compliance監査中 ---")
    compliance_prompt = (
        f"編集長から朝刊ドラフトが届きました。\n【朝刊ドラフト】{draft}\n"
        f"ハルシネーションがないかを検証し、以下のURL検証ログと合わせて監査レポートを作成してください。\n"
        f"【URLログ】{link_report}\n"
        "最後に朝刊ドラフトの末尾に監査レポートをドッキングした最終版を書き出してください。"
        "【重要規約】: 絵文字は一切使用しないでください。"
    )
    final = gemini_client.models.generate_content(
        model='gemini-2.5-pro', contents=compliance_prompt,
        config=types.GenerateContentConfig(system_instruction=auditor_instruction, temperature=0.7)
    ).text
    final = clean_emoji_and_symbols(final)
    print("Compliance監査完了.")

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
