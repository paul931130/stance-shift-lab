import Link from "next/link";

const navItems = [
  { href: "/#methods", label: "方法比較" },
  { href: "/cases", label: "公開案例" },
  { href: "/methodology", label: "研究方法" },
];

export function SiteHeader() {
  return (
    <header className="site-header">
      <div className="section-shell site-header__inner">
        <Link className="brand" href="/" aria-label="立場交換研究室首頁">
          <span className="brand-mark" aria-hidden="true"><i>L</i><i>S</i></span>
          <span><strong>立場交換研究室</strong><small>STANCE-SHIFT LAB</small></span>
        </Link>
        <nav aria-label="主要導覽">
          {navItems.map((item) => <a href={item.href} key={item.href}>{item.label}</a>)}
        </nav>
        <a className="header-action" href="/lab">進入研究室 <span aria-hidden="true">↗</span></a>
      </div>
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="section-shell footer-grid">
        <div>
          <Link className="brand brand--footer" href="/" aria-label="立場交換研究室首頁">
            <span className="brand-mark" aria-hidden="true"><i>L</i><i>S</i></span>
            <span><strong>立場交換研究室</strong><small>STANCE-SHIFT LAB</small></span>
          </Link>
          <p>以可追溯的多代理人辯論，研究 AI 如何形成決策。</p>
        </div>
        <div className="footer-links">
          <div><strong>探索</strong><a href="/cases">公開案例</a><a href="/methodology">研究方法</a><a href="/lab">執行實驗</a></div>
          <div><strong>資訊</strong><a href="/disclaimer">使用聲明</a><a href="/disclaimer#privacy">隱私說明</a><a href="/disclaimer#sources">資料來源</a></div>
        </div>
      </div>
      <div className="section-shell footer-bottom">
        <span>© 2026 STANCE-SHIFT LAB</span>
        <span>AI 研究工具 · 非投資建議</span>
      </div>
    </footer>
  );
}

export function InteriorHero({
  index,
  eyebrow,
  title,
  description,
}: {
  index: string;
  eyebrow: string;
  title: string;
  description: string;
}) {
  return (
    <section className="interior-hero section-shell">
      <div className="interior-index" aria-hidden="true">{index}</div>
      <div>
        <p className="eyebrow"><span className="eyebrow-rule" aria-hidden="true" />{eyebrow}</p>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
    </section>
  );
}
