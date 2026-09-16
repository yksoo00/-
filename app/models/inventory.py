from datetime import datetime
from .. import db

class InventoryGroup(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    group_key = db.Column(
        db.String(512),
        unique=True,
        index=True
    )

    identifier = db.Column(
        db.String(255),
        index=True
    )

    item_name = db.Column(
        db.String(255),
        index=True
    )

    manufacturer = db.Column(
        db.String(255),
        index=True
    )

    model = db.Column(
        db.String(255),
        index=True
    )

    capacity = db.Column(
        db.String(100),
        index=True
    )

    quantity = db.Column(
        db.Float,
        default=0
    )

    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )


class InventoryRow(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    excel_file_id = db.Column(
        db.Integer,
        db.ForeignKey("excel_file.id"),
        nullable=False,
        index=True
    )

    sheet_id = db.Column(
        db.Integer,
        db.ForeignKey("excel_sheet.id"),
        nullable=False,
        index=True
    )

    table_id = db.Column(
        db.Integer,
        db.ForeignKey("detected_table.id")
    )

    row_number = db.Column(
        db.Integer
    )

    data_json = db.Column(
        db.JSON,
        nullable=False
    )

    identifier = db.Column(
        db.String(255),
        index=True
    )

    item_name = db.Column(
        db.String(255),
        index=True
    )

    manufacturer = db.Column(
        db.String(255),
        index=True
    )

    model = db.Column(
        db.String(255),
        index=True
    )

    capacity = db.Column(
        db.String(100),
        index=True
    )

    quantity = db.Column(
        db.Float,
        index=True
    )

    location = db.Column(
        db.String(255),
        index=True
    )

    status = db.Column(
        db.String(100),
        index=True
    )

    inventory_group_id = db.Column(
        db.Integer,
        db.ForeignKey("inventory_group.id"),
        index=True
    )

    is_deleted = db.Column(
        db.Boolean,
        default=False
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    excel_file = db.relationship(
        "ExcelFile",
        backref=db.backref(
            "rows",
            cascade="all, delete-orphan"
        )
    )

    group = db.relationship(
        "InventoryGroup",
        backref="rows"
    )


class InventoryChange(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    inventory_row_id = db.Column(
        db.Integer,
        db.ForeignKey("inventory_row.id"),
        index=True
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id")
    )

    change_type = db.Column(
        db.String(40)
    )

    field_name = db.Column(
        db.String(255)
    )

    old_value = db.Column(
        db.Text
    )

    new_value = db.Column(
        db.Text
    )

    reason = db.Column(
        db.Text
    )

    source = db.Column(
        db.String(30),
        default="web"
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )


class StockOut(db.Model):
    """
    출고(반출) 이력. 항목 상세보기에서 출고를 기록하면
    해당 InventoryRow.quantity가 줄어들고 여기에 한 줄 남는다.
    """

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    inventory_row_id = db.Column(
        db.Integer,
        db.ForeignKey("inventory_row.id"),
        nullable=True,
        index=True
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        index=True
    )

    # 출고 시점의 품목 정보를 그대로 복사해둔다.
    # (나중에 해당 InventoryRow/Excel이 삭제되어도 출고 이력은 그대로 남아있어야 하므로)
    identifier = db.Column(
        db.String(255),
        index=True
    )

    item_name = db.Column(
        db.String(255)
    )

    site = db.Column(
        db.String(120),
        index=True
    )

    quantity = db.Column(
        db.Float,
        nullable=False
    )

    reason = db.Column(
        db.String(255)
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        index=True
    )

    row = db.relationship("InventoryRow", backref="stock_outs")

    user = db.relationship("User")


class StockRequest(db.Model):
    """
    입고 요청(자동/수동) + 승인/도착처리 이력.

    생성 경로:
      - source="auto": 출고 후 재고가 1개 이하가 되면 stockout 라우트에서 자동 생성된다.
        (기존 미승인 요청이 있더라도 합치지 않고 매번 새 행으로 생성된다)
      - source="manual": 상세보기 모달에서 사용자가 직접 등록

    상태 흐름:
      requested -(관리자 승인)-> approved -(관리자 물품도착)-> arrived
      "arrived"가 되는 순간 실제 InventoryRow.quantity에 요청수량만큼 가산된다(=자동입고).
    """

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    inventory_row_id = db.Column(
        db.Integer,
        db.ForeignKey("inventory_row.id"),
        nullable=True,
        index=True
    )

    # 요청 시점의 품목 정보를 그대로 복사해둔다 (StockOut과 동일한 이유)
    identifier = db.Column(
        db.String(255),
        index=True
    )

    item_name = db.Column(
        db.String(255)
    )

    site = db.Column(
        db.String(120),
        index=True
    )

    quantity = db.Column(
        db.Float,
        nullable=False
    )

    reason = db.Column(
        db.String(255)
    )

    source = db.Column(
        db.String(20),
        default="manual",
        index=True
    )

    status = db.Column(
        db.String(20),
        default="requested",
        index=True
    )

    requested_by_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id")
    )

    approved_by_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id")
    )

    approved_at = db.Column(
        db.DateTime
    )

    arrived_by_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id")
    )

    arrived_at = db.Column(
        db.DateTime
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        index=True
    )

    row = db.relationship("InventoryRow", backref="stock_requests")

    requested_by = db.relationship("User", foreign_keys=[requested_by_id])
    approved_by = db.relationship("User", foreign_keys=[approved_by_id])
    arrived_by = db.relationship("User", foreign_keys=[arrived_by_id])


class StockIn(db.Model):
    """
    입고(재고 가산) 이력. StockOut과 대칭.

    생성 경로:
      - source="manual": 상세보기 모달의 "입고" 버튼으로 즉시 DB 반영
      - source="auto_request": StockRequest가 "물품도착" 처리되면서 자동으로 생성
        (stock_request_id로 원본 요청을 추적할 수 있다)

    "입고 요청"(StockRequest)은 진행상황(요청됨/승인완료/입고완료) 추적용이고,
    "입고 내역"(StockIn)은 실제로 DB에 반영된 입고 이벤트만 모아둥 간결한 로그다.
    """

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    inventory_row_id = db.Column(
        db.Integer,
        db.ForeignKey("inventory_row.id"),
        nullable=True,
        index=True
    )

    stock_request_id = db.Column(
        db.Integer,
        db.ForeignKey("stock_request.id"),
        nullable=True,
        index=True
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        index=True
    )

    # 입고 시점의 품목 정보를 그대로 복사해둔다 (StockOut과 동일한 이유)
    identifier = db.Column(
        db.String(255),
        index=True
    )

    item_name = db.Column(
        db.String(255)
    )

    site = db.Column(
        db.String(120),
        index=True
    )

    quantity = db.Column(
        db.Float,
        nullable=False
    )

    reason = db.Column(
        db.String(255)
    )

    source = db.Column(
        db.String(20),
        default="manual",
        index=True
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        index=True
    )

    row = db.relationship("InventoryRow", backref="stock_ins")

    request = db.relationship("StockRequest", backref="stock_in")

    user = db.relationship("User")
