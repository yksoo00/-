"""
User 테이블에 name/position/role 컬럼이 없으면 추가해주는 1회성 스크립트.
db.create_all()은 새 테이블만 만들 뿐, 기존 테이블에 컬럼을 추가해주지 않기 때문에
이름/직책 필드를 모델에 추가한 뒤에는 이 스크립트를 한 번 실행해줘야 한다.

여러 번 실행해도 안전하다(이미 있는 컬럼은 건너뜀).

사용법 (프로젝트 루트에서, venv 활성화 후):
    python migrate_user_columns.py
"""

from sqlalchemy import inspect, text

from app import create_app, db

app = create_app()

with app.app_context():
    inspector = inspect(db.engine)
    existing_columns = {col["name"] for col in inspector.get_columns("user")}

    wanted = {
        "name": "ALTER TABLE `user` ADD COLUMN `name` VARCHAR(80) NULL",
        "position": "ALTER TABLE `user` ADD COLUMN `position` VARCHAR(80) NULL",
        "role": "ALTER TABLE `user` ADD COLUMN `role` VARCHAR(30) NULL DEFAULT 'user'",
    }

    added = []

    for column, ddl in wanted.items():
        if column in existing_columns:
            print(f"이미 있음: {column}")
            continue

        db.session.execute(text(ddl))
        added.append(column)
        print(f"추가함: {column}")

    if added:
        db.session.commit()
        print(f"완료. 추가된 컬럼: {', '.join(added)}")
    else:
        print("추가할 컬럼이 없습니다. 이미 최신 상태입니다.")
