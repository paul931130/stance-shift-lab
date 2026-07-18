import type { Metadata } from "next";
import { SiteFooter, SiteHeader } from "./components/site-shell";

export const metadata: Metadata = {
  title: "立場交換研究室｜多代理人投資決策實驗",
  description:
    "比較單一模型、自我一致性、固定辯論與立場交換辯論，讓每一項投資研究結論都有證據、有過程、可回看。",
};

const methods = [
  {
    label: "方法 A",
    title: "單一模型",
    note: "一次判斷",
    calls: "01",
    description: "以同一份研究資料直接做出結論，作為最精簡的基準線。",
    className: "method-card--baseline",
  },
  {
    label: "方法 B",
    title: "自我一致性",
    note: "五次抽樣",
    calls: "05",
    description: "獨立判斷五次，再以多數決整合，觀察答案是否穩定。",
    className: "method-card--consistency",
  },
  {
    label: "方法 C",
    title: "固定立場辯論",
    note: "三輪攻防",
    calls: "07",
    description: "看多與看空代理人堅守原立場，完整提出支持與反駁。",
    className: "method-card--debate",
  },
  {
    label: "方法 D",
    title: "立場交換辯論",
    note: "第二輪換位",
    calls: "07",
    description: "代理人必須替對方提出最強論證，再回到證據做最終整合。",
    className: "method-card--swap",
  },
];

const evidence = [
  {
    id: "E-01",
    domain: "基本面",
    claim: "營收成長與毛利變化",
    source: "公司申報文件",
    tone: "positive",
  },
  {
    id: "E-02",
    domain: "技術面",
    claim: "中期趨勢與波動區間",
    source: "歷史市場快照",
    tone: "neutral",
  },
  {
    id: "E-03",
    domain: "總體面",
    claim: "利率環境與產業敏感度",
    source: "版本化經濟資料",
    tone: "negative",
  },
];

export default function Home() {
  return (
    <div className="site-frame">
      <a className="skip-link" href="#main-content">
        跳至主要內容
      </a>
      <SiteHeader />

      <main id="main-content">
        <section className="hero section-shell" aria-labelledby="hero-title">
          <div className="hero-copy">
            <p className="eyebrow">
              <span className="eyebrow-rule" aria-hidden="true" />
              多代理人決策研究 · 公開測試版
            </p>
            <h1 id="hero-title">
              讓模型先<span className="ink-mark">換位思考</span>
              <br />
              再做決定。
            </h1>
            <p className="hero-lede">
              同一份資料、四種決策方法。研究代理人先交叉檢視證據，再由看多與看空角色交換立場，留下每一步可回看的推理紀錄。
            </p>
            <div className="hero-actions" aria-label="開始使用">
              <a className="button button--primary" href="/lab">
                開始一場研究
                <span aria-hidden="true">→</span>
              </a>
              <a className="button button--quiet" href="/cases">
                查看公開案例
              </a>
            </div>
            <ul className="assurance-list" aria-label="研究原則">
              <li>固定歷史資料</li>
              <li>完整證據引用</li>
              <li>決策後才回測</li>
            </ul>
          </div>

          <div className="dossier-wrap" aria-label="角色交換研究流程示意">
            <div className="dossier-shadow" aria-hidden="true" />
            <article className="dossier">
              <header className="dossier-head">
                <div>
                  <p>研究卷宗</p>
                  <strong>RS / 024</strong>
                </div>
                <span className="status-chip">
                  <i aria-hidden="true" /> 已完成
                </span>
              </header>
              <div className="dossier-subhead">
                <div>
                  <span>標的</span>
                  <strong>ASTS</strong>
                </div>
                <div>
                  <span>研究日</span>
                  <strong>2024 · Q4</strong>
                </div>
                <div>
                  <span>模式</span>
                  <strong>立場交換</strong>
                </div>
              </div>
              <div className="dossier-agents">
                <div className="agent agent--bull">
                  <span className="agent-index">A</span>
                  <div>
                    <small>研究代理人</small>
                    <strong>看多立場</strong>
                  </div>
                </div>
                <div className="exchange-mark" aria-hidden="true">
                  <span>→</span>
                  <span>←</span>
                </div>
                <div className="agent agent--bear">
                  <span className="agent-index">B</span>
                  <div>
                    <small>研究代理人</small>
                    <strong>看空立場</strong>
                  </div>
                </div>
              </div>
              <ol className="dossier-trace">
                <li className="is-done">
                  <span>01</span>
                  <div>
                    <strong>建立原始主張</strong>
                    <small>引用 E-01 · E-03 · E-07</small>
                  </div>
                  <i aria-label="完成">✓</i>
                </li>
                <li className="is-swap">
                  <span>02</span>
                  <div>
                    <strong>強制交換立場</strong>
                    <small>替對方提出最強論證</small>
                  </div>
                  <b>SWAP</b>
                </li>
                <li className="is-done">
                  <span>03</span>
                  <div>
                    <strong>回到證據整合</strong>
                    <small>保留尚未解決的分歧</small>
                  </div>
                  <i aria-label="完成">✓</i>
                </li>
              </ol>
              <footer className="dossier-result">
                <span>Gatekeeper 最終處置</span>
                <strong>中立 · HOLD</strong>
                <small>研究流程示意，非真實投資建議</small>
              </footer>
            </article>
          </div>
        </section>

        <section className="proof-strip" aria-label="實驗規格摘要">
          <div className="section-shell proof-strip__inner">
            <p><strong>4</strong><span>種決策方法</span></p>
            <p><strong>20</strong><span>次邏輯模型呼叫</span></p>
            <p><strong>4</strong><span>個研究面向</span></p>
            <p><strong>100%</strong><span>可追溯證據</span></p>
          </div>
        </section>

        <section className="section-shell section-block" id="methods" aria-labelledby="methods-title">
          <div className="section-heading section-heading--split">
            <div>
              <p className="section-kicker">01 / CONTROLLED COMPARISON</p>
              <h2 id="methods-title">不是問哪個模型最好，<br />而是比較它如何做決定。</h2>
            </div>
            <p>
              四組方法共用完全相同的研究快照、模型版本與交易規則，將差異留給決策機制本身。
            </p>
          </div>
          <div className="method-grid">
            {methods.map((method) => (
              <article className={`method-card ${method.className}`} key={method.label}>
                <header>
                  <span>{method.label}</span>
                  <small>{method.calls} CALLS</small>
                </header>
                <div className="method-number" aria-hidden="true">{method.label.slice(-1)}</div>
                <h3>{method.title}</h3>
                <p>{method.description}</p>
                <footer>
                  <span>{method.note}</span>
                  <span aria-hidden="true">↗</span>
                </footer>
              </article>
            ))}
          </div>
        </section>

        <section className="exchange-section" aria-labelledby="exchange-title">
          <div className="section-shell section-block">
            <div className="section-heading exchange-heading">
              <p className="section-kicker">02 / ROLE-SWITCH DEBATE</p>
              <h2 id="exchange-title">三輪辯論，第二輪必須站到對面。</h2>
              <p>
                立場交換不是改口，而是要求代理人先理解反方最強的證據，降低只替原先答案找理由的風險。
              </p>
            </div>

            <div className="rounds" aria-label="三輪角色交換流程">
              <article className="round-card">
                <header><span>ROUND 01</span><strong>建立主張</strong></header>
                <div className="position-pair">
                  <div className="position position--bull"><b>A</b><span>看多</span></div>
                  <div className="position position--bear"><b>B</b><span>看空</span></div>
                </div>
                <p>各自提出最強的初始論證，並逐項綁定證據編號。</p>
              </article>

              <div className="round-connector" aria-hidden="true"><span>01</span><i>→</i></div>

              <article className="round-card round-card--focus">
                <header><span>ROUND 02</span><strong>強制換位</strong></header>
                <div className="swap-track" aria-hidden="true">
                  <i className="track-one" />
                  <i className="track-two" />
                </div>
                <div className="position-pair">
                  <div className="position position--bear"><b>A</b><span>改辯看空</span></div>
                  <div className="position position--bull"><b>B</b><span>改辯看多</span></div>
                </div>
                <p>替對方論證，不得跳過、不准提早收斂，也不能只做表面反駁。</p>
                <em>核心實驗機制</em>
              </article>

              <div className="round-connector" aria-hidden="true"><span>02</span><i>→</i></div>

              <article className="round-card">
                <header><span>ROUND 03</span><strong>證據整合</strong></header>
                <div className="position-pair">
                  <div className="position position--neutral"><b>A</b><span>校正結論</span></div>
                  <div className="position position--neutral"><b>B</b><span>保留分歧</span></div>
                </div>
                <p>回到原始證據，承認有效反證，再交由裁決代理人判定。</p>
              </article>
            </div>
          </div>
        </section>

        <section className="section-shell section-block evidence-section" aria-labelledby="evidence-title">
          <div className="evidence-copy">
            <p className="section-kicker">03 / EVIDENCE LEDGER</p>
            <h2 id="evidence-title">每個結論，都能一路追到來源。</h2>
            <p>
              研究日之後才出現的資料不會進入決策。引用同時記錄發布時間、可取得時間與資料版本，讓回測不是事後諸葛。
            </p>
            <a className="text-link" href="/methodology">
              閱讀完整研究方法 <span aria-hidden="true">→</span>
            </a>
          </div>

          <div className="ledger" aria-label="證據帳本示意">
            <div className="ledger-head">
              <span>證據 ID</span><span>領域與主張</span><span>方向</span>
            </div>
            {evidence.map((item) => (
              <div className="ledger-row" key={item.id}>
                <strong>{item.id}</strong>
                <div><b>{item.domain}</b><span>{item.claim}</span><small>{item.source}</small></div>
                <i className={`signal signal--${item.tone}`}>
                  {item.tone === "positive" ? "+" : item.tone === "negative" ? "−" : "0"}
                </i>
              </div>
            ))}
            <div className="ledger-lock">
              <span aria-hidden="true">✓</span>
              <p><strong>時間邊界已通過</strong><small>所有證據皆早於研究截止時間</small></p>
            </div>
          </div>
        </section>

        <section className="gate-section">
          <div className="section-shell gate-grid">
            <div className="gate-seal" aria-hidden="true"><span>G</span><small>GATE</small></div>
            <div>
              <p className="section-kicker">04 / DECISION GATE</p>
              <h2>沒有足夠證據，也是一種結果。</h2>
            </div>
            <p>
              Gatekeeper 會檢查引用完整度、信心與風險。資料不足時明確標為「證據不足」，不強迫模型在看多與看空之間猜一個答案。
            </p>
          </div>
        </section>

        <section className="section-shell final-cta" aria-labelledby="cta-title">
          <p className="section-kicker">OPEN RESEARCH DOSSIER</p>
          <h2 id="cta-title">打開一份研究卷宗，<br />看見結論形成的過程。</h2>
          <p>選擇股票與歷史日期，並排比較四種決策方法。</p>
          <div className="hero-actions">
            <a className="button button--primary" href="/lab">進入研究室 <span aria-hidden="true">→</span></a>
            <a className="button button--quiet" href="/methodology">先了解方法</a>
          </div>
          <small>本平台僅供 AI 決策研究與教育用途，不構成投資建議。</small>
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}
