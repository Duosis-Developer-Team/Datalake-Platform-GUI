"""CSV, Excel, and PDF export helpers for Dash dcc.Download."""

from __future__ import annotations

import io
import logging
from datetime import datetime, timezone
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


def _serialize_filter_value(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        try:
            import json

            return json.dumps(v, ensure_ascii=False, default=str)[:8000]
        except Exception:
            return str(v)[:8000]
    return str(v)


def build_report_info_df(
    time_range: dict[str, Any] | None,
    page_name: str,
    extra_filters: dict[str, Any] | None = None,
    *,
    exported_at_utc: datetime | None = None,
) -> pd.DataFrame:
    """
    Build a two-column DataFrame (key, value) for Report_Info sheet / CSV header block.
    """
    rows: list[dict[str, Any]] = []
    at = exported_at_utc or datetime.now(timezone.utc)
    rows.append({"key": "exported_at_utc", "value": at.strftime("%Y-%m-%d %H:%M:%S UTC")})
    rows.append({"key": "page", "value": page_name})
    if time_range:
        rows.append({"key": "time_preset", "value": str(time_range.get("preset", ""))})
        rows.append({"key": "range_start", "value": str(time_range.get("start", ""))})
        rows.append({"key": "range_end", "value": str(time_range.get("end", ""))})
    if extra_filters:
        for k, v in sorted(extra_filters.items(), key=lambda x: str(x[0])):
            rows.append({"key": str(k), "value": _serialize_filter_value(v)})
    return pd.DataFrame(rows)


def dataframes_to_excel_with_meta(
    sheets: dict[str, pd.DataFrame],
    time_range: dict[str, Any] | None,
    page_name: str,
    extra_filters: dict[str, Any] | None = None,
) -> bytes:
    """Prepend Report_Info sheet, then write all other sheets (Excel 31-char sheet names)."""
    meta = build_report_info_df(time_range, page_name, extra_filters)
    ordered: dict[str, pd.DataFrame] = {"Report_Info": meta}
    for name, df in sheets.items():
        ordered[name] = df
    return dataframes_to_excel_bytes(ordered)


def csv_bytes_with_report_header(
    report_info: pd.DataFrame,
    sections: list[tuple[str, pd.DataFrame]],
) -> bytes:
    """UTF-8 BOM CSV: Report_Info block, then named sections separated by blank lines."""
    lines: list[str] = []
    lines.append("# Report_Info")
    lines.append(report_info.to_csv(index=False).strip("\r\n"))
    for section_title, df in sections:
        lines.append("")
        lines.append(f"# {section_title}")
        if df is None or df.empty:
            lines.append("(no data)")
            continue
        lines.append(df.to_csv(index=False).strip("\r\n"))
    text = "\n".join(lines) + "\n"
    return text.encode("utf-8-sig")


def dash_send_excel_workbook(
    content: bytes,
    base_filename: str,
) -> dict[str, Any]:
    """Send multi-sheet Excel bytes via dcc.Download."""
    from dash import dcc

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in base_filename)[:80]
    return dcc.send_bytes(content, filename=f"{safe}_{ts}.xlsx")


def dash_send_csv_bytes(
    content: bytes,
    base_filename: str,
) -> dict[str, Any]:
    from dash import dcc

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in base_filename)[:80]
    return dcc.send_bytes(content, filename=f"{safe}_{ts}.csv")


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
