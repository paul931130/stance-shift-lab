"""One upstream connection per service; bounded client queues and shared subscriptions."""
import asyncio
import json
import time
from .finnhub import websocket_url, finite


class TradeHub:
    def __init__(self, connector=None):
        self.connector = connector
        self.clients = {}
        self.task = None

    def symbols(self):
        return set().union(*(symbols for symbols in self.clients.values())) if self.clients else set()

    async def add(self, symbols):
        if len(self.clients) >= 16 or len(self.symbols() | set(symbols)) > 50:
            raise ValueError("本服務最多 16 個觀察連線、合計 50 檔；方案權限仍由 Finnhub 決定")
        queue = asyncio.Queue(maxsize=128)
        self.clients[queue] = set(symbols)
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self.run())
        return queue

    async def remove(self, queue):
        self.clients.pop(queue, None)
        if not self.clients:
            await self.close()

    async def close(self):
        task, self.task = self.task, None
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    def publish(self, payload):
        for queue, symbols in list(self.clients.items()):
            message = payload
            if payload.get("type") == "trade":
                rows = [row for row in payload["data"] if row["s"] in symbols]
                if not rows:
                    continue
                message = {**payload, "data": rows}
            if queue.full():
                queue.get_nowait()
                message = {**message, "dropped_messages": True}
            queue.put_nowait(message)

    async def run(self):
        import websockets
        connect = self.connector or websockets.connect
        backoff = 1
        while self.clients:
            self.publish({"type": "status", "status": "connecting", "message": "連接 Finnhub 上游；尚未確認成交資料"})
            try:
                async with connect(websocket_url(), open_timeout=15, close_timeout=3,
                                   ping_interval=20, ping_timeout=20, max_size=2_000_000) as upstream:
                    subscribed, heartbeat = set(), time.monotonic()
                    while self.clients:
                        desired = self.symbols()
                        for symbol in sorted(subscribed - desired):
                            await upstream.send(json.dumps({"type": "unsubscribe", "symbol": symbol}))
                        for symbol in sorted(desired - subscribed):
                            await upstream.send(json.dumps({"type": "subscribe", "symbol": symbol}))
                        if subscribed != desired:
                            self.publish({"type": "status", "status": "subscription_requested", "symbols": sorted(desired),
                                          "message": "已送出訂閱，等待真實成交；可用資料依市場與方案而定"})
                        subscribed = desired
                        try:
                            payload = json.loads(await asyncio.wait_for(upstream.recv(), timeout=1))
                            if not isinstance(payload, dict):
                                continue
                            if payload.get("type") == "trade" and isinstance(payload.get("data"), list):
                                rows = [{key: row[key] for key in ("s", "p", "v", "t")} for row in payload["data"]
                                        if isinstance(row, dict) and isinstance(row.get("s"), str)
                                        and finite(row.get("p"), True) and finite(row.get("v")) and row["v"] >= 0
                                        and finite(row.get("t"), True)]
                                if rows:
                                    backoff = 1
                                    self.publish({"type": "trade", "data": rows, "source": "Finnhub"})
                            elif payload.get("type") == "error":
                                self.publish({"type": "error", "message": "Finnhub 拒絕訂閱；請檢查金鑰、代號與方案權限"})
                            elif payload.get("type") == "ping":
                                self.publish({"type": "heartbeat"})
                        except asyncio.TimeoutError:
                            pass
                        if time.monotonic() - heartbeat > 15:
                            heartbeat = time.monotonic()
                            self.publish({"type": "heartbeat"})
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self.publish({"type": "status", "status": "reconnecting", "retry_seconds": backoff,
                              "message": f"上游連線中斷（{type(error).__name__}）；{backoff} 秒後重連"})
                await asyncio.sleep(backoff)
                backoff = min(30, backoff * 2)
