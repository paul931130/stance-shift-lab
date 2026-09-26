#!/usr/bin/env sh
# Mac/Linux launcher. Docker is the only supported way to run the service,
# so this wraps the same docker compose calls as research.ps1 on Windows.
set -eu

cd "$(dirname "$0")"
COMPOSE="docker compose -f compose.research.yaml"
URL="http://127.0.0.1:8000"

need_docker() {
    if ! command -v docker >/dev/null 2>&1; then
        echo "[FAIL] 找不到 Docker。請先安裝 Docker Desktop（Mac）或 Docker Engine + Compose plugin（Linux）。" >&2
        exit 1
    fi
    if ! docker compose version >/dev/null 2>&1; then
        echo "[FAIL] 找不到 docker compose（Compose v2）。" >&2
        exit 1
    fi
    if ! docker info >/dev/null 2>&1; then
        echo "[FAIL] Docker engine 尚未啟動。請開啟 Docker Desktop，或在 Linux 執行 sudo systemctl start docker。" >&2
        exit 1
    fi
}

ensure_env() {
    if [ ! -f .env.research ]; then
        cp research.env.example .env.research
        echo "[INFO] 已從 research.env.example 建立 .env.research（Git 忽略，不會上傳）。"
    fi
}

wait_health() {
    echo "[INFO] 等待研究服務健康檢查（最多 180 秒）…"
    i=0
    while [ "$i" -lt 90 ]; do
        if curl -fsS "$URL/health" 2>/dev/null | grep -q '"status":"ok"'; then
            echo "[OK] 研究台已啟動：$URL/"
            return 0
        fi
        i=$((i + 1))
        sleep 2
    done
    echo "[FAIL] 服務未在時限內就緒，請執行 ./research.sh logs 查看原因。" >&2
    exit 1
}

case "${1:-help}" in
    setup)
        ensure_env
        echo "用文字編輯器填入 .env.research 的 API key，或啟動後在網頁「設定資料來源與模型」填寫。"
        ;;
    start)
        need_docker
        ensure_env
        $COMPOSE up -d --build
        wait_health
        ;;
    stop)
        need_docker
        $COMPOSE down
        echo "服務已停止；研究資料仍保留在 Docker volume。"
        ;;
    status)
        need_docker
        $COMPOSE ps
        curl -fsS "$URL/health" && echo || echo "[WARN] 健康檢查尚未就緒。"
        ;;
    logs)
        need_docker
        $COMPOSE logs -f --tail 100 research
        ;;
    test)
        need_docker
        $COMPOSE build research
        # Run in the bare image: the service's .env.research (e.g. demo mode)
        # would change behavior the tests assert on. The checkout is mounted
        # because the image ships only the service, not every script under test.
        docker run --rm -v "$PWD:/app:ro" "$($COMPOSE config --images research)" \
            python -m unittest discover -s research_service/tests -p 'test_*.py'
        ;;
    doctor)
        need_docker
        echo "[OK] Docker 與 Compose 可用，engine 已啟動"
        [ -f .env.research ] && echo "[OK] .env.research 存在" || echo "[INFO] 尚無 .env.research；start 會自動建立"
        curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1 \
            && echo "[OK] 本機 Ollama 已連線" \
            || echo "[INFO] 本機 Ollama 未連線；可改用 GPUtw 遠端 Ollama、雲端模型金鑰或展示模式"
        curl -fsS "$URL/health" >/dev/null 2>&1 && echo "[OK] 網站服務 healthy" || echo "[INFO] 網站尚未啟動"
        ;;
    *)
        cat <<'EOF'
用法：./research.sh <命令>
  setup   建立 .env.research（第一次使用）
  start   建置並啟動研究台（http://127.0.0.1:8000/）
  stop    停止服務（資料保留）
  status  顯示容器與健康狀態
  logs    追蹤服務日誌
  doctor  檢查 Docker、Ollama 與服務狀態
  test    在容器內執行單元測試
研究操作（建立資料集、執行實驗、匯出）請在網頁介面完成。
EOF
        ;;
esac
