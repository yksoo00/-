from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
import logging

logger = logging.getLogger(__name__)
from werkzeug.security import generate_password_hash, check_password_hash
from .. import db
from .common import admin_required, log_admin_action
from ..models import User

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        u = User.query.filter_by(
            username=request.form.get("username", "").strip()
        ).first()

        logger.info(
            "Login attempt | username=%s", request.form.get("username", "").strip()
        )

        if u and check_password_hash(u.password_hash, request.form.get("password", "")):
            login_user(u)
            logger.info("Login success | user_id=%s | username=%s", u.id, u.username)

            return redirect(request.args.get("next") or url_for("main.dashboard"))

        logger.warning(
            "Login failed | username=%s", request.form.get("username", "").strip()
        )
        flash("아이디 또는 비밀번호가 올바르지 않습니다.", "error")

    return render_template("pages/auth/login.html", register=False)


# 회원가입은 관리자만 가능하다 (공개 가입 없음 — 관리자가 직접 계정을 만들어 나눠준다).
@auth_bp.route("/register", methods=["GET", "POST"])
@admin_required
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()

        pw = request.form.get("password", "")

        name = request.form.get("name", "").strip()

        position = request.form.get("position", "").strip()

        if len(username) < 3 or len(pw) < 4:
            flash("아이디 3자 이상, 비밀번호 4자 이상을 입력하세요.", "error")

        elif not name:
            flash("이름을 입력하세요.", "error")

        elif User.query.filter_by(username=username).first():
            flash("이미 사용 중인 아이디입니다.", "error")

        else:
            role = "admin" if "admin" in username.lower() else "user"

            u = User(
                username=username,
                password_hash=generate_password_hash(pw),
                role=role,
                name=name,
                position=position or None,
            )

            db.session.add(u)
            db.session.flush()
            log_admin_action(
                "user_create",
                detail=f"{u.name}({u.username}) 계정 생성 (role={u.role})",
                target_type="user",
                target_id=u.id,
            )
            db.session.commit()
            logger.info(
                "User created by admin | user_id=%s | username=%s | role=%s | created_by=%s",
                u.id,
                u.username,
                u.role,
                current_user.id,
            )

            flash(f"{u.name}({u.username}) 계정이 생성되었습니다.", "success")

            return redirect(url_for("auth.register"))

    return render_template("pages/auth/login.html", register=True)


@auth_bp.route("/logout")
@login_required
def logout():
    logger.info("Logout | user_id=%s", current_user.id)
    logout_user()

    return redirect(url_for("auth.login"))
