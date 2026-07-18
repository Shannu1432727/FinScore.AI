import app as app_module


class StubResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


TEST_GOOGLE_ID = "finscore-welcome-test-google-id"
TEST_EMAIL = "finscore-welcome-test@example.com"


def complete_google_login(client, monkeypatch, google_id=TEST_GOOGLE_ID, email=TEST_EMAIL):
    monkeypatch.setattr(app_module, "send_welcome_email", lambda user: True)
    monkeypatch.setattr(
        app_module.requests,
        "post",
        lambda *args, **kwargs: StubResponse({"access_token": "test-token"}),
    )
    monkeypatch.setattr(
        app_module.requests,
        "get",
        lambda *args, **kwargs: StubResponse(
            {"sub": google_id, "email": email, "name": "John Doe", "picture": ""}
        ),
    )
    with client.session_transaction() as session:
        session["google_oauth_state"] = "test-state"
    return client.get("/login/callback?code=test-code&state=test-state", follow_redirects=True)


def test_first_login_creates_one_user_and_shows_welcome_once(monkeypatch):
    app_module.app.config.update(TESTING=True)
    with app_module.app.app_context():
        app_module.ensure_database()
        app_module.GoogleUser.query.filter_by(email=TEST_EMAIL).delete()
        app_module.db.session.commit()

    client = app_module.app.test_client()
    response = complete_google_login(client, monkeypatch)

    assert b"Welcome to FinScore AI, John Doe!" in response.data
    assert b"Welcome, John" in response.data
    with app_module.app.app_context():
        assert app_module.GoogleUser.query.filter_by(email=TEST_EMAIL).count() == 1

    refreshed = client.get("/")
    assert b"Welcome to FinScore AI, John Doe!" not in refreshed.data
    assert b"Welcome, John" in refreshed.data


def test_welcome_email_uses_configured_smtp(monkeypatch):
    sent_messages = []

    class FakeSMTP:
        def __init__(self, server, port, timeout):
            assert (server, port, timeout) == ("smtp.example.com", 587, 10)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def starttls(self):
            pass

        def login(self, username, password):
            assert (username, password) == ("sender@example.com", "app-password")

        def send_message(self, message):
            sent_messages.append(message)

    monkeypatch.setattr(app_module.smtplib, "SMTP", FakeSMTP)
    app_module.app.config.update(
        MAIL_SERVER="smtp.example.com",
        MAIL_PORT=587,
        MAIL_USE_TLS=True,
        MAIL_USE_SSL=False,
        MAIL_USERNAME="sender@example.com",
        MAIL_PASSWORD="app-password",
        MAIL_DEFAULT_SENDER="sender@example.com",
    )
    user = app_module.GoogleUser(full_name="John Doe", email="john@example.com")

    assert app_module.send_welcome_email(user) is True
    assert len(sent_messages) == 1
    assert sent_messages[0]["To"] == "john@example.com"
    assert sent_messages[0]["Subject"] == "Welcome to FinScore AI"


def test_gmail_app_password_display_spaces_are_removed(monkeypatch):
    authenticated_passwords = []

    class FakeSMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def starttls(self):
            pass

        def login(self, username, password):
            authenticated_passwords.append(password)

        def send_message(self, message):
            pass

    monkeypatch.setattr(app_module.smtplib, "SMTP", FakeSMTP)
    app_module.app.config.update(
        MAIL_SERVER="smtp.gmail.com",
        MAIL_PORT=587,
        MAIL_USE_TLS=True,
        MAIL_USE_SSL=False,
        MAIL_USERNAME="sender@gmail.com",
        MAIL_PASSWORD="abcd efgh ijkl mnop",
        MAIL_DEFAULT_SENDER="sender@gmail.com",
    )

    assert app_module.send_welcome_email(
        app_module.GoogleUser(full_name="John Doe", email="john@example.com")
    ) is True
    assert authenticated_passwords == ["abcdefghijklmnop"]

def test_returning_login_does_not_duplicate_user(monkeypatch):
    app_module.app.config.update(TESTING=True)
    with app_module.app.app_context():
        app_module.ensure_database()
        existing_user = app_module.GoogleUser.query.filter_by(email=TEST_EMAIL).first()
        if existing_user is None:
            app_module.db.session.add(app_module.GoogleUser(
                google_user_id=TEST_GOOGLE_ID,
                full_name="John Doe",
                email=TEST_EMAIL,
            ))
            app_module.db.session.commit()
    client = app_module.app.test_client()

    response = complete_google_login(client, monkeypatch)

    assert b"Welcome back, John Doe! We are glad to see you again." in response.data
    with app_module.app.app_context():
        assert app_module.GoogleUser.query.filter_by(email=TEST_EMAIL).count() == 1
