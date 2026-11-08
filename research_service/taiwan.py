"""Isolated Taiwan exploration; no formal-study storage or brokerage execution."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
import hashlib
import json
import math
import re
import sqlite3
import threading
import uuid
from zoneinfo import ZoneInfo

from jsonschema import validate
from .logging_config import get_logger
from .models import DECISION_SCHEMA
from .protocol import StudyProtocol

LIMITATIONS = ['僅有延遲日線行情，非即時報價。', '未提供財報與新聞，不能據此判斷基本面或事件。', '台股探索功能，不屬正式 RQ 研究結果；未連接券商委託。']
logger = get_logger(__name__)
HEARTBEAT_SECONDS = 15
OWNER_TIMEOUT_SECONDS = 90
# Lunar New Year closes TWSE for up to about a week; with weekends the last
# trading day can be eleven calendar days back.
QUOTE_MAX_AGE_DAYS = 14
NUMERAL_CLAIM = re.compile(r'\d|[零〇一二三四五六七八九十百千萬億兆兩壹貳參肆伍陸柒捌玖拾佰仟]+(?:元|股|日|天|月|年|成|倍|點|趴|%)|百分之')
# Idioms that read as numeral + unit but assert no quantity.
# A numeral before 一 (十一點) is a real claim, so it is not an idiom.
NUMERAL_IDIOMS = re.compile(r'(?<![零〇一二三四五六七八九十百千萬億兆兩壹貳參肆伍陸柒捌玖拾佰仟])一(?:點|成不變|天到晚)|有朝一日')


class ReportLeaseLost(RuntimeError):
    """A closed or expired owner must discard its in-flight result."""


def now():
    return datetime.now(timezone.utc).isoformat()


def validate_ticker(value):
    value = str(value).strip().upper()
    if not re.fullmatch(r'\d{4,6}\.(TW|TWO)', value):
        raise ValueError('請使用四至六位台股代碼與 .TW 或 .TWO，例如 2330.TW')
    return value


def fetch_quote(ticker):
    import yfinance as yf
    ticker = validate_ticker(ticker)
    frame = yf.Ticker(ticker).history(period='1mo', interval='1d', auto_adjust=False, actions=False, timeout=20)
    history = []
    for stamp, row in frame.iterrows():
        price = float(row['Close'])
        if math.isfinite(price) and price > 0:
            history.append({'date': stamp.date().isoformat(), 'close': price})
    history.sort(key=lambda row: row['date'])
    if not history:
        raise ValueError('行情來源沒有有效正價格')
    price = history[-1]['close']
    previous = history[-2]['close'] if len(history) > 1 else None
    as_of = history[-1]['date']
    evidence = 'TWQ-' + hashlib.sha256(json.dumps([ticker, history], sort_keys=True).encode()).hexdigest()[:16]
    return {'ticker': ticker, 'name': ticker, 'price': price, 'previous_close': previous,
            'change': price - previous if previous else None,
            'change_pct': (price / previous - 1) * 100 if previous else None,
            'currency': 'TWD', 'as_of': as_of, 'fetched_at': now(),
            'source': 'Yahoo Finance via yfinance', 'delay_notice': LIMITATIONS[0],
            'history': history, 'evidence_id': evidence, 'limitations': LIMITATIONS}


def check_quote(quote, ticker):
    if quote.get('ticker') != ticker or isinstance(quote.get('price'), bool):
        raise ValueError('行情格式無效')
    price = quote.get('price')
    if not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 0:
        raise ValueError('行情價格無效')
    date = datetime.strptime(quote['as_of'], '%Y-%m-%d').date()
    age = datetime.now(ZoneInfo('Asia/Taipei')).date() - date
    if age < timedelta(0) or age > timedelta(days=QUOTE_MAX_AGE_DAYS):
        raise ValueError('行情過期或時間無效，請確認來源')
    if not quote.get('evidence_id'):
        raise ValueError('缺少行情證據')
    fetched = datetime.fromisoformat(quote['fetched_at'])
    if fetched.tzinfo is None or fetched > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise ValueError('行情擷取時間無效')
    history = quote.get('history')
    if not isinstance(history, list) or not history:
        raise ValueError('行情缺少歷史資料')
    dates = []
    for item in history:
        stamp = datetime.strptime(item['date'], '%Y-%m-%d').date()
        value = item['close']
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError('歷史行情價格無效')
        dates.append(stamp)
    if dates != sorted(set(dates)) or dates[-1] != date or history[-1]['close'] != price:
        raise ValueError('歷史行情與快照不一致')
    for key in ('previous_close', 'change', 'change_pct'):
        value = quote.get(key)
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)):
            raise ValueError('行情數值無效')
    return quote


def validate_output(result, evidence_id, ticker=None):
    validate(result, DECISION_SCHEMA)
    if result['action'] == 'NoTrade' or set(result['evidence_ids']) != {evidence_id}:
        raise ValueError('模型引用無效')
    if result['numeric_claims']:
        raise ValueError('本探索模式只允許引用證據 ID，不允許重述數值')
    prose = [result['rationale'], *result['risks'], result.get('strongest_counterpoint', '')]
    # Evidence IDs and the stock code may contain digits, but narrative numeric assertions cannot.
    names = [evidence_id]
    if ticker:
        names += [ticker, ticker.split('.')[0]]
    for text in prose:
        for name in names:
            text = text.replace(name, ' ')
        if NUMERAL_CLAIM.search(NUMERAL_IDIOMS.sub(' ', text)):
            raise ValueError('敘述不得包含未綁定數字，請僅引用證據 ID')
    if not math.isfinite(result['confidence']) or not math.isfinite(result['expected_return_pct']):
        raise ValueError('模型數值無效')
    return result


class TaiwanService:
    def __init__(self, root, model_call, quote_loader=fetch_quote):
        self.path = Path(root) / 'taiwan-exploratory.sqlite3'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.model_call, self.quote_loader = model_call, quote_loader
        self.lock = threading.RLock()
        self.service_id = uuid.uuid4().hex
        self.closed = False
        self.stop = threading.Event()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='taiwan-exploration')
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS reports (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS decisions (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS services (id TEXT PRIMARY KEY, heartbeat TEXT NOT NULL)')
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT INTO services VALUES (?,?)', (self.service_id, now()))
            self._recover(db)
        self.heart = threading.Thread(target=self._beat, daemon=True, name='taiwan-heartbeat')
        self.heart.start()

    @staticmethod
    def _cutoff():
        return (datetime.now(timezone.utc) - timedelta(seconds=OWNER_TIMEOUT_SECONDS)).isoformat()

    @staticmethod
    def _fail(db, report, message):
        at = now()
        report.update(status='failed', error=message, updated_at=at)
        for audit in report.get('audit', []):
            if audit.get('status') == 'running':
                audit.update(status='failed', completed_at=at, error=message)
        db.execute('UPDATE reports SET payload=? WHERE id=?',
                   (json.dumps(report, ensure_ascii=False), report['id']))

    def _recover(self, db):
        live = {row[0] for row in db.execute('SELECT id FROM services WHERE heartbeat >= ?', (self._cutoff(),))}
        count = 0
        for row in db.execute('SELECT payload FROM reports').fetchall():
            report = json.loads(row[0])
            if report['status'] in ('queued', 'running') and report.get('owner') not in live:
                self._fail(db, report, '處理服務已離線，請重新建立報告')
                count += 1
        db.execute('DELETE FROM services WHERE heartbeat < ?', (self._cutoff(),))
        return count

    def recover(self):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            return self._recover(db)

    def _beat(self):
        while not self.stop.wait(HEARTBEAT_SECONDS):
            try:
                if not self.heartbeat() and not self.rejoin():
                    return
            except Exception:
                logger.exception('Taiwan service heartbeat failed; retrying')

    def heartbeat(self):
        with self.lock, self.connect() as db:
            if self.closed:
                return False
            db.execute('BEGIN IMMEDIATE')
            # An expired service cannot revive a lease another service fenced off.
            alive = db.execute('UPDATE services SET heartbeat=? WHERE id=? AND heartbeat >= ?',
                               (now(), self.service_id, self._cutoff())).rowcount == 1
            self._recover(db)
            return alive

    def rejoin(self):
        """After a missed lease (e.g. host sleep), register under a fresh id.

        The old id stays fenced: its in-flight reports were failed by recovery
        and their workers lose every later save, so only new reports run.
        """
        with self.lock, self.connect() as db:
            if self.closed:
                return False
            db.execute('BEGIN IMMEDIATE')
            self._recover(db)
            self.service_id = uuid.uuid4().hex
            db.execute('INSERT INTO services VALUES (?,?)', (self.service_id, now()))
            logger.warning('Taiwan service lease expired; rejoined as %s', self.service_id)
            return True

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(str(self.path), timeout=10)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.stop.set()
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                for row in db.execute('SELECT payload FROM reports').fetchall():
                    report = json.loads(row[0])
                    if report.get('owner') == self.service_id and report['status'] in ('queued', 'running'):
                        self._fail(db, report, '處理服務已關閉，請重新建立報告')
                db.execute('DELETE FROM services WHERE id=?', (self.service_id,))
            self.closed = True
            self.executor.shutdown(wait=False, cancel_futures=True)
        self.heart.join(timeout=5)

    def active_count(self):
        self.recover()
        with self.connect() as db:
            return sum(json.loads(row[0]).get('status') in ('queued', 'running')
                       for row in db.execute('SELECT payload FROM reports'))

    def list(self, table):
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute(f'SELECT payload FROM {table} ORDER BY rowid DESC LIMIT 100')]

    def get(self, report_id):
        with self.connect() as db:
            row = db.execute('SELECT payload FROM reports WHERE id=?', (report_id,)).fetchone()
        if not row:
            raise KeyError(report_id)
        return json.loads(row[0])

    def save(self, report):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO reports VALUES (?,?)', (report['id'], json.dumps(report, ensure_ascii=False)))

    def _save_owned(self, report, *, claim=False):
        with self.lock, self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT payload FROM reports WHERE id=?', (report['id'],)).fetchone()
            current = json.loads(row[0]) if row else {}
            live = db.execute('SELECT 1 FROM services WHERE id=? AND heartbeat >= ?',
                              (self.service_id, self._cutoff())).fetchone()
            statuses = ('queued',) if claim else ('running',)
            if self.closed or not live or current.get('owner') != self.service_id or current.get('status') not in statuses:
                raise ReportLeaseLost(report['id'])
            db.execute('UPDATE reports SET payload=? WHERE id=?',
                       (json.dumps(report, ensure_ascii=False), report['id']))

    def create(self, ticker, model):
        ticker = validate_ticker(ticker)
        if not isinstance(model, str) or not model.strip() or len(model) > 160 or any(ord(c) < 32 for c in model):
            raise ValueError('模型名稱無效')
        StudyProtocol(model=model)
        with self.lock:
            if self.closed:
                raise ValueError('服務已關閉，請重新連線')
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                if not db.execute('SELECT 1 FROM services WHERE id=? AND heartbeat >= ?',
                                  (self.service_id, self._cutoff())).fetchone():
                    raise ValueError('服務已離線，請重新啟動')
                self._recover(db)
                active = [r for row in db.execute('SELECT payload FROM reports')
                          if (r := json.loads(row[0]))['status'] in ('queued', 'running')]
                if any(r['ticker'] == ticker and r['model'] == model for r in active):
                    raise ValueError('相同股票與模型的報告仍在處理')
                if len(active) >= 3:
                    raise ValueError('報告佇列已滿，請等待目前工作完成')
                report = {'id': uuid.uuid4().hex, 'ticker': ticker, 'model': model, 'status': 'queued',
                          'owner': self.service_id,
                          'created_at': now(), 'updated_at': now(), 'completed_at': None, 'error': None,
                          'quote': None, 'report': None, 'audit': [], 'limitations': LIMITATIONS, 'formal_result': False}
                db.execute('INSERT INTO reports VALUES (?,?)',
                           (report['id'], json.dumps(report, ensure_ascii=False)))
            try:
                self.executor.submit(self.run, report['id'])
            except Exception:
                with self.connect() as db:
                    self._fail(db, report, '工作無法排入佇列，請重新建立報告')
                raise
            return report

    def run(self, report_id):
        report = self.get(report_id)
        report.update(status='running', updated_at=now())
        try:
            self._save_owned(report, claim=True)
            quote = check_quote(self.quote_loader(report['ticker']), report['ticker'])
            report['quote'] = quote
            self._save_owned(report)
            protocol = StudyProtocol(model=report['model'])
            results = {}
            for role in ('bull', 'bear', 'judge'):
                started = now()
                report['audit'].append({'role': role, 'model': report['model'], 'started_at': started,
                                        'status': 'running', 'data_as_of': quote['as_of'],
                                        'evidence_id': quote['evidence_id']})
                self._save_owned(report)
                system = ('你是台股探索多代理人系統。只使用附帶行情證據，以繁體中文輸出 JSON。'
                          '本報告不是正式研究結果，也不會下單。未提供財報與新聞，必須明示此缺口；不得使用記憶補造事實。'
                          '多頭與空頭只呈現各自假說，沒有證據必須承認。裁判須比較雙方論證，證據不足可 Hold。'
                          '所有 evidence_ids 必須且只能包含提供的 evidence_id。敘述不要重述數字，numeric_claims 必須為 []。'
                          'expected_return_pct 是未經驗證的五交易日情境預測，confidence 不是校準勝率。'
                          '輸出符合以下 schema：' + json.dumps(DECISION_SCHEMA, ensure_ascii=False))
                payload = {'role': role, 'quote': quote, 'limitations': LIMITATIONS}
                system += {'bull': '你的職責是檢視看多假說及其支持證據，並陳述反證；證據不足可 Hold。',
                           'bear': '你的職責是檢視看空假說及其支持證據，並陳述反證；證據不足可 Hold。',
                           'judge': '你的職責是比較多空雙方、檢查引用，作出綜合判斷；證據不足可 Hold。'}[role]
                if role == 'judge':
                    payload['arguments'] = results
                messages = [{'role': 'system', 'content': system}, {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}]
                result, audit = self.model_call(protocol, messages)
                results[role] = validate_output(result, quote['evidence_id'], report['ticker'])
                # Only allow bounded, non-sensitive provider metadata into the public audit.
                usage = audit.get('usage', {}) if isinstance(audit, dict) else {}
                safe_usage = {k: v for k, v in usage.items() if k in ('prompt_tokens', 'completion_tokens', 'total_tokens', 'client_elapsed_seconds') and isinstance(v, (int, float)) and math.isfinite(v)}
                report['audit'][-1].update(status='complete', completed_at=now(), usage=safe_usage)
                self._save_owned(report)
            report.update(status='complete', report=results, completed_at=now())
        except ReportLeaseLost:
            return
        except Exception as error:
            if report['audit'] and report['audit'][-1].get('status') == 'running':
                report['audit'][-1].update(status='failed', completed_at=now(), error='模型呼叫或輸出驗證失敗', error_type=type(error).__name__)
            report['error_type'] = type(error).__name__
            report.update(status='failed', error='行情或模型處理失敗；請檢查來源、模型可用性與輸出格式後重試')
        report['updated_at'] = now()
        try:
            self._save_owned(report)
        except ReportLeaseLost:
            pass

    def decide(self, report_id, action, quantity, note=''):
        if action not in ('Buy', 'Hold', 'Sell') or type(quantity) is not int or quantity < 0 or quantity > 1000000 or (action != 'Hold' and quantity == 0):
            raise ValueError('股數須為整數；Buy/Sell 須為正數，最多一百萬股')
        if not isinstance(note, str) or len(note) > 2000:
            raise ValueError('備註最多兩千字')
        report = self.get(report_id)
        if report['status'] != 'complete' or datetime.now(timezone.utc) - datetime.fromisoformat(report['completed_at']) > timedelta(hours=24):
            raise ValueError('須使用二十四小時內完成的報告')
        quote = check_quote(report['quote'], report['ticker'])
        decision = {'id': uuid.uuid4().hex, 'report_id': report_id, 'ticker': report['ticker'], 'action': action,
                    'quantity': quantity, 'quantity_unit': '股', 'note': note, 'created_at': now(),
                    'reference_price': quote['price'], 'quote_snapshot': quote, 'report_quote': report['quote'],
                    'simulation_only': True, 'execution_status': 'recorded_only',
                    'notice': '僅記錄模擬方向；無實際成交、持倉或做空庫存驗證。'}
        with self.connect() as db:
            db.execute('INSERT INTO decisions VALUES (?,?)', (decision['id'], json.dumps(decision, ensure_ascii=False)))
        return decision
