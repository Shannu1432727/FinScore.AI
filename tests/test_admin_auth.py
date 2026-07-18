import os
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
os.environ['DATABASE_URL'] = 'sqlite:///' + os.path.join(
    tempfile.gettempdir(),
    f'finscore_test_{uuid.uuid4().hex}.db',
)

import app as app_module


def test_admin_panel_redirects_without_admin_login():
    app_module.app.config.update(TESTING=True)
    client = app_module.app.test_client()

    response = client.get('/admin')
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/admin/login')


def test_admin_data_routes_are_all_protected():
    app_module.app.config.update(TESTING=True)
    client = app_module.app.test_client()

    routes = [
        ('get', '/admin/export'),
        ('post', '/admin/delete/1'),
        ('post', '/admin/delete-log/1'),
    ]
    for method, route in routes:
        response = getattr(client, method)(route)
        assert response.status_code == 302
        assert response.headers['Location'].endswith('/admin/login')


def test_home_page_contains_google_sign_in_button():
    app_module.app.config.update(TESTING=True)
    client = app_module.app.test_client()

    response = client.get('/')
    assert response.status_code == 200
    assert b'Sign in with Google' in response.data


def test_google_oauth_settings_are_available_to_auth_routes():
    assert app_module.app.config.get('GOOGLE_CLIENT_ID') == os.getenv('GOOGLE_CLIENT_ID', '')
    assert app_module.app.config.get('GOOGLE_CLIENT_SECRET') == os.getenv('GOOGLE_CLIENT_SECRET', '')
    assert app_module.app.config.get('GOOGLE_REDIRECT_URI') == os.getenv('GOOGLE_REDIRECT_URI', '')


def test_google_login_uses_configured_redirect_uri():
    app_module.app.config.update(
        TESTING=True,
        GOOGLE_CLIENT_ID='test-client-id',
        GOOGLE_CLIENT_SECRET='test-client-secret',
        GOOGLE_REDIRECT_URI='http://localhost:5000/login/callback',
    )
    client = app_module.app.test_client()

    response = client.get('/auth/google')

    assert response.status_code == 302
    assert 'redirect_uri=http%3A%2F%2Flocalhost%3A5000%2Flogin%2Fcallback' in response.headers['Location']


def test_google_callback_route_exists():
    app_module.app.config.update(TESTING=True)
    client = app_module.app.test_client()

    response = client.get('/login/callback')

    assert response.status_code == 302


def test_personal_details_validation_accepts_supported_formats():
    assert app_module.validate_personal_details(
        "Rajesh Kumar", "rajesh@example.com", "+91 98765-43210"
    ) is None


def test_personal_details_validation_rejects_invalid_values():
    assert app_module.validate_personal_details("R4jesh", "rajesh@example.com", "9876543210")
    assert app_module.validate_personal_details("Rajesh", "not-an-email", "9876543210")
    assert app_module.validate_personal_details("Rajesh", "rajesh@example.com", "12345")


def test_protected_report_routes_redirect_to_login():
    app_module.app.config.update(TESTING=True)
    client = app_module.app.test_client()

    response = client.post('/analyze', data={'name': 'Test', 'email': 'test@example.com', 'phone': '1234567890'})
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/login')
