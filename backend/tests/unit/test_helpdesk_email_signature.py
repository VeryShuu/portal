"""Тесты отсечения корпоративной email-подписи (``strip_email_signature``).

Образец реального письма Outlook от 20.07.2026 — HTML из баг-репорта пользователя
(Word-формат с ``mso-`` стилями, ``<o:p>&nbsp;</o:p>``, ``xmlns:``). Проверяем
что подпись отрезается полностью, а тело письма сохраняется.
"""

from __future__ import annotations

from app.services.helpdesk.email_signature import strip_email_signature

# Реальный HTML письма из баг-репорта (Outlook + Word-рендер).
# Сокращён до значимой части: пустые абзацы + подпись с логотипом Mage_Ru.png
# и фирменными цветами. Тело письма «Test oe» идёт перед подписью.
REAL_OUTLOOK_HTML = (
    # Тело письма — сохраняется.
    "<p class=MsoNormal>Test oe <o:p></o:p></p>"
    # Подпись Outlook (из вопроса пользователя).
    "<table class=MsoNormalTable border=0 cellspacing=0 cellpadding=0>"
    "<tr>"
    # Ячейка с логотипом (маркер #1: Mage_Ru.png + маркер #2: border #7B92AE).
    "<td valign=top style='border:none;border-right:solid #7B92AE 1.0pt;padding:0cm 5.25pt 0cm 0cm'>"
    "<p class=MsoNormal style='margin:.1pt'>"
    "<a href=\"http://mage.ru/\"><span style='color:blue;text-decoration:none'>"
    '<img border=0 width=60 height=48 id="_x0000_i1025" src="http://mage.ru/signature/images/Mage_Ru.png">'
    "</span></a>"
    "</p></td>"
    # Ячейка с ФИО/телефонами/email (маркер #3: color #00479D, маркер #4: mailto @mage.ru).
    "<td style='padding:0cm 0cm 0cm 9.0pt'>"
    "<table class=MsoNormalTable border=0 cellspacing=0 cellpadding=0 width=400>"
    "<tr><td><p><b><span style='font-size:10.5pt;font-family:Arial;color:#00479D'>Вячеслав Борзихин</span></b></p></td></tr>"
    "<tr><td><p><span style='font-size:9.0pt;font-family:Arial;color:#9E9E9E'>Руководитель отдела ИТ</span></p></td></tr>"
    "<tr><td><p><span style='font-size:9.0pt;font-family:Arial;color:#9E9E9E'>+7 (8152) 400 580</span></p></td></tr>"
    "<tr><td><p><span style='font-size:9.0pt;font-family:Arial;color:#9E9E9E'>+7 (911) 344 6882</span></p></td></tr>"
    "<tr><td><p><span style='font-size:9.0pt;font-family:Arial;color:#9E9E9E'>"
    "<a href=\"mailto:borzihin.vs@mage.ru\"><span style='color:#9E9E9E'>borzihin.vs@mage.ru</span></a>"
    "</span></p></td></tr>"
    "</table></td>"
    "</tr></table>"
)


class TestStripEmailSignature:
    """``strip_email_signature`` — отсечение корпоративной подписи из HTML."""

    def test_strips_signature_from_real_outlook_email(self):
        """Образец из баг-репорта: подпись отрезается, тело сохраняется."""
        result = strip_email_signature(REAL_OUTLOOK_HTML)
        # Тело письма сохраняется.
        assert "Test oe" in result
        # Подпись полностью отрезана (логотип, ФИО, телефоны, email).
        assert "Mage_Ru.png" not in result
        assert "Вячеслав Борзихин" not in result
        assert "Руководитель отдела" not in result
        assert "+7 (8152)" not in result
        assert "+7 (911)" not in result
        assert "borzihin.vs@mage.ru" not in result

    def test_returns_none_for_none(self):
        assert strip_email_signature(None) is None

    def test_returns_empty_for_empty(self):
        assert strip_email_signature("") == ""

    def test_no_signature_returns_html_unchanged(self):
        """Письмо без подписи (нет ни одного маркера) → без изменений."""
        html = "<p>Просто текст письма без подписи.</p>"
        assert strip_email_signature(html) == html

    def test_does_not_strip_logo_outside_signature_container(self):
        """Одиночная картинка логотипа в тексте не считается подписью."""
        html = (
            "<p>Тело письма</p>"
            '<p><img src="https://example.com/signature/Mage_Ru.png"></p>'
            "<p>Подпись хвост</p>"
        )
        assert strip_email_signature(html) == html

    def test_does_not_strip_by_border_color_alone(self):
        """Одиночный border недостаточен: таблица может быть частью заявки."""
        html = (
            "<p>Тело</p>"
            "<table><tr><td style='border-right:solid #7B92AE 1.0pt'>логотип</td>"
            "<td>ФИО и телефоны</td></tr></table>"
        )
        assert strip_email_signature(html) == html

    def test_does_not_strip_by_blue_color_alone(self):
        """Фирменный цвет может легитимно использоваться в теле письма."""
        html = (
            "<p>Тело письма</p><p><span style='color:#00479D'>Иван Иванов</span></p><p>+7 ...</p>"
        )
        assert strip_email_signature(html) == html

    def test_does_not_strip_legitimate_corporate_mailto(self):
        """Ссылка на коллегу внутри заявки не должна удалять последующий текст."""
        html = (
            '<p>Напишите <a href="mailto:user@mage.ru">user@mage.ru</a>.</p>'
            "<p>Ошибка возникает после входа.</p>"
        )
        assert strip_email_signature(html) == html

    def test_removes_signature_node_but_preserves_following_forward(self):
        """Подпись перед forward удаляется структурно, а не вместе с хвостом."""
        html = (
            "<p>Смотрите пересланное письмо.</p>"
            "<table><tr><td style='border-right:solid 1px #7B92AE'>"
            '<img src="Mage_Ru.png"></td>'
            "<td style='color:#00479D'>Иван Иванов "
            '<a href="mailto:ivan@mage.ru">ivan@mage.ru</a></td></tr></table>'
            "<div>-----Original Message-----</div>"
            "<p>Критичная ошибка: quota exceeded</p>"
        )
        result = strip_email_signature(html)
        assert "Иван Иванов" not in result
        assert "Mage_Ru.png" not in result
        assert "-----Original Message-----" in result
        assert "quota exceeded" in result

    def test_removes_explicit_phone_signature_wrapper(self):
        html = (
            "<p>Тело заявки.</p>"
            '<div data-portal-email-signature="mage-v1">'
            "<span>Иван Иванов</span><br><span>ivan@mage.ru</span><br>"
            "<span>www.mage.ru</span></div>"
        )
        result = strip_email_signature(html)
        assert "Тело заявки" in result
        assert "Иван Иванов" not in result
        assert "www.mage.ru" not in result

    def test_case_insensitive_markers(self):
        """Маркеры ищутся case-insensitive (``mage_ru.PNG`` / ``#7b92ae``)."""
        html = '<p>Body</p><table><tr><td><img src="https://x/y/MAGE_RU.PNG"></td></tr></table>'
        result = strip_email_signature(html)
        assert "Body" in result
        assert "MAGE_RU.PNG" not in result

    def test_logo_with_any_path(self):
        """Логотип может лежать в любом пути — режем по имени файла."""
        html = '<p>Body</p><table><tr><td><img src="/some/deep/path/Mage_Ru.png"></td></tr></table>'
        result = strip_email_signature(html)
        assert "Body" in result
        assert "Mage_Ru.png" not in result

    def test_cid_logo_uses_mime_filename(self):
        """Outlook moves the known asset name from HTML src into MIME metadata."""
        html = (
            "<p>Body</p><table><tr><td><img src='cid:image001@outlook'></td>"
            "<td>Signature text</td></tr></table>"
        )

        result = strip_email_signature(
            html,
            cid_names={"image001@outlook": ("image001.png", "https://mage.ru/Mage_Ru.png")},
        )

        assert result == "<p>Body</p>"

    def test_legacy_style_variants_are_recognized_together(self):
        html = (
            "<p>Body</p><table><tr>"
            "<td style='border-right:1px solid #7B92AE'>logo</td>"
            "<td><span style='color:rgb(0, 71, 157)'>Name</span>"
            "<a href='mailto:user@mage.ru?subject=hello'>user@mage.ru</a></td>"
            "</tr></table>"
        )

        assert strip_email_signature(html) == "<p>Body</p>"

    def test_idempotent_no_signature(self):
        """Письмо без подписи: повторный вызов ничего не ломает."""
        html = "<p>Обычное письмо.</p>"
        once = strip_email_signature(html)
        twice = strip_email_signature(once)
        assert once == twice == html

    def test_preserves_text_before_signature(self):
        """Текст письма ДО подписи сохраняется полностью (включая несколько абзацев)."""
        html = (
            "<p>Первый абзац письма.</p>"
            "<p>Второй абзац с подробностями.</p>"
            "<p>Третий абзац.</p>"
            '<table><tr><td><img src="Mage_Ru.png"></td></tr></table>'  # подпись
        )
        result = strip_email_signature(html)
        assert "Первый абзац письма." in result
        assert "Второй абзац с подробностями." in result
        assert "Третий абзац." in result
        assert "Mage_Ru.png" not in result

    def test_does_not_strip_external_email(self):
        """Письмо от внешнего отправителя (не mage.ru, без наших маркеров)
        — не трогаем."""
        html = "<p>Здравствуйте!</p><p>С уважением, Иван</p><p>ivan@gmail.com</p>"
        result = strip_email_signature(html)
        assert result == html

    def test_removes_signature_container_and_preserves_later_content(self):
        """Удаляется только signature-table, а последующий контекст сохраняется."""
        html = (
            '<p>Тело</p><table><tr><td><img src="Mage_Ru.png"></td></tr></table><p>Что-то ещё</p>'
        )
        result = strip_email_signature(html)
        assert "Тело" in result
        assert "Mage_Ru.png" not in result
        assert "Что-то ещё" in result

    def test_portal_svc_mailto_alone_is_preserved(self):
        """Даже service-account mailto без контейнера не является подписью."""
        html = '<p>Системное письмо</p><a href="mailto:portal-svc@mage.ru">portal-svc@mage.ru</a>'
        assert strip_email_signature(html) == html

    def test_min_position_when_high_priority_marker_is_later(self):
        """Вся таблица удаляется, даже если BLUE расположен раньше LOGO."""
        html = (
            "<p>Тело письма.</p>"
            "<table><tr>"
            "<td><span style='color:#00479D'>ФИО подписи</span></td>"  # BLUE раньше
            "</tr><tr>"
            "<td><img src='Mage_Ru.png'></td>"  # LOGO позже
            "</tr></table>"
        )
        result = strip_email_signature(html)
        # Удаляется структурный table-контейнер целиком.
        assert "ФИО подписи" not in result
        assert "Mage_Ru.png" not in result
        assert "Тело письма." in result

    def test_all_markers_in_signature_cut_at_earliest(self):
        """Легитимный mailto до signature-table не удаляется вместе с ней."""
        html = (
            "<p>Тело.</p>"
            '<a href="mailto:first@mage.ru">first</a>'  # MAILTO @ рано
            "<table><tr><td style='border-right:solid #7B92AE 1.0pt'>"  # BORDER
            "<span style='color:#00479D'>ФИО</span></td></tr>"  # BLUE
            "<tr><td><img src='Mage_Ru.png'></td></tr></table>"  # LOGO
        )
        result = strip_email_signature(html)
        assert "Тело." in result
        # Одиночный mailto перед signature-table — легитимный текст, сохраняется.
        assert "first@mage.ru" in result
        assert "#7B92AE" not in result
        assert "#00479D" not in result
        assert "Mage_Ru.png" not in result
