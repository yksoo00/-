"""
User 테이블에 name / position 컬럼을 추가하는 1회성 마이그레이션 스크립트.
db.create_all()은 이미 존재하는 테이블에 새 컬럼을 추가해주지 않으므로 직접 실행해야 한다.

사용법 (프로젝트 루트에서, venv 활성화 후):
    python migrate_add_user_profile_fields.py

여러 번 실행해도 안전하다 (컬럼이 이미 있으면 건너뜀).
"""

from sqlalchemy import text

from app import create_app, db

app = create_app()

with app.app_context():
    existing = {
        row[0]
        for row in db.session.execute(
            text(
                "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'user'"
            )
        )
    }

    added = []

    if "name" not in existing:
        db.session.execute(text("ALTER TABLE user ADD COLUMN name VARCHAR(80) NULL"))
        added.append("name")

    if "position" not in existing:
        db.session.execute(text("ALTER TABLE user ADD COLUMN position VARCHAR(80) NULL"))
        added.append("position")

    db.session.commit()

    if added:
        print(f"컬럼 추가 완료: {', '.join(added)}")
    else:
        print("이미 컬럼이 존재합니다. 변경 없음.")
