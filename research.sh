#!/usr/bin/env sh
# Mac/Linux launcher: wraps the same docker compose calls as research.ps1 on
# Windows.
set -eu

cd "$(dirname "$0")"
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

get_value() {
    sed -n "s/^$1=//p" .env.research 2>/dev/null | tail -n 1
}

set_value() {
    # Replace NAME=... in .env.research, or append it.
    grep -v "^$1=" .env.research > .env.research.tmp || true
    printf '%s=%s\n' "$1" "$2" >> .env.research.tmp
    mv .env.research.tmp .env.research
}

# RESEARCH_OLLAMA_CONTAINER=true runs Ollama as a container next to the
# service (compose.ollama.yaml); =gpu also gives it the NVIDIA GPU.
ollama_container() {
    printf '%s' "${RESEARCH_OLLAMA_CONTAINER:-$(get_value RESEARCH_OLLAMA_CONTAINER)}"
}

compose_files() {
    COMPOSE="docker compose -f compose.research.yaml"
    case "$(ollama_container)" in
        true) COMPOSE="$COMPOSE -f compose.ollama.yaml" ;;
        gpu) COMPOSE="$COMPOSE -f compose.ollama.yaml -f compose.ollama-gpu.yaml" ;;
    esac
}
compose_files

ask() {
    # ask NAME LABEL [secret]: Enter keeps the current value.
    current=$(get_value "$1")
    state="Enter 略過"; [ -n "$current" ] && state="目前已設定，Enter 保留"
    printf '%s [%s]: ' "$2" "$state"
    if [ "${3:-}" = secret ]; then stty -echo 2>/dev/null || true; fi
    read -r answer || answer=""
    if [ "${3:-}" = secret ]; then stty echo 2>/dev/null || true; echo; fi
    if [ -n "$answer" ]; then set_value "$1" "$answer"; fi
    return 0
}

choose_model_source() {
    # One model source at a time; see docs/model-sources.md.
    echo
    echo "模型要在哪裡執行？"
    echo "  1  自己電腦（本機 Ollama，需要夠力的顯示卡或耐心）"
    echo "  2  雲端租 GPU（GPUtw 遠端 Ollama）"
    echo "  3  雲端模型 API（OpenRouter／OpenAI／Gemini，只要一把金鑰）"
    printf '選擇 1 / 2 / 3 [1]: '
    read -r source || source=""
    model=$(get_value RESEARCH_MODEL)
    case "$source" in
        2)
            ask GPUTW_OLLAMA_BASE_URL "GPUtw 遠端 Ollama 位址（例如 https://…）"
            [ -n "$(get_value GPUTW_OLLAMA_BASE_URL)" ] || { echo "[FAIL] 選擇 GPUtw 時必須填入遠端 Ollama 位址。" >&2; exit 1; }
            ask GPUTW_OLLAMA_API_KEY "遠端 Ollama 存取 key（端點沒有保護可略過）" secret
            set_value RESEARCH_OLLAMA_CONTAINER ""
            case "$model" in ollama/*) ;; *) set_value RESEARCH_MODEL ollama/qwen3:14b ;; esac
            ask RESEARCH_MODEL "模型"
            ;;
        3)
            printf '哪一家？openrouter / openai / gemini [openrouter]: '
            read -r cloud || cloud=""
            case "${cloud:-openrouter}" in
                openrouter) key=OPENROUTER_API_KEY; suggested=openrouter/qwen/qwen3-14b ;;
                openai) key=OPENAI_API_KEY; suggested=openai/gpt-4.1-mini ;;
                gemini) key=GEMINI_API_KEY; suggested=gemini/gemini-2.5-flash ;;
                *) echo "[FAIL] 不支援的雲端模型：$cloud" >&2; exit 1 ;;
            esac
            ask "$key" "${cloud:-openrouter} API key" secret
            case "$model" in "${cloud:-openrouter}"/*) ;; *) set_value RESEARCH_MODEL "$suggested" ;; esac
            ask RESEARCH_MODEL "模型（LiteLLM 名稱）"
            # A leftover GPUtw address would otherwise still take over any ollama/ model.
            set_value GPUTW_OLLAMA_BASE_URL ""
            set_value RESEARCH_OLLAMA_CONTAINER ""
            ;;
        *)
            # Local Ollama: clear the GPUtw address, which otherwise takes precedence.
            set_value GPUTW_OLLAMA_BASE_URL ""
            case "$model" in ollama/*) ;; *) set_value RESEARCH_MODEL ollama/qwen3:14b ;; esac
            ask RESEARCH_MODEL "模型"
            echo "Ollama 要怎麼跑？"
            echo "  a  這台電腦已經安裝 Ollama"
            echo "  b  讓 Docker 一起跑 Ollama（不用另外安裝）"
            echo "  c  讓 Docker 一起跑 Ollama，並使用 NVIDIA 顯示卡"
            printf '選擇 a / b / c [a]: '
            read -r where || where=""
            case "${where:-a}" in
                b) set_value RESEARCH_OLLAMA_CONTAINER true
                   echo "start 會自動下載模型 $(get_value RESEARCH_MODEL)。" ;;
                c) set_value RESEARCH_OLLAMA_CONTAINER gpu
                   echo "start 會自動下載模型 $(get_value RESEARCH_MODEL)。" ;;
                *) set_value RESEARCH_OLLAMA_CONTAINER ""
                   echo "記得先安裝 Ollama 並執行：ollama pull $(get_value RESEARCH_MODEL | sed 's#^ollama/##')" ;;
            esac
            ;;
    esac
}

check_model_source() {
    model=$(get_value RESEARCH_MODEL)
    gputw=$(get_value GPUTW_OLLAMA_BASE_URL)
    if [ "$(get_value RESEARCH_DEMO_MODE)" = true ]; then
        echo "[INFO] 模型來源：展示模式（內建合成 provider，不呼叫任何模型）"
    elif [ -n "$model" ] && [ "${model#ollama/}" = "$model" ]; then
        case "${model%%/*}" in
            openrouter) key=OPENROUTER_API_KEY ;; openai) key=OPENAI_API_KEY ;; gemini) key=GEMINI_API_KEY ;; *) key="" ;;
        esac
        if [ -z "$key" ]; then echo "[WARN] 模型來源：雲端 API · $model · 無法判斷需要哪把金鑰"
        elif [ -n "$(get_value "$key")" ]; then echo "[OK] 模型來源：雲端 API · $model · $key 已設定"
        else echo "[FAIL] 模型來源：雲端 API · $model · 缺少 $key"; fi
    elif [ -n "$gputw" ]; then
        token=$(get_value GPUTW_OLLAMA_API_KEY)
        if curl -fsS -m 10 -H "Authorization: Bearer $token" "${gputw%/}/api/tags" >/dev/null 2>&1; then
            echo "[OK] 模型來源：GPUtw 遠端 Ollama 已連線 · $model"
        else
            echo "[FAIL] 模型來源：GPUtw 遠端 Ollama 連不上；確認執行個體已啟動、位址與存取 key 正確"
        fi
    elif [ -n "$(ollama_container)" ]; then
        if $COMPOSE exec -T ollama ollama list 2>/dev/null | grep -q "${model#ollama/}"; then
            echo "[OK] 模型來源：Docker 內的 Ollama 已就緒 · $model"
        else
            echo "[FAIL] 模型來源：Docker 內的 Ollama 尚未啟動或還沒下載 $model；執行 ./research.sh start"
        fi
    elif curl -fsS -m 5 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
        echo "[OK] 模型來源：本機 Ollama 已連線 · $model"
    else
        echo "[FAIL] 模型來源：本機 Ollama 未連線；請安裝並啟動 Ollama，或執行 ./research.sh setup 改選 GPUtw／雲端 API"
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
        echo "設定值只寫入 Git 忽略的 .env.research；秘密輸入不會顯示在畫面。"
        ask SEC_USER_AGENT "SEC 研究名稱與聯絡信箱"
        ask FRED_API_KEY "FRED API key" secret
        ask ALPHA_VANTAGE_API_KEY "Alpha Vantage API key" secret
        choose_model_source
        echo "設定完成。執行 ./research.sh doctor 檢查，或 ./research.sh start 啟動。"
        ;;
    start)
        need_docker
        ensure_env
        compose_files
        $COMPOSE up -d --build
        wait_health
        if [ -n "$(ollama_container)" ] && [ "$(get_value RESEARCH_DEMO_MODE)" != true ]; then
            model=$(get_value RESEARCH_MODEL)
            case "$model" in ollama/*)
                echo "[INFO] 在 Docker 內的 Ollama 下載 ${model#ollama/}（第一次需要幾分鐘，已下載會直接略過）…"
                $COMPOSE exec -T ollama ollama pull "${model#ollama/}" ;;
            esac
        fi
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
    cli)
        # Interactive stance-shift inside the same image and data volume as the web service.
        need_docker
        ensure_env
        shift
        $COMPOSE run --rm research python -m research_service.cli "$@"
        ;;
    doctor)
        need_docker
        echo "[OK] Docker 與 Compose 可用，engine 已啟動"
        [ -f .env.research ] && echo "[OK] .env.research 存在" || echo "[INFO] 尚無 .env.research；start 會自動建立"
        check_model_source
        curl -fsS "$URL/health" >/dev/null 2>&1 && echo "[OK] 網站服務 healthy" || echo "[INFO] 網站尚未啟動"
        ;;
    *)
        cat <<'EOF'
用法：./research.sh <命令>
  setup   第一次設定：資料來源金鑰與模型來源（本機／GPUtw／雲端 API）
  start   建置並啟動研究台（http://127.0.0.1:8000/）
  stop    停止服務（資料保留）
  status  顯示容器與健康狀態
  logs    追蹤服務日誌
  doctor  檢查 Docker、Ollama 與服務狀態

.env.research 的 RESEARCH_OLLAMA_CONTAINER=true（或 gpu）會讓 Docker 一起跑 Ollama。
  test    在容器內執行單元測試
  cli     在容器內執行 stance-shift（不加參數會一步步問股票、日期、模型）
研究操作（建立資料集、執行實驗、匯出）請在網頁介面完成。
EOF
        ;;
esac
