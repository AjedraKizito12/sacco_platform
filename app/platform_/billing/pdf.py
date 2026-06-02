"""WeasyPrint-backed invoice PDF rendering.

`render_invoice_pdf` is pure — takes ORM objects, returns bytes. No I/O
beyond reading the bundled template. Callers (the API endpoint) are
responsible for setting Content-Type, Content-Disposition, etc.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape

if TYPE_CHECKING:
    from app.platform_.billing.models import Invoice, InvoiceLineItem

_log = structlog.get_logger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_env = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIR),
    autoescape=select_autoescape(["html", "xml"]),
)


def render_invoice_pdf(
    invoice: Invoice, line_items: list[InvoiceLineItem]
) -> bytes:
    """Render an invoice + its line items to a PDF byte string."""
    from weasyprint import HTML  # noqa: PLC0415  — heavy import, lazy load

    template = _env.get_template("invoice.html")
    html_str = template.render(
        invoice=invoice,
        line_items=line_items,
        now_iso=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
    )
    pdf_bytes: bytes = HTML(string=html_str).write_pdf()
    _log.info(
        "invoice.pdf_rendered",
        invoice_id=str(invoice.id),
        invoice_number=invoice.invoice_number,
        size_bytes=len(pdf_bytes),
    )
    return pdf_bytes
