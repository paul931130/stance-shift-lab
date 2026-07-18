"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import styles from "./run.module.css";

type EventItem = { id?: string | number; type?: string; message?: string; createdAt?: string; stepKey?: string };
type ArtifactItem = { id: string; kind?: string; fileName?: string; downloadUrl?: string; byteSize?: number };
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
  status?: string;
  currentStep?: string;
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
  error?: string | null;
};

const TERMINAL = new Set(["completed", "failed", "cancelled", "invalid"]);
const STAGES = ["資料快照", "四域研究", "A 單次", "B 一致性", "C 固定辯論", "D 立場交換", "證據閘門", "回測與匯出"];

function decisionLabel(value?: string) {
  const key = value?.toUpperCase();
  return key === "BUY" ? "看多" : key === "SELL" ? "看空" : key === "NOTRADE" || key === "NO_TRADE" ? "證據不足" : "中立";
}

function decisionClass(value?: string) {
  const key = value?.toUpperCase();
  return key === "BUY" ? styles.buy : key === "SELL" ? styles.sell : key?.includes("NO") ? styles.noTrade : styles.hold;
}

function normalize(payload: unknown): RunRecord {
  const source = payload as { run?: RunRecord; events?: EventItem[]; results?: ResultItem[]; artifacts?: ArtifactItem[] } & RunRecord;
  const run = source.run ?? source;
  return {
    ...run,
    events: source.events ?? run.events ?? [],
    results: source.results ?? run.results ?? [],
    artifacts: source.artifacts ?? run.artifacts ?? [],
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
      if (!response.ok && response.status !== 409) throw new Error(responseError(payload, "此步驟暫時無法執行。"));
      const next = await load();
      const nextStep = Number(next.currentStep ?? next.current_step ?? 0);
      if (nextStep !== stepIndex) idempotencyKeys.current.delete(stepIndex);
      setMessage(null);
    } catch (caught) {
      const stepIndex = Number(run?.currentStep ?? run?.current_step ?? 0);
      idempotencyKeys.current.delete(stepIndex);
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
    const timer = window.setTimeout(() => void advance(), 450);
    return () => window.clearTimeout(timer);
  }, [advance, autoRun, busy, run]);

  const completed = run?.completedSteps ?? run?.completed_steps ?? 0;
  const total = run?.totalSteps ?? run?.total_steps ?? 25;
  const progress = Math.min(100, Math.round((completed / Math.max(1, total)) * 100));
  const events = run?.events ?? [];
  const results = run?.results ?? [];
  const isTerminal = TERMINAL.has(run?.status ?? "");
  const statusText = run?.status === "completed" ? "已完成" : run?.status === "failed" ? "需要處理" : run?.status === "cancelled" ? "已取消" : busy ? "正在推進" : autoRun ? "自動執行中" : "已暫停";

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

  const stageIndex = useMemo(() => Math.min(STAGES.length - 1, Math.floor(progress / (100 / STAGES.length))), [progress]);

  return (
    <>
      <section className={styles.hero}>
        <div>
          <p className={styles.eyebrow}>RESEARCH DOSSIER · {runId.slice(0, 8)}</p>
          <h1>{run?.ticker ?? "—"} <span>/</span> {run?.analysisDate ?? run?.analysis_date ?? "讀取中"}</h1>
          <p>四種方法共用同一份已鎖定證據；D 組第 2 輪必須交換立場。</p>
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
        <div className={styles.progressTrack}><span style={{ width: `${progress}%` }} /></div>
        <div className={styles.stageLabels}>{STAGES.map((stage, index) => <span className={index <= stageIndex ? styles.stageDone : ""} key={stage}>{stage}</span>)}</div>
      </section>

      <section className={styles.controlBar}>
        <div><strong>{run?.providerMode === "gemini" ? "Gemini 新實驗" : "可重現示範"}</strong><span>邏輯呼叫 {run?.logicalCalls ?? run?.logical_calls ?? Math.min(20, completed)} / 20</span></div>
        <div className={styles.controls}>
          {!isTerminal ? <button type="button" className={styles.secondaryButton} onClick={() => setAutoRun((value) => !value)}>{autoRun ? "暫停自動執行" : "繼續自動執行"}</button> : null}
          {!isTerminal ? <button type="button" className={styles.textButton} disabled={busy} onClick={cancel}>取消</button> : null}
          {isTerminal ? <Link className={styles.primaryButton} href="/lab">建立另一份實驗</Link> : null}
        </div>
      </section>

      {message ? <p className={styles.error} role="alert">{message}</p> : null}

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

      <footer className={styles.disclaimer}>AI 研究實驗，不構成投資建議。所有歷史回測皆不代表未來績效。</footer>
    </>
  );
}
