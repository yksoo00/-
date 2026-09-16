import os
import json
import uuid
import logging
from pathlib import Path

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    send_file,
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from .. import db
from .common import admin_required, log_admin_action
from ..models import (
    ExcelFile,
    ExcelSheet,
    SheetColumn,
    DetectedTable,
    InventoryRow,
    InventoryGroup,
    InventoryChange,
    StockOut,
)
from ..services.excel.parser import parse_workbook, file_sha256
from ..services.excel.exporter import export_excel
from ..services.inventory.normalize import normalize_row, infer_field, to_number


files_bp = Blueprint("files", __name__)
logger = logging.getLogger(__name__)


# =========================================================
# 업로드 파일 실제 위치 찾기
# =========================================================
def _resolve_upload_file(excel_file):
    """
    DB에 저장된 file_path가 과거 app/uploads를 가리키고 있더라도
    현재 프로젝트 루트 uploads/에서 실제 파일을 찾는다.
    """

    stored_filename = excel_file.stored_filename

    if not stored_filename:
        return None

    candidates = []

    # -----------------------------------------------------
    # 1. DB에 저장된 기존 경로
    # -----------------------------------------------------
    if excel_file.file_path:
        candidates.append(Path(excel_file.file_path))

    # -----------------------------------------------------
    # 2. 현재 프로젝트 루트/uploads
    #
    # files.py 위치:
    # StockFlow/app/routes/files.py
    #
    # parents[0] = routes
    # parents[1] = app
    # parents[2] = StockFlow
    # -----------------------------------------------------
    project_root = Path(__file__).resolve().parents[2]

    candidates.append(project_root / "uploads" / stored_filename)

    # -----------------------------------------------------
    # 3. 현재 작업 디렉터리/uploads
    # -----------------------------------------------------
    candidates.append(Path.cwd() / "uploads" / stored_filename)

    # -----------------------------------------------------
    # 4. 환경변수 UPLOAD_DIR
    # -----------------------------------------------------
    upload_dir = os.getenv("UPLOAD_DIR")

    if upload_dir:
        candidates.append(Path(upload_dir) / stored_filename)

    # -----------------------------------------------------
    # 중복 제거 후 실제 존재하는 파일 검색
    # -----------------------------------------------------
    checked = set()

    for candidate in candidates:
        try:
            candidate = candidate.resolve()
        except OSError:
            continue

        candidate_key = str(candidate).lower()

        if candidate_key in checked:
            continue

        checked.add(candidate_key)

        if candidate.is_file():
            return candidate

    return None


# =========================================================
# Excel 목록
# =========================================================
@files_bp.get("/files")
@login_required
def files():
    return render_template(
        "pages/files/list.html",
        files=ExcelFile.query.order_by(ExcelFile.created_at.desc()).all(),
    )


# =========================================================
# Excel 상세
# =========================================================
@files_bp.get("/files/<int:file_id>")
@login_required
def file_detail(file_id):
    f = db.get_or_404(ExcelFile, file_id)

    return render_template(
        "pages/files/detail.html",
        file=f,
    )


# =========================================================
# Excel Export
# =========================================================
@files_bp.get("/files/<int:file_id>/export")
@login_required
def export_file(file_id):

    f = db.get_or_404(ExcelFile, file_id)

    logger.info(
        "Excel export started | file_id=%s | filename=%s | user_id=%s",
        file_id,
        f.original_filename,
        current_user.id,
    )

    # -----------------------------------------------------
    # 실제 Excel 파일 위치 확인
    # -----------------------------------------------------
    source_path = _resolve_upload_file(f)

    if source_path:
        logger.info(
            "Excel export source resolved | file_id=%s | path=%s",
            file_id,
            source_path,
        )

        # -------------------------------------------------
        # DB에 오래된 경로가 들어있다면 현재 실제 경로로 보정
        # -------------------------------------------------
        try:
            current_db_path = Path(f.file_path).resolve() if f.file_path else None

            if current_db_path is None or current_db_path != source_path.resolve():
                f.file_path = str(source_path.resolve())

                db.session.commit()

                logger.info(
                    "Excel file_path repaired | file_id=%s | path=%s",
                    file_id,
                    source_path,
                )

        except Exception:
            db.session.rollback()

            logger.exception(
                "Excel file_path repair failed | file_id=%s",
                file_id,
            )

    else:
        logger.warning(
            "Excel export source missing | file_id=%s | stored_filename=%s | db_path=%s",
            file_id,
            f.stored_filename,
            f.file_path,
        )

    # -----------------------------------------------------
    # Export 실행
    # -----------------------------------------------------
    try:
        output = export_excel(f)

    except FileNotFoundError as exc:
        logger.warning(
            "Excel export source missing | file_id=%s | path=%s",
            file_id,
            f.file_path,
        )

        return jsonify({"error": str(exc)}), 404

    except Exception as exc:
        db.session.rollback()

        logger.exception(
            "Excel export failed | file_id=%s | filename=%s",
            file_id,
            f.original_filename,
        )

        return jsonify({"error": f"Excel 내보내기 실패: {exc}"}), 500

    # -----------------------------------------------------
    # 다운로드 파일명
    # -----------------------------------------------------
    suffix = Path(f.original_filename).suffix.lower()

    extension = suffix if suffix in {".xlsx", ".xlsm"} else ".xlsx"

    stem = Path(f.original_filename).stem or "inventory"

    download_name = f"{stem}_수정본{extension}"

    logger.info(
        "Excel export completed | file_id=%s | filename=%s",
        file_id,
        f.original_filename,
    )

    return send_file(
        output,
        as_attachment=True,
        download_name=download_name,
        mimetype=(
            "application/vnd.ms-excel.sheet.macroEnabled.12"
            if extension == ".xlsm"
            else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
    )


# =========================================================
# Excel 삭제
# =========================================================
@files_bp.post("/files/<int:file_id>/delete")
@admin_required
def delete_file(file_id):

    f = db.get_or_404(ExcelFile, file_id)

    logger.info(
        "Excel delete started | file_id=%s | filename=%s | user_id=%s",
        file_id,
        f.original_filename,
        current_user.id,
    )

    # -----------------------------------------------------
    # 실제 파일 위치 확인
    #
    # DB가 app/uploads를 가리키고 있어도
    # 실제 루트 uploads/의 파일을 찾아낸다.
    # -----------------------------------------------------
    path = _resolve_upload_file(f)

    if path:
        logger.info(
            "Excel delete source resolved | file_id=%s | path=%s",
            file_id,
            path,
        )
    else:
        logger.warning(
            "Excel delete source missing | file_id=%s | stored_filename=%s | db_path=%s",
            file_id,
            f.stored_filename,
            f.file_path,
        )

    # -----------------------------------------------------
    # FK 의존관계 정리
    #
    # InventoryChange
    #     ↓
    # InventoryRow
    #     ↓
    # SheetColumn
    #     ↓
    # DetectedTable
    #     ↓
    # ExcelSheet
    #     ↓
    # ExcelFile
    # -----------------------------------------------------

    row_ids = [row.id for row in InventoryRow.query.filter_by(excel_file_id=f.id).all()]

    sheet_ids = [
        sheet.id for sheet in ExcelSheet.query.filter_by(excel_file_id=f.id).all()
    ]

    table_ids = (
        [
            table.id
            for table in DetectedTable.query.filter(
                DetectedTable.sheet_id.in_(sheet_ids)
            ).all()
        ]
        if sheet_ids
        else []
    )

    group_ids = {
        row.inventory_group_id
        for row in InventoryRow.query.filter_by(excel_file_id=f.id).all()
        if row.inventory_group_id
    }

    # -----------------------------------------------------
    # DB 삭제
    # -----------------------------------------------------
    try:
        # StockOut 이력은 삭제하지 않고 보존한다(품목 정보는 이미 복사되어 있음).
        # 단, InventoryRow가 사라지기 전에 연결만 끊어준다.
        if row_ids:
            StockOut.query.filter(StockOut.inventory_row_id.in_(row_ids)).update(
                {StockOut.inventory_row_id: None},
                synchronize_session=False,
            )

        # InventoryChange 삭제
        if row_ids:
            InventoryChange.query.filter(
                InventoryChange.inventory_row_id.in_(row_ids)
            ).delete(synchronize_session=False)

            # InventoryRow 삭제
            InventoryRow.query.filter(InventoryRow.id.in_(row_ids)).delete(
                synchronize_session=False
            )

        # DetectedTable 삭제
        if table_ids:
            # SheetColumn.table_id가
            # DetectedTable을 참조하므로 먼저 NULL 처리
            SheetColumn.query.filter(SheetColumn.table_id.in_(table_ids)).update(
                {SheetColumn.table_id: None},
                synchronize_session=False,
            )

            DetectedTable.query.filter(DetectedTable.id.in_(table_ids)).delete(
                synchronize_session=False
            )

        # 남은 SheetColumn / Sheet는
        # ExcelFile cascade로 제거
        db.session.delete(f)

        db.session.flush()

        # 사용하지 않는 InventoryGroup 삭제
        for gid in group_ids:
            group = db.session.get(InventoryGroup, gid)

            if group and not group.rows:
                db.session.delete(group)

        db.session.commit()

    except Exception:
        db.session.rollback()

        logger.exception(
            "Excel delete DB transaction failed | file_id=%s",
            file_id,
        )

        raise

    # -----------------------------------------------------
    # 실제 Excel 파일 삭제
    #
    # DB 삭제가 완료된 이후 실행한다.
    # -----------------------------------------------------
    try:
        if path and path.exists():
            path.unlink()

            logger.info(
                "Excel source file deleted | file_id=%s | path=%s",
                file_id,
                path,
            )

    except OSError:
        logger.exception(
            "Excel source file delete failed after DB deletion | file_id=%s | path=%s",
            file_id,
            path,
        )

        # DB 삭제는 이미 완료되었으므로
        # 파일 삭제 실패가 전체 요청을 500으로 만들지 않는다.
        pass

    logger.info(
        "Excel delete completed | file_id=%s | filename=%s",
        file_id,
        f.original_filename,
    )

    log_admin_action(
        "excel_delete",
        detail=f"{f.original_filename} 삭제",
        target_type="excel_file",
        target_id=file_id,
    )
    db.session.commit()

    flash(
        f"{f.original_filename} 삭제되었습니다.",
        "success",
    )

    return redirect(url_for("files.files"))


# =========================================================
# Excel Upload
# =========================================================
@files_bp.route("/upload", methods=["GET", "POST"])
@admin_required
def upload():

    if request.method == "POST":
        file = request.files.get("file")

        logger.info(
            "Excel upload request received | user_id=%s | filename=%s",
            current_user.id,
            getattr(file, "filename", None),
        )

        # -------------------------------------------------
        # 파일 확장자 검사
        # -------------------------------------------------
        if not file or not file.filename:
            flash(
                "업로드할 Excel 파일을 선택하세요.",
                "error",
            )

            return redirect(url_for("files.upload"))

        original_filename = file.filename or "upload.xlsx"

        extension = Path(original_filename).suffix.lower()

        if extension not in {
            ".xlsx",
            ".xlsm",
        }:
            flash(
                "xlsx/xlsm 파일만 업로드할 수 있습니다.",
                "error",
            )

            return redirect(url_for("files.upload"))

        # -------------------------------------------------
        # 업로드 폴더
        #
        # 실제 구조:
        #
        # StockFlow/
        # ├─ run.py
        # ├─ uploads/       ← 여기
        # └─ app/
        #
        # 따라서 parents[2] = 프로젝트 루트
        # -------------------------------------------------
        root = Path(
            os.getenv(
                "UPLOAD_DIR",
                str(Path(__file__).resolve().parents[2] / "uploads"),
            )
        )

        root.mkdir(
            parents=True,
            exist_ok=True,
        )

        logger.info(
            "Excel upload directory resolved | path=%s",
            root.resolve(),
        )

        # -------------------------------------------------
        # 파일명 처리
        #
        # 한글 파일명이나 특수문자로 인해
        # secure_filename() 결과가 비어버리는 것을 방지
        # -------------------------------------------------
        stem = Path(original_filename).stem

        safe_stem = secure_filename(stem)

        if not safe_stem:
            safe_stem = "inventory"

        safe = f"{safe_stem}{extension}"

        stored = f"{uuid.uuid4().hex}_{safe}"

        path = root / stored

        # -------------------------------------------------
        # 실제 파일 저장
        # -------------------------------------------------
        file.save(path)

        logger.info(
            "Excel upload saved | user_id=%s | path=%s | size=%s",
            current_user.id,
            path,
            path.stat().st_size if path.exists() else 0,
        )

        # -------------------------------------------------
        # Excel 분석 및 DB 저장
        # -------------------------------------------------
        try:
            parsed = parse_workbook(path)

            ef = ExcelFile(
                original_filename=original_filename,
                stored_filename=stored,
                file_path=str(path.resolve()),
                file_hash=file_sha256(path),
                file_size=path.stat().st_size,
                uploaded_by=current_user.id,
                processing_status="processing",
            )

            db.session.add(ef)
            db.session.flush()

            row_ids = []

            # =================================================
            # Sheet
            # =================================================
            for si, s in enumerate(parsed):
                es = ExcelSheet(
                    excel_file_id=ef.id,
                    sheet_name=s["sheet_name"],
                    sheet_order=si,
                    sheet_type=s["sheet_type"],
                    row_count=sum(len(t["rows"]) for t in s["tables"]),
                    column_count=max([len(t["headers"]) for t in s["tables"]] or [0]),
                )

                db.session.add(es)
                db.session.flush()

                # =================================================
                # Table
                # =================================================
                for ti, t in enumerate(s["tables"]):
                    dt = DetectedTable(
                        sheet_id=es.id,
                        title=s["sheet_name"],
                        header_row=s.get("header_row"),
                        start_row=(t["rows"][0]["row_number"] if t["rows"] else None),
                        end_row=(t["rows"][-1]["row_number"] if t["rows"] else None),
                        start_col=1,
                        end_col=len(t["headers"]),
                        table_type="inventory",
                    )

                    db.session.add(dt)
                    db.session.flush()

                    # =================================================
                    # Excel 실제 컬럼 자동 생성
                    # =================================================
                    for ci, h in enumerate(
                        t["headers"],
                        1,
                    ):
                        samples = [
                            r["data"].get(h)
                            for r in t["rows"][:50]
                            if r["data"].get(h) not in (None, "")
                        ]

                        numeric_count = sum(to_number(x) is not None for x in samples)

                        dtype = (
                            "number"
                            if (
                                samples
                                and numeric_count
                                >= max(
                                    2,
                                    int(len(samples) * 0.7),
                                )
                            )
                            else "string"
                        )

                        unique_count = len(
                            set(
                                map(
                                    str,
                                    samples,
                                )
                            )
                        )

                        filter_type = (
                            "range"
                            if dtype == "number"
                            else ("select" if unique_count <= 30 else "text")
                        )

                        db.session.add(
                            SheetColumn(
                                sheet_id=es.id,
                                table_id=dt.id,
                                column_index=ci,
                                original_name=h,
                                normalized_name=infer_field(h),
                                data_type=dtype,
                                filter_type=filter_type,
                            )
                        )

                    # =================================================
                    # 실제 재고 Row 저장
                    # =================================================
                    for r in t["rows"]:
                        d = r["data"]

                        n = normalize_row(d)

                        q = n.get("quantity")

                        ident = n.get("identifier")

                        # -------------------------------------------------
                        # Inventory Group Key
                        # -------------------------------------------------
                        key = "|".join(
                            str(n.get(k) or "")
                            for k in [
                                "identifier",
                                "item_name",
                                "manufacturer",
                                "model",
                                "capacity",
                            ]
                        )

                        if not key.strip("|"):
                            key = json.dumps(
                                d,
                                ensure_ascii=False,
                                sort_keys=True,
                                default=str,
                            )

                        # -------------------------------------------------
                        # 기존 Group 검색
                        # -------------------------------------------------
                        group = InventoryGroup.query.filter_by(group_key=key).first()

                        if not group:
                            group = InventoryGroup(
                                group_key=key,
                                identifier=n.get("identifier"),
                                item_name=n.get("item_name"),
                                manufacturer=n.get("manufacturer"),
                                model=n.get("model"),
                                capacity=n.get("capacity"),
                                quantity=0,
                            )

                            db.session.add(group)

                            db.session.flush()

                        # -------------------------------------------------
                        # 수량 누적
                        # -------------------------------------------------
                        group.quantity = (group.quantity or 0) + (q or 0)

                        # -------------------------------------------------
                        # Inventory Row
                        # -------------------------------------------------
                        row = InventoryRow(
                            excel_file_id=ef.id,
                            sheet_id=es.id,
                            table_id=dt.id,
                            row_number=r["row_number"],
                            data_json=d,
                            identifier=ident,
                            item_name=n.get("item_name"),
                            manufacturer=n.get("manufacturer"),
                            model=n.get("model"),
                            capacity=n.get("capacity"),
                            quantity=q,
                            location=n.get("location"),
                            status=n.get("status"),
                            inventory_group_id=group.id,
                        )

                        db.session.add(row)

                        db.session.flush()

                        row_ids.append(row.id)

            # -------------------------------------------------
            # 최종 저장
            # -------------------------------------------------
            ef.processing_status = "completed"

            db.session.commit()

            logger.info(
                "Excel upload completed | file_id=%s | filename=%s | rows=%s | user_id=%s",
                ef.id,
                original_filename,
                len(row_ids),
                current_user.id,
            )

            flash(
                f"업로드 완료: {original_filename} / {len(row_ids)}개 행",
                "success",
            )

            log_admin_action(
                "excel_upload",
                detail=f"{original_filename} 업로드 ({len(row_ids)}행)",
                target_type="excel_file",
                target_id=ef.id,
            )
            db.session.commit()

            return redirect(
                url_for(
                    "files.file_detail",
                    file_id=ef.id,
                )
            )

        except Exception as e:
            db.session.rollback()

            logger.exception(
                "Excel upload processing failed | filename=%s | user_id=%s",
                original_filename,
                current_user.id,
            )

            # 실패한 파일 삭제
            try:
                if path.exists():
                    path.unlink()

            except Exception:
                logger.exception(
                    "Failed to delete uploaded Excel after processing error | path=%s",
                    path,
                )

            flash(
                f"Excel 분석 오류: {e}",
                "error",
            )

            return redirect(url_for("files.upload"))

    return render_template("pages/files/upload.html")
