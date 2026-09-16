from datetime import datetime
from flask_login import UserMixin
from .. import db

class User(UserMixin, db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    username = db.Column(
        db.String(80),
        unique=True,
        nullable=False,
        index=True
    )

    password_hash = db.Column(
        db.String(255),
        nullable=False
    )

    role = db.Column(
        db.String(30),
        default="user"
    )

    name = db.Column(
        db.String(80)
    )

    position = db.Column(
        db.String(80)
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )
