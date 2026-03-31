"""CSV, Excel, and PDF export helpers for Dash dcc.Download."""

from __future__ import annotations

import io
import logging
from datetime import datetime, timezone
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


def dataframe_to_csv_bytes(df: pd.DataFrame) -> bytes:
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8-sig")


def dataframe_to_excel_bytes(df: pd.DataFrame, sheet_name: str = "Report") -> bytes:
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=sheet_name[:31], index=False)
    return bio.getvalue()


def dataframes_to_excel_bytes(sheets: dict[str, pd.DataFrame]) -> bytes:
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        for name, df in sheets.items():
            safe_name = (name or "Sheet")[:31]
            df.to_excel(writer, sheet_name=safe_name, index=False)
    return bio.getvalue()


def dataframe_to_pdf_bytes(
    df: pd.DataFrame,
    title: str,
    subtitle: str | None = None,
) -> bytes:
    """Render a simple table PDF (fpdf2)."""
    try:
        from fpdf import FPDF
    except ImportError as exc:
        raise RuntimeError("fpdf2 is required for PDF export") from exc

    class _PDF(FPDF):
        def header(self) -> None:
            self.set_font("Helvetica", "B", 14)
            self.cell(0, 10, title[:120], ln=True)
            if subtitle:
                self.set_font("Helvetica", "", 9)
                self.set_text_color(120, 120, 120)
                self.cell(0, 6, subtitle[:200], ln=True)
                self.set_text_color(0, 0, 0)
            self.ln(4)

    pdf = _PDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()
    pdf.set_font("Helvetica", size=8)

    cols = [str(c) for c in df.columns.tolist()]
    rows = df.fillna("").astype(str).values.tolist()
    if not cols:
        pdf.cell(0, 8, "No data", ln=True)
        return bytes(pdf.output())

    col_width = min(40, max(190, pdf.w - 24) / max(len(cols), 1))
    pdf.set_font("Helvetica", "B", 7)
    for c in cols:
        pdf.cell(col_width, 6, c[:32], border=1)
    pdf.ln()
    pdf.set_font("Helvetica", size=7)
    for row in rows[:200]:
        for cell in row:
            pdf.cell(col_width, 5, str(cell)[:40], border=1)
        pdf.ln()
    if len(rows) > 200:
        pdf.ln(2)
        pdf.cell(0, 6, f"... truncated ({len(rows) - 200} more rows)", ln=True)

    return bytes(pdf.output())


def records_to_dataframe(records: list[dict[str, Any]]) -> pd.DataFrame:
    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records)


def dash_send_dataframe(
    df: pd.DataFrame,
    base_filename: str,
    fmt: str,
) -> dict[str, Any]:
    """Return dict suitable for dcc.Download `data` prop."""
    from dash import dcc

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in base_filename)[:80]
    fmt = (fmt or "csv").lower()
    if fmt == "csv":
        return dcc.send_bytes(dataframe_to_csv_bytes(df), filename=f"{safe}_{ts}.csv")
    if fmt in ("xlsx", "excel"):
        return dcc.send_bytes(dataframe_to_excel_bytes(df), filename=f"{safe}_{ts}.xlsx")
    if fmt == "pdf":
        content = dataframe_to_pdf_bytes(df, title=safe.replace("_", " "), subtitle=ts)
        return dcc.send_bytes(content, filename=f"{safe}_{ts}.pdf")
    raise ValueError(f"Unknown export format: {fmt}")
