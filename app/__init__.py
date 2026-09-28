import logging
import os
import time
import uuid

from dotenv import load_dotenv
from flask import Flask, g, request
from flask_login import LoginManager, current_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.exceptions import HTTPException
from werkzeug.security import generate_password_hash

from .logging_config import configure_logging

load_dotenv()
db = SQLAlchemy()
login_manager = LoginManager()
logger = logging.getLogger(__name__)


def create_app():
    app = Flask(__name__)
    configure_logging(app)
    app.config.update(
        SECRET_KEY=os.getenv("SECRET_KEY", "dev-secret"),
        SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        MAX_CONTENT_LENGTH=int(os.getenv("UPLOAD_MAX_MB", "100")) * 1024 * 1024,
    )
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    @app.before_request
    def _request_start():
        g.request_id = uuid.uuid4().hex[:12]
        g.request_started_at = time.perf_counter()

    @app.after_request
    def _request_end(response):
        elapsed_ms = (
            time.perf_counter() - getattr(g, "request_started_at", time.perf_counter())
        ) * 1000
        user = (
            getattr(current_user, "id", None) if current_user.is_authenticated else None
        )
        # Never log query/form bodies or credentials.
        logger.info(
            "HTTP %s %s -> %s %.1fms request_id=%s user_id=%s",
            request.method,
            request.path,
            response.status_code,
            elapsed_ms,
            getattr(g, "request_id", "-"),
            user if user is not None else "-",
        )
        response.headers["X-Request-ID"] = getattr(g, "request_id", "-")
        return response

    @app.errorhandler(Exception)
    def _unhandled_error(exc):
        # Flask의 404, 405 등의 HTTP 예외는
        # 우리가 500으로 바꾸지 않고 원래대로 처리한다.
        if isinstance(exc, HTTPException):
            return exc

        # 그 외 실제 서버 오류만 로그에 traceback과 함께 기록한다.
        logger.exception(
            "Unhandled exception | request_id=%s | method=%s | path=%s",
            getattr(g, "request_id", "-"),
            request.method,
            request.path,
        )

        from flask import jsonify

        return jsonify(
            {
                "error": "서버 내부 오류가 발생했습니다.",
                "request_id": getattr(g, "request_id", "-"),
            }
        ), 500

    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        try:
            return db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            logger.warning("Invalid user session id received")
            return None

    from .routes import register_blueprints

    register_blueprints(app)
    with app.app_context():
        db.create_all()
        if User.query.first() is None:
            admin_username = os.getenv("ADMIN_USERNAME", "").strip()
            admin_password = os.getenv("ADMIN_PASSWORD", "")
            if len(admin_username) < 3 or len(admin_password) < 4:
                raise RuntimeError(
                    "No users exist. Set ADMIN_USERNAME (at least 3 characters) "
                    "and ADMIN_PASSWORD (at least 4 characters) before starting."
                )

            admin = User(
                username=admin_username,
                password_hash=generate_password_hash(admin_password),
                role="admin",
                name="Administrator",
            )
            db.session.add(admin)
            db.session.commit()
            logger.info("Initial administrator account created | username=%s", admin_username)
    logger.info("Flask application initialized")
    return app
