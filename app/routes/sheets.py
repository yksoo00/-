import json, logging
from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from sqlalchemy import cast, Text
from .. import db
from ..models import ExcelSheet, SheetColumn, InventoryRow, InventoryChange
from ..services.inventory.normalize import normalize_row, infer_field
from .common import serialize_row, admin_required_api, log_admin_action

sheets_bp = Blueprint("sheets", __name__)
logger = logging.getLogger(__name__)


@sheets_bp.get("/rows/<int:sheet_id>")
@login_required
def api_rows(sheet_id):
    logger.info(
        "Sheet rows request | sheet_id=%s | q_present=%s | page=%s",
        sheet_id,
        bool(request.args.get("q", "").strip()),
        request.args.get("page", 1),
    )

    page = max(request.args.get("page", 1, type=int), 1)

    size = min(max(request.args.get("size", 50, type=int), 1), 200)

    q = request.args.get("q", "").strip()

    query = InventoryRow.query.filter_by(sheet_id=sheet_id, is_deleted=False)

    if q:
        query = query.filter(cast(InventoryRow.data_json, Text).like(f"%{q}%"))

    total = query.count()

    rows = (
        query.order_by(InventoryRow.row_number)
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    cols = (
        SheetColumn.query.filter_by(sheet_id=sheet_id)
        .order_by(SheetColumn.column_index)
        .all()
    )

    return jsonify(
        {
            "columns": [c.original_name for c in cols],
            "items": [serialize_row(r) for r in rows],
            "total": total,
            "page": page,
            "size": size,
        }
    )


@sheets_bp.patch("/rows/<int:row_id>")
@admin_required_api
def update_row(row_id):

    row = db.get_or_404(InventoryRow, row_id)

    payload = request.get_json(force=True) or {}

    data = dict(row.data_json or {})

    changes = []

    for field, new in payload.get("data", {}).items():
        old = data.get(field)

        if str(old) != str(new):
            data[field] = new

            changes.append((field, old, new))

    n = normalize_row(data)

    row.data_json = data
    row.identifier = n.get("identifier")
    row.item_name = n.get("item_name")
    row.manufacturer = n.get("manufacturer")
    row.model = n.get("model")
    row.capacity = n.get("capacity")
    row.quantity = n.get("quantity")
    row.location = n.get("location")
    row.status = n.get("status")

    for field, old, new in changes:
        db.session.add(
            InventoryChange(
                inventory_row_id=row.id,
                user_id=current_user.id,
                change_type="update",
                field_name=field,
                old_value=str(old),
                new_value=str(new),
                reason=payload.get("reason", ""),
                source="web",
            )
        )

    if changes:
        log_admin_action(
            "row_edit",
            detail=f"{row.identifier or row.id}: " + ", ".join(f"{f} {o!r}→{n!r}" for f, o, n in changes),
            target_type="inventory_row",
            target_id=row.id,
        )

    db.session.commit()
    logger.info(
        "Inventory row updated | row_id=%s | sheet_id=%s | changes=%s | user_id=%s",
        row.id,
        row.sheet_id,
        len(changes),
        current_user.id,
    )

    return jsonify({"ok": True, "item": serialize_row(row)})


@sheets_bp.post("/rows/<int:row_id>/delete")
@admin_required_api
def delete_row(row_id):

    row = db.get_or_404(InventoryRow, row_id)

    logger.info(
        "Inventory row delete requested | row_id=%s | user_id=%s",
        row_id,
        current_user.id,
    )
    row.is_deleted = True

    db.session.add(
        InventoryChange(
            inventory_row_id=row.id,
            user_id=current_user.id,
            change_type="delete",
            field_name="row",
            old_value=json.dumps(row.data_json, ensure_ascii=False, default=str),
            new_value="",
            reason=(request.json.get("reason", "") if request.is_json else ""),
            source="web",
        )
    )

    log_admin_action(
        "row_delete",
        detail=f"{row.identifier or row.id} 행 삭제",
        target_type="inventory_row",
        target_id=row.id,
    )

    db.session.commit()
    logger.info(
        "Inventory row deleted | row_id=%s | user_id=%s", row_id, current_user.id
    )

    return jsonify({"ok": True})


@sheets_bp.post("/columns")
@admin_required_api
def add_column():

    payload = request.get_json(force=True) or {}

    sheet_id = payload.get("sheet_id")

    name = str(payload.get("name", "")).strip()

    if not sheet_id or not name:
        return jsonify({"error": "Sheet와 컬럼명을 입력하세요."}), 400

    if SheetColumn.query.filter_by(sheet_id=int(sheet_id), original_name=name).first():
        return jsonify({"error": "이미 존재하는 컬럼입니다."}), 409

    cols = (
        SheetColumn.query.filter_by(sheet_id=int(sheet_id))
        .order_by(SheetColumn.column_index.desc())
        .all()
    )

    idx = (cols[0].column_index if cols else 0) + 1

    c = SheetColumn(
        sheet_id=int(sheet_id),
        column_index=idx,
        original_name=name,
        normalized_name=infer_field(name),
        data_type="string",
        is_searchable=True,
        is_filterable=True,
        filter_type="text",
    )

    db.session.add(c)

    for row in InventoryRow.query.filter_by(
        sheet_id=int(sheet_id), is_deleted=False
    ).all():
        d = dict(row.data_json or {})

        d.setdefault(name, "")

        row.data_json = d

    log_admin_action(
        "column_add",
        detail=f"sheet {sheet_id}에 '{name}' 컬럼 추가",
        target_type="sheet",
        target_id=int(sheet_id),
    )

    db.session.commit()

    return jsonify({"ok": True, "column": name})
