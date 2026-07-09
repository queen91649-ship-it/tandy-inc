# Tandy.inc 組織マニュアル & 標準作業手順書 (ORGANIZATION.md)

このドキュメントは、自律型AI組織 **`Tandy.inc`** の組織構造、各部門（エージェント）の役割、および現在実装されているワークフローとスキルの一覧をまとめた「会社全体の公式マニュアル」です。

新しい部門やワークフローを追加した際は、本ドキュメントを必ず更新してください。

---

## 1. 組織構造 (Organization Chart)

Tandy.inc は、CEOである人間の「承認と意思決定」を中心に、各専門AIエージェントが連携して動作する組織です。

```mermaid
graph TD
    CEO[CEO (人間) : 最終承認・意思決定]
    
    subgraph 01_経営統括 [経営・統括部門]
        CEO_A[ceo_agent: 壁打ち・全体統括]
        AUDIT_B[auditor_board_agent: 計画の自己レビュー]
    end
    
    subgraph 04_運営総務 [運営・総務部門]
        OPS[ops_agent: ファイル循環・ナレッジ管理]
    end
    
    subgraph 02_情報リサーチ [リサーチ・調査部門]
        RES[research_agent: 情報収集・トレンド調査]
    end
    
    subgraph 03_制作開発 [制作・開発部門]
        CRE[creator_agent: 記事・コード・UI執筆]
    end
    
    subgraph 05_法務監査 [法務・広報監査部門]
        COM[auditor_agent: テキスト・ファクトチェック]
    end
    
    subgraph 06_品質保証 [品質保証・テスト部門]
        QA[qa_agent: コード品質テスト・デバッグ]
    end

    subgraph 07_デザイン監査 [デザイン・UIUX品質監査部門]
        DES[designer_agent: 美観・ユーザビリティ監査]
    end

    subgraph 08_出版事業部 [出版事業部]
        REP_A[記者A: 国内政治・経済]
        REP_B[記者B: 国際情勢・世界経済]
        REP_C[記者C: AI・テクノロジー]
        REP_D[記者D: 通信・海底ケーブル]
        REP_E[記者E: トッテナム・Spurs]
        REP_F[記者F: プレミアリーグ]
        REP_G[記者G: 欧州リーグ・カップ戦]
        REP_H[記者H: 宇宙・深海・科学]
        
        EDITOR[総合編集部 / 編集長]
    end
    
    %% 連携関係
    CEO -->|指示/承認| OPS
    OPS -->|巡回・仲介| RES
    RES -->|データ| CRE
    
    %% 朝刊発行フロー
    OPS -->|情報分配| REP_A & REP_B & REP_C & REP_D & REP_E & REP_F & REP_G & REP_H
    REP_A & REP_B & REP_C & REP_D & REP_E & REP_F & REP_G & REP_H -->|一次原稿| EDITOR
    EDITOR -->|朝刊ドラフト| COM
    
    CRE -->|ブログ等| COM
    CRE -->|コード等| DES
    DES -->|デザイン合格| QA
    COM -->|完成品| OPS
    QA -->|完成品| OPS
    OPS -->|成果物| CEO
```

---

## 2. 部門（エージェント）一覧

各部門の役割と、その定義ファイルへのリンクです。

| フォルダ名 | 部門名 | 主な役割 | 定義ファイル |
| :--- | :--- | :--- | :--- |
| **`01_経営統括`** | **経営・統括部門** | CEOの壁打ち、経営判断の支援、提案計画書の自己監査。 | [ceo_agent.md](file:///g:/マイドライブ/02_AI%20Campany/Tandy.inc/01_経営統括/ceo_agent.md) <br> [auditor_board_agent.md](file:///g:/マイドライブ/02_AI%20Campany/Tandy.inc/01_経営統括/auditor_board_agent.md) |
| **`02_情報リサーチ`** | **リサーチ部門** | Web検索やRSS等を用いた市場調査、ビジネス活用案の策定。 | [research_agent.md](file:///g:/マイドライブ/02_AI%20Campany/Tandy.inc/02_情報リサーチ/research_agent.md) |
| **`03_制作開発`** | **制作・開発部門** | ブログ記事、SNS投稿文、およびPythonやHTMLなどのプログラムコードの執筆。 | [creator_agent.md](file:///g:/マイドライブ/02_AI%20Campany/Tandy.inc/03_制作開発/creator_agent.md) |
| **`04_運営総務`** | **運営・総務部門** | フォルダ間のファイル移動制御、タスクの実行制御、本マニュアルの維持管理。および、GitHub Actions上のスケジュールによるInbox定期監視タスク、AI提案デリバリー、週次整理整頓（Housekeeping）の実行制御。 | [ops_agent.md](file:///g:/マイドライブ/02_AI%20Campany/Tandy.inc/04_運営総務/ops_agent.md) <br> [inbox_watcher_flow.md](file:///g:/マイドライブ/02_AI%20Campany/Tandy.inc/04_運営総務/inbox_watcher_flow.md) <br> [tandy_watcher.py](file:///g:/マイドライブ/02_AI%20Campany/Tandy.inc/Outputs/dashboard/tandy_watcher.py) <br> [tandy_watcher.yml](file:///g:/マイドライブ/02_AI%20Campany/Tandy.inc/.github/workflows/tandy_watcher.yml) <br> [tandy_proposal.py](file:///g:/マイドライブ/02_AI%20Campany/Tandy.inc/Outputs/dashboard/tandy_proposal.py) <br> [tandy_proposal.yml](file:///g:/マイドライブ/02_AI%20Campany/Tandy.inc/.github/workflows/tandy_proposal.yml) <br> [tandy_housekeeping.py](file:///g:/マイドライブ/02_AI%20Campany/Tandy.inc/Outputs/dashboard/tandy_housekeeping.py) <br> [tandy_housekeeping.yml](file:///g:/マイドライブ/02_AI%20Campany/Tandy.inc/.github/workflows/tandy_housekeeping.yml) |
| **`05_法務監査`** | **法務・広報監査** | ブログ等のテキスト内の事実誤認（ハルシネーション）や著作権侵害・表現リスクの監査。 | [auditor_agent.md](file:///g:/マイドライブ/02_AI%20Campany/Tandy.inc/05_法務監査/auditor_agent.md) |
| **`06_品質保証`** | **品質保証・テスト** | 生成・修正されたプログラムの静的構文テスト、セキュリティ脆弱性・バグ監査。 | [qa_agent.md](file:///g:/マイドライブ/02_AI%20Campany/Tandy.inc/06_品質保証/qa_agent.md) |
| **`07_デザイン監査`** | **デザイン・UIUX監査** | Webサイト・HTML/CSSのレイアウト崩れ、カラー、フォント、使いやすさの美的な品質監査。 | [designer_agent.md](file:///g:/マイドライブ/02_AI%20Campany/Tandy.inc/07_デザイン監査/designer_agent.md) |
| **`08_出版事業部`** | **出版事業部** | 朝刊（Tandy Times）の各専門ニュース執筆（専属記者8名）およびパッケージング編集（編集長）。 | [editor_agent.md](file:///g:/マイドライブ/02_AI%20Campany/Tandy.inc/08_出版事業部/editor_agent.md) <br> [記者定義(専属記者/)](file:///g:/マイドライブ/02_AI%20Campany/Tandy.inc/08_出版事業部/専属記者/) |

---

## 3. 実装されている自動化ワークフロー (Modes)

現在、[workflow_guide.md](file:///g:/マイドライブ/02_AI%20Campany/Tandy.inc/04_運営総務/workflow_guide.md) に定義されている自動処理フローです。エージェントはトリガーに応じて自動でモードを判定します。

*   **⏱️ 【Inbox定期監視フロー】**: GitHub Actionsにて1日2回（毎日 AM 9:00 / PM 17:00）自動で起動し、`Inbox/` をスキャンして新規ファイルがあった場合に該当する以下のモードを自動で実行する、PC稼働状況不問の自動化フロー。
*   **⏱️ 【AI提案デリバリーフロー】**: GitHub Actionsにて毎週月曜日の朝 9:00 に起動し、最新トレンドや自律的な課題分析を巡回リサーチし、Tandy.inc への適用提案書（Markdown）を自動生成して `Inbox/` およびダッシュボード（`Outputs/proposals/`）に投函するフロー。
*   **⏱️ 【週次整理整頓（Housekeeping）フロー】**: GitHub Actionsにて毎週日曜日 夜23:00（日本時間）に自動で起動し、古い意思決定済提案のアーカイブ移動、日付表記の揺れたニュースレター等の月別統合・分類リネーム、古いInbox処理済みファイルのクリーンアップを自動実行して組織美観を保つフロー。
*   **① 【ブログ記事モード】**: `Inbox/` のアイデアから完成版Markdownを `Outputs/` に保存。
*   **② 【開発モード】**: 要件定義から監査済み完成コードとレポートをパッケージ出力。
*   **③ 【UI更新モード】**: ダッシュボード（`Outputs/dashboard/`）のデザイン・機能を直接上書き更新。
*   **④ 【バグ修正モード】**: エラーログからバグ修正コードとQA監査報告書をパッケージ出力。
*   **⑤ 【市場調査モード】**: 情報調査からソースURL付きの報告書、ビジネスプラン、監査レポートをパッケージ保存。
*   **⑥ 【朝刊発行（ニュースレター）モード】**: 毎朝6:00に自動起動。または手動指示で、8名の専属記者と総合編集部による特大朝刊（Tandy Times）を出力。

---

## 4. 登録されているカスタムスキル (手動トリガーコマンド)

チャット上で特定のコマンドを指示することで、私（Antigravity）が対応するスキルファイル（`.agents/skills/` 配下）をロードして自律実行します。

* **`run_workflow`** 
  - **実行内容**: `Inbox/` のファイルをスキャンし、適切なモードで処理を行い、成果物を出力してファイルを `Archive/` に退避します。
  - **スキルファイル**: [run_workflow/SKILL.md](file:///g:/マイドライブ/02_AI%20Campany/.agents/skills/run_workflow/SKILL.md)
* **`daily_newsletter`** 
  - **実行内容**: `02_情報リサーチ/watchlist.txt` の情報源から最新ニュースをキュレーションし、8名の専属記者が記事を執筆後、総合編集部（編集長）がマージ・編集した朝刊（Tandy Times）を出力します。
  - **スキルファイル**: [daily_newsletter/SKILL.md](file:///g:/マイドライブ/02_AI%20Campany/.agents/skills/daily_newsletter/SKILL.md)
* **`update_ui`**
  - **実行内容**: ダッシュボードのソースコードを指示に従って修正し、デザイン・QA監査を経て直接上書き更新します。
  - **スキルファイル**: [update_ui/SKILL.md](file:///g:/マイドライブ/02_AI%20Campany/.agents/skills/update_ui/SKILL.md)
* **`review_plan`**
  - **実行内容**: 作成された `implementation_plan.md` を読み込み、監査役の視点でリスクや改善点を計画書に自動追記します。
  - **スキルファイル**: [review_plan/SKILL.md](file:///g:/マイドライブ/02_AI%20Campany/.agents/skills/review_plan/SKILL.md)

---

## 5. 特殊フォルダ

* **`Inbox/`**：処理待ちのアイデアや要求ファイルを投入するフォルダ。毎日AM 9:00およびPM 17:00にGitHub Actionsによって自動スキャン・処理されます。また、毎週月曜日にAI提案書もここに投函されます。
* **`Pending_Approval/`**：自動処理中に監査（Auditor/QA）でリスク（ハルシネーション・セキュリティ脆弱性など）が検出された成果物を一時的に隔離・保存するフォルダ。人間（CEO）が確認し、手動で承認または差し戻しを判断します。
* **`Archive/`**：処理が完了したインプットファイルの履歴保管先。
* **`Outputs/`**：完成した各種成果物（記事、プログラムパッケージ、調査レポート等）の出力先。
* **`Outputs/proposals/`**：AIが自発的に生成した過去の提案書がアーカイブ保存されるフォルダ。ダッシュボードの表示データとしても使用されます。
