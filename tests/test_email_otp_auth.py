import hashlib

import app as app_module


TEST_EMAIL = "email-otp-auth@example.com"


def _clear_test_data():
    with app_module.app.app_context():
        app_module.ensure_database()
        app_module.UserLoginOtp.query.filter_by(user_email=TEST_EMAIL).delete()
        app_module.User.query.filter_by(email=TEST_EMAIL).delete()
        app_module.db.session.commit()


def _request_code(client, monkeypatch):
    sent_codes = []
    monkeypatch.setattr(app_module, "_send_user_login_otp_email", lambda email, code: sent_codes.append((email, code)) or True)
    response = client.post("/login", data={"email": TEST_EMAIL}, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login/verify")
    assert sent_codes[0][0] == TEST_EMAIL
    return sent_codes[0][1]


def test_email_code_is_hashed_and_creates_a_user_after_verification(monkeypatch):
    app_module.app.config.update(TESTING=True)
    _clear_test_data()
    client = app_module.app.test_client()

    code = _request_code(client, monkeypatch)
    with app_module.app.app_context():
        otp = app_module.UserLoginOtp.query.filter_by(user_email=TEST_EMAIL).one()
        assert otp.otp_hash == hashlib.sha256(code.encode()).hexdigest()
        assert otp.expires_at > otp.created_at
        assert app_module.User.query.filter_by(email=TEST_EMAIL).count() == 0

    response = client.post("/login/verify", data={"otp": code}, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")
    with app_module.app.app_context():
        assert app_module.User.query.filter_by(email=TEST_EMAIL).count() == 1


def test_returning_user_verifies_code_without_duplicate_account(monkeypatch):
    app_module.app.config.update(TESTING=True)
    _clear_test_data()
    with app_module.app.app_context():
        app_module.db.session.add(app_module.User(full_name="Existing User", email=TEST_EMAIL))
        app_module.db.session.commit()
    client = app_module.app.test_client()

    code = _request_code(client, monkeypatch)
    response = client.post("/login/verify", data={"otp": code}, follow_redirects=False)
    assert response.status_code == 302
    with app_module.app.app_context():
        assert app_module.User.query.filter_by(email=TEST_EMAIL).count() == 1


def test_login_code_request_is_rate_limited(monkeypatch):
    app_module.app.config.update(TESTING=True)
    _clear_test_data()
    client = app_module.app.test_client()
    monkeypatch.setattr(app_module, "_send_user_login_otp_email", lambda *_: True)
    for _ in range(3):
        with app_module.app.app_context():
            app_module.db.session.add(app_module.UserLoginOtp(
                user_email=TEST_EMAIL, otp_hash="x", expires_at=app_module.datetime.utcnow()
            ))
            app_module.db.session.commit()
    response = client.post("/login", data={"email": TEST_EMAIL})
    assert b"Too many sign-in codes requested" in response.data
