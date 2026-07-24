"""Unit-тесты извлечения тел писем в helpdesk-ingress.

Часть 1 — ``_extract_rfc822``: защита от регрессии бага, при котором
``aioimaplib`` отдаёт FETCH-данные плоским списком ``[bytes, bytearray,
bytes, bytes]``, а ``_extract_rfc822`` искал ``tuple`` (старый формат) →
возвращал ``None`` → ``message_from_bytes`` падал с ``AttributeError`` →
ingress помечал каждое письмо ``errors += 1``, не создавая тикет.

Часть 2 — ``_extract_bodies``: извлечение ``(text/plain, text/html)`` с
отсечением корпоративной подписи автора письма (логотип Mage_Ru.png +
фирменные цвета #7B92AE / #00479D). Регрессия бага 20.07.2026: для писем
``multipart/alternative`` (plain+html копии в одном письме — доминирующий
формат Outlook) подпись отрезалась только из HTML, а ``plain`` уходил в БД
с подписью → попадал в MAX-уведомление о новой заявке. См.
``email_signature.strip_email_signature``.
"""

from __future__ import annotations

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.services.helpdesk.ingress import _extract_bodies, _extract_rfc822

# Реалистичный ответ aioimaplib для FETCH (RFC822): плоский список.
_AIOIMAPLIB_RESPONSE = [
    b"1 FETCH (RFC822 {11}",
    bytearray(b"hello world"),
    b")",
    b"Fetch completed (0.001 secs).",
]


def test_extract_from_flat_aioimaplib_response() -> None:
    """Основной кейс: aioimaplib отдаёт плоский список с bytearray-телом."""
    assert _extract_rfc822(_AIOIMAPLIB_RESPONSE) == b"hello world"


def test_extract_picks_longest_bytes_element() -> None:
    """Среди нескольких bytes-элементов выбирается самый длинный (тело)."""
    data = [b"1 FETCH (RFC822 {5}", bytearray(b"BODY!"), b")", b"OK"]
    assert _extract_rfc822(data) == b"BODY!"


def test_extract_from_tuple_format_legacy() -> None:
    """Совместимость со старым tuple-форматом (вдруг кто-то его отдаёт)."""
    data = [(b"1 FETCH (RFC822 {5}", bytearray(b"BODY!"))]
    assert _extract_rfc822(data) == b"BODY!"


def test_extract_from_mixed_tuple_and_flat() -> None:
    # Плоская часть с литералом имеет приоритет; тело — элемент после маркера.
    data = [b"marker", b"1 FETCH (RFC822 {22}", b"FULL RFC822 BODY HERE", b")"]
    out = _extract_rfc822(data)
    assert out == b"FULL RFC822 BODY HERE"


def test_extract_returns_none_on_empty() -> None:
    assert _extract_rfc822([]) is None


def test_extract_returns_none_when_no_bytes() -> None:
    assert _extract_rfc822([None, 42, "str"]) is None


def test_extract_handles_bytes_and_bytearray() -> None:
    """Тело может прийти и как bytes, и как bytearray (варианты aioimaplib)."""
    assert _extract_rfc822([b"1 FETCH (RFC822 {5}", b"BODY!", b")"]) == b"BODY!"
    assert _extract_rfc822([b"1 FETCH (RFC822 {5}", bytearray(b"BODY!"), b")"]) == b"BODY!"


# ──────────────────────────────────────────────────────────────────────────────
# _extract_bodies — извлечение (text/plain, text/html) с отсечением подписи.
# ──────────────────────────────────────────────────────────────────────────────

# Реальный HTML подписи (упрощённый) — маркер Mage_Ru.png как в
# test_helpdesk_email_signature.py. Полный образец там; здесь — минимально
# достаточный для срабатывания strip_email_signature по logo-маркеру.
_SIG_HTML = (
    "<p>Тело письма</p>"
    '<table><tr><td><img src="https://mage.ru/sign/Mage_Ru.png"></td>'
    "<td><b>Вячеслав Борзихин</b><br>+7 (8152) 400 580<br>"
    '<a href="mailto:borzihin.vs@mage.ru">borzihin.vs@mage.ru</a></td></tr></table>'
)

# Plain-копия той же подписи (без HTML-маркеров — только строки).
_SIG_PLAIN = (
    "Тело письма\n"
    "\n"
    "Вячеслав Борзихин\n"
    "Руководитель отдела ИТ\n"
    "+7 (8152) 400 580\n"
    "borzihin.vs@mage.ru"
)

# Уникальные маркеры подписи (любой из них в выводе = подпись утекла).
_SIG_MARKERS = (
    "Вячеслав Борзихин",
    "Руководитель отдела ИТ",
    "+7 (8152) 400 580",
    "borzihin.vs@mage.ru",
    "Mage_Ru.png",
)


def _multipart_alternative(plain: str, html: str) -> MIMEMultipart:
    """Собрать ``multipart/alternative`` письмо (стандартный формат Outlook)."""
    msg = MIMEMultipart("alternative")
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))
    return msg


class TestExtractBodiesSignatureStripping:
    """Регрессия бага 20.07.2026: подпись должна отрезаться из **обоих** тел,
    а не только из HTML. ``plain`` для ``multipart/alternative`` раньше уходил
    в БД с подписью → попадал в MAX-уведомление о новой заявке."""

    def test_multipart_alternative_strips_signature_from_plain(self) -> None:
        """multipart/alternative (plain+html) → оба тела без подписи.

        До фикса: ``plain`` возвращался оригинальным (с подписью), потому что
        ``strip_email_signature`` применялся только к ``html``, а деривация
        ``plain`` из HTML выполнялась только когда ``plain`` был пустой.
        """
        msg = _multipart_alternative(_SIG_PLAIN, _SIG_HTML)
        plain, html = _extract_bodies(msg)
        assert html is not None  # multipart/alternative гарантированно даёт html
        # Тело сохраняется в обоих.
        assert "Тело письма" in plain
        assert "Тело письма" in html
        # Подпись отрезана из ОБИХ тел (главный ассерт регрессии).
        for marker in _SIG_MARKERS:
            assert marker not in plain, f"подпись утекла в plain: {marker!r}"
            assert marker not in html, f"подпись утекла в html: {marker!r}"

    def test_multipart_alternative_without_signature_preserved(self) -> None:
        """Контроль: multipart/alternative без подписи → оба тела сохраняются."""
        msg = _multipart_alternative(
            "Просто текст без подписи.",
            "<p>Просто текст без подписи.</p>",
        )
        plain, html = _extract_bodies(msg)
        assert html is not None  # multipart/alternative → html присутствует
        assert "Просто текст без подписи." in plain
        assert "Просто текст без подписи." in html

    def test_html_only_with_signature(self) -> None:
        """Письмо text/html без plain-копии — подпись режется из HTML,
        plain деривируется из уже очищенного HTML."""
        msg = MIMEText(_SIG_HTML, "html", "utf-8")
        plain, html = _extract_bodies(msg)
        assert html is not None  # text/html-письмо → html присутствует
        assert "Тело письма" in plain
        assert "Тело письма" in html
        for marker in _SIG_MARKERS:
            assert marker not in plain
            assert marker not in html

    def test_plain_only_no_html_markers(self) -> None:
        """Письмо text/plain без html → без изменений (нет html-маркеров)."""
        body = "Простое письмо без HTML и без подписи."
        msg = MIMEText(body, "plain", "utf-8")
        plain, html = _extract_bodies(msg)
        assert plain == body
        assert html is None

    def test_empty_both_returns_placeholder(self) -> None:
        """Оба тела пусты → плейсхолдер ``"(пустое сообщение)"``, html=None.

        Покрывает edge-case: письмо только с вложениями, без text-частей.
        """
        msg = MIMEMultipart("alternative")
        # Никаких text/plain и text/html частей.
        plain, html = _extract_bodies(msg)
        assert plain == "(пустое сообщение)"
        assert html is None

    def test_real_outlook_multipart_alternative(self) -> None:
        """Регрессионный кейс: реальный образец Outlook HTML из баг-репорта
        (см. ``test_helpdesk_email_signature.REAL_OUTLOOK_HTML``), упакованный
        в multipart/alternative с plain-копией подписи — подпись должна быть
        отрезана из обоих тел.
        """
        # Сокращённый реальный HTML подписи из баг-репорта 20.07.2026.
        real_html = (
            "<p class=MsoNormal>Test oe <o:p></o:p></p>"
            "<table class=MsoNormalTable border=0 cellspacing=0 cellpadding=0><tr>"
            "<td valign=top style='border:none;border-right:solid #7B92AE 1.0pt;"
            "padding:0cm 5.25pt 0cm 0cm'>"
            '<p class=MsoNormal style="margin:.1pt">'
            '<a href="http://mage.ru/"><span style="color:blue;text-decoration:none">'
            '<img border=0 width=60 height=48 id="_x0000_i1025" '
            'src="http://mage.ru/signature/images/Mage_Ru.png"></span></a>'
            "</p></td>"
            '<td style="padding:0cm 0cm 0cm 9.0pt">'
            "<table class=MsoNormalTable border=0 cellspacing=0 cellpadding=0 width=400>"
            "<tr><td><p><b><span style='font-size:10.5pt;font-family:Arial;"
            "color:#00479D'>Вячеслав Борзихин</span></b></p></td></tr>"
            "</table></td></tr></table>"
        )
        # Outlook-генерируемая plain-копия.
        real_plain = (
            "Test oe\n"
            "\n"
            "Вячеслав Борзихин\n"
            "Руководитель отдела ИТ\n"
            "+7 (8152) 400 580\n"
            "borzihin.vs@mage.ru"
        )
        msg = _multipart_alternative(real_plain, real_html)
        plain, html = _extract_bodies(msg)
        assert html is not None  # multipart/alternative → html присутствует
        assert "Test oe" in plain
        assert "Test oe" in html
        # Подпись отсутствует в обоих телах.
        assert "Вячеслав Борзихин" not in plain
        assert "Вячеслав Борзихин" not in html
        assert "Mage_Ru.png" not in html
        assert "borzihin.vs@mage.ru" not in plain
