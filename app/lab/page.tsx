import type { Metadata } from "next";
import Link from "next/link";
import { chatGPTSignInPath, getChatGPTUser } from "../chatgpt-auth";
import { getRuntimeBindings } from "@/db";
import { inspectOllama } from "@/lib/server/ollama";
import { RunLauncher } from "./RunLauncher";
import { RunHistory } from "./RunHistory";
import styles from "./lab.module.css";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "建立新實驗",
  description: "選擇股票與歷史分析日，啟動四種多代理人決策方法的公平比較。",
};

export default async function LabPage() {
  const user = await getChatGPTUser();
  const runtime = getRuntimeBindings();
  const localEnabled = runtime.APP_ENV === "development" && runtime.LOCAL_MODE === "true";
  const localModel = runtime.OLLAMA_MODEL?.trim() || "gemma3:4b";
  const localModelState = localEnabled
    ? await inspectOllama({
        baseUrl: runtime.OLLAMA_BASE_URL?.trim() || "http://127.0.0.1:11434",
        model: localModel,
      })
    : null;

  return (
    <main className={styles.shell}>
      <header className={styles.header}>
        <Link className={styles.brand} href="/">
          <span className={styles.brandMark}>SS</span>
          <span>立場交換研究室</span>
        </Link>
        <nav aria-label="主要導覽">
          <Link href="/cases">公開案例</Link>
          <Link href="/methodology">研究方法</Link>
        </nav>
      </header>

      <section className={styles.intro}>
        <p className={styles.eyebrow}>NEW EXPERIMENT · 新實驗</p>
        <h1>{localEnabled ? "地端多代理人實驗台" : "把同一份證據，交給四種決策機制。"}</h1>
        <p>
          同一份證據、四組方法、20 個步驟。Ollama 負責本機推論，D 組只在第二輪交換立場。
        </p>
      </section>

      <p className={styles.dataNotice}>資料來源：合成示範快照（deterministic-demo-v1），不是實際歷史行情或新聞。即使使用本機模型，回測數字也僅供驗證流程。</p>

      {user ? (
        <RunLauncher
          displayName={user.displayName}
          localModel={localModelState ? { enabled: true, ...localModelState } : { enabled: false, ready: false, model: localModel, message: "" }}
        />
      ) : (
        <section className={styles.signInCard} aria-labelledby="signin-title">
          <div>
            <p className={styles.cardIndex}>AUTHENTICATED LAB</p>
            <h2 id="signin-title">登入後開始可續跑的私人實驗</h2>
            <p>
              登入只用來保存你的執行進度與限制他人讀取；公開方法與核准案例不需要登入。
            </p>
          </div>
          <Link className={styles.primaryButton} href={chatGPTSignInPath("/lab")}>
            使用 ChatGPT 登入
          </Link>
        </section>
      )}

      {user ? <RunHistory /> : null}

      <aside className={styles.notice}>
        <strong>研究用途聲明</strong>
        <span>本系統是歷史研究實驗，不構成投資建議，也不連接券商或執行交易。</span>
      </aside>
    </main>
  );
}
