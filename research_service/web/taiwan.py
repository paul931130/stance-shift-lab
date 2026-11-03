"""HTTP routes for isolated Taiwan exploration."""
import os
from typing import Literal
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, StrictInt, Field
from ..protocol import DEFAULT_RESEARCH_MODEL
from ..models import generate
from ..taiwan import TaiwanService, check_quote, validate_ticker


class ReportInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    ticker: str
    model: str


class DecisionInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    report_id: str
    action: Literal['Buy', 'Hold', 'Sell']
    quantity: StrictInt
    note: str = Field(default='', max_length=2000)


def build_router(ctx, model_call=None):
    router = APIRouter(prefix='/api/taiwan')
    service = TaiwanService(ctx.store.root, model_call or generate)
    # Exposed to deterministic tests and application shutdown handling.
    router.taiwan_service = service

    def enabled():
        if ctx.demo_mode:
            raise HTTPException(422, '展示模式不提供台股真實行情或模型報告，請以一般服務模式啟動')

    def invoke(call):
        try:
            return call()
        except KeyError:
            raise HTTPException(404, '找不到報告') from None
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        except Exception:
            raise HTTPException(502, '行情或服務暫時無法使用') from None

    @router.get('/config')
    def config():
        model = os.getenv('RESEARCH_MODEL', DEFAULT_RESEARCH_MODEL)
        return {'models': [model], 'default_model': model, 'enabled': not ctx.demo_mode,
                'simulation_only': True, 'quantity_unit': '股', 'formal_result': False,
                'source': 'Yahoo Finance via yfinance', 'delay_notice': '延遲日線行情，非即時報價'}

    @router.get('/quote')
    def quote(ticker: str):
        enabled()
        return invoke(lambda: check_quote(service.quote_loader(validate_ticker(ticker)), validate_ticker(ticker)))

    @router.post('/reports', status_code=202)
    def create_report(payload: ReportInput):
        enabled()
        return invoke(lambda: service.create(payload.ticker, payload.model))

    @router.get('/reports')
    def reports():
        enabled()
        return {'items': service.list('reports')}

    @router.get('/reports/{report_id}')
    def report(report_id: str):
        enabled()
        return invoke(lambda: service.get(report_id))

    @router.post('/decisions', status_code=201)
    def decision(payload: DecisionInput):
        enabled()
        return invoke(lambda: service.decide(payload.report_id, payload.action, payload.quantity, payload.note))

    @router.get('/decisions')
    def decisions():
        enabled()
        return {'items': service.list('decisions')}

    return router
