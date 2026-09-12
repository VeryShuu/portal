"""HTML rendering for KB article PDF export."""

from __future__ import annotations

from app.models.kb import KbArticle

from ._kb_media import inline_kb_media_as_data_uris


def render_article_html_for_pdf(article: KbArticle) -> str:
    """Render a KB article body to a self-contained HTML document for PDF export."""
    import markdown_it

    md = markdown_it.MarkdownIt()
    body_html = md.render(article.body or "")
    body_html = inline_kb_media_as_data_uris(body_html)
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
  body {{ font-family: Arial, sans-serif; margin: 0; padding: 0; color: #1a1a2e; }}
  h1 {{ font-size: 24px; margin-bottom: 8px; }}
  h2 {{ font-size: 18px; }}
  h3 {{ font-size: 16px; }}
  code {{ background: #f4f4f4; padding: 2px 4px; border-radius: 3px; font-size: 13px; }}
  pre {{ background: #f4f4f4; padding: 12px; border-radius: 4px; overflow-x: auto; }}
  blockquote {{ border-left: 3px solid #ccc; margin: 0; padding-left: 16px; color: #555; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
  img {{ max-width: 100%; height: auto; }}
</style></head><body>
<h1>{article.title}</h1>
{body_html}
</body></html>"""
