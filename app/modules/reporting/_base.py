# app/modules/reporting/_base.py
"""Shared PDF, HTML, and CSV rendering utilities for the reporting module.

render_html(template_name, context) -> str
    Renders a Jinja2 HTML template to a string. Templates live in
    app/modules/reporting/templates/<template_name>.

render_pdf(template_name, context) -> bytes
    Renders the same template with WeasyPrint (via render_html).

render_csv(headers, rows) -> bytes
    Renders a list of rows as UTF-8 CSV bytes using Python stdlib csv.
    Returns bytes with BOM so Excel opens it without encoding prompts.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def render_html(template_name: str, context: dict[str, Any]) -> str:
    """Render a Jinja2 HTML template to a string.

    Used directly for format=html previews and by render_pdf.

    Args:
        template_name: Filename inside app/modules/reporting/templates/
                       e.g. "trial_balance.html"
        context: Dict passed to template.render(**context)

    Returns:
        Rendered HTML string.
    """
    import jinja2  # noqa: PLC0415 — optional dep, imported lazily

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=True,
    )
    template = env.get_template(template_name)
    return template.render(**context)


def render_pdf(template_name: str, context: dict[str, Any]) -> bytes:
    """Render a Jinja2 HTML template to PDF bytes via WeasyPrint."""
    import weasyprint  # noqa: PLC0415 — optional dep, imported lazily

    pdf_bytes: bytes = weasyprint.HTML(
        string=render_html(template_name, context)
    ).write_pdf()
    return pdf_bytes


def render_csv(headers: list[str], rows: list[list[Any]]) -> bytes:
    """Render headers + rows as UTF-8-BOM CSV bytes.

    Args:
        headers: Column header strings, e.g. ["Account Code", "Account Name", ...]
        rows: List of rows; each row is a list of values (str/Decimal/int/date).

    Returns:
        UTF-8 BOM-prefixed CSV bytes. BOM makes Excel auto-detect UTF-8.
    """
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    for row in rows:
        writer.writerow([str(v) if v is not None else "" for v in row])
    return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")
