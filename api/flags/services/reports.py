"""PDF flag report generation using ReportLab.

WeasyPrint was attempted first but requires libgobject-2.0 which is not present
in the api Docker image. ReportLab has zero system-library dependencies and
produces comparable output.

Public API:
    generate_flag_report(flag_ids, user) -> bytes   — returns PDF bytes
"""

from __future__ import annotations

import io
import logging
from datetime import datetime, timezone as dt_tz
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from accounts.models import User

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Colour palette — Stripe-ish: clean, minimal chrome
# ---------------------------------------------------------------------------

_COLOURS = {
    "critical": (0.82, 0.10, 0.10),   # red
    "high":     (0.90, 0.45, 0.05),   # orange
    "medium":   (0.85, 0.65, 0.00),   # amber
    "low":      (0.13, 0.60, 0.25),   # green
}
_TEXT_ON_COLOUR = {
    "critical": (1, 1, 1),
    "high":     (1, 1, 1),
    "medium":   (0, 0, 0),
    "low":      (1, 1, 1),
}
_PAGE_BG      = (1, 1, 1)
_BORDER       = (0.88, 0.88, 0.88)
_HEADER_BG    = (0.10, 0.27, 0.49)   # RHA navy
_HEADER_FG    = (1, 1, 1)
_BODY_TEXT    = (0.12, 0.12, 0.12)
_MUTED        = (0.50, 0.50, 0.50)
_DRAFT_COLOUR = (0.88, 0.88, 0.88)

APP_VERSION = "0.5.0-demo"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _rgb(*args):
    """Convert 0–1 floats to a reportlab Color."""
    from reportlab.lib.colors import Color
    return Color(*args)


def _draw_severity_badge(canvas, x: float, y: float, severity: str, w: float = 70, h: float = 16):
    """Draw a coloured rounded-rect badge with severity label."""
    from reportlab.lib.colors import Color
    fg = _COLOURS.get(severity, (0.5, 0.5, 0.5))
    txt = _TEXT_ON_COLOUR.get(severity, (1, 1, 1))
    canvas.setFillColor(Color(*fg))
    canvas.roundRect(x, y, w, h, radius=3, fill=1, stroke=0)
    canvas.setFillColor(Color(*txt))
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawCentredString(x + w / 2, y + 4, severity.upper())


def _draw_rule(canvas, x: float, y: float, width: float, thickness: float = 0.5):
    from reportlab.lib.colors import Color
    canvas.setStrokeColor(Color(*_BORDER))
    canvas.setLineWidth(thickness)
    canvas.line(x, y, x + width, y)


def _label_value(canvas, label: str, value: str, x: float, y: float, col_w: float = 150):
    from reportlab.lib.colors import Color
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(Color(*_MUTED))
    canvas.drawString(x, y + 10, label.upper())
    canvas.setFont("Helvetica", 9)
    canvas.setFillColor(Color(*_BODY_TEXT))
    canvas.drawString(x, y, value or "—")


def _draw_draft_watermark(canvas, page_w: float, page_h: float, text: str = "DRAFT"):
    from reportlab.lib.colors import Color
    canvas.saveState()
    canvas.setFont("Helvetica-Bold", 72)
    canvas.setFillColor(Color(*_DRAFT_COLOUR))
    canvas.translate(page_w / 2, page_h / 2)
    canvas.rotate(45)
    canvas.drawCentredString(0, 0, text)
    canvas.restoreState()


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------


def generate_flag_report(flag_ids: list[str | int], user) -> bytes:
    """Render a PDF report for the given flag IDs.

    Args:
        flag_ids: List of Flag PKs to include.
        user: The requesting User (for audit + report metadata).

    Returns:
        PDF bytes ready to send or save.
    """
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.colors import Color
    from reportlab.lib.units import mm, cm
    from flags.models import Flag, FlagStatus

    flags = list(
        Flag.objects.filter(pk__in=flag_ids)
        .select_related("detection__parcel", "detection__job__t1_scene__aoi", "assigned_to")
        .prefetch_related("detection__parcel__permits")
        .order_by("severity", "pk")
    )

    if not flags:
        raise ValueError(f"No flags found for IDs: {flag_ids}")

    buf = io.BytesIO()
    page_w, page_h = A4
    margin = 2 * cm
    content_w = page_w - 2 * margin

    report_id = f"RPT-{datetime.now(tz=dt_tz.utc).strftime('%Y%m%d-%H%M%S')}"
    generated_at = datetime.now(tz=dt_tz.utc).strftime("%d %B %Y, %H:%M UTC")
    generated_by = getattr(user, "get_full_name", lambda: "")() or getattr(user, "username", "system")

    c = rl_canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"Imbonesha Flag Report — {report_id}")
    c.setAuthor("Imbonesha — Government Administration")

    # ---- page ----
    def new_page(page_num: int, total_pages: int) -> float:
        """Draw page chrome and return the starting y for content."""
        c.setFillColor(Color(*_PAGE_BG))
        c.rect(0, 0, page_w, page_h, fill=1, stroke=0)

        # Header bar
        c.setFillColor(Color(*_HEADER_BG))
        c.rect(0, page_h - 2.8 * cm, page_w, 2.8 * cm, fill=1, stroke=0)

        c.setFont("Helvetica-Bold", 13)
        c.setFillColor(Color(*_HEADER_FG))
        c.drawString(margin, page_h - 1.5 * cm, "Republic of Rwanda — Imbonesha Flag Report")

        c.setFont("Helvetica", 8)
        c.drawString(margin, page_h - 2.2 * cm, f"Report ID: {report_id}   |   Generated: {generated_at}   |   By: {generated_by}")

        # Footer
        c.setFont("Helvetica", 7)
        c.setFillColor(Color(*_MUTED))
        c.drawString(margin, 1.0 * cm, f"Generated by Imbonesha v{APP_VERSION}")
        c.drawRightString(page_w - margin, 1.0 * cm, f"Page {page_num} of {total_pages}")

        # Signature lines on last page
        if page_num == total_pages:
            sig_y = 1.8 * cm
            _draw_rule(c, margin, sig_y, 7 * cm)
            _draw_rule(c, page_w - margin - 7 * cm, sig_y, 7 * cm)
            c.setFont("Helvetica", 7)
            c.setFillColor(Color(*_MUTED))
            c.drawString(margin, sig_y + 2, "District Officer Signature")
            c.drawString(page_w - margin - 7 * cm, sig_y + 2, "RHA Representative Signature")

        return page_h - 2.8 * cm - 0.8 * cm   # content start y

    total_pages = max(1, (len(flags) + 1) // 2 + 1)  # rough estimate; we'll use showPage
    page_num = 1
    y = new_page(page_num, total_pages)

    for flag in flags:
        det = flag.detection
        parcel = det.parcel
        job = det.job

        # Estimate card height before drawing to decide if we need a new page.
        card_h = 6.2 * cm
        if y - card_h < 2.5 * cm:
            c.showPage()
            page_num += 1
            y = new_page(page_num, total_pages)

        card_y = y - card_h
        card_x = margin

        # Card border
        c.setStrokeColor(Color(*_BORDER))
        c.setFillColor(Color(*_PAGE_BG))
        c.setLineWidth(0.5)
        c.roundRect(card_x, card_y, content_w, card_h - 0.3 * cm, radius=4, fill=1, stroke=1)

        # Severity stripe on left edge
        sev_colour = _COLOURS.get(flag.severity, (0.5, 0.5, 0.5))
        c.setFillColor(Color(*sev_colour))
        c.roundRect(card_x, card_y, 0.5 * cm, card_h - 0.3 * cm, radius=2, fill=1, stroke=0)

        inner_x = card_x + 0.7 * cm
        top_y = card_y + card_h - 0.3 * cm - 0.35 * cm

        # Flag ID + severity badge on the same line
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(Color(*_BODY_TEXT))
        c.drawString(inner_x, top_y, f"Flag #{flag.pk}")
        _draw_severity_badge(c, inner_x + 5.5 * cm, top_y - 2, flag.severity)

        # Status badge (draft watermark on unconfirmed flags)
        if flag.status not in (FlagStatus.CONFIRMED, FlagStatus.CLOSED):
            _draw_draft_watermark(c, page_w, page_h, "UNCONFIRMED")

        # --- Row 1: Parcel + owner ---
        row1_y = top_y - 1.0 * cm
        if parcel:
            _label_value(c, "Parcel UPI", parcel.upi, inner_x, row1_y, 100)
            _label_value(c, "Owner", parcel.owner_name, inner_x + 4.5 * cm, row1_y)
            _label_value(c, "District / Sector", f"{parcel.district} / {parcel.sector}", inner_x + 10 * cm, row1_y)
        else:
            _label_value(c, "Parcel UPI", "Unmatched", inner_x, row1_y)

        # --- Row 2: Land use + zone + permit status ---
        row2_y = row1_y - 1.0 * cm
        active_permit = parcel.permits.filter(status="active").first() if parcel else None
        permit_str = active_permit.permit_no if active_permit else "NO PERMIT"

        if parcel:
            _label_value(c, "Land Use", parcel.land_use.replace("_", " ").title(), inner_x, row2_y)
            _label_value(c, "Zone Type", parcel.zone_type.replace("_", " ").title(), inner_x + 4.5 * cm, row2_y)
        _label_value(c, "Permit Status",
                     active_permit.status.upper() if active_permit else "NO PERMIT",
                     inner_x + 8.5 * cm, row2_y)
        _label_value(c, "Permit No", permit_str, inner_x + 12.5 * cm, row2_y)

        # --- Row 3: Detection details ---
        row3_y = row2_y - 1.0 * cm
        _label_value(c, "Confidence", f"{det.confidence:.1%}", inner_x, row3_y)
        _label_value(c, "Footprint Area", f"{det.area_sqm:.0f} sqm", inner_x + 3.5 * cm, row3_y)
        _label_value(c, "Change Type", det.change_type.replace("_", " ").title(), inner_x + 7 * cm, row3_y)
        _label_value(c, "Detected", det.created_at.strftime("%Y-%m-%d"), inner_x + 11 * cm, row3_y)

        # Centroid coordinates
        centroid = det.footprint.centroid
        coord_str = f"{centroid.y:.5f}°N, {centroid.x:.5f}°E"
        _label_value(c, "Centroid", coord_str, inner_x + 14 * cm, row3_y)

        # --- Separator ---
        _draw_rule(c, inner_x, card_y + 0.5 * cm, content_w - 0.8 * cm)

        y = card_y - 0.3 * cm

    c.save()

    pdf_bytes = buf.getvalue()

    # Audit log — best effort, don't fail the report if audit write fails.
    try:
        _audit_report_generated(flags, user, report_id)
    except Exception as exc:
        logger.warning("Failed to write audit log for report %s: %s", report_id, exc)

    logger.info(
        "Generated report %s: %d flags, %d bytes, user=%s",
        report_id, len(flags), len(pdf_bytes), generated_by,
    )
    return pdf_bytes


def _audit_report_generated(flags, user, report_id: str) -> None:
    from flags.models import AuditLog
    from django.utils import timezone
    for flag in flags:
        AuditLog.objects.create(
            flag=flag,
            actor=user if user and user.is_authenticated else None,
            event="report_generated",
            after={"report_id": report_id},
            message=f"Included in PDF report {report_id}",
            timestamp=timezone.now(),
        )
