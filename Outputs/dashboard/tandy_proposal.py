import os
import sys
import datetime
import traceback
import json

try:
    from google import genai
    from google.genai import types
except ImportError as e:
    print(f"Error: Missing dependency. {e}")
    sys.exit(1)

# tandy_watcher から Driveクライアントをインポート
from tandy_watcher import TandyWatcherDriveClient
from tandy_core import clean_emoji_and_symbols

ROOT_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_ROOT_FOLDER_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

def generate_proposal(gemini_client):
    """Gemini-2.5-pro を用いて、最新トレンドのリサーチとTandy.inc向け提案書を自動生成"""
    today_str = datetime.date.today().strftime("%Y年%m月%d日")
    
    system_instruction = (
        "あなたは Tandy.inc の最高技術責任者 (CTO) 兼 経営企画室長を務める優秀なAIエージェントです。"
        "世の中の最新技術やトレンドを常に監視し、CEO（人間）に向けて非常に具体的で付加価値の高い「ビジネス提案書」を作成するのが役割です。"
        "提案書は、客観的なデータに基づきつつ、CEOが読んだときに知的興奮を覚え、今週のビジネス活動に高いモチベーションと自己肯定感を持って臨めるような、高尚で建設的な文体で執筆してください。"
        "【重要規約】: 本文および見出しにおいて、絵文字やシンボルマーク（✅や🚀など）は一切使用しないでください。"
    )

    prompt = (
        f"本日の日付は {today_str} です。\n\n"
        "Google Searchツールを使用して、以下の分野の「直近1ヶ月以内の最新トレンド、他社事例、または技術的なブレイクスルー」を調査してください:\n"
        "1. 生成AIを用いた業務の自律自動化（AIエージェント、ワークフロー自動化）の最新トレンドや導入事例\n"
        "2. モダンでプレミアムなWebデザイン/UIUXの最新トレンドや、使いやすさを高めるアクセシビリティの好事例\n"
        "3. 現在ビジネス界で注目されているIT/テクノロジー関連の重要トピック\n\n"
        "リサーチ結果をベースに、Tandy.inc のビジネス価値を最大化するための【今週のAI提案書】を以下の構成で執筆してください:\n\n"
        "--- 構成内容 ---\n"
        "# 【AI提案】[YYYYMMDD]_[今週のメインテーマ]\n"
        "（※見出しの絵文字は厳禁）\n\n"
        "## 1. はじめに\n"
        "今週のビジネスを取り巻く状況と、本日の提案の背景となる市場トレンドの概要を論述してください。\n\n"
        "## 2. リサーチ結果：今週キャッチアップすべき重要トレンド ＆ 他社事例\n"
        "Google Searchで調査した具体的な最新データ、ツール名、または他社の成功事例を、一次ソースURLを交えて分かりやすくまとめてください。\n\n"
        "## 3. Tandy.inc への具体的な適用提案（3つのアクションプラン）\n"
        "Tandy.inc が今週実行すべき具体的な改善案を、以下の3点についてそれぞれ詳細に立案してください。\n"
        "各提案には【概要】、【期待されるメリット】、【想定コスト ＆ 費用対効果（ROI）】、【具体的な実装ステップ】を記述してください。\n"
        "- **提案A: 業務効率化・自動化の強化案** (Operations/Researchの強化)\n"
        "- **提案B: UIダッシュボードのデザイン・アクセシビリティ改善案** (UIUX Design/Creativeの強化)\n"
        "- **提案C: ブログ記事または新規コンテンツのバズテーマ案** (Creative/リサーチトレンドに基づくネタ出し)\n\n"
        "## 4. 期待される効果 ＆ CEOへの応援メッセージ\n"
        "今週の提案がTandy.incにもたらす長期的な成長ビジョンと、CEOが今週も素晴らしい意思決定を行えるよう、自己肯定感を高める知的な激励の言葉で締めくくってください。\n\n"
        "--- 執筆ルール ---\n"
        "- 全ての外部リンクのURLが正しいか、ハルシネーションがないか、自己監査した上で組み立ててください。\n"
        "- シンボルマークや絵文字（✅や🚀など）は一切使用しないでください。"
    )

    print("Geminiによる提案書の生成を開始します（Web検索連携）...")
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


def main():
    if not ROOT_FOLDER_ID or not GEMINI_API_KEY:
        print("エラー: 必要な環境変数が設定されていません。")
        sys.exit(1)

    print("Google Drive API に接続中...")
    drive = TandyWatcherDriveClient()
    
    # フォルダIDの取得
    inbox_id = drive.get_folder_id_by_path("Inbox")
    proposals_id = drive.get_or_create_folder_by_path("Outputs/proposals", drive.root_id)

    if not inbox_id or not proposals_id:
        print("エラー: 必要なフォルダ構造が見つかりません。")
        sys.exit(1)

    # ロックファイルチェック
    lock_id = drive.find_file_id_by_path(".workflow_lock", parent_id=drive.root_id)
    if lock_id:
        print("【処理スキップ】ロックファイル (.workflow_lock) が存在するため、提案生成フローをスキップします。")
        sys.exit(0)

    # ロックの確保
    print("ロックファイル (.workflow_lock) を作成します。")
    lock_time_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    lock_id = drive.create_file(".workflow_lock", f"Locked by Proposal Agent at {lock_time_str}", drive.root_id, mime_type='text/plain')

    try:
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        
        # 提案書の自動生成
        proposal_content = generate_proposal(gemini_client)
        print(f"提案書の生成が完了しました (文字数: {len(proposal_content)} 文字)")
        
        # テーマタイトルを簡易抽出してファイル名にする (例: 【AI提案】YYYYMMDD_AIエージェントの導入.md)
        today_date_str = datetime.date.today().strftime('%Y%m%d')
        filename = f"【AI提案】{today_date_str}_ビジネス自動化案.md"
        
        # タイトル行からもう少しスマートに抽出を試みる
        title_match = re.search(r'^#\s*【AI提案】\d+_(.+)$', proposal_content, re.MULTILINE)
        if title_match:
            theme_clean = title_match.group(1).strip()
            # 記号除去
            theme_clean = re.sub(r'[\\/*?:"<>|]', "", theme_clean)
            filename = f"【AI提案】{today_date_str}_{theme_clean[:20]}.md"
            
        print(f"ファイル名: {filename}")
        
        # 1. Google Drive の Inbox に投函
        print("Google Drive の Inbox フォルダに投函します...")
        drive.create_file(filename, proposal_content, inbox_id)
        
        # 2. Outputs/proposals フォルダにアーカイブ保存
        print("Google Drive の Outputs/proposals フォルダにアーカイブ保存します...")
        drive.create_file(filename, proposal_content, proposals_id)
        
        print("✅ 提案書のデリバリーおよびアーカイブ保存が正常に完了しました！")
        
    except Exception as e:
        print(f"❌ 提案書の生成中にエラーが発生しました: {e}")
        traceback.print_exc()
        # 失敗時も例外を投げてGitHub Actionsで検知できるようにする
        sys.exit(1)
        
    finally:
        # ロックファイルの削除
        try:
            drive.delete_file(lock_id)
            print("ロックファイル (.workflow_lock) を削除しました。")
        except Exception as e:
            print(f"警告: ロックファイルの削除に失敗しました: {e}")


import re # 正規表現モジュールを念のため追加

if __name__ == "__main__":
    main()
