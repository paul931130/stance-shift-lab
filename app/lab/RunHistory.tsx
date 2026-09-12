"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import styles from "./lab.module.css";

type SavedRun = {
  id: string; ticker: string; analysisDate: string; status: string;
  model: string; executionMode: string; completedSteps: number; totalSteps: number;
};
const labels: Record<string, string> = { queued: "待續跑", running: "執行中／可續跑", completed: "已完成", failed: "執行失敗", cancelled: "已取消" };

export function RunHistory() {
  const [runs, setRuns] = useState<SavedRun[] | null>(null);
  const [error, setError] = useState("");
  const refresh = useCallback(async () => {
    try {
      const response = await fetch("/api/runs", { cache: "no-store" });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error?.message ?? "無法讀取歷史紀錄。");
      setRuns(body.runs);
      setError("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "無法讀取歷史紀錄。");
    }
  }, []);
  useEffect(() => {
    const timer = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(timer);
  }, [refresh]);

  return <section className={styles.history} aria-labelledby="history-title">
    <div className={styles.launcherHead}>
      <h2 id="history-title">我的實驗紀錄</h2>
      <button type="button" onClick={() => void refresh()}>重新整理</button>
    </div>
    <p>未完成的實驗優先顯示，其餘顯示最近紀錄（最多 100 筆）。進度保存在此電腦。</p>
    {error ? <p className={styles.error} role="alert">{error}</p> : null}
    {!runs && !error ? <p role="status">讀取中…</p> : null}
    {runs?.length === 0 ? <p>尚未建立實驗。選擇上方模型與案例即可開始。</p> : null}
    <ul>{runs?.map((run) => <li key={run.id}>
      <div><strong>{run.ticker} · {run.analysisDate}</strong><small>{run.executionMode === "demo" ? "固定示範" : run.model} · {run.id.slice(0, 8)}</small></div>
      <span>{labels[run.status] ?? run.status} · {run.completedSteps}/{run.totalSteps}</span>
      <Link href={`/runs/${run.id}`}>{["queued", "running"].includes(run.status) ? "開啟並續跑" : "查看結果"} →</Link>
    </li>)}</ul>
  </section>;
}
