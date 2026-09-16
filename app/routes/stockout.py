import logging
from datetime import datetime

from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user, login_required

from .. import db
from ..models import InventoryRow, StockOut, StockRequest, User
from ..services.inventory.normalize import find_quantity_key, normalize_row

stockout_bp = Blueprint("stockout", __name__)
logger = logging.getLogger(__name__)


def _serialize(entry):
    return {
        "id": entry.id,
        "row_id": entry.inventory_row_id,
        "identifier": entry.identifier,
        "item_name": entry.item_name,
        "site": entry.site,
        "quantity": entry.quantity,
        "reason": entry.reason,
        "created_at": entry.created_at.strftime("%Y-%m-%d %H:%M"),
        # 요청하신 "2026.09.09 1ea 장애처리" 형식의 요약 한 줄
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


@stockout_bp.post("/api/stockout")
@login_required
def create_stockout():

    payload = request.get_json(force=True) or {}

    row_id = payload.get("row_id")
    site = str(payload.get("site", "")).strip()
    reason = str(payload.get("reason", "")).strip()

    try:
        quantity = float(payload.get("quantity"))
    except (TypeError, ValueError):
        quantity = None

    if not row_id:
        return jsonify({"error": "row_id가 필요합니다."}), 400

    if not site:
        return jsonify({"error": "출고할 사이트를 입력하세요."}), 400

    if not quantity or quantity <= 0:
        return jsonify({"error": "출고 수량은 0보다 커야 합니다."}), 400

    row = db.get_or_404(InventoryRow, row_id)

    current_qty = row.quantity or 0

    if quantity > current_qty:
        return jsonify(
            {"error": f"현재 재고({current_qty:g})보다 많은 수량은 출고할 수 없습니다."}
        ), 400

    # -----------------------------------------------------
    # 1) InventoryRow.quantity 차감
    # -----------------------------------------------------
    new_qty = current_qty - quantity
    row.quantity = new_qty

    # -----------------------------------------------------
    # 2) data_json(원본 엑셀 셀 값)도 같이 차감
    #    -> 상세보기/테이블에 보이는 값과 실제 수량이 어긋나지 않도록
    # -----------------------------------------------------
    data = dict(row.data_json or {})
    qty_key = find_quantity_key(data)

    if qty_key:
        data[qty_key] = new_qty
        row.data_json = data

        # 다른 정규화 필드들도 최신 상태로 재계산
        n = normalize_row(data)
        row.identifier = n.get("identifier", row.identifier)
        row.item_name = n.get("item_name", row.item_name)
        row.manufacturer = n.get("manufacturer", row.manufacturer)
        row.model = n.get("model", row.model)
        row.capacity = n.get("capacity", row.capacity)
        row.location = n.get("location", row.location)
        row.status = n.get("status", row.status)

    # -----------------------------------------------------
    # 3) 출고 이력 기록
    # -----------------------------------------------------
    entry = StockOut(
        inventory_row_id=row.id,
        user_id=current_user.id,
        identifier=row.identifier,
        item_name=row.item_name,
        site=site,
        quantity=quantity,
        reason=reason or None,
        created_at=datetime.utcnow(),
    )

    db.session.add(entry)

    # -----------------------------------------------------
    # 4) 자동 입고요청 생성 — 출고 후 재고가 1개 이하로 떨어지면,
    #    기존에 미승인 요청이 있더라도 합치지 않고 매번 새 건으로 따로 생성한다.
    #    요청수량 = 2(버퍼) - 현재수량  ->  1개 남았으면 1개, 0개이면 2개 요청
    # -----------------------------------------------------
    auto_request_created = new_qty <= 1

    if auto_request_created:
        auto_request = StockRequest(
            inventory_row_id=row.id,
            identifier=row.identifier,
            item_name=row.item_name,
            site=site,
            quantity=2 - new_qty,
            reason=f"출고 후 재고 {new_qty:g}개 — 자동 생성된 입고요청",
            source="auto",
            status="requested",
            requested_by_id=current_user.id,
        )
        db.session.add(auto_request)
        logger.info(
            "Auto stock-request created | row_id=%s | quantity=%s",
            row.id,
            auto_request.quantity,
        )

    db.session.commit()

    logger.info(
        "Stock-out recorded | row_id=%s | site=%s | quantity=%s | user_id=%s",
        row.id,
        site,
        quantity,
        current_user.id,
    )

    return jsonify(
        {
            "ok": True,
            "item": _serialize(entry),
            "row_quantity": new_qty,
            "auto_request_created": auto_request_created,
        }
    )


@stockout_bp.get("/api/stockout")
@login_required
def list_stockout():

    page = max(request.args.get("page", 1, type=int), 1)
    page_size = min(max(request.args.get("page_size", 10, type=int), 1), 200)
    sort_col = request.args.get("sort", "").strip()
    sort_dir = request.args.get("dir", "desc").strip().lower()
    sort_dir = "asc" if sort_dir == "asc" else "desc"

    q = request.args.get("q", "").strip()
    date = request.args.get("date", "").strip()

    query = StockOut.query

    if q:
        like = f"%{q}%"
        query = query.filter(
            db.or_(
                StockOut.identifier.ilike(like),
                StockOut.item_name.ilike(like),
                StockOut.site.ilike(like),
                StockOut.reason.ilike(like),
            )
        )

    if date:
        try:
            day = datetime.strptime(date, "%Y-%m-%d").date()
            query = query.filter(db.func.date(StockOut.created_at) == day)
        except ValueError:
            pass

    total = query.count()
    total_pages = max((total + page_size - 1) // page_size, 1)
    page = min(page, total_pages)

    sortable_columns = {
        "created_at": StockOut.created_at,
        "identifier": StockOut.identifier,
        "item_name": StockOut.item_name,
        "site": StockOut.site,
        "quantity": StockOut.quantity,
        "reason": StockOut.reason,
    }

    if sort_col == "user":
        query = query.outerjoin(User, StockOut.user_id == User.id)
        column_expr = db.func.coalesce(User.name, User.username)
    else:
        column_expr = sortable_columns.get(sort_col, StockOut.created_at)

    order_by_clause = (
        column_expr.asc() if sort_dir == "asc" else column_expr.desc()
    )

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


@stockout_bp.get("/stockout")
@login_required
def stockout_page():
    return render_template("pages/stockout/list.html")
