"""HTTP 入口：FastAPI 应用与路由。"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Query, Response

from . import db
from .schemas import AmendCommand, PublishCommand, RevokeCommand
from .service import (
    handle_amend,
    handle_publish,
    handle_revoke,
    query_broadcast,
    query_broadcast_schedule,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_pool()      # 等待数据库就绪
    db.init_schema()    # 幂等建表，容器重复启动安全
    yield
    db.close_pool()


app = FastAPI(
    title="园区应急广播播发裁决服务",
    version="1.2.0",
    lifespan=lifespan,
)


@app.get("/")
def index():
    return {
        "service": "园区应急广播播发裁决服务",
        "docs": "/docs",
        "endpoints": [
            "POST /api/commands/publish",
            "POST /api/commands/amend",
            "POST /api/commands/revoke",
            "GET  /api/broadcast?at=<ISO8601>&area=<区域>",
            "GET  /api/broadcast/schedule?area=<区域>&from=<ISO8601>&to=<ISO8601>",
            "GET  /healthz",
        ],
    }


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.post("/api/commands/publish", status_code=201)
def publish(cmd: PublishCommand, response: Response):
    """提交发布命令。首次受理 201，同请求号同载荷重放 200 并返回首次回执。"""
    receipt, status = handle_publish(cmd)
    response.status_code = status
    return receipt


@app.post("/api/commands/revoke", status_code=201)
def revoke(cmd: RevokeCommand, response: Response):
    """提交撤销命令。首次受理 201，同请求号同载荷重放 200 并返回首次回执。"""
    receipt, status = handle_revoke(cmd)
    response.status_code = status
    return receipt


@app.post("/api/commands/amend", status_code=201)
def amend(cmd: AmendCommand, response: Response):
    """提交修订命令：整体替换进行中告警的文案/级别/区域。首次 201，同载荷重放 200。"""
    receipt, status = handle_amend(cmd)
    response.status_code = status
    return receipt


@app.get("/api/broadcast")
def broadcast(
    at: datetime | None = Query(default=None, description="查询时刻，ISO 8601，缺省为当前时间"),
    area: str | None = Query(default=None, description="限定区域，缺省返回所有区域"),
):
    """查询指定时刻各区域应播发的告警；无有效告警时 results 为空列表。"""
    return query_broadcast(at, area)


@app.get("/api/broadcast/schedule")
def broadcast_schedule(
    area: str = Query(description="限定区域"),
    from_: datetime = Query(alias="from", description="区间起点（含），ISO 8601，须带时区"),
    to: datetime = Query(description="区间终点（不含），ISO 8601，须带时区"),
):
    """查询某区域在 [from, to) 时段内实际应播发的片段序列。

    返回按时间升序、无缝覆盖整个区间、互不重叠的左闭右开片段；无告警的空档
    以空告警（alert_no/level/message 为 null）表示；相邻内容相同的片段已合并；
    边界时刻属于后一段。起点须早于终点且跨度不超过 24 小时。
    """
    return query_broadcast_schedule(area, from_, to)
