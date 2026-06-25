# Claude Hourglass ⏳

Claude Code の使用制限を Windows タスクトレイから砂時計風に確認できる常駐アプリ。

![スクリーンショット](Docs/screenshot.png)

## 機能

| 機能 | 概要 |
|------|------|
| トレイ常駐 | 使用率に応じて色が変わるピクセルアート砂時計アイコン |
| ホバーツールチップ | 5時間制限・7日制限の使用率とリセット時刻 |
| クリックパネル | 砂時計アニメーション + 詳細メトリクス |
| 履歴グラフ | 日別・週別・セッション別 (pyqtgraph) |
| データ保存 | SQLite + latest_usage.json |
| statusLine フック | Claude Code から自動収集 |

## セットアップ

```bash
# 依存パッケージをインストール
pip install -r requirements.txt

# サンプルデータを生成して動作確認
python scripts/seed_data.py --days 14

# アプリを起動
python -m claude_hourglass.main
```

## Claude Code との連携

### 仕組み

Claude Code の `statusLine` 設定に登録したコマンドは、**ターン毎に Claude Code から呼び出され**、  
現在のセッション情報（レート制限・コスト・モデルなど）を **stdin に JSON として受け取ります**。  
コマンドが stdout に出力したテキストは Claude Code のステータスバーに表示されます。

`save_usage.py` はこのフローを利用して:
1. stdin から JSON を読み込む
2. `usage.sqlite` にスナップショットを保存する
3. `latest_usage.json` を上書きする（トレイアプリが参照）
4. 現在の使用率を stdout に出力する（ステータスバーに表示）

### 設定方法

`.claude/settings.json` に `statusLine` を追加します:

```json
{
  "statusLine": "python C:/path/to/claude-hourglass/statusline_hook/save_usage.py"
}
```

Windows で `python` が PATH に入っていない場合はフルパスを指定してください:

```json
{
  "statusLine": "C:/Users/yourname/AppData/Local/Programs/Python/Python312/python.exe C:/path/to/claude-hourglass/statusline_hook/save_usage.py"
}
```

設定後、Claude Code を再起動するとステータスバーに以下のように表示されます:

```
[Hourglass] 5h 42.5% | 7d 18.0%
```

### statusLine が受け取る JSON 形式

```json
{
  "captured_at": "2026-06-25T12:34:56Z",
  "session_id": "abc-123",
  "model": { "display_name": "Claude Sonnet 4.6" },
  "rate_limits": {
    "five_hour": { "used_percentage": 42.5, "resets_at": "2026-06-25T17:00:00Z" },
    "seven_day": { "used_percentage": 18.0, "resets_at": "2026-07-01T00:00:00Z" }
  },
  "cost": { "total_cost_usd": 0.1234 },
  "context_window": { "current_usage": 45000 },
  "version": "1.0.0"
}
```

### 手動テスト

```bash
echo '{"captured_at":"2026-06-25T12:00:00Z","rate_limits":{"five_hour":{"used_percentage":55.0,"resets_at":"2026-06-25T17:00:00Z"},"seven_day":{"used_percentage":20.0,"resets_at":"2026-07-01T00:00:00Z"}},"cost":{"total_cost_usd":0.25},"model":{"display_name":"Claude Sonnet 4.6"}}' | python statusline_hook/save_usage.py
```

## Windows 自動起動

アプリ起動後に **設定画面**（トレイアイコン右クリック → 設定）を開き、  
「Windows ログオン時に Claude Hourglass を自動起動する」をチェックして OK を押してください。

### 内部動作

1. VBS ランチャーを `~/.claude_hourglass/launch_hourglass.vbs` に生成する
2. レジストリキー `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` に以下を登録する

```
ClaudeHourglass = wscript.exe "C:\Users\<name>\.claude_hourglass\launch_hourglass.vbs"
```

VBS ランチャーは作業ディレクトリをプロジェクトルートに設定したうえで `pythonw.exe` でコンソールなし起動します。

### 注意

- 管理者権限は不要（`HKCU` = 現在ユーザーのみ）
- VBS ファイルはアプリが自動生成するため手動編集は不要
- Python 環境を変えた場合は一度 OFF → ON で再登録してください
- PyInstaller 等で EXE 化した場合は VBS を経由せず EXE パスが直接登録されます

### 手動での確認・削除

レジストリエディター (`regedit`) で以下を確認できます:

```
HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run
└── ClaudeHourglass
```

## ファイル構成

```
claude-hourglass/
├── claude_hourglass/          # メインアプリパッケージ
│   ├── main.py                # エントリポイント
│   ├── tray.py                # タスクトレイ管理
│   ├── config.py              # 設定管理
│   ├── database.py            # SQLite 操作
│   ├── models.py              # データモデル
│   ├── startup.py             # 自動起動の登録・解除 (VBS生成 + レジストリ)
│   └── ui/
│       ├── theme.py           # カラーパレット・スタイルシート
│       ├── hourglass_panel.py # クリックパネル
│       ├── main_window.py     # メイン画面
│       ├── settings_dialog.py # 設定ダイアログ
│       └── widgets/
│           ├── hourglass_widget.py  # 砂時計アニメーション
│           └── usage_chart.py       # グラフウィジェット
├── statusline_hook/
│   └── save_usage.py          # データ受信・保存スクリプト
├── scripts/
│   └── seed_data.py           # サンプルデータ生成
├── Docs/
│   └── 仕様.md
├── requirements.txt
└── pyproject.toml
```

## データの保存先

デフォルトは `~/.claude_hourglass/` 以下:

| ファイル | 内容 |
|----------|------|
| `usage.sqlite` | スナップショット履歴 |
| `latest_usage.json` | 最新状態 (トレイアプリがポーリング) |
| `config.json` | アプリ設定 |
| `launch_hourglass.vbs` | 自動起動用 VBS ランチャー（設定画面から生成） |

設定画面から変更可能。

## グラフについての注意

`rate_limits.*.used_percentage` は現在の制限枠に対する使用率であり、  
日別・週別グラフは **使用率の推移** として表示しています (厳密な利用量ではありません)。  
`cost.total_cost_usd` の差分から将来的により精度の高い推定を追加予定。

## デザイン

- 背景: ダークブラウン (`#1C1814`)
- 文字: クリーム色 (`#F5F0E8`)
- アクセント: オレンジ (`#E8892A`) / アンバー (`#C4782A`) / ブルー (`#7BA7C2`)
- フォント: IBM Plex Sans JP / JetBrains Mono (フォールバックあり)
- 砂時計: ドットグリッドで粒状感を表現、使用率に応じて色変化

## 要件

- Python 3.10+
- Windows 10/11
- PySide6 >= 6.6
- pyqtgraph >= 0.13
