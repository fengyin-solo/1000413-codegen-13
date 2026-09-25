"""设备检修业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "maint"
REQUIRED_FIELDS = ["检修单号", "关联设备", "检修类型"]
STATUS_ORDER = ["待受理", "检修中", "待验收", "已验收"]
ACTION_RULES = {"受理检修": "检修中", "提交验收": "待验收", "确认验收": "已验收"}
NEGATIVE_ACTIONS = []

# 验收材料归档：材料类型、各类型允许的文件格式与条目动作
MATERIAL_TYPES = ["设备照片", "检测报告"]
MATERIAL_FORMATS = {"设备照片": {"jpg", "jpeg", "png"}, "检测报告": {"pdf"}}
ARCHIVE_ITEM_ACTIONS = ["确认材料", "驳回材料", "重新报送"]
ARCHIVE_ACTIONS = ["整组归档"]


class MaintService:
    def __init__(self) -> None:
        # 验收材料批次与检修单分开存放，检修单本身的受理/验收口径不受影响
        self._archives: list[dict[str, Any]] = []
        self._archive_seq = 0

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("检修单号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"检修单 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于设备检修可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"检修单已{action}"

    # ---------- 验收材料归档 ----------

    def list_archives(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        batches = self._archives
        if keyword:
            batches = [batch for batch in batches if keyword in str(batch.get("检修单号", ""))]
        views = [self._archive_view(batch) for batch in batches]
        if status:
            views = [view for view in views if view["归档状态"] == status]
        total = len(views)
        start = max(page - 1, 0) * size
        return views[start:start + size], total

    def get_archive(self, batch_id: int) -> dict[str, Any] | None:
        batch = self._find_archive(batch_id)
        return None if batch is None else self._archive_view(batch)

    def submit_archive(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """按检修单号批量报送验收材料；重复报送、材料缺失都在这一步拦下并说明理由。"""
        order_no = str(values.get("检修单号") or "").strip()
        if not order_no:
            return None, "缺少必填字段：检修单号"
        reporter = str(values.get("报送人") or "").strip()
        if not reporter:
            return None, "缺少必填字段：报送人"
        if not any(str(row.get("检修单号", "")) == order_no for row in store.rows(MODULE)):
            return None, f"检修单号 {order_no} 不存在，验收材料必须挂在已登记的检修单上"
        existing = self._find_archive_by_order(order_no)
        if existing is not None:
            status = self._archive_view(existing)["归档状态"]
            return None, (
                f"检修单 {order_no} 已报送过验收材料（批次 #{existing['id']}，当前{status}），"
                "同一检修单不能重复报送；被驳回的材料请在原批次内整改后重新报送"
            )
        materials = values.get("materials")
        if not isinstance(materials, list) or not materials:
            return None, "验收材料缺失：请把设备照片与检测报告一次批量提交"
        items: list[dict[str, Any]] = []
        for index, raw in enumerate(materials, start=1):
            if not isinstance(raw, dict):
                return None, f"第 {index} 条材料格式不对：每条材料都要包含材料类型、材料名称、文件格式"
            material_type = str(raw.get("材料类型") or "").strip()
            name = str(raw.get("材料名称") or "").strip()
            fmt = str(raw.get("文件格式") or "").strip().lower().lstrip(".")
            if material_type not in MATERIAL_TYPES:
                return None, f"第 {index} 条材料类型「{material_type or '空'}」不在允许范围（{'、'.join(MATERIAL_TYPES)}）"
            if not name:
                return None, f"第 {index} 条材料缺失名称，请补齐后再报送"
            if not fmt:
                return None, f"第 {index} 条材料缺失文件格式，请补齐后再报送"
            items.append({
                "id": index,
                "材料类型": material_type,
                "材料名称": name,
                "文件格式": fmt,
                "status": "待确认",
                "驳回理由": "",
            })
        missing_types = [t for t in MATERIAL_TYPES if not any(item["材料类型"] == t for item in items)]
        if missing_types:
            return None, f"验收材料缺失：缺少{'、'.join(missing_types)}"
        self._archive_seq += 1
        batch = {
            "id": self._archive_seq,
            "检修单号": order_no,
            "报送人": reporter,
            "验收人员": str(values.get("验收人员") or "").strip(),
            "报送时间": datetime.now().isoformat(timespec="seconds"),
            "归档时间": "",
            "archived": False,
            "items": items,
        }
        self._archives.append(batch)
        return self._archive_view(batch), f"检修单 {order_no} 的 {len(items)} 条验收材料已报送，等待验收人逐条确认"

    def run_archive_item_action(
        self,
        batch_id: int,
        item_id: int,
        action: str,
        values: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, str]:
        """验收人逐条处理材料：确认、驳回、驳回后重新报送。"""
        batch = self._find_archive(batch_id)
        if batch is None:
            return None, f"归档批次 {batch_id} 不存在"
        if action not in ARCHIVE_ITEM_ACTIONS:
            return None, f"动作「{action}」不属于验收材料可执行范围"
        if batch["archived"]:
            return None, f"批次 #{batch_id} 已整组归档，材料不能再改动"
        item = next((entry for entry in batch["items"] if entry["id"] == item_id), None)
        if item is None:
            return None, f"批次 #{batch_id} 里没有材料 {item_id}"
        if action == "确认材料":
            return self._confirm_item(batch, item, values)
        if action == "驳回材料":
            return self._reject_item(batch, item, values)
        return self._resubmit_item(batch, item, values)

    def run_archive_action(
        self,
        batch_id: int,
        action: str,
        values: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, str]:
        """整组归档：全部条目确认完毕且验收人已签才允许归档。"""
        batch = self._find_archive(batch_id)
        if batch is None:
            return None, f"归档批次 {batch_id} 不存在"
        if action not in ARCHIVE_ACTIONS:
            return None, f"动作「{action}」不属于验收归档可执行范围"
        if batch["archived"]:
            return None, f"批次 #{batch_id} 已归档，同一批次不能重复归档"
        signer = str(values.get("验收人员") or "").strip() or batch["验收人员"]
        if not signer:
            return None, "验收人未签：请先填写验收人员再整组归档"
        pending = sum(1 for entry in batch["items"] if entry["status"] == "待确认")
        rejected = sum(1 for entry in batch["items"] if entry["status"] == "已驳回")
        blockers: list[str] = []
        if pending:
            blockers.append(f"还有 {pending} 条材料未确认")
        if rejected:
            blockers.append(f"还有 {rejected} 条材料被驳回待整改")
        if blockers:
            return None, "，".join(blockers) + "，验收人逐条确认（驳回的需重新报送）后才能整组归档"
        batch["archived"] = True
        batch["验收人员"] = signer
        batch["归档时间"] = datetime.now().isoformat(timespec="seconds")
        return self._archive_view(batch), f"检修单 {batch['检修单号']} 的 {len(batch['items'])} 条验收材料已整组归档"

    def _confirm_item(
        self,
        batch: dict[str, Any],
        item: dict[str, Any],
        values: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, str]:
        signer = str(values.get("验收人员") or "").strip() or batch["验收人员"]
        if not signer:
            return None, "验收人未签：请先填写验收人员再确认材料"
        if item["status"] != "待确认":
            return None, f"材料 #{item['id']} 当前状态为「{item['status']}」，不能重复确认"
        if not item["材料名称"]:
            return None, f"材料 #{item['id']} 缺失材料，请单条驳回并注明缺材料"
        allowed = MATERIAL_FORMATS.get(item["材料类型"], set())
        if item["文件格式"] not in allowed:
            return None, f"材料 #{item['id']} 格式不对（{item['材料类型']}仅支持 {'/'.join(sorted(allowed))}），请单条驳回"
        item["status"] = "已确认"
        batch["验收人员"] = signer
        return self._archive_view(batch), f"材料 #{item['id']} 已确认"

    def _reject_item(
        self,
        batch: dict[str, Any],
        item: dict[str, Any],
        values: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, str]:
        signer = str(values.get("验收人员") or "").strip() or batch["验收人员"]
        if not signer:
            return None, "验收人未签：请先填写验收人员再驳回材料"
        if item["status"] != "待确认":
            return None, f"材料 #{item['id']} 当前状态为「{item['status']}」，不能驳回"
        reason = str(values.get("驳回理由") or "").strip()
        if not reason:
            return None, "驳回必须填写理由（如缺材料、格式不对）"
        item["status"] = "已驳回"
        item["驳回理由"] = reason
        batch["验收人员"] = signer
        return self._archive_view(batch), f"材料 #{item['id']} 已驳回：{reason}"

    def _resubmit_item(
        self,
        batch: dict[str, Any],
        item: dict[str, Any],
        values: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, str]:
        if item["status"] != "已驳回":
            return None, f"材料 #{item['id']} 当前状态为「{item['status']}」，只有被驳回的材料才能重新报送"
        material_type = str(values.get("材料类型") or item["材料类型"]).strip()
        if material_type not in MATERIAL_TYPES:
            return None, f"材料类型「{material_type}」不在允许范围（{'、'.join(MATERIAL_TYPES)}）"
        name = str(values.get("材料名称") or "").strip()
        if not name:
            return None, "重新报送时材料名称不能为空"
        fmt = str(values.get("文件格式") or "").strip().lower().lstrip(".")
        if not fmt:
            return None, "重新报送时文件格式不能为空"
        item.update({"材料类型": material_type, "材料名称": name, "文件格式": fmt, "status": "待确认", "驳回理由": ""})
        return self._archive_view(batch), f"材料 #{item['id']} 已重新报送，等待验收人确认"

    def _find_archive(self, batch_id: int) -> dict[str, Any] | None:
        for batch in self._archives:
            if batch["id"] == batch_id:
                return batch
        return None

    def _find_archive_by_order(self, order_no: str) -> dict[str, Any] | None:
        for batch in self._archives:
            if batch["检修单号"] == order_no:
                return batch
        return None

    def _archive_view(self, batch: dict[str, Any]) -> dict[str, Any]:
        """批次对外视图：进度与归档状态由条目实时汇总，保证整组进度与实际条目一致。"""
        items = batch["items"]
        total = len(items)
        confirmed = sum(1 for entry in items if entry["status"] == "已确认")
        rejected = sum(1 for entry in items if entry["status"] == "已驳回")
        pending = sum(1 for entry in items if entry["status"] == "待确认")
        if batch["archived"]:
            status = "已归档"
        elif pending:
            status = "待确认"
        elif rejected:
            status = "待整改"
        else:
            status = "待归档"
        return {
            "id": batch["id"],
            "检修单号": batch["检修单号"],
            "报送人": batch["报送人"],
            "验收人员": batch["验收人员"],
            "报送时间": batch["报送时间"],
            "归档时间": batch["归档时间"],
            "材料总数": total,
            "已确认": confirmed,
            "已驳回": rejected,
            "待确认": pending,
            "归档进度": f"{confirmed}/{total}",
            "归档状态": status,
            "items": [dict(entry) for entry in items],
        }
