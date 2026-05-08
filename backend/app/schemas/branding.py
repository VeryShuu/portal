"""Pydantic schemas for the branding / email-settings API.

Extracted from ``app.api.branding`` so that handlers stay thin and schemas can
be reused by other modules (for example the bootstrap aggregator) without
pulling in router dependencies.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class BrandingSettings(BaseModel):
    portal_name: str = "Корпоративный портал"
    portal_tagline: str = ""
    accent_color: str = "#d8262c"
    welcome_subtitle: str = ""
    banner_enabled: bool = False
    banner_text: str = ""
    banner_type: Literal["info", "warning", "error", "success"] = "info"
    banner_expires_at: str | None = None


class BrandingSettingsOut(BrandingSettings):
    has_favicon: bool = False
    has_login_bg: bool = False
    has_logo: bool = False
    logo_updated_at: str | None = None
    allowed_iframe_origins: list[str] = []


class EmailSettings(BaseModel):
    host: str = Field(default="")
    port: int = Field(default=25, ge=1, le=65535)
    from_address: str = Field(default="")
    username: str = Field(default="")
    password: str = Field(default="", description="Masked as '***' in GET response if set")
    use_tls: bool = Field(default=False)
    use_starttls: bool = Field(default=False)


class EmailSettingsIn(BaseModel):
    host: str = Field(default="")
    port: int = Field(default=25, ge=1, le=65535)
    from_address: str = Field(default="")
    username: str = Field(default="")
    password: str | None = Field(
        default=None,
        description=(
            "Pass null or '***' to keep existing password; "
            "pass '' to clear; pass new value to update"
        ),
    )
    use_tls: bool = Field(default=False)
    use_starttls: bool = Field(default=False)


class EmailSettingsOut(BaseModel):
    host: str
    port: int
    from_address: str
    username: str
    password_set: bool
    use_tls: bool
    use_starttls: bool


class EmailTestRequest(BaseModel):
    to: str = Field(description="Email address to send test message to")
