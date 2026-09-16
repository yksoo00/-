import logging
from datetime import datetime

from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user, login_required

from .. import db
from .common import admin_required_api, log_admin_action
from .stockin import apply_stock_in
from ..models import InventoryRow, StockRequest

stockrequest_bp = Blueprint("stockrequest", __name__)
logger = logging.getLogger(__name__)


def _user_label(user):
    if not user:
        return None
    return user.name or user.username


def _serialize(entry):
    return {
        "id": entry.id,
        "row_id": entry.inventory_row_id,
        "identifier": entry.identifier,
        "item_name": entry.item_name,
        "site": entry.site,
        "quantity": entry.quantity,
        "reason": entry.reason,
        "source": entry.source,
        "status": entry.status,
        "created_at": entry.created_at.strftime("%Y-%m-%d %H:%M"),
        "created_date": entry.created_at.strftime("%Y-%m-%d"),
        "requested_by": _user_label(entry.requested_by),
        "approved_by": _user_label(entry.approved_by),
        "approved_at": entry.approved_at.strftime("%Y-%m-%d %H:%M") if entry.approved_at else None,
        "arrived_by": _user_label(entry.arrived_by),
        "arrived_at": entry.arrived_at.strftime("%Y-%m-%d %H:%M") if entry.arrived_at else None,
    }


# =========================================================
# 목록 조회 (사용자/관리자 모두 접근 가능 — 버튼 노출만 프론트에서 role로 구분)
# =========================================================
@stockrequest_bp.get("/api/stockrequest")
@login_required
def list_stockrequest():

    page = max(request.args.get("page", 1, type=int), 1)
    page_size = min(max(request.args.get("page_size", 10, type=int), 1), 200)
    sort_col = request.args.get("sort", "").strip()
    sort_dir = request.args.get("dir", "desc").strip().lower()
    sort_dir = "asc" if sort_dir == "asc" else "desc"

    q = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip()
    date = request.args.get("date", "").strip()  # YYYY-MM-DD

    query = StockRequest.query

    if q:
        like = f"%{q}%"
        query = query.filter(
            db.or_(
                StockRequest.identifier.ilike(like),
                StockRequest.item_name.ilike(like),
                StockRequest.site.ilike(like),
                StockRequest.reason.ilike(like),
            )
        )

    if status:
        query = query.filter(StockRequest.status == status)

    if date:
        try:
            day = datetime.strptime(date, "%Y-%m-%d").date()
            query = query.filter(db.func.date(StockRequest.created_at) == day)
        except ValueError:
            pass

    total = query.count()
    total_pages = max((total + page_size - 1) // page_size, 1)
    page = min(page, total_pages)

    sortable_columns = {
        "created_at": StockRequest.created_at,
        "identifier": StockRequest.identifier,
        "item_name": StockRequest.item_name,
        "site": StockRequest.site,
        "quantity": StockRequest.quantity,
        "status": StockRequest.status,
    }
    column_expr = sortable_columns.get(sort_col, StockRequest.created_at)
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


# =========================================================
# 수동 요청 생성 (물품 선택 / 현재수량 자동 / 사이트 / 요청수량 / 요청이유)
# =========================================================
@stockrequest_bp.post("/api/stockrequest")
@login_required
def create_stockrequest():

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
        return jsonify({"error": "요청할 사이트를 입력하세요."}), 400

    if not quantity or quantity <= 0:
        return jsonify({"error": "요청 수량은 0보다 커야 합니다."}), 400

    row = db.get_or_404(InventoryRow, row_id)

    entry = StockRequest(
        inventory_row_id=row.id,
        identifier=row.identifier,
        item_name=row.item_name,
        site=site,
        quantity=quantity,
        reason=reason or None,
        source="manual",
        status="requested",
        requested_by_id=current_user.id,
        created_at=datetime.utcnow(),
    )

    db.session.add(entry)
    db.session.commit()

    logger.info(
        "Manual stock-request created | row_id=%s | quantity=%s | user_id=%s",
        row.id,
        quantity,
        current_user.id,
    )

    return jsonify({"ok": True, "item": _serialize(entry)})


# =========================================================
# 승인 (관리자 전용) — "확인했다"는 의미일 뿐 DB 재고엔 아직 반영되지 않는다.
# =========================================================
@stockrequest_bp.post("/api/stockrequest/<int:request_id>/approve")
@admin_required_api
def approve_stockrequest(request_id):

    entry = db.get_or_404(StockRequest, request_id)

    if entry.status != "requested":
        return jsonify({"error": "이미 처리된 요청입니다."}), 400

    entry.status = "approved"
    entry.approved_by_id = current_user.id
    entry.approved_at = datetime.utcnow()
    log_admin_action(
        "stockrequest_approve",
        detail=f"{entry.identifier or entry.item_name} 입고요청 #{entry.id} 승인",
        target_type="stock_request",
        target_id=entry.id,
    )
    db.session.commit()

    logger.info(
        "Stock-request approved | request_id=%s | admin_id=%s",
        entry.id,
        current_user.id,
    )

    return jsonify({"ok": True, "item": _serialize(entry)})


# =========================================================
# 물품도착 (관리자 전용) — 실제로 InventoryRow.quantity에 요청수량만큼 가산한다(=자동입고).
# =========================================================
@stockrequest_bp.post("/api/stockrequest/<int:request_id>/arrive")
@admin_required_api
def arrive_stockrequest(request_id):

    entry = db.get_or_404(StockRequest, request_id)

    if entry.status != "approved":
        return jsonify({"error": "승인된 요청만 물품도착 처리할 수 있습니다."}), 400

    row = entry.row

    if row is None:
        return jsonify({"error": "원본 품목이 삭제되어 재고에 반영할 수 없습니다."}), 400

    new_qty, stock_in_entry = apply_stock_in(
        row,
        entry.quantity,
        reason=f"입고요청 #{entry.id} 물품도착 처리",
        source="auto_request",
        user_id=current_user.id,
        site=entry.site,
        stock_request_id=entry.id,
    )

    entry.status = "arrived"
    entry.arrived_by_id = current_user.id
    entry.arrived_at = datetime.utcnow()

    log_admin_action(
        "stockrequest_arrive",
        detail=f"{entry.identifier or entry.item_name} 입고요청 #{entry.id} 물품도착 처리 ({entry.quantity:g}개)",
        target_type="stock_request",
        target_id=entry.id,
    )

    db.session.commit()

    logger.info(
        "Stock-request arrived (auto stock-in) | request_id=%s | row_id=%s | quantity=%s | admin_id=%s | stock_in_id=%s",
        entry.id,
        row.id,
        entry.quantity,
        current_user.id,
        stock_in_entry.id,
    )

    return jsonify({"ok": True, "item": _serialize(entry), "row_quantity": new_qty})


@stockrequest_bp.get("/requests")
@login_required
def stockrequest_page():
    return render_template("pages/stockrequest/list.html")
