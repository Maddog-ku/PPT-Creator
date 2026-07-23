# PPT Creator

[![CI](https://github.com/Maddog-ku/PPT-Creator/actions/workflows/ci.yml/badge.svg)](https://github.com/Maddog-ku/PPT-Creator/actions/workflows/ci.yml)

PPT Creator 會依照主題與參考資料產生簡報。網站先顯示正式 PPTX／PDF 的逐頁渲染結果，使用者確認後才下載檔案。

## 主要能力

- 先確認大綱，再分批生成 3 至 50 頁完整內容。
- 依內容自動選擇頁型，並提供 10 種視覺模板。
- 繁體中文／英文介面與深色／淺色模式。
- 可編輯 PPTX、PDF 與正式逐頁預覽。
- 可取消、恢復與重試背景任務，並顯示動態預估時間。
- 任務結束後自動卸載本機文字與圖片模型。

## 啟動

請先安裝 Docker Desktop 與 Ollama，再執行：

```bash
./scripts/start.sh
```

首次啟動會準備本機文字與圖片模型，所需時間依模型大小而定。完成後開啟：

- 網站：`http://localhost:3000`
- API 文件：`http://localhost:8000/docs`

停止服務：

```bash
./scripts/stop.sh
```

PostgreSQL 資料與已產生的簡報檔案會保留在 Docker volume 中。

## 建立簡報

1. 輸入簡報主題與需求。
2. 視需要上傳最多 8 個 `.txt`、`.md`、`.pdf` 或 `.pptx` 檔案；畫面會顯示每個檔案的解析結果。
3. 選擇語言、3 至 50 頁的頁數、AI 模型與 10 種視覺模板。
4. 如需圖片，可開啟圖片生成並選擇本機圖片模型。
5. 按下「先產生簡報大綱」。
6. 修改、增刪或排序大綱頁面，確認後再生成完整內容。

系統會依每頁內容自動選擇封面、章節轉場、重點卡片、左右圖文、數據焦點、雙欄比較、執行路徑、關鍵引言或結尾版型，並避免同一構圖連續重複。卡片、數據、比較與路線圖會使用各自的結構化內容，不再從同一段內文猜測欄位；使用者仍可在大綱或編輯工作台手動切換頁型。

生成工作會在背景執行，超過 10 頁的內容會均衡分批產生，每批可獨立驗證與重試。重新整理網站後仍可繼續查看進度，也可按下取消並釋放本機模型。

等待畫面會依頁數、圖片數、目前進度與實際執行時間顯示動態 ETA。成功、失敗或取消後，Worker 會清理 Ollama 文字模型、Ollama 圖片模型與本機 Stable Diffusion checkpoint。

## 預覽與下載

- 縮圖與主畫面都來自正式輸出檔的渲染結果。
- 可使用上一頁、下一頁、縮圖與全螢幕模式檢查內容。
- 可直接切換 10 種模板；每套都有獨立配色、字體與裝飾語言，切換模板不會重新呼叫文字 AI。
- 「加入動畫」會在下載的 PPTX 中加入淡入轉場。
- 確認簡報後，可分別下載可編輯 PPTX 與 PDF。
- 瀏覽器不會在確認或按下下載前自動接收檔案。

## 編輯簡報

在正式預覽按下「返回修改」即可開啟簡報編輯工作台：

- 可直接修改簡報名稱、頁面類型、眉標、標題與內文。
- 重點卡片、數據焦點、雙欄比較與執行路徑可分別編輯各自的標籤、小標題、數值與說明。
- 可新增、複製、刪除及拖曳排序投影片；簡報至少保留 3 頁，最多 50 頁。
- 尚未儲存的修改會顯示提醒，離開頁面前也會再次確認。
- 文字修改與排序不會呼叫 AI。
- 按下「儲存並更新預覽」後，系統會保存新版內容並重新產生 PPTX、PDF 與逐頁預覽。
- 內容修改後，舊的輸出檔會暫停下載，直到新版正式預覽完成，避免下載到過期內容。
- 「版本紀錄」可以查看每次生成、修改或還原的內容；還原舊版會另外建立新版本，不會刪除原有紀錄。

## 我的簡報

已生成的簡報會保存在 PostgreSQL 與本機 Docker volume，可從「我的簡報」重新開啟、預覽及下載，也可複製、單筆刪除或批次刪除。生成或渲染失敗時，簡報卡片會顯示錯誤原因與重試按鈕；重新渲染不會再次呼叫 AI。

## 任務中心

「任務中心」會集中顯示大綱與內容生成任務，可依執行中、失敗、完成或取消狀態篩選。執行中的任務可重新接回進度或取消；完成後可直接查看結果，失敗時則會從原本階段重新排入背景處理。

## AI 模型設定

預設使用本機 Ollama API，不需要 API Key，也不會產生雲端費用。設定頁可以保存多個本機或雲端 API，建立簡報時再由使用者自行選擇。

如需完全避免費用，請只選擇本機 Ollama 或本機 Stable Diffusion 類型的 Provider。

## 專案結構

```text
app/                  前端頁面、偏好、API 型別與 PPTX 建構
backend/app/          FastAPI、Worker、AI Provider 與渲染服務
backend/alembic/      PostgreSQL migrations
backend/tests/        後端測試
tests/                前端純函式與 SSR 測試
scripts/              跨平台啟停腳本
docs/                 架構與模組邊界
.github/              CI、Dependabot 與 PR 規範
```

詳細責任與後續拆分順序請見 [架構文件](docs/ARCHITECTURE.md)。

## 開發與測試

前端：

```bash
npm ci
npm run check
```

後端：

```bash
python -m venv backend/.venv
source backend/.venv/bin/activate
python -m pip install -e "./backend[dev]"
cd backend
python -m pytest -q
```

完整容器建置：

```bash
docker compose build web api worker
```

貢獻前請閱讀 [CONTRIBUTING.md](CONTRIBUTING.md)；安全問題請依 [SECURITY.md](SECURITY.md) 私下回報。

## 授權

此儲存庫目前尚未指定開源授權。公開前請由專案擁有者選擇合適的授權條款；在授權檔加入前，預設保留所有權利。
