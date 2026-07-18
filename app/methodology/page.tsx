import type { Metadata } from "next";
import { InteriorHero, SiteFooter, SiteHeader } from "../components/site-shell";

export const metadata: Metadata = {
  title: "研究方法｜立場交換研究室",
  description: "了解多代理人立場交換辯論的實驗設計、證據規則、裁決與回測方式。",
};

export default function MethodologyPage() {
  return (
    <div className="site-frame">
      <a className="skip-link" href="#main-content">跳至主要內容</a>
      <SiteHeader />
      <main id="main-content">
        <InteriorHero
          index="02"
          eyebrow="METHODOLOGY"
          title="把決策過程變成可檢查的實驗"
          description="我們控制模型、資料與交易規則，只改變決策機制；並把每一項證據、每一次發言與每一道風險閘門留下紀錄。"
        />

        <section className="section-shell methodology-layout">
          <aside className="methodology-nav" aria-label="本頁章節">
            <strong>研究章節</strong>
            <a href="#design">01 實驗設計</a>
            <a href="#agents">02 研究代理人</a>
            <a href="#debate">03 角色交換</a>
            <a href="#gate">04 裁決與回測</a>
          </aside>
          <div className="methodology-content">
            <section id="design">
              <p className="section-kicker">01 / CONTROL VARIABLES</p>
              <h2>四組方法，共用同一個起點</h2>
              <p>同一案例中的四種決策方法使用完全相同的歷史快照、研究日期、模型版本與輸出格式。方法 A 呼叫 1 次、方法 B 呼叫 5 次、方法 C 與 D 各呼叫 7 次，共 20 次邏輯模型呼叫。</p>
              <div className="call-formula" aria-label="模型呼叫數計算">
                <span>A<strong>1</strong></span><i>＋</i><span>B<strong>5</strong></span><i>＋</i><span>C<strong>7</strong></span><i>＋</i><span>D<strong>7</strong></span><i>＝</i><b>20</b>
              </div>
            </section>
            <section id="agents">
              <p className="section-kicker">02 / RESEARCH TEAM</p>
              <h2>先研究，再辯論</h2>
              <p>技術面、基本面、情緒面與總體面代理人先各自整理資料。Coordinator 再建立中立報告與證據帳本，避免辯論代理人自行增加沒有來源的事實。</p>
              <div className="agent-domain-grid"><span><b>01</b>技術面</span><span><b>02</b>基本面</span><span><b>03</b>情緒面</span><span><b>04</b>總體面</span></div>
            </section>
            <section id="debate">
              <p className="section-kicker">03 / ROLE SWITCH</p>
              <h2>第二輪，代理人必須替反方辯護</h2>
              <p>第一輪建立原始主張；第二輪交換 Bull 與 Bear 身分，要求代理人完整提出對方最強的理由；第三輪才回到證據整合。流程不允許在交換前提早收斂。</p>
              <div className="method-note"><strong>為什麼要交換？</strong><p>固定辯論容易把更多運算花在證明自己是對的。角色交換迫使模型先處理不利證據，再決定哪些原始主張仍然成立。</p></div>
            </section>
            <section id="gate">
              <p className="section-kicker">04 / GATE &amp; BACKTEST</p>
              <h2>決策鎖定後，才打開未來</h2>
              <p>Gatekeeper 先檢查引用通過率、研究領域覆蓋、信心與風險。證據不足時輸出 NoTrade；研究充分但方向中性時輸出 Hold。四組決策鎖定後，系統才讀取 30、60、90 日後價格進行回測。</p>
              <ul className="rule-list"><li><span>80%</span>最低證據通過率</li><li><span>3+</span>最低研究領域數</li><li><span>0</span>決策前的未來資料存取</li></ul>
            </section>
          </div>
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}
