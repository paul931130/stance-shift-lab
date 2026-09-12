"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import styles from "./lab.module.css";

const TICKERS = ["AAPL", "NVDA", "GOOGL", "MSFT", "AMZN", "JPM", "MCD", "LLY", "ASTS", "GE"] as const;

const DATES = Array.from({ length: 5 }, (_, yearIndex) => {
  const year = 2021 + yearIndex;
  return ["03-31", "06-30", "09-30", "12-31"].map((tail) => `${year}-${tail}`);
}).flat();

type Mode = "demo" | "local" | "live";

type LocalModelState = {
  enabled: boolean;
  ready: boolean;
  model: string;
  message: string;
};

export function RunLauncher({ displayName, localModel }: { displayName: string; localModel: LocalModelState }) {
  const router = useRouter();
  const [ticker, setTicker] = useState<(typeof TICKERS)[number]>("NVDA");
  const [analysisDate, setAnalysisDate] = useState("2024-12-31");
  const [mode, setMode] = useState<Mode>(localModel.enabled ? "local" : "demo");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);

  const estimate = useMemo(
    () =>
      mode === "demo"
        ? "不使用模型運算，完整重播流程"
        : mode === "local"
          ? `固定 20 次本機推論 · ${localModel.model}`
          : "固定 20 個 Gemini 邏輯模型呼叫",
    [localModel.model, mode],
  );
  const modeReady = mode !== "local" || localModel.ready;

  async function startRun() {
    setSubmitting(true);
    setError(null);
    try {
      const response = await fetch("/api/runs", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ ticker, analysisDate, mode }),
      });
      const payload = (await response.json()) as {
        id?: string;
        run?: { id?: string };
        error?: string | { message?: string; details?: { runId?: string } };
      };
      if (!response.ok) {
        if (typeof payload.error === "object" && payload.error.details?.runId) {
          setActiveRunId(payload.error.details.runId);
        }
        const detail = typeof payload.error === "string" ? payload.error : payload.error?.message;
        throw new Error(detail ?? "目前無法建立實驗，請稍後重試。");
      }
      const id = payload.id ?? payload.run?.id;
      if (!id) throw new Error("伺服器沒有回傳實驗編號。");
      router.push(`/runs/${encodeURIComponent(id)}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "建立實驗時發生未知錯誤。");
      setSubmitting(false);
    }
  }

  return (
    <section className={styles.launcher} aria-labelledby="launcher-title">
      <div className={styles.launcherHead}>
        <div>
          <p className={styles.cardIndex}>SIGNED IN · {displayName}</p>
          <h2 id="launcher-title">設定歷史研究案例</h2>
        </div>
        <span className={styles.guardBadge}>Future-data gate · ON</span>
      </div>

      <div className={styles.fieldGrid}>
        <label>
          <span>股票代號</span>
          <select value={ticker} onChange={(event) => setTicker(event.target.value as typeof ticker)}>
            {TICKERS.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
        </label>
        <label>
          <span>分析日期</span>
          <select value={analysisDate} onChange={(event) => setAnalysisDate(event.target.value)}>
            {DATES.map((date) => (
              <option key={date} value={date}>{date}</option>
            ))}
          </select>
        </label>
      </div>

      <fieldset className={styles.modeFieldset}>
        <legend>執行模式</legend>
        {localModel.enabled ? (
          <label className={localModel.ready ? (mode === "local" ? styles.modeSelected : styles.modeOption) : styles.modeDisabled}>
            <input
              type="radio"
              name="mode"
              value="local"
              checked={mode === "local"}
              disabled={!localModel.ready}
              onChange={() => setMode("local")}
            />
            <span>
              <strong>本機基礎模型（推薦）</strong>
              <small>Ollama · {localModel.model}。推論與研究資料都留在這台電腦。</small>
              <em>{localModel.message}</em>
            </span>
          </label>
        ) : null}
        <label className={mode === "demo" ? styles.modeSelected : styles.modeOption}>
          <input type="radio" name="mode" value="demo" checked={mode === "demo"} onChange={() => setMode("demo")} />
          <span><strong>可重現示範</strong><small>使用固定種子與內建證據，適合先體驗完整網站。</small></span>
        </label>
        {!localModel.enabled ? (
          <label className={mode === "live" ? styles.modeSelected : styles.modeOption}>
            <input type="radio" name="mode" value="live" checked={mode === "live"} onChange={() => setMode("live")} />
            <span><strong>Gemini 新實驗</strong><small>相同快照、相同模型設定，依序完成四組比較。</small></span>
          </label>
        ) : null}
      </fieldset>

      <div className={styles.callPlan} aria-label="模型呼叫配置">
        <span>A 單次判斷 <b>1</b></span>
        <span>B 自我一致性 <b>5</b></span>
        <span>C 固定辯論 <b>7</b></span>
        <span>D 立場交換 <b>7</b></span>
      </div>

      <div className={styles.actionRow}>
        <div>
          <strong>{estimate}</strong>
          <small>請保持頁面開啟以自動推進；離開後可從下方歷史紀錄續跑。</small>
        </div>
        <button className={styles.primaryButton} type="button" disabled={submitting || !modeReady} onClick={startRun}>
          {submitting ? "正在建立…" : "開始四組比較"}
        </button>
      </div>
      {localModel.enabled && !localModel.ready ? <p className={styles.error} role="alert">{localModel.message} 啟動 Ollama 後，<button type="button" onClick={() => router.refresh()}>重新檢查連線</button>。示範模式須手動選擇。</p> : null}
      {error ? <p className={styles.error} role="alert">{error}</p> : null}
      {activeRunId ? <Link className={styles.primaryButton} href={`/runs/${activeRunId}`}>返回未完成的實驗</Link> : null}
    </section>
  );
}
