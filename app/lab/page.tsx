import type { Metadata } from "next";
import Link from "next/link";
import { chatGPTSignInPath, getChatGPTUser } from "../chatgpt-auth";
import { RunLauncher } from "./RunLauncher";
import styles from "./lab.module.css";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "建立新實驗",
  description: "選擇股票與歷史分析日，啟動四種多代理人決策方法的公平比較。",
};

export default async function LabPage() {
  const user = await getChatGPTUser();

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
        <h1>把同一份證據，交給四種決策機制。</h1>
        <p>
          系統會先鎖定分析日當下可取得的資料，再依序完成 A、B、C、D 四組比較；
          任何未來價格都必須等決策鎖定後才會解封。
        </p>
      </section>

      {user ? (
        <RunLauncher displayName={user.displayName} />
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

      <aside className={styles.notice}>
        <strong>研究用途聲明</strong>
        <span>本系統是歷史研究實驗，不構成投資建議，也不連接券商或執行交易。</span>
      </aside>
    </main>
  );
}
