# FinScore AI

FinScore AI is a Flask credit-scoring application with secure email-based sign-in.

## Authentication

Users sign in by entering an email address and verifying a six-digit, SHA-256-hashed one-time code. Codes expire in 60 seconds, may be resent after the expiry window, are limited to three requests per email per hour, and are locked after five failed verification attempts. A verified email automatically creates a new user account; existing users simply verify a new code.

Admin sign-in, admin OTP, password reset, report-download OTP, dashboard, reporting, statement validation, and prediction behavior are unchanged.

## Setup

1. Install dependencies: `pip install -r requirements.txt`
2. Copy `.env.example` to `.env`.
3. Set a long `FLASK_SECRET_KEY` and configure the existing Resend/email settings.
4. Run the app: `python app.py`

## Production deployment (Render)

`render.yaml` provisions the web service, PostgreSQL database, health check, and persistent report disk. Set every environment variable marked `sync: false` in Render, including the email provider credentials and `APP_BASE_URL`. Then deploy and open `/admin/setup` once to create the first administrator.

The production container uses Gunicorn and includes Poppler and Tesseract for scanned-PDF processing. PostgreSQL stores application records and the mounted disk stores generated PDF reports.
