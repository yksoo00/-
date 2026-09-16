from flask import Blueprint, render_template, jsonify
from flask_login import login_required
from ..models import ExcelFile, InventoryRow

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


@main_bp.route("/ebay/<code>")
@login_required
def ebay(code):
    return render_template("pages/ebay/results.html", code=code)
