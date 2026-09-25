"""设备检修接口：维护检修单，覆盖受理检修、提交验收、确认验收等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, ArchiveResult, EntryPayload, PageResult
from app.services.maint import MaintService
from app.services.maint_archive import GROUP_STATUSES, MaintArchiveService

router = APIRouter(prefix="/api/maint", tags=["设备检修"])

service = MaintService()
archive_service = MaintArchiveService()

LIST_FIELDS = ["检修单号", "关联设备", "检修类型", "计划开始日", "实际完成日", "检修人员", "验收人员", "检修状态"]
STATUSES = ["待受理", "检修中", "待验收", "已验收"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按检修单号检索"),
    status: str | None = Query(default=None, description="待受理、检修中、待验收、已验收"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按检修单号与状态过滤设备检修列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条检修单，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="检修单已登记", entry=entry)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出设备检修清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "maint", "total": total, "items": items}


# 以下字面量路由必须排在 /{entry_id} 之前，否则会被整型参数路由先匹配而返回 422。
# ---------------------------------------------------------------- 验收材料归档
@router.get("/archives", response_model=PageResult[dict])
def list_archives(
    keyword: str | None = Query(default=None, description="按检修单号检索归档批次"),
    status: str | None = Query(default=None, description="验收中、待归档、已归档、已退回"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """归档批次列表：整组进度（已确认/总数、待确认、已驳回）由实际条目实时计算。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    if status and status not in GROUP_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"归档状态仅支持：{'、'.join(GROUP_STATUSES)}",
        )
    items, total = archive_service.list_groups(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.post("/archives", response_model=ArchiveResult)
def submit_archive(payload: EntryPayload) -> ArchiveResult:
    """按检修单号批量报送设备照片与检测报告；重复报送、材料缺失、格式不对均给出理由。"""
    group, message, errors = archive_service.submit(payload.values)
    if errors or group is None:
        return ArchiveResult(ok=False, message=message, errors=errors)
    return ArchiveResult(ok=True, message=message, group=group)


@router.get("/archives/{group_id}", response_model=dict)
def get_archive(group_id: int) -> dict[str, Any]:
    """读取单批验收材料及逐条条目、整组进度。"""
    group = archive_service.get_group(group_id)
    if group is None:
        raise HTTPException(status_code=404, detail=f"验收批次 {group_id} 不存在或已删除")
    return group


@router.post("/archives/{group_id}/items/{item_id}/review", response_model=ActionResult)
def review_archive_item(group_id: int, item_id: int, payload: EntryPayload) -> ActionResult:
    """验收人对单条材料确认或单条驳回；未签字、缺驳回理由都会被拦下并说明原因。"""
    item, message = archive_service.review_item(group_id, item_id, payload.values)
    if item is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=item)


@router.post("/archives/{group_id}/archive", response_model=ArchiveResult)
def finish_archive(group_id: int, payload: EntryPayload) -> ArchiveResult:
    """全部条目确认通过且验收人签字后整组归档，否则返回不能归档的理由。"""
    group, message = archive_service.archive_group(group_id, payload.values)
    if group is None:
        return ArchiveResult(ok=False, message=message)
    return ArchiveResult(ok=True, message=message, group=group)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条检修单明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"检修单 {entry_id} 不存在或已归档")
    return entry


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条检修单执行受理检修、提交验收、确认验收；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
