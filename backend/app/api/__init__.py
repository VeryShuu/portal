from fastapi import FastAPI


def register_routers(app: FastAPI) -> None:
    """Register all API routers on the application."""
    from app.api.analytics import router as analytics_router
    from app.api.audit import router as audit_router
    from app.api.auth import router as auth_router
    from app.api.bookmarks import router as bookmarks_router
    from app.api.bootstrap import router as bootstrap_router
    from app.api.branding import router as branding_router
    from app.api.files import router as files_router
    from app.api.health import router as health_router
    from app.api.kb import router as kb_router
    from app.api.kb_extra import router as kb_extra_router
    from app.api.keycloak_admin import router as keycloak_admin_router
    from app.api.links import router as links_router
    from app.api.modules import router as modules_router
    from app.api.nc_federation import router as nc_federation_router
    from app.api.news import router as news_router
    from app.api.news_categories import router as news_categories_router
    from app.api.notifications import router as notifications_router
    from app.api.photos import router as photos_router
    from app.api.search import router as search_router
    from app.api.system_settings import router as system_settings_router
    from app.api.user_attribute_mappings import router as user_attribute_mappings_router
    from app.api.users import router as users_router

    app.include_router(health_router)
    app.include_router(nc_federation_router)
    app.include_router(bootstrap_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(users_router, prefix="/api/v1")
    app.include_router(news_router, prefix="/api/v1")
    app.include_router(news_categories_router, prefix="/api/v1")
    app.include_router(links_router, prefix="/api/v1")
    app.include_router(bookmarks_router, prefix="/api/v1")
    app.include_router(branding_router, prefix="/api/v1")
    app.include_router(kb_router, prefix="/api/v1")
    app.include_router(kb_extra_router, prefix="/api/v1")
    app.include_router(search_router, prefix="/api/v1")
    app.include_router(notifications_router, prefix="/api/v1")
    app.include_router(keycloak_admin_router, prefix="/api/v1")
    app.include_router(system_settings_router, prefix="/api/v1")
    app.include_router(modules_router, prefix="/api/v1")
    app.include_router(photos_router, prefix="/api/v1")
    app.include_router(files_router, prefix="/api/v1")
    app.include_router(audit_router, prefix="/api/v1")
    app.include_router(analytics_router, prefix="/api/v1")
    app.include_router(user_attribute_mappings_router, prefix="/api/v1")
