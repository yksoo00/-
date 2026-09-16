import logging
from datetime import datetime

from flask import Blueprint, jsonify, render_template, request

from .. import db
from .common import admin_required, admin_required_api
from ..models import AdminLog, User

adminlog_bp = Blueprint("adminlog", __name__)
logger = logging.getLogger(__name__)


ACTION_LABEL = {
    "row_edit": "재고 수정",
    "row_delete": "재고 삭제",
    "column_add": "컬럼 추가",
    "excel_upload": "Excel 업로드",
    "excel_delete": "Excel 삭제",
    "user_create": "사용자 생성",
    "stockrequest_approve": "입고요청 승인",
    "stockrequest_arrive": "입고요청 물품도착",
}


def _serialize(entry):
    return {
        "id": entry.id,
        "action": entry.action,
        "action_label": ACTION_LABEL.get(entry.action, entry.action),
        "target_type": entry.target_type,
        "target_id": entry.target_id,
        "detail": entry.detail,
        "user": (entry.user.name or entry.user.username) if entry.user else None,
        "created_at": entry.created_at.strftime("%Y-%m-%d %H:%M"),
    }


@adminlog_bp.get("/api/adminlog")
@admin_required_api
def list_adminlog():

    page = max(request.args.get("page", 1, type=int), 1)
    page_size = min(max(request.args.get("page_size", 10, type=int), 1), 200)

    q = request.args.get("q", "").strip()
    action = request.args.get("action", "").strip()
    date = request.args.get("date", "").strip()

    query = AdminLog.query

    if q:
        like = f"%{q}%"
        query = query.outerjoin(User, AdminLog.user_id == User.id).filter(
            db.or_(
                AdminLog.detail.ilike(like),
                User.name.ilike(like),
                User.username.ilike(like),
            )
        )

    if action:
        query = query.filter(AdminLog.action == action)

    if date:
        try:
            day = datetime.strptime(date, "%Y-%m-%d").date()
            query = query.filter(db.func.date(AdminLog.created_at) == day)
        except ValueError:
            pass

    total = query.count()
    total_pages = max((total + page_size - 1) // page_size, 1)
    page = min(page, total_pages)

    rows = (
        query.order_by(AdminLog.created_at.desc())
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
            "actions": ACTION_LABEL,
        }
    )


@adminlog_bp.get("/admin/logs")
@admin_required
def adminlog_page():
    return render_template("pages/adminlog/list.html", actions=ACTION_LABEL)
