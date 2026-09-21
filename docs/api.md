# API review surface

FastAPI 的 generated contract 已開放：

- `/docs`：Swagger UI
- `/redoc`：ReDoc
- `/openapi.json`：機器可讀 schema

在 remote mode，這些路徑與其他 API 一樣需要研究室 access key；local mode 仍只接受 loopback。`GET /api/jobs/{id}` 預設只回傳 config、status 與 progress summary，避免把完整 trace、cases、daily returns 一次送出；UI 需要完整 state 時使用 `?detail=true`。

研究報告、pilot 與穩定性分開提供：

- `GET /api/studies/{protocol_hash}`：主要 summary 與正式統計 gate
- `GET /api/studies/{protocol_hash}/pilot`：機制辨識與品質診斷
- `GET /api/studies/{protocol_hash}/stability`：重複完整執行的描述統計

