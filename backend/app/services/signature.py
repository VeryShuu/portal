"""Email-signature renderer (docs/wip/signature.md).

Pure, stateless rendering of an HTML email signature from form input. Ported
from the legacy PHP service ``./sign``: the 16 PHP templates collapse into four
device layouts (PC/Apple/Web share a table layout, Phone is a text layout),
parameterised by language and the presence of a mobile phone.

HTML is escaped via :func:`html.escape` (the direct equivalent of the original
``htmlspecialchars``) — no template engine dependency is added.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape

from app.schemas.signature import (
    Device,
    Language,
    SignatureGenerateRequest,
    SignatureGenerateResponse,
    SignatureSettings,
)


@dataclass(frozen=True)
class _Logo:
    filename: str
    width: int
    height: int


# device → (ru logo, eng logo) | None (Phone has no logo).
_LOGO_SPEC: dict[Device, tuple[_Logo, _Logo] | None] = {
    "PC": (_Logo("Mage_Ru.png", 60, 48), _Logo("Mage_Eng.png", 60, 48)),
    "Apple": (_Logo("Mage_Ru.png", 60, 48), _Logo("Mage_Eng.png", 60, 48)),
    "Web": (_Logo("WebRu.png", 68, 125), _Logo("WebEng.png", 68, 125)),
    "Phone": None,
}

# (device, language) → filename suffix (without the ".htm" extension).
_FILE_SUFFIX: dict[tuple[Device, Language], str] = {
    ("PC", "Ru"): "_Ru",
    ("PC", "Eng"): "_Eng",
    ("Web", "Ru"): "_Ru",
    ("Web", "Eng"): "_Eng",
    ("Apple", "Ru"): "_AppleRu",
    ("Apple", "Eng"): "_AppleEng",
    ("Phone", "Ru"): "_AndroidRu",
    ("Phone", "Eng"): "_AndroidEng",
}


def _city_suffix(req: SignatureGenerateRequest, settings: SignatureSettings) -> str:
    for city in settings.cities:
        if city.id == req.city_id:
            return city.suffix_ru if req.language == "Ru" else city.suffix_eng
    return ""


def _phone_line(req: SignatureGenerateRequest) -> str:
    """``+7 (...) / 123`` — mirrors the original ``phone + " / " + dob``."""
    if not req.office_phone:
        return ""
    if req.extension:
        return f"{req.office_phone} / {req.extension}"
    return req.office_phone


def _filename(req: SignatureGenerateRequest) -> str:
    suffix = _FILE_SUFFIX[(req.device, req.language)]
    return f"{req.name}{req.surname}{suffix}.htm"


_GRAY_TD = (
    "width:400px; padding-bottom: 5px; color: #9e9e9e; font-size: 12px; "
    "font-family: Arial, Helvetica, sans-serif; line-height: 15px; "
    "-webkit-text-size-adjust:none; display: block;"
)
_NAME_TD = (
    "width: 400px; padding-bottom: 5px; color: #00479D; font-size: 14px; "
    "font-family: Arial, Helvetica, sans-serif; font-weight: bold; line-height: 15px; "
    "-webkit-text-size-adjust:none; display: block;"
)
_EMAIL_TD = (
    "width:400px; padding-bottom: 2px; color: #9e9e9e; font-size: 12px; "
    "font-family: Arial, Helvetica, sans-serif; line-height: 15px; "
    "-webkit-text-size-adjust:none; display: block;"
)
_LOGO_TD = (
    "padding-top: 0; padding-bottom: 0; padding-left: 0; padding-right: 7px; "
    "border-top: 0; border-bottom: 0; border-left: 0; border-right: solid 1px #7B92AE"
)
_OUTER_TABLE = "background: none; border-width: 0px; border: 0px; margin: 0; padding: 0;"
_INNER_TABLE = (
    "background: none; border-width: 0px; border: 0px; margin: 0; padding: 0; width: 400px; "
)
_P_RESET = "margin-top: 0.1px; margin-bottom:0.1px; margin-left:0.1px; margin-right:0.1px;"


def _img_style(w: int, h: int) -> str:
    return (
        f"display: block; border: none; width: {w}px; max-width: {w}px !important; "
        f"height: {h}px; max-height: {h}px !important;"
    )


def _render_table(
    req: SignatureGenerateRequest,
    settings: SignatureSettings,
    logos: tuple[_Logo, _Logo],
) -> str:
    """PC / Apple / Web layout (table with logo)."""
    logo = logos[0] if req.language == "Ru" else logos[1]
    logo_url = settings.logo_base_url.rstrip("/") + "/" + logo.filename
    lang_attr = "ru" if req.language == "Ru" else "en"

    full_name = escape(f"{req.name} {req.surname}")
    position = escape(req.position) + escape(_city_suffix(req, settings))
    phone = escape(_phone_line(req))
    email = escape(req.email)
    company_url = escape(settings.company_url)

    def _row(td_style: str, inner: str) -> str:
        return f'<tr><td colspan="2" style="{td_style}"><p style="{_P_RESET}">{inner}</p></td></tr>'

    rows = [
        _row(_NAME_TD, full_name),
        _row(_GRAY_TD, position),
        _row(_GRAY_TD, phone),
    ]
    if req.mobile_phone:
        rows.append(_row(_GRAY_TD, escape(req.mobile_phone)))
    mail_link = (
        f'<a href="mailto:{email}" style="text-decoration: none; color: #9e9e9e;">{email}</a>'
    )
    rows.append(_row(_EMAIL_TD, mail_link))
    inner_rows = "\n".join(rows)

    img = (
        f'<img id="preview-image-url" width="{logo.width}" height="{logo.height}" '
        f'style="{_img_style(logo.width, logo.height)}" alt="" src="{escape(logo_url)}">'
    )

    return f"""<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0 Transitional//EN">
<html lang="{lang_attr}">
<head>
    <meta charset="UTF-8">
    <title>Готовая подпись</title>
</head>
<body style="width: 400px; height: 300px;">
<table cellpadding="0" cellspacing="0" border="0" style="{_OUTER_TABLE}">
<tbody>
    <tr>
        <td valign="top" style="{_LOGO_TD}">
            <p style="{_P_RESET}">
            <a href="{company_url}" style="text-decoration: none;">
            {img}</a></p>
        </td>
        <td style="padding-top: 0; padding-bottom: 0; padding-left: 12px; padding-right: 0;">
            <table cellpadding="0" cellspacing="0" border="0" style="{_INNER_TABLE}">
                <tbody>
{inner_rows}
                </tbody>
            </table>
        </td>
    </tr>
</tbody>
</table>
</body>
</html>
"""


def _render_phone(req: SignatureGenerateRequest, settings: SignatureSettings) -> str:
    """Phone (Android) layout — plain text spans, no logo, ends with site line."""
    full_name = escape(f"{req.name} {req.surname}")
    position = escape(req.position) + escape(_city_suffix(req, settings))
    phone = escape(_phone_line(req))
    email = escape(req.email)

    lines = [
        f"<span>{full_name}</span><br>",
        f"<span>{position}</span><br>",
        f"<span>{phone}</span><br>",
    ]
    if req.mobile_phone:
        lines.append(f"<span>{escape(req.mobile_phone)}</span><br>")
    lines.append(f"<span>{email}</span><br>")
    lines.append("<span>www.mage.ru</span>")
    body = "\n".join(lines)

    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="UTF-8">
    <title>Готовая подпись</title>
</head>
{body}
</html>
"""


def render_signature(
    req: SignatureGenerateRequest,
    settings: SignatureSettings,
) -> SignatureGenerateResponse:
    logos = _LOGO_SPEC[req.device]
    html = _render_phone(req, settings) if logos is None else _render_table(req, settings, logos)
    return SignatureGenerateResponse(html=html, filename=_filename(req))
