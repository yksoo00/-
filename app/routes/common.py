from functools import wraps

from flask import flash, jsonify, redirect, request, url_for
from flask_login import current_user, login_required

from .. import db
from ..models import (
    AdminLog,
    ExcelFile,
    ExcelSheet,
    InventoryChange,
    InventoryGroup,
    InventoryRow,
    SheetColumn,
)
from ..services.inventory.normalize import infer_field, normalize_row, to_number


def schema_columns(file_id=None, sheet_id=None, sheet_ids=None):
    query = SheetColumn.query
    if sheet_ids:
        query = query.filter(SheetColumn.sheet_id.in_(sheet_ids))
    elif sheet_id:
        query = query.filter_by(sheet_id=sheet_id)
    elif file_id:
        query = query.join(ExcelSheet, SheetColumn.sheet_id == ExcelSheet.id).filter(
            ExcelSheet.excel_file_id == file_id
        )

    columns = query.order_by(SheetColumn.column_index, SheetColumn.id).all()
    seen = set()
    result = []
    for column in columns:
        if column.original_name and column.original_name not in seen:
            seen.add(column.original_name)
            result.append(column.original_name)
    return result


def serialize_row(row):
    return {
        "id": row.id,
        "file_id": row.excel_file_id,
        "file_name": row.excel_file.original_filename if row.excel_file else None,
        "sheet_id": row.sheet_id,
        "row_number": row.row_number,
        "quantity": row.quantity,
        "identifier": row.identifier,
        "item_name": row.item_name,
        "manufacturer": row.manufacturer,
        "model": row.model,
        "capacity": row.capacity,
        "location": row.location,
        "status": row.status,
        "data": row.data_json,
    }


def parse_id_list(value):
    if not value:
        return []
    result = []
    for item in str(value).split(","):
        try:
            value = int(item)
        except (TypeError, ValueError):
            continue
        if value > 0:
            result.append(value)
    return list(dict.fromkeys(result))


def admin_required(view):
    """
    관리자(role == 'admin')만 접근 가능하도록 제한하는 데코레이터 (페이지용).
    로그인 검사까지 함께 처리하므로 @login_required와 중복으로 붙일 필요 없다.
    권한이 없으면 대시보드로 되돌려보낸다.
    """

    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if current_user.role != "admin":
            flash("관리자만 사용할 수 있는 기능입니다.", "error")
            return redirect(url_for("main.dashboard"))
        return view(*args, **kwargs)

    return wrapped


def admin_required_api(view):
    """
    관리자(role == 'admin')만 호출 가능하도록 제한하는 데코레이터 (JSON API용).
    페이지 리다이렉트가 아니라 JSON 403을 돌려줌 — fetch로 호출하는 엔드포인트에만 쓴다.
    """

    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if current_user.role != "admin":
            return jsonify({"error": "관리자만 수정할 수 있습니다."}), 403
        return view(*args, **kwargs)

    return wrapped


def log_admin_action(action, detail=None, target_type=None, target_id=None):
    """
    관리자가 수행한 작업을 AdminLog에 한 줄 남긴다.
    db.session.commit()은 호출하는 쪽에서 기존 커밋과 함께 하면 된다(여기서는 add만).
    """

    if not current_user.is_authenticated:
        return

    db.session.add(
        AdminLog(
            user_id=current_user.id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail=detail,
        )
    )
