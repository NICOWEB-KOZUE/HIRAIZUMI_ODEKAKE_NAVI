ひらいずみ おでかけナビ（高齢者おでかけ支援アプリ）

## 動かし方

```bash
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

ブラウザで http://127.0.0.1:8000 を開く。

- はじめに開くと「いつも乗るバス停」を選ぶ画面が出る。選んだ内容は `data/user_settings.json` に保存される
- バス停を選び直すときは、最初の画面の「乗るバス停を変える」を押す（またはこのファイルを消す）

## ファイル

- `app.py`: 画面の流れ（Flask）
- `planner.py`: 時刻表から行きと帰りの乗り換え候補を作る
- `data/`: 時刻表・行き先の JSON（出典は `docs/timetable.md`）
- `templates/`, `static/`: 画面の HTML・CSS・JavaScript
- `docs/`: 設計メモ（リーンキャンバス、画面設計、時刻表）
