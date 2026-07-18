import os, re, uuid, json, secrets, smtplib, hashlib, csv
from email.message import EmailMessage
from html import escape
from datetime import datetime, timedelta
from functools import wraps
from urllib.parse import urlencode
from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from dotenv import load_dotenv
import joblib
import requests
import numpy as np
import pandas as pd
import pdfplumber
from pdfplumber.utils.exceptions import PdfminerException
from pdfminer.pdfdocument import PDFPasswordIncorrect
from pdfminer.pdfparser import PDFSyntaxError
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from fpdf import FPDF

from document_validator import validate_document   # â† Security layer

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)
app.secret_key = os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv("APP_BASE_URL", "").startswith("https")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["PERMANENT_SESSION_LIFETIME"] = 3600
app.config["SESSION_COOKIE_SECURE"] = os.getenv("APP_BASE_URL", "").startswith("https://")
app.config["GOOGLE_CLIENT_ID"] = os.getenv("GOOGLE_CLIENT_ID", "")
app.config["GOOGLE_CLIENT_SECRET"] = os.getenv("GOOGLE_CLIENT_SECRET", "")
app.config["GOOGLE_REDIRECT_URI"] = os.getenv("GOOGLE_REDIRECT_URI", "")
app.config["MAIL_SERVER"] = os.getenv("MAIL_SERVER", "")
app.config["MAIL_PORT"] = int(os.getenv("MAIL_PORT", "587"))
app.config["MAIL_USE_TLS"] = os.getenv("MAIL_USE_TLS", "true").lower() in {"1", "true", "yes", "on"}
app.config["MAIL_USE_SSL"] = os.getenv("MAIL_USE_SSL", "false").lower() in {"1", "true", "yes", "on"}
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME", "")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD", "")
app.config["MAIL_DEFAULT_SENDER"] = os.getenv("MAIL_DEFAULT_SENDER", os.getenv("MAIL_USERNAME", ""))
app.config["ADMIN_EMAIL"] = os.getenv("ADMIN_EMAIL", app.config["MAIL_USERNAME"])


def login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please sign in with Google to continue.", "warning")
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)

    wrapped.__name__ = view_func.__name__
    return wrapped


# ---------------------------
# â”€â”€ Database â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
database_url = os.getenv(
    "DATABASE_URL",
    "sqlite:///" + os.path.join(BASE_DIR, "finscore.db"),
)
if database_url.startswith("postgres://"):
    database_url = "postgresql+psycopg://" + database_url[len("postgres://"):]
elif database_url.startswith("postgresql://"):
    database_url = "postgresql+psycopg://" + database_url[len("postgresql://"):]
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)


# â”€â”€ Models â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
class CreditRecord(db.Model):
    __tablename__ = "credit_records"
    id             = db.Column(db.Integer, primary_key=True)
    report_id      = db.Column(db.String(20), unique=True, nullable=False)
    name           = db.Column(db.String(120), nullable=False)
    email          = db.Column(db.String(120), nullable=False)
    phone          = db.Column(db.String(30),  nullable=False)
    credit_score   = db.Column(db.Integer,  nullable=False)
    status         = db.Column(db.String(20),  nullable=False)
    creditworthy   = db.Column(db.String(30),  nullable=False)
    loan_rec       = db.Column(db.String(40),  nullable=False)
    confidence     = db.Column(db.Float,  nullable=False)
    monthly_income = db.Column(db.Float,  default=0)
    monthly_expense= db.Column(db.Float,  default=0)
    net_savings    = db.Column(db.Float,  default=0)
    savings_rate   = db.Column(db.Float,  default=0)
    avg_balance    = db.Column(db.Float,  default=0)
    emi_count      = db.Column(db.Integer, default=0)
    file_type      = db.Column(db.String(10), default="unknown")
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)


class ValidationLog(db.Model):
    __tablename__ = "validation_logs"
    id             = db.Column(db.Integer, primary_key=True)
    file_name      = db.Column(db.String(200), nullable=False)
    file_type      = db.Column(db.String(10),  nullable=False)
    validation_status = db.Column(db.String(10), nullable=False)   # PASS / FAIL
    validation_score  = db.Column(db.Integer,  nullable=False)
    bank_detected  = db.Column(db.String(80),  nullable=True)
    txn_count      = db.Column(db.Integer,  default=0)
    reject_reason  = db.Column(db.String(400), nullable=True)
    uploader_name  = db.Column(db.String(120), nullable=True)
    uploader_email = db.Column(db.String(120), nullable=True)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)


# â”€â”€ App config â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
class AdminUser(db.Model):
    __tablename__ = "admin_users"
    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active     = db.Column(db.Boolean, default=True, nullable=False)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class AdminLoginOtp(db.Model):
    __tablename__ = "admin_login_otps"
    id             = db.Column(db.Integer, primary_key=True)
    admin_username = db.Column(db.String(80), nullable=False, index=True)
    admin_email    = db.Column(db.String(255), nullable=False)
    otp_hash       = db.Column(db.String(256), nullable=False)
    expires_at     = db.Column(db.DateTime, nullable=False)
    attempts       = db.Column(db.Integer, default=0)
    used           = db.Column(db.Boolean, default=False)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)


class AdminPasswordResetOtp(db.Model):
    __tablename__ = "admin_password_reset_otps"
    id             = db.Column(db.Integer, primary_key=True)
    admin_username = db.Column(db.String(80), nullable=False, index=True)
    admin_email    = db.Column(db.String(255), nullable=False)
    otp_hash       = db.Column(db.String(256), nullable=False)
    expires_at     = db.Column(db.DateTime, nullable=False)
    attempts       = db.Column(db.Integer, default=0)
    used           = db.Column(db.Boolean, default=False)
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)


class GoogleUser(db.Model):
    __tablename__ = "google_users"
    id = db.Column(db.Integer, primary_key=True)
    google_user_id = db.Column(db.String(120), unique=True, nullable=False, index=True)
    full_name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    profile_picture = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)




class OtpRecord(db.Model):
    __tablename__ = "otp_records"
    id         = db.Column(db.Integer, primary_key=True)
    report_id  = db.Column(db.String(20), nullable=False, index=True)
    user_email = db.Column(db.String(255), nullable=False)
    otp_hash   = db.Column(db.String(256), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    attempts   = db.Column(db.Integer, default=0)
    used       = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

def ensure_database():
    db.create_all()


def has_admin_user():
    ensure_database()
    return AdminUser.query.filter_by(is_active=True).first() is not None


def admin_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        ensure_database()
        admin_user_id = session.get("admin_user_id")
        admin_user = db.session.get(AdminUser, admin_user_id) if admin_user_id else None

        if not session.get("admin_authenticated") or not admin_user or not admin_user.is_active:
            session.pop("admin_authenticated", None)
            session.pop("admin_user_id", None)
            session.pop("admin_username", None)
            flash("Please sign in with an authorized admin account.", "warning")
            return redirect(url_for("admin_login"))

        return view_func(*args, **kwargs)

    return wrapped


UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", os.path.join(BASE_DIR, "uploads"))
REPORT_FOLDER = os.getenv("REPORT_FOLDER", os.path.join(BASE_DIR, "reports"))
ALLOWED_EXT   = {"pdf", "csv"}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(REPORT_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"]      = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

model = joblib.load(os.path.join(BASE_DIR, "credit_score_model.pkl"))
if hasattr(model, "n_jobs"):
    model.n_jobs = 1


def safe_commit(context):
    try:
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        app.logger.warning("Database commit skipped for %s: %s", context, e)
        return False


def _smtp_send(message):
    """Send an EmailMessage via configured SMTP. Returns True on success."""
    mail_server = app.config.get("MAIL_SERVER", "").strip()
    mail_username = app.config.get("MAIL_USERNAME", "").strip()
    mail_password = app.config.get("MAIL_PASSWORD", "")
    if mail_server.lower() in {"smtp.gmail.com", "smtp.googlemail.com"}:
        mail_password = "".join(mail_password.split())
    sender = app.config.get("MAIL_DEFAULT_SENDER", "").strip() or mail_username

    if not all((mail_server, mail_username, mail_password, sender)):
        app.logger.warning("Email skipped because SMTP settings are incomplete.")
        return False

    message["From"] = sender
    try:
        smtp_class = smtplib.SMTP_SSL if app.config.get("MAIL_USE_SSL") else smtplib.SMTP
        with smtp_class(mail_server, app.config["MAIL_PORT"], timeout=10) as smtp:
            if app.config.get("MAIL_USE_TLS") and not app.config.get("MAIL_USE_SSL"):
                smtp.starttls()
            smtp.login(mail_username, mail_password)
            smtp.send_message(message)
        return True
    except (OSError, smtplib.SMTPException) as exc:
        app.logger.exception("Could not send email to %s: %s", message["To"], exc)
        return False


def _send_admin_reset_otp_email(admin_email, otp_code, username):
    msg = EmailMessage()
    msg["Subject"] = "FinScore AI — Admin Password Reset OTP"
    msg["To"] = admin_email
    msg.set_content(
        f"Your admin password reset code for user '{username}' is:\n\n"
        f"  {otp_code}\n\n"
        "This OTP expires in 60 seconds. Do not share it with anyone.\n\n"
        "If you did not request this, ignore this email.\n\n"
        "Regards,\nFinScore AI Team"
    )
    msg.add_alternative(f"""<!doctype html><html><body style=\"font-family:Arial,sans-serif;background:#f1f5f9;margin:0;padding:32px\">
<div style=\"max-width:480px;margin:auto;background:#fff;border-radius:14px;overflow:hidden;border:1px solid #e2e8f0\">
  <div style=\"background:#0f172a;padding:24px 32px;color:#fff\">
    <h2 style=\"margin:0\">FinScore <span style=\"color:#22c55e\">AI</span></h2>
    <p style=\"margin:4px 0 0;font-size:13px;color:#94a3b8\">Admin Password Reset</p>
  </div>
  <div style=\"padding:32px\">
    <p style=\"font-size:15px;color:#0f172a\">Your password reset OTP for admin user <strong>{username}</strong> is:</p>
    <div style=\"text-align:center;margin:24px 0\">
      <span style=\"font-size:42px;font-weight:800;letter-spacing:10px;color:#1d4ed8;font-family:monospace\">{otp_code}</span>
    </div>
    <p style=\"color:#64748b;font-size:13px\">This OTP expires in <strong>60 seconds</strong>. Never share it with anyone.</p>
    <p style=\"color:#64748b;font-size:13px;margin-top:20px\">Regards,<br><strong>FinScore AI Team</strong></p>
  </div>
</div>
</body></html>""", subtype="html")
    return _smtp_send(msg)


def _send_admin_login_otp_email(admin_email, otp_code, username):
    msg = EmailMessage()
    msg["Subject"] = "FinScore AI — Admin Login OTP"
    msg["To"] = admin_email
    msg.set_content(
        f"Your admin login OTP for user '{username}' is:\n\n"
        f"  {otp_code}\n\n"
        "This OTP expires in 60 seconds. Do not share it with anyone.\n\n"
        "Regards,\nFinScore AI Team"
    )
    msg.add_alternative(f"""<!doctype html><html><body style=\"font-family:Arial,sans-serif;background:#f1f5f9;margin:0;padding:32px\">
<div style=\"max-width:480px;margin:auto;background:#fff;border-radius:14px;overflow:hidden;border:1px solid #e2e8f0\">
  <div style=\"background:#0f172a;padding:24px 32px;color:#fff\">
    <h2 style=\"margin:0\">FinScore <span style=\"color:#22c55e\">AI</span></h2>
    <p style=\"margin:4px 0 0;font-size:13px;color:#94a3b8\">Admin Login</p>
  </div>
  <div style=\"padding:32px\">
    <p style=\"font-size:15px;color:#0f172a\">Your login OTP for admin user <strong>{username}</strong> is:</p>
    <div style=\"text-align:center;margin:24px 0\">
      <span style=\"font-size:42px;font-weight:800;letter-spacing:10px;color:#1d4ed8;font-family:monospace\">{otp_code}</span>
    </div>
    <p style=\"color:#64748b;font-size:13px\">This OTP expires in <strong>60 seconds</strong>. Never share it with anyone.</p>
    <p style=\"color:#64748b;font-size:13px;margin-top:20px\">Regards,<br><strong>FinScore AI Team</strong></p>
  </div>
</div>
</body></html>""", subtype="html")
    return _smtp_send(msg)


def send_welcome_email(user):
    """Send the first-login welcome email."""
    safe_name = escape(user.full_name)
    message = EmailMessage()
    message["Subject"] = "Welcome to FinScore AI"
    message["To"] = user.email
    message.set_content(
        f"Welcome to FinScore AI, {user.full_name}!\n\n"
        "Your account has been successfully created.\n\nRegards,\nThe FinScore AI Team"
    )
    message.add_alternative(
        f"""<!doctype html><html lang="en"><body style="margin:0;background:#f1f5f9;font-family:Arial,sans-serif;color:#0f172a">
        <div style="max-width:600px;margin:32px auto;background:#fff;border-radius:16px;overflow:hidden;border:1px solid #e2e8f0">
          <div style="padding:24px 32px;background:#0f172a;color:#fff"><h1 style="margin:0;font-size:24px">FinScore <span style="color:#22c55e">AI</span></h1></div>
          <div style="padding:32px">
            <div style="font-size:38px;color:#22c55e">&#10003;</div>
            <h2 style="margin:12px 0">Welcome, {safe_name}!</h2>
            <p style="line-height:1.7;color:#475569">Your account has been successfully created. You can now securely analyze your financial documents and generate AI-powered credit reports instantly.</p>
            <p style="margin-top:28px;color:#64748b">Regards,<br><strong>The FinScore AI Team</strong></p>
          </div>
        </div></body></html>""",
        subtype="html",
    )
    return _smtp_send(message)


def send_result_email(user_name, user_email, credit_score, credit_category, prediction_date):
    """Send credit score result email to the logged-in Google user."""
    safe_name = escape(user_name)
    score_color = (
        "#22c55e" if credit_category == "Excellent" else
        "#3b82f6" if credit_category == "Good" else
        "#f59e0b" if credit_category in ("Fair", "Average") else
        "#ef4444"
    )
    message = EmailMessage()
    message["Subject"] = "Your FinScore AI Credit Assessment Report"
    message["To"] = user_email
    message.set_content(
        f"Dear {user_name},\n\nYour credit score assessment is ready.\n"
        f"Credit Score: {credit_score}\nCredit Category: {credit_category}\n"
        f"Report Generated On: {prediction_date}\n\nRegards,\nFinScore AI Team"
    )
    message.add_alternative(
        f"""<!doctype html><html lang="en"><body style="margin:0;background:#f1f5f9;font-family:Arial,sans-serif;color:#0f172a">
<div style="max-width:620px;margin:32px auto;background:#fff;border-radius:16px;overflow:hidden;border:1px solid #e2e8f0">
  <div style="padding:24px 32px;background:#0f172a;color:#fff">
    <h1 style="margin:0;font-size:24px">FinScore <span style="color:#22c55e">AI</span></h1>
    <p style="margin:4px 0 0;font-size:13px;color:#94a3b8">AI-Powered Credit Assessment Platform</p>
  </div>
  <div style="padding:32px">
    <p style="font-size:16px">Dear <strong>{safe_name}</strong>,</p>
    <p style="color:#475569;line-height:1.7">Thank you for choosing FinScore AI. Your bank statement analysis has been successfully completed and your personalized credit score assessment is now available.</p>
    <div style="background:#f8fafc;border-radius:12px;padding:24px;margin:24px 0;text-align:center;border:1px solid #e2e8f0">
      <div style="font-size:13px;color:#64748b;text-transform:uppercase;letter-spacing:1px">Credit Score</div>
      <div style="font-size:56px;font-weight:800;color:{score_color};line-height:1.1">{credit_score}</div>
      <div style="display:inline-block;background:{score_color};color:#fff;padding:4px 18px;border-radius:20px;font-size:14px;font-weight:600;margin-top:8px">{credit_category}</div>
      <div style="margin-top:12px;font-size:13px;color:#94a3b8">Report Generated On: {prediction_date}</div>
    </div>
    <p style="color:#475569;line-height:1.7">Our AI-powered analysis evaluated transaction patterns, income consistency, spending behavior, and overall financial stability to generate your credit score estimate.</p>
    <h3 style="color:#0f172a;margin-top:24px">Recommended Next Steps</h3>
    <ul style="color:#475569;line-height:2">
      <li>Maintain consistent banking and repayment habits.</li>
      <li>Monitor your spending patterns regularly.</li>
      <li>Avoid unnecessary debt accumulation.</li>
      <li>Ensure timely payment of all financial obligations.</li>
      <li>Continue building a stable financial history.</li>
    </ul>
    <div style="background:#fef9c3;border-left:4px solid #f59e0b;padding:12px 16px;border-radius:6px;margin:24px 0;font-size:13px;color:#78350f">
      <strong>Important Disclaimer:</strong> This credit score has been generated using FinScore AI&#39;s machine learning and predictive analytics models. The result is provided solely for informational and educational purposes and should not be considered an official credit bureau score or a lending decision.
    </div>
    <p style="color:#475569">You can log in to your FinScore AI account at any time to review your results and continue monitoring your financial profile.</p>
    <p style="margin-top:28px;color:#64748b">Warm Regards,<br><strong>FinScore AI Team</strong><br>
      <span style="font-size:12px">AI-Powered Credit Assessment Platform &nbsp;·&nbsp; Empowering Smarter Financial Decisions</span><br>
      <span style="font-size:12px">Contact Email: {escape(user_email)}</span>
    </p>
  </div>
  <div style="padding:16px 32px;background:#f8fafc;border-top:1px solid #e2e8f0;font-size:11px;color:#94a3b8;text-align:center">
    © 2024 FinScore AI. All rights reserved.
  </div>
</div>
</body></html>""",
        subtype="html",
    )
    return _smtp_send(message)


def get_google_redirect_uri():
    configured_uri = app.config.get("GOOGLE_REDIRECT_URI", "").strip()
    if configured_uri:
        return configured_uri
    base_url = os.getenv("APP_BASE_URL", "http://localhost:5000").rstrip("/")
    return f"{base_url}/login/callback"


def validate_personal_details(name, email, phone):
    """Return a user-friendly validation error, or None when all fields are valid."""
    if not name or not email or not phone:
        return "Please fill all personal details."

    name_characters_are_valid = all(
        character.isalpha() or character in " .'-" for character in name
    )
    if not 2 <= len(name) <= 80 or not name_characters_are_valid or sum(c.isalpha() for c in name) < 2:
        return "Enter a valid full name (2-80 letters; spaces, apostrophes, hyphens and periods are allowed)."

    email_pattern = r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
    if len(email) > 254 or not re.fullmatch(email_pattern, email):
        return "Enter a valid email address, for example name@example.com."

    compact_phone = re.sub(r"[\s()-]", "", phone)
    if not re.fullmatch(r"(?:\+91)?[6-9]\d{9}", compact_phone):
        return "Enter a valid 10-digit Indian mobile number, optionally starting with +91."

    return None


def get_current_user():
    if not session.get("user_id"):
        return None
    return GoogleUser.query.get(session["user_id"])


def set_user_session(user):
    session.permanent = True
    session["user_id"] = user.id
    session["user_name"] = user.full_name
    session["user_email"] = user.email
    session["user_picture"] = user.profile_picture or ""
    session["user_google_id"] = user.google_user_id
    session.modified = True


def clear_user_session():
    session.pop("user_id", None)
    session.pop("user_name", None)
    session.pop("user_email", None)
    session.pop("user_picture", None)
    session.pop("user_google_id", None)


# â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def extract_amount(text):
    text = text.replace(",", "")
    m = re.search(r"[\d]+(?:\.\d+)?", text)
    return float(m.group()) if m else 0.0


def extract_money_cell(value):
    text = str(value or "").replace(",", "").strip()
    if not text:
        return 0.0
    m = re.search(r"(?:\d+(?:\.\d+)?|\.\d+)", text)
    if not m:
        return 0.0
    amount = m.group()
    if amount.startswith("."):
        amount = "0" + amount
    return float(amount)


INCOME_KW  = ["salary","credit","deposit","credited","neft cr","imps cr","income","received"]
EXPENSE_KW = ["debit","withdrawal","purchase","shopping","bill","payment","transfer",
              "amazon","flipkart","swiggy","zomato","uber","ola"]
EMI_KW     = ["emi","loan","equated","installment"]
UTILITY_KW = ["electricity","water","gas","internet","broadband","recharge"]
CASH_KW    = ["atm","cash withdrawal","atm withdrawal"]


def categorise(desc):
    d = desc.lower()
    if any(k in d for k in EMI_KW):     return "emi"
    if any(k in d for k in CASH_KW):    return "cash_withdrawal"
    if any(k in d for k in UTILITY_KW): return "utility"
    if any(k in d for k in INCOME_KW):  return "income"
    if any(k in d for k in EXPENSE_KW): return "expense"
    return "other"


def parse_pdf(path, password=None):
    rows = []
    with pdfplumber.open(path, password=password or "") as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if row and len(row) >= 3:
                        rows.append(row)
            if not tables:
                for line in (page.extract_text() or "").splitlines():
                    rows.append([line, "", ""])
    return rows


def check_pdf_access(path, password=None):
    """Validate PDF structure and credentials without extracting statement data."""
    try:
        with pdfplumber.open(path, password=password or "") as pdf:
            # Accessing pages forces pdfminer to parse the document catalogue.
            page_count = len(pdf.pages)
            if page_count == 0:
                return "invalid", "The uploaded PDF does not contain any pages."
        return "ok", None
    except PDFPasswordIncorrect:
        if password is None:
            return "password_required", (
                "This bank statement is password protected. "
                "Please enter the PDF password to continue."
            )
        return "invalid_password", "Invalid PDF password. Please try again."
    except PdfminerException as exc:
        # pdfplumber wraps PDFPasswordIncorrect as the first argument rather
        # than preserving it as __cause__ in current releases.
        wrapped = exc.args[0] if exc.args else None
        cause = exc.__cause__ or exc.__context__
        message = " ".join(str(value) for value in exc.args).lower()
        if (
            isinstance(wrapped, PDFPasswordIncorrect)
            or isinstance(cause, PDFPasswordIncorrect)
            or "password" in message
        ):
            if password is None:
                return "password_required", (
                    "This bank statement is password protected. "
                    "Please enter the PDF password to continue."
                )
            return "invalid_password", "Invalid PDF password. Please try again."
        return "invalid", "The uploaded PDF is corrupted or uses an unsupported PDF format."
    except (PDFSyntaxError, ValueError, TypeError):
        return "invalid", "The uploaded PDF is corrupted or uses an unsupported PDF format."
    except Exception:
        app.logger.exception("PDF preflight failed for an uploaded document")
        return "invalid", "The PDF could not be processed. Please upload a valid bank statement."


def parse_csv(path):
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    return df


def engineer_features_from_rows(rows):
    income = expenses = emi_total = cash = utility = 0.0
    emi_count = 0

    credits = []
    debits = []
    balances = []

    for row in rows:
        cells = [str(c or "").strip() for c in row]
        text = " ".join(c for c in cells if c)

        if len(cells) >= 5:
            desc = cells[2] if len(cells) > 2 else text

            debit = extract_money_cell(cells[3])
            credit = extract_money_cell(cells[4])
            balance = extract_money_cell(cells[5]) if len(cells) > 5 else 0.0

            if "transaction total" in desc.lower():
                continue

            if debit or credit:

                if credit > 0:
                    income += credit
                    credits.append(credit)

                if debit > 0:
                    cat = categorise(desc)

                    if cat == "emi":
                        emi_total += debit
                        emi_count += 1

                    elif cat == "cash_withdrawal":
                        cash += debit

                    elif cat == "utility":
                        utility += debit
                        expenses += debit

                    else:
                        expenses += debit

                    debits.append(debit)

                if balance > 0:
                    balances.append(balance)

                continue

        cat = categorise(text)

        if cat == "other":
            continue

        amount = extract_amount(text)

        if amount == 0:
            continue

        if cat == "income":
            income += amount
            credits.append(amount)

        elif cat in ("expense", "utility", "other"):
            expenses += amount
            debits.append(amount)

            if cat == "utility":
                utility += amount

        elif cat == "emi":
            emi_total += amount
            emi_count += 1
            debits.append(amount)

        elif cat == "cash_withdrawal":
            cash += amount
            debits.append(amount)

    total_debit = sum(debits) or 1

    net_savings = income - expenses - emi_total - cash

    avg_balance = (
        sum(balances) / len(balances)
    ) if balances else net_savings * 0.6

    # NEW: Get latest balance from statement
    closing_balance = balances[-1] if balances else 0

    print("Balances Found:", balances)

    if balances:
        print("Closing Balance:", closing_balance)

    return {
        "monthly_income": round(income, 2),

        "monthly_expense": round(expenses + emi_total + cash, 2),

        "net_savings": round(net_savings, 2),

        "savings_rate": round(
            (income - expenses) / income,
            4
        ) if income else 0,

        "avg_balance": round(avg_balance, 2),

        # NEW FIELD
        "closing_balance": round(closing_balance, 2),

        "emi_count": emi_count,

        "salary_frequency": len(
            [c for c in credits if c > 10000]
        ),

        "debit_credit_ratio": round(
            sum(debits) / (sum(credits) or 1),
            4
        ),

        "cash_withdrawal_ratio": round(
            cash / total_debit,
            4
        ),

        "loan_payment_history":
            1 if emi_count > 0 and emi_total < income * 0.4 else 0,

        "_utility": round(utility, 2),

        "_cash": round(cash, 2),

        "_emi_total": round(emi_total, 2),

        "_txn_count": len(credits) + len(debits),
    }


def engineer_features_from_csv(df):
    income = expenses = emi_total = cash = 0.0
    emi_count = 0; credits = []; debits = []
    desc_col   = next((c for c in df.columns if any(k in c for k in
                       ["desc","narr","detail","particular"])), None)
    amount_col = next((c for c in df.columns if "amount" in c), None)
    debit_col  = next((c for c in df.columns if "debit"  in c), None)
    credit_col = next((c for c in df.columns if "credit" in c), None)
    for _, row in df.iterrows():
        desc = str(row.get(desc_col, "")) if desc_col else ""
        cat  = categorise(desc)
        if credit_col and debit_col:
            cr = extract_amount(str(row.get(credit_col, 0) or 0))
            db_val = extract_amount(str(row.get(debit_col, 0) or 0))
        elif amount_col:
            val = extract_amount(str(row.get(amount_col, 0) or 0))
            cr  = val if cat == "income" else 0
            db_val = val if cat != "income" else 0
        else:
            continue
        if cr > 0:    income += cr;   credits.append(cr)
        if db_val > 0:
            if cat == "emi":               emi_total += db_val; emi_count += 1
            elif cat == "cash_withdrawal": cash += db_val
            else:                          expenses += db_val
            debits.append(db_val)
    total_debit = sum(debits) or 1
    return {
        "monthly_income":        round(income, 2),
        "monthly_expense":       round(expenses + emi_total + cash, 2),
        "net_savings":           round(income - expenses - emi_total - cash, 2),
        "savings_rate":          round((income - expenses) / income, 4) if income else 0,
        "avg_balance":           round((income - expenses - emi_total - cash) * 0.6, 2),
        "emi_count":             emi_count,
        "salary_frequency":      len([c for c in credits if c > 10000]),
        "debit_credit_ratio":    round(sum(debits) / (sum(credits) or 1), 4),
        "cash_withdrawal_ratio": round(cash / total_debit, 4),
        "loan_payment_history":  1 if emi_count > 0 and emi_total < income * 0.4 else 0,
        "_utility": 0, "_cash": round(cash, 2),
        "_emi_total": round(emi_total, 2), "_txn_count": len(credits) + len(debits),
    }


def predict_credit(feats):
    default_feature_order = [
        "monthly_income","monthly_expense","net_savings","savings_rate",
        "avg_balance","emi_count","salary_frequency","debit_credit_ratio",
        "cash_withdrawal_ratio","loan_payment_history",
    ]
    FEATURE_ORDER = list(getattr(model, "feature_names_in_", default_feature_order))

    # Estimate CIBIL score from statement cashflow: income, credits, debits,
    # savings behavior, and spending discipline.
    sr = feats["savings_rate"]
    cw = feats["cash_withdrawal_ratio"]
    mi = feats["monthly_income"]
    dr = feats["debit_credit_ratio"]
    sf = feats["salary_frequency"]
    ns = feats["net_savings"]

    estimated_cibil = 500  # base
    if sr >= 0.40:   estimated_cibil += 120
    elif sr >= 0.25: estimated_cibil += 80
    elif sr >= 0.15: estimated_cibil += 40
    elif sr < 0.05:  estimated_cibil -= 60

    if ns >= 50000: estimated_cibil += 60
    elif ns >= 25000: estimated_cibil += 40
    elif ns >= 10000: estimated_cibil += 20
    elif ns < 0: estimated_cibil -= 60

    if cw <= 0.05:   estimated_cibil += 30
    elif cw >= 0.35: estimated_cibil -= 50

    if mi >= 150000: estimated_cibil += 50
    elif mi >= 80000: estimated_cibil += 30
    elif mi >= 40000: estimated_cibil += 10
    elif mi < 15000: estimated_cibil -= 40

    if dr <= 0.4:    estimated_cibil += 50
    elif dr <= 0.7:  estimated_cibil += 25
    elif dr >= 1.0:  estimated_cibil -= 70
    elif dr >= 0.9:  estimated_cibil -= 40

    if sf >= 3:      estimated_cibil += 30
    elif sf >= 1:    estimated_cibil += 10
    else:            estimated_cibil -= 20

    feats["cibil_score"] = int(np.clip(estimated_cibil, 300, 900))

    # The saved model was trained with EMI columns, so keep compatible inputs
    # while making EMI neutral for prediction.
    model_feats = dict(feats)
    model_feats["avg_balance"] = 50000
    model_feats["emi_count"] = 0
    model_feats["loan_payment_history"] = 1
    X     = pd.DataFrame([[model_feats.get(k, 0) for k in FEATURE_ORDER]], columns=FEATURE_ORDER)
    pred  = int(model.predict(X)[0])
    proba = float(model.predict_proba(X)[0][1])

    # Final score = estimated CIBIL adjusted by ML confidence
    cibil = feats["cibil_score"]
    ml_boost = (proba - 0.5) * 100   # -50 to +50 adjustment
    score = int(np.clip(cibil + ml_boost, 300, 900))

    return pred, proba, score


def score_label(score):
    if score >= 750: return "Excellent"
    if score >= 700: return "Good"
    if score >= 650: return "Fair"
    if score >= 600: return "Average"
    return "Poor"


def loan_recommendation(score, pred):
    if score >= 750:               return "Approved", "green"           # excellent score always approved
    if score >= 700 and pred == 1: return "Approved", "green"           # good score + model agrees
    if score >= 650:               return "Conditionally Approved", "orange"  # fair score
    if score >= 600 and pred == 1: return "Conditionally Approved", "orange"  # average but model ok
    return "Not Approved", "red"


def ai_recommendations(feats, score):
    tips = []
    if feats["savings_rate"] < 0.2:
        tips.append("Increase your savings rate to at least 20% of income.")
    if feats["cash_withdrawal_ratio"] > 0.3:
        tips.append("Reduce cash withdrawals; use digital transactions instead.")
    if feats["debit_credit_ratio"] > 0.9:
        tips.append("Control spending - your debit/credit ratio is high.")
    if score < 650:
        tips.append("Avoid new loans until credit score improves above 650.")
    if not tips:
        tips.append("Maintain your current financial discipline to keep a high score.")
    return tips


def generate_pdf_report(user, feats, pred, proba, score, tips, report_id):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_fill_color(15, 23, 42)
    pdf.rect(0, 0, 210, 40, "F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 12, "  AI Credit Scoring Report", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 8, f"  Report ID: {report_id}   |   Generated by FinScore AI", ln=True)
    pdf.ln(10)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "Customer Details", ln=True)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 7, f"Name  : {user['name']}",  ln=True)
    pdf.cell(0, 7, f"Email : {user['email']}", ln=True)
    pdf.cell(0, 7, f"Phone : {user['phone']}", ln=True)
    pdf.ln(5)
    status   = score_label(score)
    loan_rec, _ = loan_recommendation(score, pred)
    pdf.set_fill_color(30, 58, 138)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, f"  Credit Score: {score}   |   Status: {status}   |   Loan: {loan_rec}",
             ln=True, fill=True)
    pdf.ln(5)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "Financial Summary", ln=True)
    pdf.set_font("Helvetica", "", 11)
    for label, val in [
        ("Monthly Income",  f"Rs. {feats['monthly_income']:,.0f}"),
        ("Monthly Expense", f"Rs. {feats['monthly_expense']:,.0f}"),
        ("Net Savings",     f"Rs. {feats['net_savings']:,.0f}"),
        ("Savings Rate",    f"{feats['savings_rate']*100:.1f}%"),
        ("Debit/Credit Ratio", f"{feats['debit_credit_ratio']:.2f}"),
        ("Salary Credits",  str(feats["salary_frequency"])),
        ("Confidence",      f"{proba*100:.1f}%"),
    ]:
        pdf.cell(80, 7, label, border=1)
        pdf.cell(0,  7, val,   border=1, ln=True)
    pdf.ln(5)
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "AI Recommendations", ln=True)
    pdf.set_font("Helvetica", "", 11)
    for tip in tips:
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(0, 7, f"  * {tip}")
    pdf.ln(3)
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 6, "Disclaimer: This report is AI-generated for informational purposes only.", ln=True)
    out_path = os.path.join(REPORT_FOLDER, f"report_{report_id}.pdf")
    pdf.output(out_path)
    return out_path


# â”€â”€ Routes â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@app.route("/auth/google")
def google_login():
    ensure_database()
    client_id = app.config.get("GOOGLE_CLIENT_ID", "").strip()
    client_secret = app.config.get("GOOGLE_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        flash("Google OAuth is not configured yet. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.", "danger")
        return redirect(url_for("home"))

    params = {
        "client_id": client_id,
        "redirect_uri": get_google_redirect_uri(),
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "online",
        "prompt": "select_account",
        "state": secrets.token_urlsafe(32),
    }
    session["google_oauth_state"] = params["state"]
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    return redirect(auth_url)


@app.route("/auth/google/callback")  # Backward-compatible alias for old bookmarks/configuration.
@app.route("/login/callback")
def google_callback():
    ensure_database()

    # Check for OAuth errors FIRST (user may deny access — Google can omit state)
    error = request.args.get("error")
    if error:
        app.logger.info("Google OAuth error: %s", error)
        flash("Google sign-in was cancelled or denied.", "warning")
        return redirect(url_for("login"))

    # CSRF state validation
    expected_state = session.pop("google_oauth_state", None)
    received_state = request.args.get("state")
    app.logger.debug("OAuth state — expected present: %s, received present: %s",
                     bool(expected_state), bool(received_state))
    if not expected_state or not received_state or not secrets.compare_digest(expected_state, received_state):
        app.logger.warning("OAuth state mismatch. expected=%s received=%s",
                           repr(expected_state), repr(received_state))
        flash("Sign-in session expired. Please click Sign in with Google again.", "warning")
        return redirect(url_for("login"))

    code = request.args.get("code")
    if not code:
        flash("Google sign-in failed because no authorization code was returned.", "danger")
        return redirect(url_for("home"))

    try:
        token_response = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": app.config.get("GOOGLE_CLIENT_ID", "").strip(),
                "client_secret": app.config.get("GOOGLE_CLIENT_SECRET", "").strip(),
                "redirect_uri": get_google_redirect_uri(),
                "grant_type": "authorization_code",
            },
            timeout=15,
        )
    except requests.RequestException as exc:
        app.logger.warning("Google token exchange request failed: %s", exc)
        flash("Google sign-in is temporarily unavailable. Please try again.", "danger")
        return redirect(url_for("home"))

    try:
        token_payload = token_response.json()
    except requests.exceptions.JSONDecodeError:
        token_payload = {}
    if token_response.status_code != 200 or "access_token" not in token_payload:
        app.logger.warning("Google token exchange failed: %s", token_payload)
        flash("Google sign-in could not be completed right now.", "danger")
        return redirect(url_for("home"))

    try:
        user_info_response = requests.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {token_payload['access_token']}"},
            timeout=15,
        )
        user_info = user_info_response.json()
    except (requests.RequestException, requests.exceptions.JSONDecodeError) as exc:
        app.logger.warning("Google user-info request failed: %s", exc)
        flash("Google sign-in is temporarily unavailable. Please try again.", "danger")
        return redirect(url_for("home"))
    if user_info_response.status_code != 200 or not user_info.get("email"):
        flash("Could not retrieve your Google account information.", "danger")
        return redirect(url_for("home"))

    google_user_id = user_info.get("sub") or user_info.get("id")
    if not google_user_id:
        flash("Google account information was incomplete.", "danger")
        return redirect(url_for("home"))

    user = GoogleUser.query.filter((GoogleUser.google_user_id == google_user_id) | (GoogleUser.email == user_info["email"])).first()
    is_new_user = user is None
    if is_new_user:
        user = GoogleUser(
            google_user_id=google_user_id,
            full_name=user_info.get("name") or user_info.get("given_name") or "Google User",
            email=user_info["email"],
            profile_picture=user_info.get("picture"),
        )
        db.session.add(user)
    else:
        user.google_user_id = google_user_id
        user.full_name = user_info.get("name") or user_info.get("given_name") or user.full_name
        user.email = user_info["email"]
        user.profile_picture = user_info.get("picture") or user.profile_picture

    if safe_commit("google user login"):
        set_user_session(user)
        if is_new_user:
            flash(f"Welcome to FinScore AI, {user.full_name}! Your account has been successfully created.", "success")
            send_welcome_email(user)
        else:
            flash(f"Welcome back, {user.full_name}! We are glad to see you again.", "success")
    else:
        flash("We could not persist your Google account session. Please try again.", "danger")

    return redirect(url_for("home"))


@app.route("/logout")
def logout():
    clear_user_session()
    flash("You have been logged out.", "info")
    return redirect(url_for("home"))


@app.route("/login")
def login():
    if get_current_user():
        return redirect(url_for("home"))
    return render_template("login.html", current_user=None)


@app.route("/")
def home():
    ensure_database()
    return render_template("index.html", current_user=get_current_user())


@app.route("/healthz")
def healthcheck():
    try:
        ensure_database()
        return jsonify({"status": "ok"}), 200
    except Exception:
        app.logger.exception("Health check failed")
        return jsonify({"status": "unhealthy"}), 503


@app.route("/analyze", methods=["POST"])
@login_required
def analyze():
    name  = request.form.get("name",  "").strip()
    email = request.form.get("email", "").strip()
    phone = request.form.get("phone", "").strip()

    personal_details_error = validate_personal_details(name, email, phone)
    if personal_details_error:
        return jsonify({"error": personal_details_error}), 400
    current_user = get_current_user()
    if not current_user or email.casefold() != current_user.email.casefold():
        return jsonify({"error": "Use the email address associated with your signed-in Google account."}), 403
    if "statement" not in request.files:
        return jsonify({"error": "No file uploaded."}), 400

    file = request.files["statement"]
    if file.filename == "" or not allowed_file(file.filename):
        return jsonify({
            "error": "Unsupported file format. Only PDF and CSV bank statements are accepted.",
            "validation_failed": True,
            "reasons": ["âœ— Invalid file type. Please upload a PDF or CSV bank statement."]
        }), 400

    ext      = file.filename.rsplit(".", 1)[1].lower()
    orig_name = file.filename
    filename  = secure_filename(f"{uuid.uuid4()}_{orig_name}")
    filepath  = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(filepath)

    pdf_password = request.form.get("pdf_password") or None
    if ext == "pdf":
        access_status, access_error = check_pdf_access(filepath, pdf_password)
        if access_status != "ok":
            try: os.remove(filepath)
            except OSError: pass
            password_required = access_status in {"password_required", "invalid_password"}
            return jsonify({
                "error": access_error,
                "password_required": password_required,
                "invalid_password": access_status == "invalid_password",
                "validation_failed": not password_required,
            }), 401 if password_required else 422

    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    #  DOCUMENT VALIDATION LAYER â€” ML model never runs if this fails
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
    try:
        vr = validate_document(filepath, ext, pdf_password=pdf_password)
    except Exception as e:
        try: os.remove(filepath)
        except: pass
        app.logger.exception("Statement validation failed")
        return jsonify({
            "error": "The statement could not be validated due to a processing error.",
            "validation_failed": True,
        }), 500

    # â”€â”€ Audit log â€” always saved regardless of pass/fail â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    vlog = ValidationLog(
        file_name         = orig_name,
        file_type         = ext.upper(),
        validation_status = "PASS" if vr["valid"] else "FAIL",
        validation_score  = vr["score"],
        bank_detected     = vr["bank_name"],
        txn_count         = vr["txn_count"],
        reject_reason     = "; ".join(r for r in vr["reasons"] if r.startswith("âœ—")) or None,
        uploader_name     = name,
        uploader_email    = email,
    )
    db.session.add(vlog)
    safe_commit("validation log")

    if not vr["valid"]:
        try: os.remove(filepath)
        except: pass
        if vr.get("password_required"):
            return jsonify({
                "error": vr["error_msg"],
                "password_required": True,
            }), 401
        return jsonify({
            "error":            vr["error_msg"],
            "validation_failed": True,
            "score":            vr["score"],
            "reasons":          vr["reasons"],
            "bank_name":        vr["bank_name"],
            "txn_count":        vr["txn_count"],
        }), 422
    # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

    # Feature extraction
    try:
        if ext == "pdf":
            rows  = parse_pdf(filepath, password=pdf_password)
            feats = engineer_features_from_rows(rows)
        else:
            df    = parse_csv(filepath)
            feats = engineer_features_from_csv(df)
    except (PDFSyntaxError, ValueError, TypeError):
        return jsonify({"error": "The PDF is corrupted or uses an unsupported format."}), 422
    except Exception:
        app.logger.exception("Statement transaction extraction failed")
        return jsonify({"error": "The statement could not be processed. Please try again."}), 500
    finally:
        pdf_password = None
        try: os.remove(filepath)
        except OSError: pass

    # Only use fallback when PDF/CSV had zero extractable transactions
    # Return an error instead of silently using fake data
    if feats["monthly_income"] == 0:
        return jsonify({
            "error": "Could not extract any financial transactions from the uploaded file. "
                     "Please upload a bank statement with visible transaction history.",
            "validation_failed": True,
            "reasons": ["âœ— No income or transaction data found in the document."]
        }), 422

    pred, proba, score = predict_credit(feats)
    status             = score_label(score)
    loan_rec, loan_color = loan_recommendation(score, pred)
    tips               = ai_recommendations(feats, score)
    report_id          = str(uuid.uuid4())[:8].upper()

    generate_pdf_report({"name": name, "email": email, "phone": phone},
                        feats, pred, proba, score, tips, report_id)

    record = CreditRecord(
        report_id       = report_id,
        name            = name,
        email           = email,
        phone           = phone,
        credit_score    = score,
        status          = status,
        creditworthy    = "Creditworthy" if pred == 1 else "Not Creditworthy",
        loan_rec        = loan_rec,
        confidence      = round(proba * 100, 1),
        monthly_income  = feats["monthly_income"],
        monthly_expense = feats["monthly_expense"],
        net_savings     = feats["net_savings"],
        savings_rate    = feats["savings_rate"],
        avg_balance     = feats["avg_balance"],
        emi_count       = feats["emi_count"],
        file_type       = ext.upper(),
    )
    db.session.add(record)
    safe_commit("credit record")

    result = {
        "name": name, "email": email, "phone": phone,
        "score": score, "status": status,
        "creditworthy": "Creditworthy" if pred == 1 else "Not Creditworthy",
        "loan_rec": loan_rec, "loan_color": loan_color,
        "confidence": round(proba * 100, 1),
        "report_id": report_id,
        "features":  {
            k: v for k, v in feats.items()
            if not k.startswith("_") and k not in {"avg_balance", "emi_count", "loan_payment_history"}
        },
        "tips":      tips,
        "validation": {
            "score":     vr["score"],
            "bank_name": vr["bank_name"],
            "txn_count": vr["txn_count"],
        },
        "chart_data": {
            "income":  feats["monthly_income"],
            "expense": feats["monthly_expense"],
            "savings": feats["net_savings"],
            "emi":     feats["_emi_total"],
            "cash":    feats["_cash"],
            "utility": feats["_utility"],
        }
    }

    session["last_result"] = json.dumps(result)
    return jsonify(result)



@app.route("/dashboard")
@login_required
def dashboard():
    data = session.get("last_result")
    if not data:
        return render_template("index.html", current_user=get_current_user())
    return render_template("dashboard.html", result=json.loads(data), current_user=get_current_user())


@app.route("/admin/setup", methods=["GET", "POST"])
def admin_setup():
    ensure_database()
    if has_admin_user():
        return redirect(url_for("admin_login"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if len(username) < 3:
            flash("Admin user ID must be at least 3 characters.", "danger")
        elif len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
        elif password != confirm_password:
            flash("Passwords do not match.", "danger")
        else:
            admin_user = AdminUser(
                username=username,
                password_hash=generate_password_hash(password),
            )
            db.session.add(admin_user)
            db.session.commit()
            flash("Admin account created. Please sign in.", "success")
            return redirect(url_for("admin_login"))

    return render_template("admin_setup.html")


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    ensure_database()
    if not has_admin_user():
        return redirect(url_for("admin_setup"))

    if session.get("admin_user_id"):
        admin_user = AdminUser.query.get(session["admin_user_id"])
        if admin_user and admin_user.is_active:
            return redirect(url_for("admin"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        admin_user = AdminUser.query.filter_by(username=username, is_active=True).first()

        if admin_user and admin_user.check_password(password):
            otp_code = str(secrets.randbelow(900000) + 100000)
            otp_hash = hashlib.sha256(otp_code.encode()).hexdigest()
            admin_email = app.config.get("ADMIN_EMAIL", "").strip().lower()

            otp_record = AdminLoginOtp(
                admin_username=username,
                admin_email=admin_email,
                otp_hash=otp_hash,
                expires_at=datetime.utcnow() + timedelta(seconds=60),
            )
            db.session.add(otp_record)
            safe_commit("admin login otp")

            if _send_admin_login_otp_email(admin_email, otp_code, username):
                session["admin_login_username"] = username
                flash("A login OTP was sent to your admin email. Please enter it to continue.", "success")
                return redirect(url_for("admin_login_verify", username=username))
            flash("Could not send login OTP. Check SMTP settings.", "danger")
            return redirect(url_for("admin_login"))

    return render_template("admin_login.html")


@app.route("/admin/login/verify/<username>", methods=["GET", "POST"])
def admin_login_verify(username):
    ensure_database()
    if session.get("admin_login_username") != username:
        flash("Please sign in again to request an OTP.", "warning")
        return redirect(url_for("admin_login"))

    admin_user = AdminUser.query.filter_by(username=username, is_active=True).first()
    if not admin_user:
        flash("Invalid admin user.", "danger")
        return redirect(url_for("admin_login"))

    otp_rec = AdminLoginOtp.query.filter(
        AdminLoginOtp.admin_username == username,
        AdminLoginOtp.used == False,
        AdminLoginOtp.expires_at > datetime.utcnow(),
    ).order_by(AdminLoginOtp.created_at.desc()).first()

    if request.method == "POST":
        if not otp_rec:
            flash("No valid OTP found. Please sign in again.", "warning")
            return redirect(url_for("admin_login"))

        entered = request.form.get("otp", "").strip()
        if not entered:
            flash("Enter the OTP sent to your email.", "danger")
            return render_template("admin_login_verify.html", username=username)

        entered_hash = hashlib.sha256(entered.encode()).hexdigest()
        otp_rec.attempts += 1
        if otp_rec.attempts > 5:
            otp_rec.used = True
            safe_commit("admin login otp lockout")
            flash("Too many attempts. Please sign in again.", "danger")
            return redirect(url_for("admin_login"))

        if entered_hash != otp_rec.otp_hash:
            safe_commit("admin login otp attempt")
            flash(f"Incorrect OTP. {5 - otp_rec.attempts} attempt(s) remaining.", "danger")
            return render_template("admin_login_verify.html", username=username)

        otp_rec.used = True
        safe_commit("admin login otp verified")
        session.pop("admin_login_username", None)
        session["admin_authenticated"] = True
        session["admin_user_id"] = admin_user.id
        session["admin_username"] = admin_user.username
        flash("Admin login successful.", "success")
        return redirect(url_for("admin"))

    return render_template("admin_login_verify.html", username=username)


@app.route("/admin/forgot-password", methods=["GET", "POST"])
def admin_forgot_password():
    ensure_database()
    if not has_admin_user():
        return redirect(url_for("admin_setup"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()

        if not username or not email:
            flash("Enter both admin user ID and email.", "danger")
            return render_template("admin_forgot_password.html")

        admin_user = AdminUser.query.filter_by(username=username, is_active=True).first()
        if not admin_user:
            flash("No active admin found with that user ID.", "danger")
            return render_template("admin_forgot_password.html")

        configured_email = app.config.get("ADMIN_EMAIL", "").strip().lower()
        if not configured_email:
            flash("Admin reset email is not configured.", "danger")
            return render_template("admin_forgot_password.html")

        if email.lower() != configured_email:
            flash("Email does not match the configured admin address.", "danger")
            return render_template("admin_forgot_password.html")

        otp_code = str(secrets.randbelow(900000) + 100000)
        otp_hash = hashlib.sha256(otp_code.encode()).hexdigest()
        otp_record = AdminPasswordResetOtp(
            admin_username=username,
            admin_email=configured_email,
            otp_hash=otp_hash,
            expires_at=datetime.utcnow() + timedelta(seconds=60),
        )
        db.session.add(otp_record)
        safe_commit("admin reset otp")

        if _send_admin_reset_otp_email(configured_email, otp_code, username):
            flash("OTP sent to your admin email. Check Gmail for the code.", "success")
            return redirect(url_for("admin_forgot_verify", username=username))

        flash("Could not send OTP email. Check SMTP settings.", "danger")

    return render_template("admin_forgot_password.html")


@app.route("/admin/forgot-password/verify/<username>", methods=["GET", "POST"])
def admin_forgot_verify(username):
    ensure_database()
    if not has_admin_user():
        return redirect(url_for("admin_setup"))

    admin_user = AdminUser.query.filter_by(username=username, is_active=True).first()
    if not admin_user:
        flash("Invalid admin user.", "danger")
        return redirect(url_for("admin_forgot_password"))

    otp_rec = AdminPasswordResetOtp.query.filter(
        AdminPasswordResetOtp.admin_username == username,
        AdminPasswordResetOtp.used == False,
        AdminPasswordResetOtp.expires_at > datetime.utcnow(),
    ).order_by(AdminPasswordResetOtp.created_at.desc()).first()

    if request.method == "POST":
        if not otp_rec:
            flash("No valid OTP found. Request a new password reset.", "warning")
            return redirect(url_for("admin_forgot_password"))

        entered = request.form.get("otp", "").strip()
        if not entered:
            flash("Enter the OTP sent to your email.", "danger")
            return render_template("admin_forgot_verify.html", username=username)

        entered_hash = hashlib.sha256(entered.encode()).hexdigest()
        otp_rec.attempts += 1
        if otp_rec.attempts > 5:
            otp_rec.used = True
            safe_commit("admin otp lockout")
            flash("Too many attempts. Request a new OTP.", "danger")
            return redirect(url_for("admin_forgot_password"))

        if entered_hash != otp_rec.otp_hash:
            safe_commit("admin otp attempt")
            flash(f"Incorrect OTP. {5 - otp_rec.attempts} attempt(s) remaining.", "danger")
            return render_template("admin_forgot_verify.html", username=username)

        otp_rec.used = True
        safe_commit("admin otp verified")
        session["admin_reset_username"] = username
        return redirect(url_for("admin_reset_password", username=username))

    return render_template("admin_forgot_verify.html", username=username)


@app.route("/admin/reset-password/<username>", methods=["GET", "POST"])
def admin_reset_password(username):
    ensure_database()
    if session.get("admin_reset_username") != username:
        flash("Please verify the password reset OTP first.", "warning")
        return redirect(url_for("admin_forgot_password"))

    admin_user = AdminUser.query.filter_by(username=username, is_active=True).first()
    if not admin_user:
        flash("Invalid admin user.", "danger")
        return redirect(url_for("admin_forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
        elif password != confirm:
            flash("Passwords do not match.", "danger")
        else:
            admin_user.password_hash = generate_password_hash(password)
            db.session.commit()
            session.pop("admin_reset_username", None)
            flash("Password updated. You can now log in.", "success")
            return redirect(url_for("admin_login"))

    return render_template("admin_reset_password.html", username=username)


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_authenticated", None)
    session.pop("admin_username", None)
    session.pop("admin_user_id", None)
    flash("You have been logged out.", "info")
    return redirect(url_for("admin_login"))


@app.route("/admin")
@admin_required
def admin():
    ensure_database()
    records   = CreditRecord.query.order_by(CreditRecord.created_at.desc()).all()
    val_logs  = ValidationLog.query.order_by(ValidationLog.created_at.desc()).all()
    total     = len(records)
    approved  = sum(1 for r in records if r.loan_rec == "Approved")
    avg_score = round(sum(r.credit_score for r in records) / total, 1) if total else 0
    pdf_count = sum(1 for r in records if r.file_type == "PDF")
    csv_count = sum(1 for r in records if r.file_type == "CSV")
    val_pass  = sum(1 for v in val_logs if v.validation_status == "PASS")
    val_fail  = sum(1 for v in val_logs if v.validation_status == "FAIL")
    return render_template("admin.html",
        records=records, val_logs=val_logs,
        total=total, approved=approved, avg_score=avg_score,
        pdf_count=pdf_count, csv_count=csv_count,
        val_pass=val_pass, val_fail=val_fail)


@app.route("/admin/delete/<int:record_id>", methods=["POST"])
@admin_required
def delete_record(record_id):
    ensure_database()
    record = CreditRecord.query.get_or_404(record_id)
    pdf_path = os.path.join(REPORT_FOLDER, f"report_{record.report_id}.pdf")
    if os.path.exists(pdf_path):
        os.remove(pdf_path)
    db.session.delete(record)
    db.session.commit()
    return jsonify({"success": True})


@app.route("/admin/delete-log/<int:log_id>", methods=["POST"])
@admin_required
def delete_log(log_id):
    ensure_database()
    log = ValidationLog.query.get_or_404(log_id)
    db.session.delete(log)
    db.session.commit()
    return jsonify({"success": True})


@app.route("/admin/export")
@admin_required
def export_csv():
    ensure_database()
    records  = CreditRecord.query.order_by(CreditRecord.created_at.desc()).all()
    rows     = [list(CreditRecord.__table__.columns.keys())]
    for r in records:
        rows.append([str(getattr(r, c)) for c in CreditRecord.__table__.columns.keys()])
    csv_path = os.path.join(REPORT_FOLDER, "all_records.csv")
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(rows)
    return send_file(csv_path, as_attachment=True, download_name="FinScore_Records.csv")



def _mask_email(email):
    local, domain = email.split('@', 1)
    return local[:2] + '***@' + domain


def _send_otp_email(user_email, otp_code, report_id):
    msg = EmailMessage()
    msg["Subject"] = f"FinScore AI — OTP to download Report {report_id}"
    msg["To"] = user_email
    msg.set_content(
        f"Your one-time password to download Report {report_id} is:\n\n"
        f"  {otp_code}\n\n"
        "This OTP expires in 60 seconds. Do not share it with anyone.\n\n"
        "Regards,\nFinScore AI Team"
    )
    msg.add_alternative(f"""<!doctype html><html><body style="font-family:Arial,sans-serif;background:#f1f5f9;margin:0;padding:32px">
<div style="max-width:480px;margin:auto;background:#fff;border-radius:14px;overflow:hidden;border:1px solid #e2e8f0">
  <div style="background:#0f172a;padding:24px 32px;color:#fff">
    <h2 style="margin:0">FinScore <span style="color:#22c55e">AI</span></h2>
    <p style="margin:4px 0 0;font-size:13px;color:#94a3b8">Secure Report Download</p>
  </div>
  <div style="padding:32px">
    <p style="font-size:15px;color:#0f172a">Your one-time password for Report <strong>{report_id}</strong>:</p>
    <div style="text-align:center;margin:24px 0">
      <span style="font-size:42px;font-weight:800;letter-spacing:10px;color:#1d4ed8;font-family:monospace">{otp_code}</span>
    </div>
    <p style="color:#64748b;font-size:13px">This OTP expires in <strong>60 seconds</strong>. Never share it with anyone.</p>
    <p style="color:#64748b;font-size:13px;margin-top:20px">Regards,<br><strong>FinScore AI Team</strong></p>
  </div>
</div>
</body></html>""", subtype="html")
    return _smtp_send(msg)


def _owned_report_or_none(report_id, user):
    if not user:
        return None
    return CreditRecord.query.filter_by(report_id=report_id).filter(
        func.lower(CreditRecord.email) == user.email.lower()
    ).first()


@app.route("/report/<report_id>/request-otp", methods=["GET", "POST"])
@login_required
def request_otp(report_id):
    ensure_database()
    google_user = get_current_user()
    if not _owned_report_or_none(report_id, google_user):
        flash("That report was not found in your account.", "danger")
        return redirect(url_for("dashboard"))
    user_email  = google_user.email

    # Rate-limit: max 3 OTPs per hour per report per user
    one_hour_ago = datetime.utcnow() - timedelta(hours=1)
    recent_count = OtpRecord.query.filter(
        OtpRecord.report_id  == report_id,
        OtpRecord.user_email == user_email,
        OtpRecord.created_at >= one_hour_ago,
    ).count()

    if request.method == "POST":
        if recent_count >= 3:
            flash("Too many OTP requests. Please wait an hour before trying again.", "danger")
            return redirect(url_for("request_otp", report_id=report_id))

        otp_code = str(secrets.randbelow(900000) + 100000)   # 6-digit
        otp_hash = hashlib.sha256(otp_code.encode()).hexdigest()

        record = OtpRecord(
            report_id  = report_id,
            user_email = user_email,
            otp_hash   = otp_hash,
            expires_at = datetime.utcnow() + timedelta(seconds=60),
        )
        db.session.add(record)
        safe_commit("otp record")

        sent = _send_otp_email(user_email, otp_code, report_id)
        if sent:
            flash(f"OTP sent to {_mask_email(user_email)}. It expires in 60 seconds.", "success")
        else:
            flash("Could not send OTP email. Check your SMTP settings.", "danger")
            return redirect(url_for("request_otp", report_id=report_id))

        return redirect(url_for("verify_otp", report_id=report_id))

    return render_template("otp.html",
        report_id=report_id,
        masked_email=_mask_email(user_email),
        rate_limited=(recent_count >= 3),
    )


@app.route("/report/<report_id>/verify-otp", methods=["GET", "POST"])
@login_required
def verify_otp(report_id):
    ensure_database()
    google_user = get_current_user()
    if not _owned_report_or_none(report_id, google_user):
        flash("That report was not found in your account.", "danger")
        return redirect(url_for("dashboard"))
    user_email  = google_user.email

    # Find the latest unused, unexpired OTP for this user+report
    otp_rec = OtpRecord.query.filter(
        OtpRecord.report_id  == report_id,
        OtpRecord.user_email == user_email,
        OtpRecord.used       == False,
        OtpRecord.expires_at >  datetime.utcnow(),
    ).order_by(OtpRecord.created_at.desc()).first()

    if not otp_rec:
        flash("No valid OTP found. Please request a new one.", "warning")
        return redirect(url_for("request_otp", report_id=report_id))

    attempts_left = 3 - otp_rec.attempts

    if request.method == "POST":
        entered = request.form.get("otp", "").strip()
        entered_hash = hashlib.sha256(entered.encode()).hexdigest()

        otp_rec.attempts += 1
        safe_commit("otp attempt")

        if otp_rec.attempts > 3:
            flash("Maximum attempts exceeded. Please request a new OTP.", "danger")
            return redirect(url_for("request_otp", report_id=report_id))

        if entered_hash != otp_rec.otp_hash:
            flash(f"Incorrect OTP. {3 - otp_rec.attempts} attempt(s) remaining.", "danger")
            return redirect(url_for("verify_otp", report_id=report_id))

        # Correct — mark used and serve the PDF
        otp_rec.used = True
        safe_commit("otp used")

        path = os.path.join(REPORT_FOLDER, f"report_{report_id}.pdf")
        if not os.path.exists(path):
            flash("Report file not found.", "danger")
            return redirect(url_for("dashboard"))
        return send_file(path, as_attachment=True, download_name=f"CreditReport_{report_id}.pdf")

    return render_template("verify.html",
        report_id=report_id,
        attempts_left=attempts_left,
    )

@app.route("/report/<report_id>")
def download_report(report_id):
    ensure_database()
    path = os.path.join(REPORT_FOLDER, f"report_{report_id}.pdf")
    if not os.path.exists(path):
        return "Report not found.", 404

    admin_user_id = session.get("admin_user_id")
    admin_user = db.session.get(AdminUser, admin_user_id) if admin_user_id else None
    if session.get("admin_authenticated") and admin_user and admin_user.is_active:
        return send_file(path, as_attachment=True, download_name=f"CreditReport_{report_id}.pdf")

    user = get_current_user()
    if not user:
        flash("Please sign in with Google to continue.", "warning")
        return redirect(url_for("login"))
    if not _owned_report_or_none(report_id, user):
        return "Report not found.", 404
    return redirect(url_for("request_otp", report_id=report_id))


if __name__ == "__main__":
    with app.app_context():
        try:
            ensure_database()
        except Exception as e:
            db.session.rollback()
            print(f"Database unavailable; scoring will still run without history logging. {e}")
        print("Database startup check complete.")
    app.run(debug=False)
