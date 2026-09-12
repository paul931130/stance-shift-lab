"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import styles from "./run.module.css";

type EventItem = { id?: string | number; type?: string; message?: string; createdAt?: string; stepKey?: string };
type ArtifactItem = { id: string; kind?: string; fileName?: string; downloadUrl?: string; byteSize?: number };
type StepItem = {
  index: number; groupCode: string; round: number | null; agentId: string; stance: string; status: string;
  output?: { decision: string; thesis: string; argument: string; counterpoint: string; evidenceIds: string[] } | null;
};
type ResultItem = {
  group?: string;
  method?: string;
  groupCode?: string;
  decision?: string;
  finalDecision?: string;
  confidence?: number;
  rationale?: string;
  thesis?: string;
  roleSwitched?: boolean;
};
type RunRecord = {
  id: string;
  ticker?: string;
  analysisDate?: string;
  analysis_date?: string;
  mode?: string;
  providerMode?: string;
  model?: string;
  status?: string;
  currentStep?: number;
  current_step?: string;
  completedSteps?: number;
  completed_steps?: number;
  totalSteps?: number;
  total_steps?: number;
  logicalCalls?: number;
  logical_calls?: number;
  events?: EventItem[];
  results?: ResultItem[];
  artifacts?: ArtifactItem[];
  steps?: StepItem[];
  exportsReady?: boolean;
  providerAttempts?: number;
  errorMessage?: string | null;
  error?: string | null;
};

const TERMINAL = new Set(["completed", "failed", "cancelled", "invalid"]);
const STAGES = ["A 單次", "B 一致性", "C 固定辯論", "D 立場交換", "回測與匯出"];

function decisionLabel(value?: string) {
  const key = value?.toUpperCase();
  return key === "BUY" ? "看多" : key === "SELL" ? "看空" : key === "NOTRADE" || key === "NO_TRADE" ? "證據不足" : "中立";
}

function decisionClass(value?: string) {
  const key = value?.toUpperCase();
  return key === "BUY" ? styles.buy : key === "SELL" ? styles.sell : key?.includes("NO") ? styles.noTrade : styles.hold;
}

function normalize(payload: unknown): RunRecord {
  const source = payload as { run?: RunRecord; events?: EventItem[]; results?: ResultItem[]; artifacts?: ArtifactItem[]; steps?: StepItem[] } & RunRecord;
  const run = source.run ?? source;
  return {
    ...run,
    events: source.events ?? run.events ?? [],
    results: source.results ?? run.results ?? [],
    artifacts: source.artifacts ?? run.artifacts ?? [],
    steps: source.steps ?? run.steps ?? [],
  };
}

function responseError(payload: unknown, fallback: string): string {
  const error = (payload as { error?: string | { message?: string } } | null)?.error;
  return typeof error === "string" ? error : error?.message ?? fallback;
}

export function RunConsole({ runId }: { runId: string }) {
  const [run, setRun] = useState<RunRecord | null>(null);
  const [autoRun, setAutoRun] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const advancing = useRef(false);
  const idempotencyKeys = useRef(new Map<number, string>());
  const [retryAfterMs, setRetryAfterMs] = useState(450);

  const load = useCallback(async () => {
    const response = await fetch(`/api/runs/${encodeURIComponent(runId)}`, { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok) throw new Error(responseError(payload, "無法讀取這份實驗卷宗。"));
    const next = normalize(payload);
    setRun(next);
    return next;
  }, [runId]);

  const advance = useCallback(async () => {
    if (advancing.current) return;
    advancing.current = true;
    setBusy(true);
    try {
      const stepIndex = Number(run?.currentStep ?? run?.current_step ?? 0);
      const idempotencyKey = idempotencyKeys.current.get(stepIndex) ?? crypto.randomUUID();
      idempotencyKeys.current.set(stepIndex, idempotencyKey);
      const response = await fetch(`/api/runs/${encodeURIComponent(runId)}/advance`, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "Idempotency-Key": idempotencyKey,
        },
        body: JSON.stringify({ expectedStep: run?.currentStep ?? run?.current_step ?? null }),
      });
      const payload = await response.json();
      if (!response.ok) {
        idempotencyKeys.current.delete(stepIndex);
        await load();
        throw new Error(responseError(payload, "此步驟暫時無法執行。"));
      }
      setRetryAfterMs(response.status === 202 ? Math.max(1500, Math.min(5000, Number(payload.retryAfterMs) || 1500)) : 450);
      const next = await load();
      const nextStep = Number(next.currentStep ?? next.current_step ?? 0);
      if (nextStep !== stepIndex) idempotencyKeys.current.delete(stepIndex);
      setMessage(null);
    } catch (caught) {
      // Unknown network outcomes retain their key; the server can safely replay.
      setAutoRun(false);
      setMessage(caught instanceof Error ? caught.message : "執行時發生未知錯誤。");
    } finally {
      setBusy(false);
      advancing.current = false;
    }
  }, [load, run, runId]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void load().catch((caught) => setMessage(caught instanceof Error ? caught.message : "無法讀取實驗。"));
    }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  useEffect(() => {
    if (!run || !autoRun || TERMINAL.has(run.status ?? "") || busy) return;
    const timer = window.setTimeout(() => void advance(), retryAfterMs);
    return () => window.clearTimeout(timer);
  }, [advance, autoRun, busy, run, retryAfterMs]);

  const completed = run?.completedSteps ?? run?.completed_steps ?? 0;
  const total = run?.totalSteps ?? run?.total_steps ?? 20;
  const progress = Math.min(100, Math.round((completed / Math.max(1, total)) * 100));
  const events = run?.events ?? [];
  const results = run?.results ?? [];
  const isTerminal = TERMINAL.has(run?.status ?? "");
  const isLocalModel = run?.providerMode === "ollama-local";
  const providerLabel = isLocalModel
    ? `本機模型 · ${run?.model ?? "Ollama"}`
    : run?.providerMode === "gemini"
      ? "Gemini 新實驗"
      : "可重現示範";
  const statusText = run?.status === "completed" ? "已完成" : run?.status === "failed" ? "需要處理" : run?.status === "cancelled" ? "已取消" : busy ? (isLocalModel ? "本機推論中" : "正在推進") : autoRun ? "自動執行中" : "已暫停";

  async function cancel() {
    setBusy(true);
    try {
      const response = await fetch(`/api/runs/${encodeURIComponent(runId)}/cancel`, { method: "POST" });
      const payload = await response.json();
      if (!response.ok) throw new Error(responseError(payload, "無法取消實驗。"));
      setAutoRun(false);
      await load();
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "無法取消實驗。");
    } finally {
      setBusy(false);
    }
  }

  const stageIndex = useMemo(() => completed < 1 ? 0 : completed < 6 ? 1 : completed < 13 ? 2 : completed < 20 ? 3 : 4, [completed]);

  async function repairExports() {
    setBusy(true);
    try {
      const response = await fetch(`/api/runs/${encodeURIComponent(runId)}/exports`, { method: "POST" });
      const payload = await response.json();
      if (!response.ok) throw new Error(responseError(payload, "匯出失敗，請稍後重試。"));
      await load();
      setMessage(null);
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "匯出失敗。");
    } finally { setBusy(false); }
  }

  return (
    <>
      <section className={styles.hero}>
        <div>
          <p className={styles.eyebrow}>RESEARCH DOSSIER · {runId.slice(0, 8)}</p>
          <h1>{run?.ticker ?? "—"} <span>/</span> {run?.analysisDate ?? run?.analysis_date ?? "讀取中"}</h1>
          <p>四種方法共用合成示範證據；D 組第 2 輪必須交換立場。回測價格也為合成資料，非真實市場績效。</p>
        </div>
        <div className={styles.statusBlock} aria-live="polite">
          <span className={styles.statusDot} data-active={!isTerminal} />
          <div><small>STATUS</small><strong>{statusText}</strong></div>
        </div>
      </section>

      <section className={styles.progressPanel} aria-label="執行進度">
        <div className={styles.progressTop}>
          <span>{STAGES[stageIndex]}</span><strong>{progress}%</strong>
        </div>
        <div className={styles.progressTrack} role="progressbar" aria-label="模型步驟" aria-valuemin={0} aria-valuemax={total} aria-valuenow={completed}><span style={{ width: `${progress}%` }} /></div>
        <div className={styles.stageLabels}>{STAGES.map((stage, index) => <span className={index <= stageIndex ? styles.stageDone : ""} key={stage}>{stage}</span>)}</div>
      </section>

      <section className={styles.controlBar}>
        <div><strong>{providerLabel}</strong><span>邏輯呼叫 {run?.logicalCalls ?? run?.logical_calls ?? Math.min(20, completed)} / 20</span></div>
        <div className={styles.controls}>
          {!isTerminal ? <button type="button" className={styles.secondaryButton} onClick={() => setAutoRun((value) => !value)}>{autoRun ? "暫停自動執行" : "繼續自動執行"}</button> : null}
          {!isTerminal ? <button type="button" className={styles.textButton} disabled={busy} onClick={cancel}>取消</button> : null}
          {isTerminal ? <Link className={styles.primaryButton} href="/lab">建立另一份實驗</Link> : null}
        </div>
      </section>

      <p className={styles.operationNote}>已保存 {completed}/{total} 步 · 模型嘗試 {run?.providerAttempts ?? 0}/25。暫停會等目前步驟完成；關閉頁面後不會持續自動推進，可從「實驗紀錄」返回。</p>

      {message ? <p className={styles.error} role="alert">{message}</p> : null}
      {run?.errorMessage && !message ? <p className={styles.error} role="alert">{run.errorMessage}</p> : null}
      {run?.status === "completed" && !run.exportsReady ? <p className={styles.error}>決策已保存，但匯出檔尚未齊全。<button className={styles.secondaryButton} disabled={busy} onClick={() => void repairExports()}>重試產生下載檔</button></p> : null}

      <section className={styles.grid}>
        <article className={styles.timeline}>
          <div className={styles.sectionHead}><p>STATE TRACE</p><h2>執行軌跡</h2></div>
          <ol>
            {events.length ? events.slice().reverse().map((event, index) => (
              <li key={event.id ?? `${event.stepKey}-${index}`}>
                <span>{String(events.length - index).padStart(2, "0")}</span>
                <div><strong>{event.message ?? event.stepKey ?? event.type ?? "完成一個步驟"}</strong><small>{event.createdAt ?? "已保存至研究卷宗"}</small></div>
              </li>
            )) : <li><span>00</span><div><strong>等待第一個研究步驟</strong><small>建立後會自動開始</small></div></li>}
          </ol>
        </article>

        <article className={styles.matrix}>
          <div className={styles.sectionHead}><p>DECISION MATRIX</p><h2>四組決策</h2></div>
          <div className={styles.resultGrid}>
            {["A", "B", "C", "D"].map((group) => {
              const result = results.find((item) => (item.group ?? item.method ?? item.groupCode)?.startsWith(group));
              const decision = result?.decision ?? result?.finalDecision;
              return (
                <div className={group === "D" ? styles.roleCard : styles.resultCard} key={group}>
                  <div><span>GROUP {group}</span>{group === "D" ? <em>ROUND 2 ↔</em> : null}</div>
                  <strong className={decisionClass(decision)}>{result ? decisionLabel(decision) : "待決策"}</strong>
                  <small>{result?.confidence != null ? `信心 ${Math.round(result.confidence * 100)}%` : group === "A" ? "單次判斷" : group === "B" ? "5 次多數決" : group === "C" ? "固定立場辯論" : "強制交換立場"}</small>
                  {result?.rationale ?? result?.thesis ? <p>{result.rationale ?? result?.thesis}</p> : null}
                </div>
              );
            })}
          </div>
        </article>
      </section>

      <section className={styles.transcript} aria-labelledby="transcript-title">
        <div className={styles.sectionHead}><p>AGENT TRANSCRIPT</p><h2 id="transcript-title">逐步論證與立場交換</h2></div>
        {(run?.steps ?? []).filter((step) => step.output).map((step) => <details key={step.index}>
          <summary>{String(step.index + 1).padStart(2, "0")} · {step.groupCode} 組 · {step.agentId} · {step.round ? `第 ${step.round} 輪 · ` : ""}{step.stance}{step.groupCode === "D" && step.round === 2 ? " ↔ 交換立場" : ""}</summary>
          <div><h3>{step.output?.thesis}</h3><p>{step.output?.argument}</p><p><strong>反方觀點：</strong>{step.output?.counterpoint}</p><p><strong>證據：</strong>{step.output?.evidenceIds.join("、")}</p></div>
        </details>)}
        {!completed ? <p>完成第一個步驟後，即可展開查看模型的論證。</p> : null}
      </section>

      {run?.status === "completed" && (run.artifacts?.length ?? 0) > 0 ? (
        <section className={styles.downloads} aria-labelledby="downloads-title">
          <div className={styles.sectionHead}><p>REPRODUCIBLE OUTPUTS</p><h2 id="downloads-title">下載研究產物</h2></div>
          <div>
            {run.artifacts?.map((artifact) => (
              <a key={artifact.id} href={artifact.downloadUrl ?? `/api/runs/${runId}/artifacts/${artifact.id}`}>
                <span>{artifact.fileName ?? artifact.kind ?? "artifact"}</span>
                <small>{artifact.byteSize ? `${Math.max(1, Math.round(artifact.byteSize / 1024))} KB` : "DOWNLOAD"}</small>
              </a>
            ))}
          </div>
        </section>
      ) : null}

      <footer className={styles.disclaimer}>AI 研究實驗。合成示範證據與回測價格不能證明投資績效，不構成投資建議。</footer>
    </>
  );
}
