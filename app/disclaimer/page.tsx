import type { Metadata } from "next";
import { InteriorHero, SiteFooter, SiteHeader } from "../components/site-shell";

export const metadata: Metadata = {
  title: "使用聲明｜立場交換研究室",
  description: "立場交換研究室的研究用途、資料來源與隱私說明。",
};

export default function DisclaimerPage() {
  return (
    <div className="site-frame">
      <a className="skip-link" href="#main-content">跳至主要內容</a>
      <SiteHeader />
      <main id="main-content">
        <InteriorHero
          index="03"
          eyebrow="RESEARCH NOTICE"
          title="使用聲明與研究邊界"
          description="這是一套用來觀察 AI 決策機制的研究工具。清楚知道它不做什麼，與理解它如何運作同樣重要。"
        />
        <section className="section-shell notice-grid">
          <article><span>01</span><div><h2>非投資建議</h2><p>本站內容僅供教育、研究與方法比較，不構成投資建議、交易邀約或任何報酬保證。模型輸出可能不完整、過時或錯誤，不應作為個人財務決策的唯一依據。</p></div></article>
          <article id="sources"><span>02</span><div><h2>資料與來源</h2><p>公開研究使用版本化的歷史資料快照，並保留來源、發布時間與當時可取得時間。不同來源的授權與更新頻率可能造成案例涵蓋範圍不同，個別卷宗會揭露實際使用資料。</p></div></article>
          <article id="privacy"><span>03</span><div><h2>身分與隱私</h2><p>執行私人實驗需登入，以保護研究紀錄與控制服務用量。私人案例不會自動公開；只有經使用者選擇及管理者審核的內容，才可能加入公開案例庫。</p></div></article>
          <article><span>04</span><div><h2>模型限制</h2><p>多代理人辯論能呈現不同論點，但不保證消除偏誤或產生正確答案。角色交換是在控制條件下比較決策機制，不代表模型真正持有立場或理解市場。</p></div></article>
          <article><span>05</span><div><h2>歷史回測</h2><p>回測結果受到期間、資料品質、交易成本與規則假設影響。歷史表現不代表未來結果；系統會先鎖定決策再取得未來價格，以降低前視偏誤。</p></div></article>
        </section>
        <section className="section-shell notice-callout">
          <strong>使用前請記得</strong>
          <p>把這裡的輸出視為一份可檢查的研究紀錄，而不是答案。閱讀證據、理解不確定性，再自行做出負責任的判斷。</p>
          <a className="text-link" href="/methodology">了解研究設計 <span aria-hidden="true">→</span></a>
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}
