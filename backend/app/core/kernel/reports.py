"""
app/core/kernel/reports.py
ReportBuilder — PDF (table + receipt + thermal receipt) and Excel
multi-sheet report generator, owned by resort-os.

Usage:
    from app.core.kernel.reports import ReportBuilder

    rb = ReportBuilder(app_name="الخيمة بيتش ريزورت", primary_color="#1A1A2E")

    pdf_bytes = rb.table_pdf(
        title="تقرير الحجوزات اليومي",
        headers=["رقم الحجز", "الاسم", "الغرفة", "الإجمالي"],
        rows=[["BK-001", "أحمد محمد", "101", "500 EGP"]],
    )
"""

from __future__ import annotations

import os
from datetime import datetime
from io import BytesIO
from typing import Optional


# ── Theme defaults ────────────────────────────────────────────────────────────

_DEFAULT_PRIMARY = "#1A1A2E"
_DEFAULT_ACCENT = "#C9A84C"
_DEFAULT_LIGHT = "#F8F9FA"
_GRAY_TEXT = "#6B7280"
_BORDER_COLOR = "#DDDDDD"


class ReportBuilder:
    """
    Per-project report builder. Instantiate once at app startup.

    Args:
        app_name:      Shown in PDF headers/footers and Excel titles.
        primary_color: Hex color for headers (default dark navy).
        accent_color:  Hex color for totals/highlights (default gold).
        logo_path:     Absolute path to a PNG/JPG logo (optional).
        rtl:           Right-to-left layout for Arabic reports (default True).
    """

    def __init__(
        self,
        app_name: str = "Resort OS",
        primary_color: str = _DEFAULT_PRIMARY,
        accent_color: str = _DEFAULT_ACCENT,
        logo_path: str = "",
        rtl: bool = True,
    ):
        self.app_name = app_name
        self.primary_color = primary_color.lstrip("#")
        self.accent_color = accent_color.lstrip("#")
        self.logo_path = logo_path
        self.rtl = rtl

    # ── PDF: Table Report ─────────────────────────────────────────────────

    def table_pdf(
        self,
        title: str,
        headers: list[str],
        rows: list[list],
        *,
        subtitle: str = "",
        summary: Optional[list[tuple[str, str]]] = None,
        footer: str = "",
        landscape: bool = False,
        col_widths: Optional[list[float]] = None,   # in cm
    ) -> bytes:
        """Generate a professional table-based PDF report."""
        try:
            from reportlab.pdfgen import canvas as rl_canvas
            from reportlab.lib.pagesizes import A4, landscape as rl_landscape
            from reportlab.lib import colors
            from reportlab.lib.units import cm
        except ImportError:
            raise RuntimeError("pip install reportlab to use PDF generation")

        pagesize = rl_landscape(A4) if landscape else A4
        buf = BytesIO()
        c = rl_canvas.Canvas(buf, pagesize=pagesize)
        W, H = pagesize

        primary = colors.HexColor(f"#{self.primary_color}")
        accent = colors.HexColor(f"#{self.accent_color}")
        light = colors.HexColor(_DEFAULT_LIGHT)
        gray = colors.HexColor(_GRAY_TEXT)

        margin = 2 * cm
        usable = W - 2 * margin

        # ── Header band ──────────────────────────────────────────────────
        c.setFillColor(primary)
        c.rect(0, H - 75, W, 75, fill=True, stroke=False)

        if self.logo_path and os.path.isfile(self.logo_path):
            try:
                from reportlab.lib.utils import ImageReader
                c.drawImage(ImageReader(self.logo_path), margin, H - 65, 50, 50,
                            preserveAspectRatio=True, mask="auto")
            except Exception:
                pass

        c.setFillColor(colors.HexColor(f"#{self.accent_color}"))
        c.setFont("Helvetica-Bold", 11)
        c.drawString(margin, H - 25, self._t(self.app_name))

        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(margin, H - 48, self._t(title))

        if subtitle:
            c.setFont("Helvetica", 9)
            c.setFillColor(colors.HexColor("#AAAAAA"))
            c.drawString(margin, H - 62, self._t(subtitle))

        c.setFont("Helvetica", 8)
        c.setFillColor(colors.HexColor("#AAAAAA"))
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        c.drawRightString(W - margin, H - 20, ts)

        # ── Summary box ──────────────────────────────────────────────────
        y = H - 95
        if summary:
            box_h = 18
            cols = min(len(summary), 4)
            box_w = usable / cols
            c.setFillColor(light)
            c.setStrokeColor(colors.HexColor(_BORDER_COLOR))
            c.setLineWidth(0.5)
            c.roundRect(margin, y - box_h - 6, usable, box_h + 12, 4, fill=True, stroke=True)
            for i, (label, val) in enumerate(summary[:4]):
                bx = margin + i * box_w + 8
                c.setFont("Helvetica", 7)
                c.setFillColor(gray)
                c.drawString(bx, y - 2, self._t(label.upper()))
                c.setFont("Helvetica-Bold", 11)
                c.setFillColor(primary)
                c.drawString(bx, y - box_h + 2, self._t(str(val)))
            y -= box_h + 22

        # ── Table ─────────────────────────────────────────────────────────
        n_cols = len(headers)
        if col_widths:
            widths = [w * cm for w in col_widths]
        else:
            widths = [usable / n_cols] * n_cols

        row_h = 18
        head_h = 20

        x = margin
        c.setFillColor(primary)
        c.rect(margin, y - head_h, usable, head_h, fill=True, stroke=False)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 9)
        for i, (hdr, w) in enumerate(zip(headers, widths)):
            c.drawString(x + 4, y - head_h + 6, self._t(str(hdr)))
            x += w
        y -= head_h

        c.setFont("Helvetica", 9)
        for ri, row in enumerate(rows):
            if y - row_h < 60:  # new page
                self._add_footer(c, W, footer or self.app_name, accent)
                c.showPage()
                y = H - 40
                x = margin
                c.setFillColor(primary)
                c.rect(margin, y - head_h, usable, head_h, fill=True, stroke=False)
                c.setFillColor(colors.white)
                c.setFont("Helvetica-Bold", 9)
                for hdr, w in zip(headers, widths):
                    c.drawString(x + 4, y - head_h + 6, self._t(str(hdr)))
                    x += w
                y -= head_h
                c.setFont("Helvetica", 9)

            row_bg = light if ri % 2 == 0 else colors.white
            c.setFillColor(row_bg)
            c.rect(margin, y - row_h, usable, row_h, fill=True, stroke=False)

            c.setStrokeColor(colors.HexColor(_BORDER_COLOR))
            c.setLineWidth(0.3)
            c.line(margin, y - row_h, margin + usable, y - row_h)

            c.setFillColor(colors.black)
            x = margin
            for val, w in zip(row, widths):
                c.drawString(x + 4, y - row_h + 5, self._t(str(val) if val is not None else "—"))
                x += w
            y -= row_h

        self._add_footer(c, W, footer or self.app_name, accent)
        c.save()
        return buf.getvalue()

    # ── PDF: Receipt ──────────────────────────────────────────────────────

    def receipt_pdf(
        self,
        reference: str,
        title: str,
        fields: list[tuple[str, str]],
        total: float,
        currency: str = "EGP",
        *,
        note: str = "",
        footer: str = "",
        qr_data: str = "",
    ) -> bytes:
        """Generate a professional receipt / invoice PDF."""
        try:
            from reportlab.pdfgen import canvas as rl_canvas
            from reportlab.lib.pagesizes import A4
            from reportlab.lib import colors
            from reportlab.lib.units import cm
        except ImportError:
            raise RuntimeError("pip install reportlab to use PDF generation")

        buf = BytesIO()
        c = rl_canvas.Canvas(buf, pagesize=A4)
        W, H = A4
        margin = 2 * cm
        primary = colors.HexColor(f"#{self.primary_color}")
        accent = colors.HexColor(f"#{self.accent_color}")

        c.setFillColor(primary)
        c.rect(0, H - 85, W, 85, fill=True, stroke=False)

        if self.logo_path and os.path.isfile(self.logo_path):
            try:
                from reportlab.lib.utils import ImageReader
                c.drawImage(ImageReader(self.logo_path), margin, H - 78, 55, 55,
                            preserveAspectRatio=True, mask="auto")
            except Exception:
                pass

        c.setFillColor(colors.HexColor(f"#{self.accent_color}"))
        c.setFont("Helvetica-Bold", 13)
        c.drawString(margin, H - 30, self._t(self.app_name))

        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 18)
        c.drawString(margin, H - 55, self._t(title))

        c.setFont("Helvetica", 9)
        c.setFillColor(colors.HexColor("#AAAAAA"))
        c.drawString(margin, H - 70, datetime.now().strftime("%Y-%m-%d %H:%M"))

        y = H - 108
        c.setFillColor(colors.HexColor("#EEF2FF"))
        c.setStrokeColor(accent)
        c.setLineWidth(1.5)
        c.roundRect(margin, y - 10, W - 2 * margin, 30, 5, fill=True, stroke=True)
        c.setFillColor(primary)
        c.setFont("Helvetica-Bold", 13)
        c.drawString(margin + 8, y + 8, self._t(f"# {reference}"))

        y -= 30
        c.setStrokeColor(colors.HexColor(_BORDER_COLOR))
        c.setLineWidth(0.5)
        for label, val in fields:
            y -= 22
            c.setFont("Helvetica-Bold", 9)
            c.setFillColor(colors.HexColor(_GRAY_TEXT))
            c.drawString(margin, y, self._t(label) + ":")
            c.setFont("Helvetica", 10)
            c.setFillColor(colors.black)
            c.drawString(margin + 5.5 * cm, y, self._t(str(val)))
            c.line(margin, y - 4, W - margin, y - 4)

        y -= 28
        c.setFillColor(colors.HexColor("#F0F9FF"))
        c.setStrokeColor(accent)
        c.setLineWidth(2)
        c.roundRect(margin, y - 18, W - 2 * margin, 50, 8, fill=True, stroke=True)
        c.setFont("Helvetica-Bold", 11)
        c.setFillColor(primary)
        c.drawString(margin + 10, y + 20, self._t("الإجمالي / Total"))
        c.setFont("Helvetica-Bold", 22)
        c.setFillColor(accent)
        c.drawRightString(W - margin - 10, y + 12, f"{total:,.2f} {currency}")

        if note:
            c.setFont("Helvetica", 8)
            c.setFillColor(colors.HexColor(_GRAY_TEXT))
            c.drawString(margin, y - 26, self._t(note))

        if qr_data:
            try:
                import qrcode as _qrcode
                qr_img = _qrcode.make(qr_data)
                qr_buf = BytesIO()
                qr_img.save(qr_buf, format="PNG")
                qr_buf.seek(0)
                from reportlab.lib.utils import ImageReader
                qr_size = 3.5 * cm
                c.drawImage(ImageReader(qr_buf),
                            W - margin - qr_size, H - 85 - qr_size - 10,
                            qr_size, qr_size)
            except ImportError:
                pass

        self._add_footer(c, W, footer or self.app_name, accent)
        c.save()
        return buf.getvalue()

    # ── PDF: Thermal Roll Receipt ───────────────────────────────────────

    def receipt_pdf_thermal(
        self,
        reference: str,
        title: str,
        fields: list[tuple[str, str]],
        total: float,
        currency: str = "EGP",
        *,
        width_mm: float = 80.0,
        note: str = "",
        footer: str = "",
        qr_data: str = "",
    ) -> bytes:
        """Receipt PDF sized for thermal roll printers (80mm/58mm rolls)."""
        try:
            from reportlab.pdfgen import canvas as rl_canvas
            from reportlab.lib import colors
            from reportlab.lib.units import mm
        except ImportError:
            raise RuntimeError("pip install reportlab to use PDF generation")

        W = width_mm * mm
        margin = 3 * mm
        line_h = 5.2 * mm
        primary = colors.HexColor(f"#{self.primary_color}")
        accent = colors.HexColor(f"#{self.accent_color}")

        qr_size = min(W * 0.5, 30 * mm) if qr_data else 0
        base_units = 8.2 + len(fields) + (1 if note else 0)
        H = (
            2 * margin
            + base_units * line_h
            + (qr_size + 4 * mm if qr_data else 0)
            + 14 * mm
        )

        buf = BytesIO()
        c = rl_canvas.Canvas(buf, pagesize=(W, H))
        y = H - margin

        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(primary)
        c.drawCentredString(W / 2, y, self._t(self.app_name))
        y -= line_h

        c.setFont("Helvetica-Bold", 11)
        c.setFillColor(colors.black)
        c.drawCentredString(W / 2, y, self._t(title))
        y -= line_h

        c.setFont("Helvetica", 7)
        c.setFillColor(colors.HexColor(_GRAY_TEXT))
        c.drawCentredString(W / 2, y, datetime.now().strftime("%Y-%m-%d %H:%M"))
        y -= line_h * 1.3

        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(primary)
        c.drawCentredString(W / 2, y, self._t(f"# {reference}"))
        y -= line_h * 1.3

        c.setStrokeColor(colors.HexColor(_BORDER_COLOR))
        c.setLineWidth(0.5)
        c.line(margin, y, W - margin, y)
        y -= line_h * 0.6

        for label, val in fields:
            c.setFont("Helvetica", 7)
            c.setFillColor(colors.HexColor(_GRAY_TEXT))
            c.drawString(margin, y, self._t(label) + ":")
            c.setFont("Helvetica-Bold", 7)
            c.setFillColor(colors.black)
            c.drawRightString(W - margin, y, self._t(str(val)))
            y -= line_h

        c.line(margin, y, W - margin, y)
        y -= line_h * 1.2

        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(primary)
        c.drawString(margin, y, self._t("الإجمالي / Total"))
        c.setFont("Helvetica-Bold", 13)
        c.setFillColor(accent)
        c.drawRightString(W - margin, y - 1, f"{total:,.2f} {currency}")
        y -= line_h * 1.8

        if note:
            c.setFont("Helvetica", 6.5)
            c.setFillColor(colors.HexColor(_GRAY_TEXT))
            c.drawCentredString(W / 2, y, self._t(note))
            y -= line_h

        if qr_data:
            try:
                import qrcode as _qrcode
                qr_img = _qrcode.make(qr_data)
                qr_buf = BytesIO()
                qr_img.save(qr_buf, format="PNG")
                qr_buf.seek(0)
                from reportlab.lib.utils import ImageReader
                c.drawImage(ImageReader(qr_buf), (W - qr_size) / 2, y - qr_size, qr_size, qr_size)
            except ImportError:
                pass

        self._add_footer(c, W, footer or self.app_name, accent)
        c.save()
        return buf.getvalue()

    # ── Excel: Multi-sheet Workbook ─────────────────────────────────────

    def excel(
        self,
        sheets: list[dict],
        *,
        title: str = "",
        freeze_rows: bool = True,
        auto_width: bool = True,
    ) -> bytes:
        """Generate a multi-sheet Excel workbook."""
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
            from openpyxl.utils import get_column_letter
        except ImportError:
            raise RuntimeError("pip install openpyxl to use Excel generation")

        _thin = Side(style="thin", color=_BORDER_COLOR.lstrip("#"))
        _border = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)

        primary = self.primary_color
        accent = self.accent_color
        light = "F8F9FA"
        white = "FFFFFF"

        def _hcell(ws, row, col, value, bg=primary, fg=white, bold=True, width=None):
            cell = ws.cell(row=row, column=col, value=value)
            cell.font = Font(bold=bold, color=fg, size=10, name="Calibri")
            cell.fill = PatternFill("solid", fgColor=bg)
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = _border
            if width:
                ws.column_dimensions[get_column_letter(col)].width = width
            return cell

        def _dcell(ws, row, col, value, bold=False, align="left", num_fmt=None, bg=None):
            cell = ws.cell(row=row, column=col, value=value)
            cell.font = Font(bold=bold, size=10, name="Calibri")
            cell.alignment = Alignment(horizontal=align, vertical="center")
            cell.border = _border
            if bg:
                cell.fill = PatternFill("solid", fgColor=bg)
            if num_fmt:
                cell.number_format = num_fmt
            return cell

        wb = Workbook()
        if wb.active is not None:
            wb.remove(wb.active)  # remove default empty sheet

        gen_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        for si, sheet_def in enumerate(sheets):
            ws = wb.create_sheet(title=sheet_def.get("name", f"Sheet{si+1}"))
            ws.sheet_view.showGridLines = False

            s_headers = sheet_def.get("headers", [])
            s_rows = sheet_def.get("rows", [])
            s_summary = sheet_def.get("summary", {})
            s_col_types = sheet_def.get("col_types", [])
            n_cols = len(s_headers)

            ws.merge_cells(f"A1:{get_column_letter(n_cols)}1")
            t = ws["A1"]
            t.value = f"{self.app_name}  —  {sheet_def.get('name', title)}  |  {gen_str}"
            t.font = Font(bold=True, size=13, color=white, name="Calibri")
            t.fill = PatternFill("solid", fgColor=primary)
            t.alignment = Alignment(horizontal="center", vertical="center")
            ws.row_dimensions[1].height = 28

            for ci, hdr in enumerate(s_headers, 1):
                _hcell(ws, 2, ci, hdr, bg=accent, fg=primary)
            ws.row_dimensions[2].height = 22

            if freeze_rows:
                ws.freeze_panes = "A3"

            for ri, row in enumerate(s_rows, 3):
                bg = light if (ri - 3) % 2 == 0 else None
                for ci, val in enumerate(row, 1):
                    col_type = s_col_types[ci - 1] if ci - 1 < len(s_col_types) else "text"
                    num_fmt = None
                    align = "left"
                    if col_type == "currency":
                        num_fmt = "#,##0.00"
                        align = "right"
                    elif col_type == "number":
                        align = "right"
                    elif col_type == "percent":
                        num_fmt = "0.0%"
                        align = "right"
                    _dcell(ws, ri, ci, val, align=align, num_fmt=num_fmt, bg=bg)

            if s_summary:
                total_rows = len(s_rows)
                sr = 3 + total_rows
                keys = list(s_summary.keys())
                vals = list(s_summary.values())
                merge_end = max(1, n_cols - len(vals))
                if merge_end > 1:
                    ws.merge_cells(f"A{sr}:{get_column_letter(merge_end)}{sr}")
                lbl_val = keys[0] if len(keys) == 1 else "الإجمالي / Total"
                lbl = ws.cell(row=sr, column=1, value=lbl_val)
                lbl.font = Font(bold=True, size=10, color=white, name="Calibri")
                lbl.fill = PatternFill("solid", fgColor=accent)
                lbl.alignment = Alignment(horizontal="left", vertical="center")
                lbl.border = _border
                for vi, (_, v) in enumerate(s_summary.items()):
                    ci = merge_end + vi + 1
                    if ci > n_cols:
                        break
                    cell = ws.cell(row=sr, column=ci, value=v)
                    cell.font = Font(bold=True, size=10, color=primary, name="Calibri")
                    cell.fill = PatternFill("solid", fgColor=accent)
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                    cell.border = _border
                    if isinstance(v, (int, float)):
                        cell.number_format = "#,##0.00"

            if auto_width:
                for col_cells in ws.columns:
                    max_len = 0
                    col_letter = get_column_letter(col_cells[0].column)
                    for cell in col_cells:
                        if cell.value:
                            max_len = max(max_len, len(str(cell.value)))
                    ws.column_dimensions[col_letter].width = min(max(max_len + 2, 10), 40)

        buf = BytesIO()
        wb.save(buf)
        return buf.getvalue()

    # ── Helpers ───────────────────────────────────────────────────────────

    def _t(self, text: str) -> str:
        """Apply Arabic reshaping + bidi if available and rtl=True."""
        if not self.rtl or not text:
            return text
        try:
            import arabic_reshaper
            from bidi.algorithm import get_display
            result = get_display(arabic_reshaper.reshape(text))
            return result if isinstance(result, str) else result.decode("utf-8")
        except ImportError:
            return text

    @staticmethod
    def _add_footer(c, W, text: str, accent_color) -> None:
        from reportlab.lib import colors
        c.setFillColor(colors.HexColor("#1A1A2E"))
        c.rect(0, 0, W, 35, fill=True, stroke=False)
        c.setFillColor(accent_color)
        c.setFont("Helvetica", 8)
        c.drawCentredString(W / 2, 20, text)
        c.setFillColor(colors.HexColor("#AAAAAA"))
        c.setFont("Helvetica", 7)
        c.drawCentredString(W / 2, 10, datetime.now().strftime("%Y-%m-%d %H:%M"))
