import type { Metadata } from "next";
import { InteriorHero, SiteFooter, SiteHeader } from "../components/site-shell";

export const metadata: Metadata = {
  title: "公開案例｜立場交換研究室",
  description: "瀏覽經過審核、可追溯證據的多代理人決策研究案例。",
};

const cases = [
  { id: "CASE 024", ticker: "ASTS", date: "2024 · Q4", result: "中立", tone: "hold", evidence: "12 項證據", note: "角色交換後，由看多修正為中立" },
  { id: "CASE 018", ticker: "NVDA", date: "2023 · Q3", result: "看多", tone: "buy", evidence: "15 項證據", note: "四組方法結論一致" },
  { id: "CASE 011", ticker: "JPM", date: "2022 · Q4", result: "證據不足", tone: "none", evidence: "7 項證據", note: "Gatekeeper 阻擋方向性結論" },
  { id: "CASE 006", ticker: "MCD", date: "2022 · Q1", result: "看空", tone: "sell", evidence: "13 項證據", note: "固定辯論與立場交換出現分歧" },
];

export default function CasesPage() {
  return (
    <div className="site-frame">
      <a className="skip-link" href="#main-content">跳至主要內容</a>
      <SiteHeader />
      <main id="main-content">
        <InteriorHero index="01" eyebrow="PUBLIC CASE ARCHIVE" title="公開案例卷宗" description="只展示經過來源、時間邊界與研究流程檢查的案例。每份卷宗都能回看四組方法如何從同一份證據走向不同結論。" />
        <section className="section-shell archive-section" aria-labelledby="archive-title">
          <div className="archive-toolbar">
            <div><p className="section-kicker">CURATED DOSSIERS</p><h2 id="archive-title">精選研究紀錄</h2></div>
            <p>目前展示介面示例；正式公開的研究資料將標示真實來源與完整時間戳。</p>
          </div>
          <div className="case-grid">
            {cases.map((item) => (
              <article className="case-card" key={item.id}>
                <header><span>{item.id}</span><span>{item.date}</span></header>
                <div className="case-symbol">{item.ticker}<small>NASDAQ / NYSE</small></div>
                <div className="case-outcome"><span>立場交換結論</span><strong className={`outcome outcome--${item.tone}`}>{item.result}</strong></div>
                <p>{item.note}</p>
                <footer><span>{item.evidence}</span><span>查看卷宗 <i aria-hidden="true">→</i></span></footer>
              </article>
            ))}
          </div>
          <div className="archive-note"><strong>資料公開原則</strong><p>私人研究不會自動進入公開案例庫。只有完成來源稽核並由管理者核准的案例，才會出現在此頁。</p></div>
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}
