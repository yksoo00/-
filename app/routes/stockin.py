import logging
from datetime import datetime

from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user, login_required

from .. import db
from ..models import InventoryRow, StockIn, User
from ..services.inventory.normalize import find_quantity_key, normalize_row

stockin_bp = Blueprint("stockin", __name__)
logger = logging.getLogger(__name__)


SOURCE_LABEL = {
    "manual": "수동",
    "auto_request": "자동(요청승인)",
}


def _serialize(entry):
    return {
        "id": entry.id,
        "row_id": entry.inventory_row_id,
        "request_id": entry.stock_request_id,
        "identifier": entry.identifier,
        "item_name": entry.item_name,
        "site": entry.site,
        "quantity": entry.quantity,
        "reason": entry.reason,
        "source": entry.source,
        "source_label": SOURCE_LABEL.get(entry.source, entry.source),
        "created_at": entry.created_at.strftime("%Y-%m-%d %H:%M"),
        "summary": "{date} {qty}ea {reason}".format(
            date=entry.created_at.strftime("%Y.%m.%d"),
            qty=(
                int(entry.quantity)
                if float(entry.quantity).is_integer()
                else entry.quantity
            ),
            reason=entry.reason or "",
        ),
        "user": entry.user.name or entry.user.username if entry.user else None,
    }


def apply_stock_in(row, quantity, *, reason, source, user_id, site=None, stock_request_id=None):
    """
    InventoryRow.quantity를 실제로 가산하고 StockIn 이력을 한 줄 남기는 공용 로직.
    수동입고(/api/stockin)와 입고요청 물품도착 처리(stockrequest.py) 둘 다 여기를 거친다.
    """

    old_qty = row.quantity or 0
    new_qty = old_qty + quantity
    row.quantity = new_qty

    data = dict(row.data_json or {})
    qty_key = find_quantity_key(data)

    if qty_key:
        data[qty_key] = new_qty
        row.data_json = data

        n = normalize_row(data)
        row.identifier = n.get("identifier", row.identifier)
        row.item_name = n.get("item_name", row.item_name)
        row.manufacturer = n.get("manufacturer", row.manufacturer)
        row.model = n.get("model", row.model)
        row.capacity = n.get("capacity", row.capacity)
        row.location = n.get("location", row.location)
        row.status = n.get("status", row.status)

    entry = StockIn(
        inventory_row_id=row.id,
        stock_request_id=stock_request_id,
        user_id=user_id,
        identifier=row.identifier,
        item_name=row.item_name,
        site=site,
        quantity=quantity,
        reason=reason,
        source=source,
        created_at=datetime.utcnow(),
    )
    db.session.add(entry)

    return new_qty, entry


# =========================================================
# 수동입고 — 물품/현재수량은 프론트에서 자동 표시되고 수량만 받아 즉시 DB에 가산한다.
# =========================================================
@stockin_bp.post("/api/stockin")
@login_required
def create_stockin():

    payload = request.get_json(force=True) or {}

    row_id = payload.get("row_id")

    try:
        quantity = float(payload.get("quantity"))
    except (TypeError, ValueError):
        quantity = None

    if not row_id:
        return jsonify({"error": "row_id가 필요합니다."}), 400

    if not quantity or quantity <= 0:
        return jsonify({"error": "입고 수량은 0보다 커야 합니다."}), 400

    row = db.get_or_404(InventoryRow, row_id)

    new_qty, entry = apply_stock_in(
        row,
        quantity,
        reason="수동입고",
        source="manual",
        user_id=current_user.id,
    )

    db.session.commit()

    logger.info(
        "Manual stock-in recorded | row_id=%s | quantity=%s | user_id=%s",
        row.id,
        quantity,
        current_user.id,
    )

    return jsonify({"ok": True, "item": _serialize(entry), "row_quantity": new_qty})


# =========================================================
# 입고 내역 조회 — 수동입고 + 입고요청 물품도착(자동) 전부 여기 한 곳에 모인다.
# =========================================================
@stockin_bp.get("/api/stockin")
@login_required
def list_stockin():

    page = max(request.args.get("page", 1, type=int), 1)
    page_size = min(max(request.args.get("page_size", 10, type=int), 1), 200)
    sort_col = request.args.get("sort", "").strip()
    sort_dir = request.args.get("dir", "desc").strip().lower()
    sort_dir = "asc" if sort_dir == "asc" else "desc"

    q = request.args.get("q", "").strip()
    source = request.args.get("source", "").strip()

    query = StockIn.query

    if q:
        like = f"%{q}%"
        query = query.filter(
            db.or_(
                StockIn.identifier.ilike(like),
                StockIn.item_name.ilike(like),
                StockIn.site.ilike(like),
                StockIn.reason.ilike(like),
            )
        )

    if source:
        query = query.filter(StockIn.source == source)

    total = query.count()
    total_pages = max((total + page_size - 1) // page_size, 1)
    page = min(page, total_pages)

    sortable_columns = {
        "created_at": StockIn.created_at,
        "identifier": StockIn.identifier,
        "item_name": StockIn.item_name,
        "site": StockIn.site,
        "quantity": StockIn.quantity,
        "source": StockIn.source,
    }

    if sort_col == "user":
        query = query.outerjoin(User, StockIn.user_id == User.id)
        column_expr = db.func.coalesce(User.name, User.username)
    else:
        column_expr = sortable_columns.get(sort_col, StockIn.created_at)

    order_by_clause = column_expr.asc() if sort_dir == "asc" else column_expr.desc()

    rows = (
        query.order_by(order_by_clause)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return jsonify(
        {
            "items": [_serialize(entry) for entry in rows],
            "count": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "sort": sort_col,
            "dir": sort_dir,
        }
    )


@stockin_bp.get("/stockin")
@login_required
def stockin_page():
    return render_template("pages/stockin/list.html")
