import http.server
import socketserver
import json
import os
import datetime
import threading
import time
import subprocess

PORT = 3000
# ダッシュボードフォルダの絶対パス
DIRECTORY = os.path.dirname(os.path.abspath(__file__))
# ワークスペース（Tandy.inc）のルートパス
WORKSPACE_ROOT = os.path.dirname(os.path.dirname(DIRECTORY))

class TandyDashboardHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def do_GET(self):
        # API 1: Inbox内の新規ファイルをリアルタイムに実スキャンして返す
        if self.path == '/api/inbox':
            inbox_path = os.path.join(WORKSPACE_ROOT, 'Inbox')
            files = []
            if os.path.exists(inbox_path):
                for f in os.listdir(inbox_path):
                    if f != 'README.md' and os.path.isfile(os.path.join(inbox_path, f)):
                        files.append({'name': f})
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(files, ensure_ascii=False).encode('utf-8'))
            return
            
        return super().do_GET()

    def do_POST(self):
        # API 2: ワークフロー実行リクエスト
        if self.path == '/api/run-workflow':
            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'success', 'message': 'Tandy.inc workflow triggered.'}).encode('utf-8'))
            return
            
        self.send_error(404, "Not Found")


def run_scheduler():
    """
    Tandy.inc 専用の軽量自動スケジューラー（cron）。
    ダッシュボードサーバー起動中、バックグラウンドスレッドで時刻を監視し、
    予定時刻に対応するバッチファイルを非同期実行します。
    """
    print("\n[⏰ Scheduler] 自動スケジュール監視スレッドが起動しました。")
    print("   - 毎日 AM 6:30 : 朝刊作成 (run_tandy_core.bat)")
    print("   - 毎日 AM 6:40 : AI提案 (run_tandy_proposal.bat)")
    print("   - 毎日 AM 6:45 : Inbox監視 (run_tandy_watcher.bat)")
    print("   - 毎週日曜日 AM 6:50 : クリーンアップ (run_tandy_housekeeping.bat)\n")
    
    last_run = {}
    
    while True:
        try:
            now = datetime.datetime.now()
            time_str = now.strftime("%H:%M")
            weekday = now.weekday()  # 6 = 日曜日
            
            # 1. 毎日 6:30 朝刊作成
            if time_str == "06:30" and last_run.get("core") != now.date():
                print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ⏰ スケジュール起動: 朝刊作成...")
                subprocess.Popen(["run_tandy_core.bat"], shell=True, cwd=WORKSPACE_ROOT)
                last_run["core"] = now.date()
                
            # 2. 毎日 6:40 AI提案デリバリー
            if time_str == "06:40" and last_run.get("proposal") != now.date():
                print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ⏰ スケジュール起動: AI提案デリバリー...")
                subprocess.Popen(["run_tandy_proposal.bat"], shell=True, cwd=WORKSPACE_ROOT)
                last_run["proposal"] = now.date()
                
            # 3. 毎日 6:45 インボックス監視
            if time_str == "06:45" and last_run.get("watcher") != now.date():
                print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ⏰ スケジュール起動: インボックス監視...")
                subprocess.Popen(["run_tandy_watcher.bat"], shell=True, cwd=WORKSPACE_ROOT)
                last_run["watcher"] = now.date()
                
            # 4. 毎週日曜日 6:50 クリーンアップ
            if time_str == "06:50" and weekday == 6 and last_run.get("housekeeping") != now.date():
                print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ⏰ スケジュール起動: クリーンアップ...")
                subprocess.Popen(["run_tandy_housekeeping.bat"], shell=True, cwd=WORKSPACE_ROOT)
                last_run["housekeeping"] = now.date()
                
        except Exception as e:
            print(f"【エラー】スケジュール監視中に想定外のエラーが発生しました: {e}")
            
        time.sleep(30)


if __name__ == '__main__':
    # スケジュール監視スレッドの開始
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), TandyDashboardHandler) as httpd:
        print("==================================================")
        print(" 🚀 Tandy.inc Control Dashboard (Python版サーバー)")
        print("    自動スケジュール監視（AM 6:30-6:50）が有効です")
        print(f" 🔗 アドレス: http://localhost:{PORT}")
        print("==================================================")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nサーバーを停止しました。")
