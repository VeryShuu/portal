"""Unit-тесты: safe_redirect — защита от open-redirect атак."""

from app.core.redirects import safe_redirect


class TestSafeRedirectAllowed:
    def test_root_path(self):
        assert safe_redirect("/") == "/"

    def test_simple_path(self):
        assert safe_redirect("/news") == "/news"

    def test_nested_path(self):
        assert safe_redirect("/kb/articles/123") == "/kb/articles/123"

    def test_path_with_query(self):
        assert safe_redirect("/news?page=2") == "/news?page=2"

    def test_path_with_fragment(self):
        assert safe_redirect("/news#section") == "/news#section"

    def test_path_with_query_and_fragment(self):
        assert safe_redirect("/search?q=hello#results") == "/search?q=hello#results"

    def test_path_with_encoded_chars(self):
        assert safe_redirect("/files/my%20file") == "/files/my%20file"

    def test_path_with_equals_and_ampersand(self):
        assert safe_redirect("/search?q=foo&type=news") == "/search?q=foo&type=news"


class TestSafeRedirectBlocked:
    def test_absolute_http_url(self):
        assert safe_redirect("http://evil.com/") == "/"

    def test_absolute_https_url(self):
        assert safe_redirect("https://evil.com/steal") == "/"

    def test_protocol_relative_double_slash(self):
        assert safe_redirect("//evil.com") == "/"

    def test_protocol_relative_backslash(self):
        assert safe_redirect("/\\evil.com") == "/"

    def test_javascript_scheme(self):
        assert safe_redirect("javascript:alert(1)") == "/"

    def test_data_scheme(self):
        assert safe_redirect("data:text/html,<h1>") == "/"

    def test_empty_string(self):
        assert safe_redirect("") == "/"

    def test_none(self):
        assert safe_redirect(None) == "/"

    def test_api_prefix_blocked(self):
        assert safe_redirect("/api/v1/users") == "/"

    def test_realms_prefix_blocked(self):
        assert safe_redirect("/realms/company/tokens") == "/"

    def test_auth_prefix_blocked(self):
        assert safe_redirect("/auth/login") == "/"

    def test_auth_callback_blocked(self):
        assert safe_redirect("/auth/callback?code=1") == "/"

    def test_colon_in_path_blocked(self):
        assert safe_redirect("/path:evil") == "/"

    def test_custom_default(self):
        result = safe_redirect("https://evil.com", default="/home")
        assert result == "/home"

    def test_backslash_normalised_to_slash_protocol_relative(self):
        assert safe_redirect("/\\evil.com/page") == "/"


class TestSafeRedirectAuthAllowlist:
    """SPA-страницы /auth/local и /auth/error разрешены как redirect target."""

    def test_auth_local_allowed(self):
        assert safe_redirect("/auth/local") == "/auth/local"

    def test_auth_local_with_query_allowed(self):
        assert safe_redirect("/auth/local?logged_out=1") == "/auth/local?logged_out=1"

    def test_auth_error_allowed(self):
        assert safe_redirect("/auth/error") == "/auth/error"

    def test_auth_error_with_reason_allowed(self):
        assert safe_redirect("/auth/error?reason=sso_failed") == "/auth/error?reason=sso_failed"

    def test_admin_allowed(self):
        assert safe_redirect("/admin") == "/admin"

    def test_root_allowed(self):
        assert safe_redirect("/") == "/"

    def test_auth_local_evil_suffix_blocked(self):
        # /auth/localish should NOT match /auth/local prefix-allowlist.
        assert safe_redirect("/auth/localish") == "/"
