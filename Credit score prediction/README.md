# FinScore AI with Google Sign-In

This Flask app now supports Google Sign-In via OAuth 2.0 and Google Identity Services.

## Features
- "Sign in with Google" button on the homepage and dashboard
- OAuth redirect to Google login
- User profile data stored in SQLite via SQLAlchemy
- Automatic account creation for new users and login for existing users
- Flask session-based authentication
- Logout button

## Setup
1. Install dependencies:
   pip install -r requirements.txt
2. Copy the sample environment file:
   copy .env.example .env
3. Fill in your Google OAuth credentials:
   - GOOGLE_CLIENT_ID
   - GOOGLE_CLIENT_SECRET
   - GOOGLE_REDIRECT_URI
4. Run the app:
   python app.py

## Google OAuth configuration
1. Create a project in Google Cloud Console.
2. Enable the Google Identity Services OAuth consent screen.
3. Create OAuth credentials for a Web application.
4. Add the authorized redirect URI:
   http://localhost:5000/login/callback
5. Copy the client ID and client secret into the environment variables.

## Production deployment (Render)

1. Copy `.env.example` to `.env` for local development. Never commit `.env`.
2. Push the project to a private Git repository.
3. In Render, create a Blueprint from this repository. `render.yaml` provisions the web service, PostgreSQL database, health check, and persistent report disk.
4. Set every environment variable marked `sync: false` in the Render dashboard.
5. Set `APP_BASE_URL` to the public HTTPS URL, for example `https://finscore-ai.onrender.com`.
6. Set `GOOGLE_REDIRECT_URI` to `<APP_BASE_URL>/login/callback` and add that exact URI to the Google Cloud OAuth client.
7. Deploy, then open `/admin/setup` once to create the first administrator.

The production container uses Gunicorn and includes Poppler and Tesseract for scanned-PDF processing. PostgreSQL stores application records and the mounted disk stores generated PDF reports.

Before the first public deployment, rotate any credentials that were previously kept in an unignored `.env` file.
