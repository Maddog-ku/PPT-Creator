# PPT Creator 使用說明

PPT Creator 可依照主題與參考資料產生簡報，並讓使用者先在網站逐頁預覽，確認無誤後再下載可編輯的 PowerPoint 檔案。

## 主要功能

- 輸入簡報主題與需求。
- 加入多個參考檔案。
- 選擇語言、頁數及視覺風格。
- 透過後端 AI API 產生逐頁內容。
- 使用縮圖、上一頁、下一頁及全螢幕模式預覽。
- 返回修改內容或模板後重新產生。
- 確認簡報後才開放下載 PPTX。

## 建立簡報

1. 選擇左側的「建立簡報」。
2. 輸入簡報主題、用途或希望呈現的重點。
3. 視需要加入 `.pdf`、`.ppt`、`.pptx`、`.txt` 或 `.md` 檔案。
4. 選擇語言、預計頁數及視覺風格。
5. 按下「產生簡報預覽」。

生成完成後，網站會直接進入預覽，不會自動下載檔案。

## 預覽與下載

- 點擊左側縮圖，或使用上一頁、下一頁切換投影片。
- 使用全螢幕模式檢查文字與版面。
- 若需要調整，按下「返回修改」後重新產生。
- 確認內容無誤後，按下「確認簡報沒問題」。
- 「下載 PPTX」啟用後即可下載可編輯檔案。

## 設定

設定頁可新增本機 API、OpenAI、Anthropic、Google Gemini 或其他 OpenAI 相容 API。填寫名稱、Base URL、模型名稱與 API Key 後儲存，再使用「測試」確認連線。

可同時保存多個模型設定。建立簡報時，從「使用的 AI 模型」選單指定這次要使用的模型。API Key 由後端加密保存，設定頁不會再次顯示明文；網站前端也不會直接連接模型服務。

## 本機啟動

### 1. 啟動網站

```bash
npm install
npm run dev
```

開啟 `http://localhost:3000`。

### 2. 啟動後端 API

```bash
export PPT_CREATOR_VENV="/path/to/your/venv"
source "$PPT_CREATOR_VENV/bin/activate"
pip install -r requirements.txt
uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

API 文件位於 `http://localhost:8000/docs`。AI 服務與 PostgreSQL 的連線設定可由 `.env.example` 建立 `.env` 後調整。

### 3. 使用 Docker

先啟動 Docker Desktop，再執行：

```bash
docker compose up -d --build
```

停止服務：

```bash
docker compose down
```

## 開發檢查

```bash
npm run lint
npx tsc --noEmit
npm test
python -m unittest discover -s backend/tests -v
```

## 目前限制

- `.txt` 與 `.md` 內容會送至 AI API；PDF 與 PPTX 解析尚未完成。
- 「我的簡報」目前仍為示範資料，尚未完整連接 PostgreSQL。
- 尚未提供 PDF 下載、版本管理及刪除功能。
- AI 與簡報設定目前尚未保存。
