from datetime import datetime, timedelta

from flask import Blueprint, render_template, jsonify
from flask_login import login_required

from .. import db
from ..models import ExcelFile, InventoryRow, StockOut

main_bp = Blueprint("main", __name__)


@main_bp.route("/health")
def health():
    return jsonify({"ok": True, "service": "inventory"})


@main_bp.route("/")
@login_required
def dashboard():
    files = ExcelFile.query.order_by(ExcelFile.created_at.desc()).all()

    total = InventoryRow.query.filter_by(is_deleted=False).count()

    low = InventoryRow.query.filter(
        InventoryRow.is_deleted == False,
        InventoryRow.quantity != None,
        InventoryRow.quantity <= 1,
        InventoryRow.capacity != None,
        InventoryRow.capacity != "",
    ).count()

    return render_template("pages/dashboard.html", files=files, total=total, low=low)


@main_bp.route("/chat")
@login_required
def chat():
    return render_template("pages/chat/index.html")


@main_bp.get("/api/stats/outflow")
@login_required
def stats_outflow():
    """
    최근 1년간의 출고 데이터를 집계해 대시보드 차트 2개를 그린다.
      - sites: 디스크가 가장 많이 나간 사이트 TOP 10
      - items: 가장 많이 사용된 디스크(품목) TOP 10
    """

    since = datetime.utcnow() - timedelta(days=365)

    site_rows = (
        db.session.query(
            StockOut.site.label("label"),
            db.func.sum(StockOut.quantity).label("total"),
        )
        .filter(StockOut.created_at >= since, StockOut.site.isnot(None))
        .group_by(StockOut.site)
        .order_by(db.desc("total"))
        .limit(10)
        .all()
    )

    # 품목명은 identifier(품번)를 우선하되, 비어있으면 item_name으로 대체한다.
    item_label = db.func.coalesce(
        db.func.nullif(StockOut.identifier, ""),
        StockOut.item_name,
    )

    item_rows = (
        db.session.query(
            item_label.label("label"),
            db.func.sum(StockOut.quantity).label("total"),
        )
        .filter(StockOut.created_at >= since)
        .group_by(item_label)
        .having(item_label.isnot(None))
        .order_by(db.desc("total"))
        .limit(10)
        .all()
    )

    return jsonify(
        {
            "since": since.strftime("%Y-%m-%d"),
            "sites": [
                {"label": row.label, "total": float(row.total or 0)} for row in site_rows
            ],
            "items": [
                {"label": row.label, "total": float(row.total or 0)} for row in item_rows
            ],
        }
    )


@main_bp.route("/ebay/<code>")
@login_required
def ebay(code):
    return render_template("pages/ebay/results.html", code=code)
