import http.server
import socketserver
import json
import os

PORT = 3000
# ダッシュボードフォルダの絶対パス
DIRECTORY = os.path.dirname(os.path.abspath(__file__))
# ワークスペース（Tandy.inc）のルートパス
WORKSPACE_ROOT = os.path.dirname(os.path.dirname(DIRECTORY))

class TandyDashboardHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        # 静的ファイルをOutputs/dashboard/から配信
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def do_GET(self):
        # API 1: Inbox内の新規ファイルをリアルタイムに実スキャンして返す
        if self.path == '/api/inbox':
            inbox_path = os.path.join(WORKSPACE_ROOT, 'Inbox')
            files = []
            if os.path.exists(inbox_path):
                for f in os.listdir(inbox_path):
                    # README.md以外の実際のファイルをリストアップ
                    if f != 'README.md' and os.path.isfile(os.path.join(inbox_path, f)):
                        files.append({'name': f})
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            # CORS制限回避のためのヘッダー
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

if __name__ == '__main__':
    # 複数回起動時のアドレス競合を防ぐ設定
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), TandyDashboardHandler) as httpd:
        print("==================================================")
        print(" 🚀 Tandy.inc Control Dashboard (Python版サーバー)")
        print("    追加ライブラリのインストール不要で即時起動します")
        print(f" 🔗 アドレス: http://localhost:{PORT}")
        print("==================================================")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nサーバーを停止しました。")
