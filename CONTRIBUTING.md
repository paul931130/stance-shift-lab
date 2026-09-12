# 貢獻指南

這是一個學術專題的研究台，目前由單人維護。歡迎回報問題或提出改進，以下是建議流程。

## 回報問題

先查一下 [Issues](../../issues) 有沒有重複回報。開新 issue 時盡量附上：

- 重現步驟（哪個指令、哪個 API、輸入了什麼）
- 預期行為 vs. 實際行為
- `research.ps1 doctor` 的輸出（如果跟啟動、模型或資料來源有關）
- 你是用 Docker 還是 `.venv` 執行

## 開發環境

```bash
git clone https://github.com/<你的帳號>/stance-shift-lab.git
cd stance-shift-lab
python -m venv .venv
.venv\Scripts\pip install -r research_service/requirements.txt ruff
```

## 送出修改前

```powershell
ruff check research_service scripts
python -m unittest discover -s research_service/tests -p "test_*.py"
node --check research_service\static\app.js
docker build -f Dockerfile.research -t stance-shift-lab-research .
```

這些檢查跟 CI（`.github/workflows/ci.yml`）跑的一樣；PR 送出後 CI 也會自動跑一次。

## 提交 PR

- 一個 PR 專注一件事，避免把 lint 修正、功能改動、文件更新混在一起。
- 若改動會影響決策提示詞、協議欄位或資料口徑，請同時更新 [CHANGELOG.md](CHANGELOG.md) 並考慮是否需要新的 protocol 版本（見 [design-notes](docs/design-notes-v3-0908.md) 的版本規則）。
- 不要提交任何 API 金鑰、`.env.research`、SQLite 資料庫或未授權的第三方資料（新聞 CSV 等）。
