"""检修验收材料归档：按检修单号批量报送设备照片与检测报告，验收人逐条确认后整组归档。

口径边界：本服务只管“验收材料归档”这条支线，绝不改动检修单本身
待受理 / 检修中 / 待验收 / 已验收 的状态与动作（见 services/maint.py）。

整组状态不入库：批次状态与进度在读取时按条目实时派生，
保证“整组进度”永远和实际条目一致，不会出现先改状态、条目没跟上的漂移。
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from app.store import store

MAINT_MODULE = "maint"
GROUP_MODULE = "maint_archive_group"
ITEM_MODULE = "maint_archive_item"

MATERIAL_TYPES = ("设备照片", "检测报告")
PHOTO_EXTS = (".jpg", ".jpeg", ".png")
REPORT_EXTS = (".pdf", ".doc", ".docx")

ITEM_PENDING = "待验收"
ITEM_PASSED = "已通过"
ITEM_REJECTED = "已驳回"

GROUP_IN_REVIEW = "验收中"
GROUP_READY = "待归档"
GROUP_ARCHIVED = "已归档"
GROUP_RETURNED = "已退回"
GROUP_STATUSES = (GROUP_IN_REVIEW, GROUP_READY, GROUP_ARCHIVED, GROUP_RETURNED)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class MaintArchiveService:
    # ------------------------------------------------------------------ 读取
    def _groups(self) -> list[dict[str, Any]]:
        return store.rows(GROUP_MODULE)

    def _items(self) -> list[dict[str, Any]]:
        return store.rows(ITEM_MODULE)

    def _items_of(self, group_id: int) -> list[dict[str, Any]]:
        return [item for item in self._items() if int(item.get("group_id", 0)) == group_id]

    def _find_group(self, group_id: int) -> dict[str, Any] | None:
        for group in self._groups():
            if int(group.get("id", 0)) == group_id:
                return group
        return None

    def _find_order(self, order_no: str) -> dict[str, Any] | None:
        for row in store.rows(MAINT_MODULE):
            if str(row.get("检修单号", "")).strip() == order_no:
                return row
        return None

    def _latest_group(self, order_no: str) -> dict[str, Any] | None:
        groups = [g for g in self._groups() if g.get("检修单号") == order_no]
        return max(groups, key=lambda g: int(g.get("id", 0)), default=None)

    def _progress(self, group: dict[str, Any]) -> dict[str, Any]:
        """整组进度全部由实际条目现算，不读任何缓存状态。"""
        items = self._items_of(int(group["id"]))
        total = len(items)
        confirmed = sum(1 for item in items if item.get("status") == ITEM_PASSED)
        rejected = sum(1 for item in items if item.get("status") == ITEM_REJECTED)
        pending = total - confirmed - rejected
        if group.get("archived"):
            status = GROUP_ARCHIVED
        elif total == 0 or pending > 0:
            # 还有条目没审完（含已通过/已驳回混在里面），整组仍处于验收阶段
            status = GROUP_IN_REVIEW
        elif rejected > 0:
            # 全部审完但有驳回，整组不能归档，退回报送方补正后重新报送
            status = GROUP_RETURNED
        else:
            status = GROUP_READY
        return {
            "status": status,
            "total": total,
            "confirmed": confirmed,
            "rejected": rejected,
            "pending": pending,
            "progress": f"{confirmed}/{total}",
        }

    def _serialize(self, group: dict[str, Any]) -> dict[str, Any]:
        data = dict(group)
        data.update(self._progress(group))
        data["items"] = [dict(item) for item in self._items_of(int(group["id"]))]
        return data

    def list_groups(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        groups = sorted(self._groups(), key=lambda g: int(g.get("id", 0)), reverse=True)
        if keyword:
            groups = [g for g in groups if keyword in str(g.get("检修单号", ""))]
        serialized = [self._serialize(g) for g in groups]
        if status:
            serialized = [g for g in serialized if g["status"] == status]
        total = len(serialized)
        start = max(page - 1, 0) * size
        return serialized[start:start + size], total

    def get_group(self, group_id: int) -> dict[str, Any] | None:
        group = self._find_group(group_id)
        return self._serialize(group) if group else None

    # ------------------------------------------------------------------ 报送
    def submit(
        self, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str, list[dict[str, Any]]]:
        """按检修单号一次批量报送；任何不满足条件的地方都给出明确理由。

        返回 (批次, 总述, 逐条错误)：有错误时不落任何数据，报送方改完整批重报。
        """
        errors: list[dict[str, Any]] = []

        order_no = str(values.get("order_no") or values.get("检修单号") or "").strip()
        submitter = str(values.get("submitter") or values.get("报送人") or "").strip()
        raw_items = values.get("items") or values.get("材料") or []

        if not order_no:
            errors.append({"line": 0, "reason": "缺少检修单号，无法确定材料归属"})
        elif self._find_order(order_no) is None:
            errors.append({"line": 0, "reason": f"检修单号 {order_no} 不存在，请先登记检修单"})
        else:
            latest = self._latest_group(order_no)
            if latest is not None:
                latest_status = self._progress(latest)["status"]
                if latest_status in (GROUP_IN_REVIEW, GROUP_READY):
                    errors.append({
                        "line": 0,
                        "reason": (
                            f"同一检修单重复报送：{order_no} 已有一批验收材料"
                            f"（批次 #{latest['id']}，状态：{latest_status}），"
                            "请待本组验收结束后再报"
                        ),
                    })
                elif latest_status == GROUP_ARCHIVED:
                    errors.append({
                        "line": 0,
                        "reason": f"同一检修单重复报送：{order_no} 的验收材料已整组归档，不能再次报送",
                    })
        if not submitter:
            errors.append({"line": 0, "reason": "缺少报送人，报送时需填写报送人员"})

        if not isinstance(raw_items, list) or not raw_items:
            errors.append({"line": 0, "reason": "材料缺失：本次未提交任何设备照片或检测报告"})
            raw_items = []

        typed_lines: list[str] = []
        for index, raw in enumerate(raw_items, start=1):
            raw = raw if isinstance(raw, dict) else {}
            mtype = str(raw.get("material_type") or raw.get("材料类型") or "").strip()
            name = str(raw.get("material_name") or raw.get("材料名称") or "").strip()
            file_name = str(raw.get("file_name") or raw.get("文件名") or "").strip()
            if mtype not in MATERIAL_TYPES:
                errors.append({
                    "line": index,
                    "reason": f"第 {index} 条材料类型缺失或不支持，仅支持：设备照片、检测报告",
                })
                continue
            typed_lines.append(mtype)
            if not name:
                errors.append({"line": index, "reason": f"材料缺失：第 {index} 条（{mtype}）未填写材料名称"})
            if not file_name:
                errors.append({"line": index, "reason": f"材料缺失：第 {index} 条（{mtype}）未上传文件"})
                continue
            ext = os.path.splitext(file_name)[1].lower()
            allowed = PHOTO_EXTS if mtype == "设备照片" else REPORT_EXTS
            if ext not in allowed:
                allowed_text = "jpg/jpeg/png" if mtype == "设备照片" else "pdf/doc/docx"
                errors.append({
                    "line": index,
                    "reason": f"格式不对：第 {index} 条{mtype}仅支持 {allowed_text}，收到的文件为「{file_name}」",
                })

        # 整组层面两类材料至少各一条，缺整类按材料缺失给出理由
        if isinstance(raw_items, list) and raw_items:
            if "设备照片" not in typed_lines:
                errors.append({"line": 0, "reason": "材料缺失：本批未包含关联设备照片，至少报送一条"})
            if "检测报告" not in typed_lines:
                errors.append({"line": 0, "reason": "材料缺失：本批未包含检测报告，至少报送一条"})

        if errors:
            return None, f"报送未受理，共发现 {len(errors)} 处问题，请按理由逐条核对后整批重报", errors

        groups = self._groups()
        group = {
            "id": max((int(g.get("id", 0)) for g in groups), default=0) + 1,
            "检修单号": order_no,
            "报送人": submitter,
            "报送时间": _now(),
            "archived": False,
            "验收人签字": None,
            "归档时间": None,
        }
        groups.append(group)

        items = self._items()
        next_id = max((int(i.get("id", 0)) for i in items), default=0) + 1
        for raw in raw_items:
            item = {
                "id": next_id,
                "group_id": group["id"],
                "材料类型": str(raw.get("material_type") or raw.get("材料类型") or "").strip(),
                "材料名称": str(raw.get("material_name") or raw.get("材料名称") or "").strip(),
                "文件名": str(raw.get("file_name") or raw.get("文件名") or "").strip(),
                "status": ITEM_PENDING,
                "reject_reason": None,
                "验收人签字": None,
                "验收时间": None,
            }
            items.append(item)
            next_id += 1
        return self._serialize(group), f"已按检修单号 {order_no} 批量报送 {len(raw_items)} 条材料，等待验收人员逐条确认", []

    # ------------------------------------------------------------------ 验收
    def review_item(
        self, group_id: int, item_id: int, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        """验收人对单条材料确认或驳回；驳回必须写明理由，未签字一律拦下。"""
        group = self._find_group(group_id)
        if group is None:
            return None, f"验收批次 #{group_id} 不存在或已删除"
        if group.get("archived"):
            return None, "该批次已整组归档，条目不能再修改"
        item = next(
            (i for i in self._items_of(group_id) if int(i.get("id", 0)) == item_id),
            None,
        )
        if item is None:
            return None, f"材料条目 #{item_id} 不存在或不属于批次 #{group_id}"
        if item.get("status") != ITEM_PENDING:
            return None, f"该材料状态为「{item.get('status')}」，不能重复验收"

        reviewer = str(
            values.get("reviewer") or values.get("验收人签字") or values.get("验收人员") or ""
        ).strip()
        if not reviewer:
            return None, "验收人未签字：逐条确认前请先填写验收人员签字"

        action = str(values.get("action") or "").strip()
        if action == "确认":
            item["status"] = ITEM_PASSED
            item["验收人签字"] = reviewer
            item["验收时间"] = _now()
            item["reject_reason"] = None
            return item, "材料已确认通过"
        if action == "驳回":
            reason = str(values.get("reason") or values.get("驳回理由") or "").strip()
            if not reason:
                return None, "驳回材料必须填写理由（如：材料缺失、格式不对）"
            item["status"] = ITEM_REJECTED
            item["reject_reason"] = reason
            item["验收人签字"] = reviewer
            item["验收时间"] = _now()
            return item, f"材料已单条驳回，理由：{reason}"
        return None, "动作不支持，验收材料仅支持：确认、驳回"

    def archive_group(
        self, group_id: int, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        """整组归档：全部条目确认通过且验收人签字后才放行，否则给出理由。"""
        group = self._find_group(group_id)
        if group is None:
            return None, f"验收批次 #{group_id} 不存在或已删除"
        if group.get("archived"):
            return None, "该批次已整组归档，请勿重复归档"

        reviewer = str(
            values.get("reviewer") or values.get("验收人签字") or values.get("验收人员") or ""
        ).strip()
        if not reviewer:
            return None, "验收人未签字：整组归档前必须由验收人员签字确认"

        progress = self._progress(group)
        if progress["status"] != GROUP_READY:
            return None, (
                f"尚不能整组归档：还有 {progress['pending']} 条待确认、"
                f"{progress['rejected']} 条已驳回，需全部条目确认通过"
            )

        group["archived"] = True
        group["验收人签字"] = reviewer
        group["归档时间"] = _now()
        return self._serialize(group), f"批次 #{group_id} 全部 {progress['total']} 条材料确认通过，已整组归档"
