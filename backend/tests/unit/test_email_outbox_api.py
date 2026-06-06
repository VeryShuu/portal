from app.api.email_outbox import _like_escape


class TestLikeEscape:
    def test_escapes_percent(self):
        assert _like_escape("100%") == "100\\%"

    def test_escapes_underscore(self):
        assert _like_escape("a_b") == "a\\_b"

    def test_escapes_backslash_first(self):
        assert _like_escape("a\\b") == "a\\\\b"

    def test_plain_text_untouched(self):
        assert _like_escape("user@example.com") == "user@example.com"
