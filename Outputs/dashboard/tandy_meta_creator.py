import os
import sys
import datetime
import traceback
import json
import re
import ast
import subprocess

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("Error: google-genai package is missing.")
    sys.exit(1)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# 作業ルートディレクトリの特定
DASHBOARD_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_ROOT = os.path.dirname(DASHBOARD_DIR)

def run_git_command(args, cwd):
    """Git コマンドを実行するヘルパー"""
    try:
        result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Git command failed: {' '.join(args)}")
        print(f"Error output: {e.stderr}")
        raise e

def design_and_generate_code(gemini_client, requirement):
    """要件から新しいワークフローのID、表示名、説明文、Pythonコード、YAML設定を自律起案(Creative)"""
    print(f"\n[起案部門 (Creative)] 要件「{requirement}」の設計を開始します...")
    
    prompt = (
        f"以下の【CEO要求】に基づいて、新しい自動化ワークフローを設計してください。\n\n"
        f"【CEO要求】:\n{requirement}\n\n"
        f"【設計条件】:\n"
        f"1. ワークフローID (一意の英小文字とアンダースコア, 例: github_stats) を決定してください。\n"
        f"2. 表示用日本語名 (例: GitHub統計レポート) を決定してください。\n"
        f"3. ワークフローの説明文 (100文字程度、知的で簡潔な表現) を決定してください。\n"
        f"4. 自動化スクリプトの Python コードを生成してください。\n"
        f"   - Pythonコードは必ず Tandy.inc の共通クライアント(TandyWatcherDriveClient)をインポートして Google Drive に保存するか、"
        f"     または outputs/ 配下にファイルを直接書き出すようにしてください。\n"
        f"   - 【最重要】作成される Python コード自体の内部に、Creatorによるドラフト生成のあと、必ず「QA監査」や「法務監査(Auditor)」の論理的チェックルーチン（例: try-exceptによる検証、不正データのチェック）を含めるようにしてください。\n"
        f"   - 外部認証キー（GitHub トークンなど）はハードコードせず、必ず os.environ.get('GITHUB_TOKEN') などの環境変数から取得するようにしてください。\n"
        f"5. GitHub Actions 用の YAML 設定を生成してください。\n"
        f"   - スケジュール(cron)を適切に設定してください（例: 毎週金曜の10時など、CEO要求に沿った時間）。\n"
        f"   - 手動実行(workflow_dispatch)を必ず含めてください。\n\n"
        f"【出力フォーマット】:\n"
        f"以下のJSONフォーマットでのみ返答してください。他の説明テキストは一切含めないでください。```json の囲いも不要です。\n\n"
        "{\n"
        "  \"id\": \"ワークフローID\",\n"
        "  \"name\": \"表示用日本語名\",\n"
        "  \"description\": \"説明文\",\n"
        "  \"python_code\": \"Pythonコードの文字列。インテンドの改行などはエスケープされたJSON文字列として正しく格納してください。\",\n"
        "  \"yaml_content\": \"YAML設定ファイルの文字列。\"\n"
        "}"
    )
    
    response = gemini_client.models.generate_content(
        model='gemini-2.5-pro',
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.4
        )
    )
    
    clean_text = response.text.strip()
    clean_text = re.sub(r'^```json\s*', '', clean_text, flags=re.IGNORECASE)
    clean_text = re.sub(r'\s*```$', '', clean_text)
    
    try:
        return json.loads(clean_text)
    except Exception as e:
        print(f"JSONパースエラー。Creativeの出力:\n{response.text}")
        raise e

def audit_design_ui(gemini_client, draft_data):
    """追加するUIボタンの配色や文言、配置がダッシュボードのダークテーマと調和しているか監査(Design)"""
    print(f"\n[デザイン監査部門 (UIUX Design)] ボタンとUI表示の調和を審査中...")
    
    button_html = f"<button class=\"btn btn-secondary\" id=\"btn-{draft_data['id']}\" onclick=\"selectWorkflowMode('{draft_data['id']}')\">{draft_data['name']}</button>"
    
    prompt = (
        f"新ワークフロー「{draft_data['name']} (ID: {draft_data['id']})」を手動実行するためのUI要素:\n"
        f"`{button_html}`\n"
        f"およびその説明文「{draft_data['description']}」について、ダッシュボードのダークテーマ（ネオンサイアン、ネオンパープルを基調とするプレミアム・サイバーパンク調）の美観と調和しているか監査してください。\n\n"
        f"問題がなければ、以下のJSON形式でのみ出力してください。```json などの囲いは不要です。\n\n"
        "{\n"
        "  \"approved\": true,\n"
        "  \"feedback\": \"調和しています。ボタンの命名規則やID構成、コントラスト比についてもWCAG基準を満たしていると判定します。\"\n"
        "}"
    )
    
    response = gemini_client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt
    )
    
    clean_text = response.text.strip()
    clean_text = re.sub(r'^```json\s*', '', clean_text, flags=re.IGNORECASE)
    clean_text = re.sub(r'\s*```$', '', clean_text)
    
    return json.loads(clean_text)

def audit_qa_code(gemini_client, draft_data):
    """Pythonコードの構文検査（静的解析）およびエラートラップ審査(QA)"""
    print(f"\n[品質保証部門 (QA Engineering)] Pythonコードの構文テストおよび例外処理の検証中...")
    
    code = draft_data['python_code']
    
    # 1. Python 標準の ast モジュールによる静的構文チェック
    try:
        ast.parse(code)
        print("-> [QA] 静的コンパイル（ast.parse）による文法テストに合格しました。")
    except SyntaxError as se:
        print(f"-> [QA] 文法エラー検出: {se}")
        return {"approved": False, "feedback": f"SyntaxError detected: {se}"}
        
    # 2. Gemini によるエラートラップ、多重起動防止などの論理監査
    prompt = (
        f"以下の生成された Python コードについて、例外処理（try-except）、ロック制御、リソース解放が適切に設計されているか監査してください。\n\n"
        f"【コード】:\n{code}\n\n"
        f"監査結果を以下のJSON形式でのみ出力してください。```json の囲いは不要です。\n"
        "{\n"
        "  \"approved\": true または false (boolean),\n"
        "  \"feedback\": \"エラートラップが十分であることの証明、または不足している修正箇所の指摘\"\n"
        "}"
    )
    
    response = gemini_client.models.generate_content(
        model='gemini-2.5-pro',
        contents=prompt
    )
    
    clean_text = response.text.strip()
    clean_text = re.sub(r'^```json\s*', '', clean_text, flags=re.IGNORECASE)
    clean_text = re.sub(r'\s*```$', '', clean_text)
    
    return json.loads(clean_text)

def audit_security_secrets(gemini_client, draft_data):
    """環境変数の利用チェック、トークン漏洩等のセキュリティ監査(Auditor)"""
    print(f"\n[法務・広報監査部門 (Auditor)] トークン・環境変数の安全性とセキュリティチェック中...")
    
    code = draft_data['python_code']
    yaml = draft_data['yaml_content']
    
    prompt = (
        f"以下の Python コードおよび GitHub Actions YAML について、APIキーやトークンなどの秘匿情報が直接コード中にハードコードされていないか（envやsecretsから取得しているか）、セキュリティホールがないかを監査してください。\n\n"
        f"【Pythonコード】:\n{code}\n\n"
        f"【YAML設定】:\n{yaml}\n\n"
        f"監査結果を以下のJSON形式でのみ出力してください。```json の囲いは不要です。\n"
        "{\n"
        "  \"approved\": true または false (boolean),\n"
        "  \"feedback\": \"セキュリティ要件を満たしていることの証明、または修正要求\"\n"
        "}"
    )
    
    response = gemini_client.models.generate_content(
        model='gemini-2.5-pro',
        contents=prompt
    )
    
    clean_text = response.text.strip()
    clean_text = re.sub(r'^```json\s*', '', clean_text, flags=re.IGNORECASE)
    clean_text = re.sub(r'\s*```$', '', clean_text)
    
    return json.loads(clean_text)

def register_workflow_to_dashboard(data):
    """新ワークフローを手動起動できるようにダッシュボードの HTML, JS, ORGANIZATION.md に自動登録（インジェクション）"""
    print("\n--- 新ワークフローのダッシュボード自動登録を開始します ---")
    
    id_name = data['id']
    disp_name = data['name']
    desc_text = data['description']
    
    # 1. index.html に手動起動ボタンを挿入
    html_path = os.path.join(DASHBOARD_DIR, 'index.html')
    if os.path.exists(html_path):
        with open(html_path, 'r', encoding='utf-8') as f:
            html = f.read()
            
        btn_tag = f'<button class="btn btn-secondary" id="btn-{id_name}" onclick="selectWorkflowMode(\'{id_name}\')">{disp_name}</button>'
        
        # すでにボタンが存在しないか確認
        if f'id="btn-{id_name}"' not in html:
            # 挿入ターゲットプレイス: 個別選択ボタン群のコンテナの末尾
            target = '<div class="workflow-buttons" id="mode-btn-container">'
            pos = html.find(target)
            if pos != -1:
                # コンテナの閉じタグ </div> の前にボタンを挿入
                container_end = html.find('</div>', pos)
                if container_end != -1:
                    new_html = html[:container_end] + f'                                    {btn_tag}\n' + html[container_end:]
                    with open(html_path, 'w', encoding='utf-8') as wf:
                        wf.write(new_html)
                    print(f"-> index.html に起動ボタン「{disp_name}」を追加しました。")
                    
    # 2. app.js に説明文と名前を追加
    js_path = os.path.join(DASHBOARD_DIR, 'app.js')
    if os.path.exists(js_path):
        with open(js_path, 'r', encoding='utf-8') as f:
            js = f.read()
            
        desc_entry = f'    {id_name}: "【{disp_name}】<br>{desc_text} (※監査部門チェック通過済)",'
        name_entry = f'    {id_name}: "{disp_name}",'
        
        # workflowDescriptions 内への追記
        if f'{id_name}:' not in js:
            desc_target = 'const workflowDescriptions = {'
            desc_pos = js.find(desc_target)
            if desc_pos != -1:
                insert_pos = js.find('\n', desc_pos)
                if insert_pos != -1:
                    js = js[:insert_pos+1] + desc_entry + '\n' + js[insert_pos+1:]
                    
            name_target = 'const workflowNames = {'
            name_pos = js.find(name_target)
            if name_pos != -1:
                insert_pos = js.find('\n', name_pos)
                if insert_pos != -1:
                    js = js[:insert_pos+1] + name_entry + '\n' + js[insert_pos+1:]
                    
            # simulateWorkflowRun 内の folderName 分岐への追記 (プレビューパス用)
            sim_pos = js.find('else if (resolvedMode === \'design_audit\')')
            if sim_pos != -1:
                sim_insert = f"\n        else if (resolvedMode === '{id_name}') {{ modeName = \"{disp_name}\"; folderName += \"{id_name}/\"; }}"
                insert_line_end = js.find('\n', sim_pos)
                if insert_line_end != -1:
                    js = js[:insert_line_end+1] + sim_insert + js[insert_line_end+1:]
                    
            with open(js_path, 'w', encoding='utf-8') as wf:
                wf.write(js)
            print(f"-> app.js の説明テーブルと名称テーブルに「{id_name}」を登録しました。")

    # 3. ORGANIZATION.md にワークフローを追記
    org_path = os.path.join(WORKSPACE_ROOT, 'ORGANIZATION.md')
    if os.path.exists(org_path):
        with open(org_path, 'r', encoding='utf-8') as f:
            org = f.read()
            
        org_entry = f"*   **⏱️ 【{disp_name}】**: {desc_text}。起案からデザイン・QA・法務監査を通過した組織公認の自動ワークフロー。"
        
        if f'【{disp_name}】' not in org:
            # 「## 3. 実装されている自動化ワークフロー (Modes)」の下に追記
            target_sec = '## 3. 実装されている自動化ワークフロー (Modes)'
            pos = org.find(target_sec)
            if pos != -1:
                # 次の改行を見つけて挿入
                insert_pos = org.find('\n\n', pos + len(target_sec))
                if insert_pos != -1:
                    new_org = org[:insert_pos+2] + org_entry + '\n' + org[insert_pos+2:]
                    with open(org_path, 'w', encoding='utf-8') as wf:
                        wf.write(new_org)
                    print(f"-> ORGANIZATION.md に「{disp_name}」の説明を追記しました。")

def main():
    if len(sys.argv) < 2:
        print("エラー: 開発要求テキストが引数として指定されていません。")
        sys.exit(1)

    requirement = sys.argv[1]
    
    if not GEMINI_API_KEY:
        print("エラー: GEMINI_API_KEY が環境変数に設定されていません。")
        sys.exit(1)
        
    try:
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        
        # 1. 起案と監査のフィードバックループの開始 (最大3回)
        draft = None
        loop_count = 0
        max_loops = 3
        
        while loop_count < max_loops:
            loop_count += 1
            print(f"\n===== 開発・監査サイクル (ループ {loop_count} / {max_loops}) =====")
            
            # 起案
            draft = design_and_generate_code(gemini_client, requirement)
            
            # 監査
            design_audit = audit_design_ui(gemini_client, draft)
            qa_audit = audit_qa_code(gemini_client, draft)
            sec_audit = audit_security_secrets(gemini_client, draft)
            
            print(f"\n[監査判定結果 (ループ {loop_count})]:")
            print(f"- UIデザイン監査: {'合格' if design_audit['approved'] else '不合格'} (フィードバック: {design_audit['feedback']})")
            print(f"- QA技術監査: {'合格' if qa_audit['approved'] else '不合格'} (フィードバック: {qa_audit['feedback']})")
            print(f"- セキュリティ監査: {'合格' if sec_audit['approved'] else '不合格'} (フィードバック: {sec_audit['feedback']})")
            
            if design_audit['approved'] and qa_audit['approved'] and sec_audit['approved']:
                print("\n🎉 経営監査ボード全員一致により、新ワークフローの開発設計案が可決されました！")
                break
            else:
                print("\n⚠️ 一部の監査で不合格となったため、次サイクルでフィードバックを取り入れ自動再設計します。")
                # ユーザー要求プロンプトにフィードバックを上書きマージ
                requirement += (
                    f"\n\n【前回の監査不合格フィードバック】:\n"
                    f"- UIデザイン指摘: {design_audit['feedback']}\n"
                    f"- QA技術指摘: {qa_audit['feedback']}\n"
                    f"- セキュリティ指摘: {sec_audit['feedback']}\n"
                    f"これらの指摘点を必ず完全に修正・克服するよう、コードおよびYAMLを再作成してください。"
                )
        else:
            print("\n❌ 規定のループ内にすべての監査を合格させることができませんでした。開発を中止します。")
            sys.exit(1)
            
        # 2. ファイル書き出し
        id_name = draft['id']
        py_filename = f"tandy_{id_name}.py"
        yml_filename = f"tandy_{id_name}.yml"
        
        py_filepath = os.path.join(DASHBOARD_DIR, py_filename)
        yml_filepath = os.path.join(WORKSPACE_ROOT, '.github', 'workflows', yml_filename)
        
        print(f"\nファイルをローカルに出力します:")
        print(f"- Python: {py_filepath}")
        print(f"- YAML: {yml_filepath}")
        
        with open(py_filepath, 'w', encoding='utf-8') as f:
            f.write(draft['python_code'])
            
        # .github/workflows ディレクトリの存在確認
        os.makedirs(os.path.dirname(yml_filepath), exist_ok=True)
        with open(yml_filepath, 'w', encoding='utf-8') as f:
            f.write(draft['yaml_content'])
            
        # 3. ダッシュボード ＆ 組織マニュアルの更新
        register_workflow_to_dashboard(draft)
        
        # 4. Git への自動コミット ＆ プッシュによるデプロイ
        print("\n--- 自動デプロイ (Git Commit & Push) を開始します ---")
        run_git_command(["git", "add", py_filepath, yml_filepath, os.path.join(DASHBOARD_DIR, 'index.html'), os.path.join(DASHBOARD_DIR, 'app.js'), os.path.join(WORKSPACE_ROOT, 'ORGANIZATION.md')], WORKSPACE_ROOT)
        run_git_command(["git", "commit", "-m", f"Auto-deploy new audited workflow: {draft['name']}"], WORKSPACE_ROOT)
        run_git_command(["git", "push", "origin", "main"], WORKSPACE_ROOT)
        
        print(f"\n🚀 自己進化デプロイ成功！新ワークフロー「{draft['name']}」がシステムに追加され、クラウド側スケジュールも開始されました。")
        
    except Exception as e:
        print(f"❌ 自己進化開発中にエラーが発生しました: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
