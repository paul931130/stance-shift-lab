# 部署正式研究台

此版本需要常駐 Python 服務、持久化磁碟，以及可連線的 Ollama 或雲端模型。Cloudflare Workers / GitHub Pages 無法直接執行這個 Python + 本機模型後端。

## Docker 部署

1. 本機只透過 `127.0.0.1:8000` 操作時，可直接啟動。建議先執行 `.\research.ps1 setup`；正式上線時選擇 `server`，精靈會設定網域並產生研究室存取金鑰。
2. 若手動設定，將 `research.env.example` 複製成 `.env.research`，並填入至少 32 字元的 `RESEARCH_ACCESS_KEY`；不要提交至原始碼。
3. 設定 `RESEARCH_ALLOWED_HOSTS=research.example.com,localhost,127.0.0.1` 及 `RESEARCH_PUBLIC_ORIGIN=https://research.example.com`，將 example.com 換成實際網域。
4. 使用同主機 Ollama 時，容器內的 `OLLAMA_BASE_URL` 改為 `http://host.docker.internal:11434`，並確認 Ollama 僅允許受信任主機或 Docker 網路連線。或者指定雲端模型及伺服器端 API key。
5. 本機執行 `docker compose --env-file .env.research -f compose.research.yaml up -d --build`。正式上線執行 `docker compose --env-file .env.research -f compose.research.yaml -f compose.production.yaml up -d --build`。資料保存在具名 volume `research-data`，不要執行 `down -v` 除非確定要刪除研究資料。
6. 將 HTTPS 反向代理導向主機 `127.0.0.1:8000`。容器的主機連接埠僅綁 loopback；TLS 由反向代理負責。

登入後的 cookie 是 12 小時短期簽章 session，不保存研究室主金鑰，並設為 HttpOnly、Secure、SameSite=Strict。遠端介面必須使用 HTTPS；健康檢查不洩露研究資料。只有單一研究室擁有者，存取金鑰可存取所有研究資料，不提供多租戶身分隔離。研究 API 拒絕不符允許主機及來源的修改要求。

可從 `deploy/Caddyfile.example` 複製 Caddy 設定並替換實際網域：

```text
research.example.com {
    encode zstd gzip
    reverse_proxy 127.0.0.1:8000
}
```

## 不使用 Docker

安裝 Python 3.12 以上，建立獨立虛擬環境並安裝 `research_service/requirements.txt`。以 systemd、Windows 服務或平台工作程序啟動：

```text
python -m uvicorn research_service.app:app --host 0.0.0.0 --port 8000 --workers 1 --no-proxy-headers
```

由服務管理器注入 `.env.research` 的設定，另設 `RESEARCH_REMOTE=true`、`RESEARCH_DATA_DIR` 為持久化目錄。Uvicorn 不會自行讀取 `.env.research`；Windows 啟動腳本才有讀取功能。務必配置 HTTPS、私有後端連線與來源白名單。

## 上線驗收

- `/health` 回傳版本與 ok；未登入訪問 `/api/jobs` 應為 401。
- 實際網域登入、取得或匯入資料、開始工作、檢視進度、下載 ZIP 與統計。
- 重新啟動容器後資料保留，進行中的案例顯示可續跑。
- 伺服器真正能連上所選模型；雲端前端不會呼叫訪客電腦的 localhost。

本文件提供部署方法，不代表已替你取得網域、建立雲端主機或完成公開發布。
