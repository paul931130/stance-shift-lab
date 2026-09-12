import type { Metadata } from "next";
import Link from "next/link";
import { RunConsole } from "./RunConsole";
import styles from "./run.module.css";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "實驗卷宗",
  description: "查看多代理人辯論的執行軌跡、證據與決策結果。",
};

export default async function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <main className={styles.shell}>
      <header className={styles.header}>
        <Link className={styles.brand} href="/"><span>SS</span>立場交換研究室</Link>
        <nav aria-label="實驗導覽"><Link href="/lab">實驗紀錄／新實驗</Link><Link href="/cases">公開案例</Link></nav>
      </header>
      <RunConsole runId={id} />
    </main>
  );
}
