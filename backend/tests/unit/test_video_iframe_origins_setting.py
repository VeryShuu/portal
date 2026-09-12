"""Runtime-настройка ``system.json → video_iframe_origins`` (Admin UI → System).

Покрывает: валидатор/нормализацию списка, дефолт (= константа, синхронную с
fallback'ом nginx-sidecar), мета-эндпоинт learning (обоих контуров) и
прокидку списка в CSP-хелпер.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.constants import DEFAULT_VIDEO_IFRAME_ORIGINS
from app.core.system_config._schemas import SystemSettings, _normalize_video_iframe_origins


class TestNormalizeVideoIframeOrigins:
    def test_default_equals_constant(self):
        """Дефолт схемы = константа (fallback sidecar держат равным bats-тест)."""
        assert SystemSettings().video_iframe_origins == list(DEFAULT_VIDEO_IFRAME_ORIGINS)

    def test_normalizes_case_trailing_slash_path_and_dedupes(self):
        out = _normalize_video_iframe_origins(
            [
                "https://Video.Mage.RU/",
                "https://video.mage.ru/watch?v=1",
                "https://VIDEO.mage.ru",
                "http://video.lan:8080/media/x",
            ]
        )
        assert out == [
            "https://video.mage.ru",
            "http://video.lan:8080",
        ]

    def test_rejects_non_http_scheme(self):
        with pytest.raises(ValueError, match=r"http"):
            _normalize_video_iframe_origins(["ftp://rutube.ru"])

    def test_rejects_wildcards(self):
        with pytest.raises(ValueError, match=r"[Ww]ildcard"):
            _normalize_video_iframe_origins(["https://*.mage.ru"])

    def test_rejects_userinfo(self):
        with pytest.raises(ValueError, match=r"userinfo"):
            _normalize_video_iframe_origins(["https://user:pass@evil.example"])

    def test_rejects_missing_host(self):
        with pytest.raises(ValueError, match=r"host"):
            _normalize_video_iframe_origins(["https://"])

    def test_rejects_empty_entry(self):
        with pytest.raises(ValueError, match=r"[Ee]mpty"):
            _normalize_video_iframe_origins(["  "])

    def test_rejects_more_than_cap(self):
        raw = [f"https://host{i}.example" for i in range(33)]
        with pytest.raises(ValueError, match="32"):
            _normalize_video_iframe_origins(raw)

    def test_empty_list_allowed_disables_embedding(self):
        assert _normalize_video_iframe_origins([]) == []


class TestBuildNginxCspWithSettings:
    def test_custom_origins_replace_defaults(self):
        from app.services.nginx_config import _build_nginx_csp

        csp = _build_nginx_csp("", "", ["https://video.internal:8443"])
        frame_src = csp.split("frame-src ", 1)[1].split(";", 1)[0].split()
        assert frame_src == ["'self'", "https://video.internal:8443"]

    def test_none_uses_default_constant(self):
        from app.services.nginx_config import _build_nginx_csp

        csp = _build_nginx_csp("", "")
        assert " ".join(DEFAULT_VIDEO_IFRAME_ORIGINS) in csp


@pytest.fixture()
def meta_client(monkeypatch):
    """Приложение с learning-роутером и включённым модулем (без БД/аутентификации:
    /learning/meta не требует принципала)."""
    from app.api.deps import require_learning_module
    from app.api.learning import meta_routes

    def _module_ok() -> None:
        return None

    app = FastAPI()
    app.include_router(meta_routes.router, prefix="/api/v1")
    app.dependency_overrides[require_learning_module] = _module_ok
    yield TestClient(app)


class TestLearningMetaEndpoint:
    def test_returns_settings_list(self, meta_client, monkeypatch):
        import app.api.learning.meta_routes as meta

        monkeypatch.setattr(
            meta,
            "load_system_settings",
            lambda: SystemSettings(video_iframe_origins=["https://video.mage.ru"]),
        )
        r = meta_client.get("/api/v1/learning/meta")
        assert r.status_code == 200
        assert r.json() == {"video_iframe_origins": ["https://video.mage.ru"]}

    def test_router_is_module_gated(self):
        """Мета закрыта гейтом модуля: learning выключен → 404 (§8 ТЗ)."""
        from app.api.learning import meta_routes

        deps = [getattr(d, "dependency", None) for d in meta_routes.router.dependencies]
        assert any(getattr(d, "__name__", "") == "require_learning_module" for d in deps)
