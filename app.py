"""Tax Anomaly & BTD Profiler — Streamlit Executive Dashboard.

Audit-ready interactive interface for DJP tax examiners to screen Indonesian
corporate taxpayers (Wajib Pajak Badan) for Book-Tax Difference anomalies,
aggressive ETR planning, and OCF/fiscal mismatches.

Run:
    streamlit run app.py
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ---------------------------------------------------------------------------
# Path setup — allow imports from src/ whether run from project root or not
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.tax_calculator import calculate_ratios, add_peer_benchmarks
from src.risk_scorer import score_taxpayers, STATUTORY_RATE

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Tax Anomaly & BTD Profiler | DJP Analytics",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Global style — high-contrast executive palette
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    /* ---- Top bar ---- */
    .main-header {
        background: linear-gradient(90deg, #0d2340 0%, #154369 100%);
        padding: 18px 28px 14px 28px;
        border-radius: 8px;
        margin-bottom: 20px;
    }
    .main-header h1 {color:#ffffff; font-size:1.65rem; margin:0; font-weight:700;}
    .main-header p  {color:#9ec8f0; font-size:0.85rem; margin:4px 0 0 0;}

    /* ---- KPI cards ---- */
    .kpi-card {
        background:#f7f9fc;
        border:1px solid #d0dae8;
        border-left:5px solid #1a6bb5;
        border-radius:6px;
        padding:14px 18px;
        height:100%;
    }
    .kpi-card.red   {border-left-color:#c0392b;}
    .kpi-card.amber {border-left-color:#d35400;}
    .kpi-card.green {border-left-color:#1e8449;}
    .kpi-label  {color:#57606a; font-size:0.75rem; font-weight:600; text-transform:uppercase; letter-spacing:.04em;}
    .kpi-value  {color:#0d2340; font-size:1.75rem; font-weight:800; line-height:1.2; margin:4px 0 2px 0;}
    .kpi-delta  {color:#57606a; font-size:0.78rem;}

    /* ---- Section titles ---- */
    .section-title {
        font-size:1.05rem; font-weight:700; color:#38BDF8;
        border-bottom:2px solid #38BDF8; padding-bottom:5px;
        margin-top:10px; margin-bottom:14px;
        text-shadow: 0 1px 2px rgba(0,0,0,0.18);
    }

    /* ---- Risk badge ---- */
    .badge-high   {background:#fdecea; color:#c0392b; padding:2px 10px; border-radius:12px; font-weight:700; font-size:0.78rem;}
    .badge-medium {background:#fef3e2; color:#d35400; padding:2px 10px; border-radius:12px; font-weight:700; font-size:0.78rem;}
    .badge-normal {background:#eafaf1; color:#1e8449; padding:2px 10px; border-radius:12px; font-weight:700; font-size:0.78rem;}

    /* ---- Sidebar — WCAG AA high-contrast ---- */
    section[data-testid="stSidebar"] {
        background: #F8FAFC;
    }
    /* Force all text inside sidebar to dark slate */
    section[data-testid="stSidebar"] *,
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] span,
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] div,
    section[data-testid="stSidebar"] .stMarkdown,
    section[data-testid="stSidebar"] .stMarkdown p,
    section[data-testid="stSidebar"] .stMarkdown h1,
    section[data-testid="stSidebar"] .stMarkdown h2,
    section[data-testid="stSidebar"] .stMarkdown h3,
    section[data-testid="stSidebar"] .stMarkdown strong {
        color: #0F172A !important;
    }
    /* Radio button labels */
    section[data-testid="stSidebar"] .stRadio label,
    section[data-testid="stSidebar"] .stRadio span {
        color: #0F172A !important;
    }
    /* Multiselect labels and selected tags text */
    section[data-testid="stSidebar"] .stMultiSelect label,
    section[data-testid="stSidebar"] .stMultiSelect span {
        color: #0F172A !important;
    }
    /* Text input label */
    section[data-testid="stSidebar"] .stTextInput label {
        color: #0F172A !important;
    }
    /* Caption / small text */
    section[data-testid="stSidebar"] .stCaption,
    section[data-testid="stSidebar"] small,
    section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
        color: #475569 !important;
    }
    /* Divider */
    section[data-testid="stSidebar"] hr {
        border-color: #CBD5E1;
    }

    /* ---- Sidebar file uploader — light container, dark text ---- */
    section[data-testid="stSidebar"] [data-testid="stFileUploader"] {
        background: #E2E8F0;
        border-radius: 6px;
        padding: 4px;
    }
    section[data-testid="stSidebar"] [data-testid="stFileUploader"] *,
    section[data-testid="stSidebar"] [data-testid="stFileUploader"] section *,
    section[data-testid="stSidebar"] [data-testid="stFileUploaderFile"] *,
    section[data-testid="stSidebar"] [data-testid="stFileUploaderFile"] span,
    section[data-testid="stSidebar"] [data-testid="stFileUploaderFile"] small,
    section[data-testid="stSidebar"] [data-testid="stFileUploader"] span,
    section[data-testid="stSidebar"] [data-testid="stFileUploader"] p,
    section[data-testid="stSidebar"] [data-testid="stFileUploader"] small,
    section[data-testid="stSidebar"] [data-testid="stFileUploader"] button {
        color: #0F172A !important;
    }
    /* Uploader dropzone border */
    section[data-testid="stSidebar"] [data-testid="stFileUploader"] section {
        border-color: #94A3B8 !important;
        background: #F1F5F9 !important;
    }

    /* ---- Sidebar download button — ensure readable text ---- */
    section[data-testid="stSidebar"] [data-testid="stDownloadButton"] button,
    section[data-testid="stSidebar"] [data-testid="stDownloadButton"] button *,
    section[data-testid="stSidebar"] [data-testid="stDownloadButton"] button span,
    section[data-testid="stSidebar"] [data-testid="stDownloadButton"] button p {
        color: #F8FAFC !important;
    }

    /* ---- Dataframe override ---- */
    .stDataFrame {border:1px solid #d0dae8; border-radius:6px;}

    /* ---- Hide Streamlit default elements ---- */
    #MainMenu {visibility:hidden;}
    footer    {visibility:hidden;}
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_CSV = _ROOT / "data" / "dummy_wp_dataset.csv"
STATUTORY_PCT = STATUTORY_RATE * 100  # 22.0

RISK_COLOR_MAP = {
    "HIGH RISK": "#c0392b",
    "MEDIUM":    "#d35400",
    "NORMAL":    "#1e8449",
}

REQUIRED_COLS = {
    "npwp_dummy", "nama_wp", "klu_sektor", "tahun_pajak",
    "peredaran_usaha", "laba_komersial", "koreksi_fiskal_positif",
    "koreksi_fiskal_negatif", "laba_fiskal", "pph_terutang",
    "arus_kas_operasi", "total_aset",
}

# ---------------------------------------------------------------------------
# Helper: Indonesian Rupiah formatter
# ---------------------------------------------------------------------------

def fmt_idr(value: float, short: bool = False) -> str:
    """Format a numeric value as Indonesian Rupiah.

    Args:
        value: Monetary amount in IDR.
        short: When True, abbreviate to Miliar (B) or Juta (M).

    Returns:
        Formatted string, e.g. ``"Rp 1,23 T"`` or ``"Rp 4.567.890.000"``.
    """
    if pd.isna(value):
        return "N/A"
    if short:
        abs_v = abs(value)
        sign = "-" if value < 0 else ""
        if abs_v >= 1e12:
            return f"{sign}Rp {abs_v/1e12:.2f} T"
        if abs_v >= 1e9:
            return f"{sign}Rp {abs_v/1e9:.2f} M"
        if abs_v >= 1e6:
            return f"{sign}Rp {abs_v/1e6:.2f} Jt"
        return f"{sign}Rp {abs_v:,.0f}"
    return f"Rp {value:,.0f}"


def fmt_pct(value: float, decimals: int = 1) -> str:
    """Format a decimal ratio as a percentage string.

    Args:
        value: Decimal ratio (e.g. 0.22).
        decimals: Number of decimal places.

    Returns:
        Formatted string, e.g. ``"22.0%"``.
    """
    if pd.isna(value):
        return "N/A"
    return f"{value * 100:.{decimals}f}%"


# ---------------------------------------------------------------------------
# Data pipeline (cached)
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def run_pipeline(raw_bytes: bytes | None, file_ext: str = "csv") -> pd.DataFrame:
    """Load raw data and run the full three-stage tax analytics pipeline.

    Args:
        raw_bytes: Raw file bytes from uploader, or None to use default CSV.
        file_ext: ``"csv"`` or ``"xlsx"``.

    Returns:
        Fully enriched DataFrame with ratios, benchmarks, and risk scores.
    """
    if raw_bytes is None:
        df = pd.read_csv(DEFAULT_CSV)
    elif file_ext == "xlsx":
        df = pd.read_excel(io.BytesIO(raw_bytes))
    else:
        df = pd.read_csv(io.BytesIO(raw_bytes))

    missing = REQUIRED_COLS - set(df.columns)
    if missing:
        raise ValueError(
            f"File tidak valid. Kolom berikut tidak ditemukan: {sorted(missing)}"
        )

    df = _sanitize_df(df)
    df = calculate_ratios(df)
    df = add_peer_benchmarks(df)
    df = score_taxpayers(df)
    return df


# ---------------------------------------------------------------------------
# Data sanitizer — coerces types and strips artefacts from uploaded files
# ---------------------------------------------------------------------------

_MONETARY_COLS = [
    "peredaran_usaha", "laba_komersial", "koreksi_fiskal_positif",
    "koreksi_fiskal_negatif", "laba_fiskal", "pph_terutang",
    "arus_kas_operasi", "total_aset",
]


def _sanitize_df(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce column types and strip formatting artefacts from uploaded data.

    Handles CSVs where monetary values arrive as strings with currency
    symbols (``Rp``), thousand separators (``,`` or ``.``), or leading/
    trailing whitespace — all of which cause ``TypeError`` in arithmetic.

    Steps applied:
    - Strip leading/trailing whitespace from all string columns.
    - Strip ``Rp``, ``IDR``, space, and thousand-separator commas from
      monetary columns, then coerce to ``float64`` (NaN → 0.0).
    - Cast ``tahun_pajak`` to ``int`` (NaN → 0).
    - Strip whitespace from ``klu_sektor`` and ``npwp_dummy`` so sidebar
      filter multiselects match correctly.

    Args:
        df: Raw DataFrame immediately after loading from CSV or Excel.

    Returns:
        Sanitized copy of *df* with correct dtypes.
    """
    df = df.copy()

    # --- String columns: strip whitespace ---
    for col in ("nama_wp", "npwp_dummy", "klu_sektor"):
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    # --- Monetary columns: strip symbols then coerce to float ---
    for col in _MONETARY_COLS:
        if col in df.columns:
            series = df[col]
            if series.dtype == object:
                series = (
                    series.astype(str)
                    .str.strip()
                    .str.replace(r"[Rp\sIDR]", "", regex=True)   # currency symbols
                    .str.replace(r"[,]", "", regex=True)          # thousand separators
                )
            df[col] = pd.to_numeric(series, errors="coerce").fillna(0.0)

    # --- tahun_pajak: coerce to int ---
    if "tahun_pajak" in df.columns:
        df["tahun_pajak"] = (
            pd.to_numeric(df["tahun_pajak"], errors="coerce")
            .fillna(0)
            .astype(int)
        )

    return df


def build_csv_template() -> bytes:
    """Build a minimal CSV template matching the required schema.

    Returns:
        UTF-8-encoded CSV bytes for download.
    """
    sample = pd.DataFrame(
        [
            {
                "npwp_dummy": "WP-001",
                "nama_wp": "PT Contoh Sejahtera",
                "klu_sektor": "Perdagangan Besar",
                "tahun_pajak": 2024,
                "peredaran_usaha": 50000000000,
                "laba_komersial": 5000000000,
                "koreksi_fiskal_positif": 200000000,
                "koreksi_fiskal_negatif": 100000000,
                "laba_fiskal": 5100000000,
                "pph_terutang": 1122000000,
                "arus_kas_operasi": 5500000000,
                "total_aset": 120000000000,
            }
        ]
    )
    return sample.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")


# ---------------------------------------------------------------------------
# Excel export builder
# ---------------------------------------------------------------------------

def build_excel_export(df: pd.DataFrame) -> bytes:
    """Build a formatted Excel workbook from the scored DataFrame.

    Produces three sheets:
    - **Ringkasan Risiko**: full scored dataset with IDR-formatted columns
    - **High Risk**: only HIGH RISK rows
    - **Statistik Sektor**: sector-year aggregate statistics

    Args:
        df: Fully enriched and filtered DataFrame.

    Returns:
        Raw bytes of the ``.xlsx`` workbook.
    """
    output = io.BytesIO()

    # --- Prepare display columns ---
    display_cols = [
        "npwp_dummy", "nama_wp", "klu_sektor", "tahun_pajak",
        "peredaran_usaha", "laba_komersial", "laba_fiskal",
        "btd_nominal", "btd_ratio", "gaap_etr",
        "ocf_to_fiscal_ratio", "pph_terutang",
        "risk_score", "risk_category", "catatan_red_flag",
    ]
    df_export = df[[c for c in display_cols if c in df.columns]].copy()

    col_labels = {
        "npwp_dummy": "NPWP (Dummy)",
        "nama_wp": "Nama WP",
        "klu_sektor": "Sektor KLU",
        "tahun_pajak": "Tahun Pajak",
        "peredaran_usaha": "Peredaran Usaha (IDR)",
        "laba_komersial": "Laba Komersial (IDR)",
        "laba_fiskal": "Laba Fiskal (IDR)",
        "btd_nominal": "BTD Nominal (IDR)",
        "btd_ratio": "BTD Ratio",
        "gaap_etr": "GAAP ETR",
        "ocf_to_fiscal_ratio": "OCF/Fiskal Ratio",
        "pph_terutang": "PPh Terutang (IDR)",
        "risk_score": "Risk Score (0-100)",
        "risk_category": "Kategori Risiko",
        "catatan_red_flag": "Catatan Red Flag (SP2DK)",
    }
    df_export = df_export.rename(columns=col_labels)

    # Sector statistics
    sector_stats = (
        df.groupby(["klu_sektor", "tahun_pajak"])
        .agg(
            jumlah_wp=("npwp_dummy", "nunique"),
            high_risk_count=("risk_category", lambda s: (s == "HIGH RISK").sum()),
            avg_etr=("gaap_etr", "mean"),
            median_btd_ratio=("btd_ratio", "median"),
            total_btd_nominal=("btd_nominal", "sum"),
        )
        .reset_index()
    )

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_export.to_excel(writer, sheet_name="Ringkasan Risiko", index=False)
        df_export[df_export["Kategori Risiko"] == "HIGH RISK"].to_excel(
            writer, sheet_name="High Risk", index=False
        )
        sector_stats.to_excel(writer, sheet_name="Statistik Sektor", index=False)

        # Basic column width auto-fit
        for sheet_name in writer.sheets:
            ws = writer.sheets[sheet_name]
            for col_cells in ws.columns:
                max_len = max(
                    (len(str(cell.value)) if cell.value else 0 for cell in col_cells),
                    default=10,
                )
                ws.column_dimensions[col_cells[0].column_letter].width = min(
                    max_len + 4, 60
                )

    return output.getvalue()


# ===========================================================================
# SIDEBAR
# ===========================================================================

with st.sidebar:
    st.markdown("## 🔍 BTD Profiler")
    st.markdown("**DJP Tax Compliance Analytics**")
    st.divider()

    # ---- Data source ----
    st.markdown("### 📂 Sumber Data")
    data_source = st.radio(
        "Pilih sumber data:",
        options=["Dataset Bawaan (Demo)", "Unggah File Sendiri"],
        index=0,
        label_visibility="collapsed",
    )

    uploaded_file = None
    if data_source == "Unggah File Sendiri":
        uploaded_file = st.file_uploader(
            "Upload CSV / Excel",
            type=["csv", "xlsx"],
            help="File harus memiliki 12 kolom skema standar.",
        )
        st.download_button(
            label="⬇️  Unduh Template CSV",
            data=build_csv_template(),
            file_name="template_wp_dataset.csv",
            mime="text/csv",
            use_container_width=True,
        )

    st.divider()

    # ---- Load data ----
    try:
        if uploaded_file is not None:
            ext = uploaded_file.name.rsplit(".", 1)[-1].lower()
            df_full = run_pipeline(uploaded_file.getvalue(), file_ext=ext)
        else:
            df_full = run_pipeline(None)
        load_error = None
    except Exception as exc:
        load_error = str(exc)
        df_full = pd.DataFrame()

    if load_error:
        st.error(f"**Error memuat data:**\n\n{load_error}")
        st.stop()

    # ---- Filters ----
    st.markdown("### 🎛️ Filter Data")

    all_years = sorted(df_full["tahun_pajak"].unique().tolist())
    sel_years = st.multiselect(
        "Tahun Pajak",
        options=all_years,
        default=all_years,
        placeholder="Pilih tahun...",
    )

    all_sektors = sorted(df_full["klu_sektor"].unique().tolist())
    sel_sektors = st.multiselect(
        "Sektor KLU",
        options=all_sektors,
        default=all_sektors,
        placeholder="Pilih sektor...",
    )

    all_risks = ["HIGH RISK", "MEDIUM", "NORMAL"]
    sel_risks = st.multiselect(
        "Status Risiko",
        options=all_risks,
        default=all_risks,
        placeholder="Pilih kategori...",
    )

    search_query = st.text_input(
        "🔎 Cari NPWP / Nama WP",
        placeholder="Ketik NPWP atau nama...",
        help="Pencarian tidak case-sensitive.",
    )

    st.divider()
    st.caption(
        "Tax Anomaly & BTD Profiler v1.0  \n"
        "Capstone Project — UNSIA  \n"
        "Data bersifat sintetis untuk keperluan analitik."
    )


# ===========================================================================
# APPLY FILTERS
# ===========================================================================

df_view = df_full.copy()

if sel_years:
    df_view = df_view[df_view["tahun_pajak"].isin(sel_years)]
if sel_sektors:
    df_view = df_view[df_view["klu_sektor"].isin(sel_sektors)]
if sel_risks:
    df_view = df_view[df_view["risk_category"].isin(sel_risks)]
if search_query.strip():
    q = search_query.strip().lower()
    mask = (
        df_view["npwp_dummy"].str.lower().str.contains(q, na=False)
        | df_view["nama_wp"].str.lower().str.contains(q, na=False)
    )
    df_view = df_view[mask]


# ===========================================================================
# HEADER
# ===========================================================================

st.markdown(
    """
    <div class="main-header">
        <h1>🔍 Tax Anomaly &amp; BTD Profiler</h1>
        <p>Sistem Skrining Kepatuhan Pajak Badan — Analisis Book-Tax Difference &amp; ETR | Direktorat Jenderal Pajak</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ===========================================================================
# KPI STRIP
# ===========================================================================

st.markdown('<p class="section-title">📊 Indikator Utama Kepatuhan</p>', unsafe_allow_html=True)

total_wp = df_view["npwp_dummy"].nunique()
high_risk_count = int((df_view["risk_category"] == "HIGH RISK").sum())
total_positive_btd = df_view.loc[df_view["btd_nominal"] > 0, "btd_nominal"].sum()
mean_etr = df_view["gaap_etr"].mean()
etr_vs_statutory = (mean_etr - STATUTORY_RATE) * 100  # pct-point difference

k1, k2, k3, k4 = st.columns(4)

with k1:
    st.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-label">Total WP Dianalisis</div>
            <div class="kpi-value">{total_wp:,}</div>
            <div class="kpi-delta">{len(df_view):,} rekaman tahun-pajak</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with k2:
    pct_hr = (high_risk_count / len(df_view) * 100) if len(df_view) else 0
    st.markdown(
        f"""
        <div class="kpi-card red">
            <div class="kpi-label">Jumlah Rekaman HIGH RISK</div>
            <div class="kpi-value" style="color:#c0392b;">{high_risk_count:,}</div>
            <div class="kpi-delta">{pct_hr:.1f}% dari total rekaman</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with k3:
    st.markdown(
        f"""
        <div class="kpi-card amber">
            <div class="kpi-label">Total BTD Positif Terindikasi</div>
            <div class="kpi-value" style="color:#d35400; font-size:1.35rem;">{fmt_idr(total_positive_btd, short=True)}</div>
            <div class="kpi-delta">Selisih laba komersial vs. fiskal (BTD &gt; 0)</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with k4:
    # Guard against NaN when df_view is empty or all gaap_etr values are NaN
    if pd.isna(etr_vs_statutory) or len(df_view) == 0:
        etr_delta_txt = "— pp vs. tarif statutori 22%"
        k4_cls = "kpi-card"
        color = "#57606a"
    else:
        sign = "+" if etr_vs_statutory >= 0 else ""
        etr_delta_txt = f"{sign}{etr_vs_statutory:.1f} pp vs. tarif statutori 22%"
        k4_cls = "kpi-card " + ("green" if etr_vs_statutory >= 0 else "red")
        color = "#1e8449" if etr_vs_statutory >= 0 else "#c0392b"
    st.markdown(
        f"""
        <div class="{k4_cls}">
            <div class="kpi-label">Rata-rata GAAP ETR</div>
            <div class="kpi-value" style="color:{color};">{fmt_pct(mean_etr)}</div>
            <div class="kpi-delta">{etr_delta_txt}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("<br>", unsafe_allow_html=True)

# ===========================================================================
# CHARTS — Row 1
# ===========================================================================

st.markdown('<p class="section-title">📈 Visualisasi Analitik</p>', unsafe_allow_html=True)

chart_col1, chart_col2 = st.columns([6, 5], gap="medium")

# ---- Chart 1: ETR vs BTD Scatter ----
with chart_col1:
    st.markdown("**Chart 1 — GAAP ETR vs. BTD Ratio (per Risk Status)**")

    scatter_df = df_view.dropna(subset=["gaap_etr", "btd_ratio"]).copy()
    scatter_df["etr_pct"] = scatter_df["gaap_etr"] * 100
    scatter_df["btd_pct"] = scatter_df["btd_ratio"] * 100
    scatter_df["hover_text"] = (
        scatter_df["nama_wp"]
        + "<br>" + scatter_df["npwp_dummy"]
        + " | " + scatter_df["tahun_pajak"].astype(str)
        + "<br>ETR: " + scatter_df["etr_pct"].map(lambda x: f"{x:.2f}%")
        + "<br>BTD Ratio: " + scatter_df["btd_pct"].map(lambda x: f"{x:.2f}%")
        + "<br>Score: " + scatter_df["risk_score"].astype(str)
    )

    fig_scatter = px.scatter(
        scatter_df,
        x="etr_pct",
        y="btd_pct",
        color="risk_category",
        color_discrete_map=RISK_COLOR_MAP,
        size="risk_score",
        size_max=18,
        hover_name="nama_wp",
        custom_data=["hover_text"],
        labels={
            "etr_pct": "GAAP ETR (%)",
            "btd_pct": "BTD Ratio (% dari Total Aset)",
            "risk_category": "Status Risiko",
        },
        title="",
    )
    # Statutory rate reference line at 22%
    fig_scatter.add_vline(
        x=STATUTORY_PCT,
        line_dash="dash",
        line_color="#888888",
        annotation_text=f"Tarif Statutori {STATUTORY_PCT:.0f}%",
        annotation_position="top right",
        annotation_font_size=11,
        annotation_font_color="#555555",
    )
    # Zero BTD reference line (BTD Ratio on Y-axis → use add_hline with y=)
    fig_scatter.add_hline(
        y=0,
        line_dash="dot",
        line_color="#aaaaaa",
    )
    fig_scatter.update_traces(
        hovertemplate="%{customdata[0]}<extra></extra>",
        marker=dict(opacity=0.82, line=dict(width=0.6, color="#ffffff")),
    )
    fig_scatter.update_layout(
        height=400,
        margin=dict(l=10, r=10, t=10, b=40),
        legend=dict(
            title_text="Status Risiko",
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(color="#0F172A"),
        ),
        plot_bgcolor="#F8FAFC",
        paper_bgcolor="#FFFFFF",
        font=dict(color="#0F172A"),
        xaxis=dict(
            gridcolor="#e8ecf1",
            zeroline=False,
            tickfont=dict(color="#0F172A"),
            title_font=dict(color="#0F172A"),
        ),
        yaxis=dict(
            gridcolor="#e8ecf1",
            zeroline=True,
            zerolinecolor="#cccccc",
            tickfont=dict(color="#0F172A"),
            title_font=dict(color="#0F172A"),
        ),
    )
    st.plotly_chart(fig_scatter, use_container_width=True)

# ---- Chart 2: Sector peer-group ETR comparison ----
with chart_col2:
    st.markdown("**Chart 2 — Perbandingan GAAP ETR per Sektor (vs. Median Peer)**")

    peer_df = df_view.dropna(subset=["gaap_etr", "peer_etr_median"]).copy()
    peer_df["etr_pct"] = peer_df["gaap_etr"] * 100
    peer_df["peer_median_pct"] = peer_df["peer_etr_median"] * 100

    # Group: show box + median peer line per sector
    fig_box = go.Figure()

    for sektor in sorted(peer_df["klu_sektor"].unique()):
        sub = peer_df[peer_df["klu_sektor"] == sektor]
        fig_box.add_trace(
            go.Box(
                y=sub["etr_pct"],
                x=[sektor] * len(sub),
                name=sektor,
                boxpoints="all",
                jitter=0.35,
                pointpos=-1.6,
                marker=dict(size=5, opacity=0.7),
                line=dict(width=1.5),
                hovertemplate=(
                    "<b>%{x}</b><br>"
                    "ETR: %{y:.2f}%<extra></extra>"
                ),
            )
        )

    # Statutory reference
    fig_box.add_hline(
        y=STATUTORY_PCT,
        line_dash="dash",
        line_color="#c0392b",
        annotation_text=f"Tarif Statutori {STATUTORY_PCT:.0f}%",
        annotation_position="top right",
        annotation_font_size=11,
        annotation_font_color="#c0392b",
    )
    fig_box.update_layout(
        height=400,
        showlegend=False,
        margin=dict(l=10, r=10, t=10, b=60),
        plot_bgcolor="#F8FAFC",
        paper_bgcolor="#FFFFFF",
        font=dict(color="#0F172A"),
        xaxis=dict(
            title="",
            tickangle=-15,
            gridcolor="#e8ecf1",
            tickfont=dict(color="#0F172A"),
            title_font=dict(color="#0F172A"),
        ),
        yaxis=dict(
            title="GAAP ETR (%)",
            gridcolor="#e8ecf1",
            tickfont=dict(color="#0F172A"),
            title_font=dict(color="#0F172A"),
        ),
    )
    st.plotly_chart(fig_box, use_container_width=True)

# ===========================================================================
# PRIORITY AUDIT TABLE
# ===========================================================================

st.markdown('<p class="section-title">🚨 Tabel Prioritas Audit</p>', unsafe_allow_html=True)

# Display columns for the table
TABLE_COLS = [
    "npwp_dummy", "nama_wp", "klu_sektor", "tahun_pajak",
    "risk_score", "risk_category",
    "btd_ratio", "gaap_etr", "ocf_to_fiscal_ratio",
    "pph_terutang", "laba_komersial", "laba_fiskal",
]
table_df = df_view[[c for c in TABLE_COLS if c in df_view.columns]].copy()

# Sort default: risk_score descending
table_df = table_df.sort_values("risk_score", ascending=False).reset_index(drop=True)

# Format for display
display_map = {
    "npwp_dummy":          "NPWP",
    "nama_wp":             "Nama WP",
    "klu_sektor":          "Sektor",
    "tahun_pajak":         "Tahun",
    "risk_score":          "Skor Risiko",
    "risk_category":       "Kategori",
    "btd_ratio":           "BTD Ratio",
    "gaap_etr":            "GAAP ETR",
    "ocf_to_fiscal_ratio": "OCF/Fiskal",
    "pph_terutang":        "PPh Terutang",
    "laba_komersial":      "Laba Komersial",
    "laba_fiskal":         "Laba Fiskal",
}
table_display = table_df.rename(columns=display_map)
table_display["BTD Ratio"] = table_df["btd_ratio"].map(lambda x: fmt_pct(x, 2) if pd.notna(x) else "N/A")
table_display["GAAP ETR"]  = table_df["gaap_etr"].map(lambda x: fmt_pct(x, 2) if pd.notna(x) else "N/A")
table_display["OCF/Fiskal"] = table_df["ocf_to_fiscal_ratio"].map(
    lambda x: f"{x:.1f}x" if pd.notna(x) else "N/A"
)
table_display["PPh Terutang"]   = table_df["pph_terutang"].map(lambda x: fmt_idr(x, short=True))
table_display["Laba Komersial"] = table_df["laba_komersial"].map(lambda x: fmt_idr(x, short=True))
table_display["Laba Fiskal"]    = table_df["laba_fiskal"].map(lambda x: fmt_idr(x, short=True))

# Color-code risk category column using background
def _color_risk(val: str) -> str:
    colors = {
        "HIGH RISK": "background-color:#fdecea; color:#c0392b; font-weight:700;",
        "MEDIUM":    "background-color:#fef3e2; color:#d35400; font-weight:700;",
        "NORMAL":    "background-color:#eafaf1; color:#1e8449; font-weight:700;",
    }
    return colors.get(val, "")


def _color_score(val) -> str:
    try:
        v = float(val)
    except (TypeError, ValueError):
        return ""
    if v >= 70:
        return "color:#c0392b; font-weight:700;"
    if v >= 40:
        return "color:#d35400; font-weight:600;"
    return "color:#1e8449;"


# .map() replaces the deprecated .applymap() in Pandas 2.1+;
# fall back to .applymap() on older installs for forward compatibility.
_styler_cell_fn = "map" if hasattr(pd.DataFrame().style, "map") else "applymap"

styled = (
    table_display.style
    .pipe(lambda s: getattr(s, _styler_cell_fn)(_color_risk, subset=["Kategori"]))
    .pipe(lambda s: getattr(s, _styler_cell_fn)(_color_score, subset=["Skor Risiko"]))
    .set_properties(**{"font-size": "0.82rem"})
    .hide(axis="index")
)
st.dataframe(styled, use_container_width=True, height=320)

st.caption(
    f"Menampilkan {len(table_df):,} rekaman  |  "
    f"HIGH RISK: {int((table_df['risk_category']=='HIGH RISK').sum())}  |  "
    f"MEDIUM: {int((table_df['risk_category']=='MEDIUM').sum())}  |  "
    f"NORMAL: {int((table_df['risk_category']=='NORMAL').sum())}"
)

# ===========================================================================
# DRILL-DOWN & SP2DK GENERATOR
# ===========================================================================

st.markdown('<p class="section-title">🔎 Drill-Down Wajib Pajak & Generator SP2DK</p>', unsafe_allow_html=True)

dd_col1, dd_col2 = st.columns([3, 4], gap="large")

with dd_col1:
    # Selectbox: sorted by risk_score desc, show NPWP + name
    wp_options = (
        df_view.drop_duplicates("npwp_dummy")
        .sort_values("risk_score", ascending=False)["npwp_dummy"]
        .tolist()
    )
    if not wp_options:
        st.info("Tidak ada data yang cocok dengan filter saat ini.")
    else:
        selected_npwp = st.selectbox(
            "Pilih Wajib Pajak:",
            options=wp_options,
            format_func=lambda npwp: (
                f"{npwp} — "
                + df_view.loc[df_view["npwp_dummy"] == npwp, "nama_wp"].iloc[0]
            ),
        )

        wp_data = df_view[df_view["npwp_dummy"] == selected_npwp].sort_values("tahun_pajak")
        wp_name = wp_data["nama_wp"].iloc[0]
        wp_sector = wp_data["klu_sektor"].iloc[0]
        max_score = int(wp_data["risk_score"].max())
        max_category = wp_data.loc[wp_data["risk_score"].idxmax(), "risk_category"]

        badge_cls = {
            "HIGH RISK": "badge-high",
            "MEDIUM": "badge-medium",
            "NORMAL": "badge-normal",
        }.get(max_category, "badge-normal")

        st.markdown(
            f"""
            <div style="background:#f0f4fa; border-radius:8px; padding:14px 16px; margin-bottom:12px;">
                <div style="font-size:1.1rem; font-weight:700; color:#0d2340;">{wp_name}</div>
                <div style="color:#57606a; font-size:0.82rem; margin-top:3px;">{selected_npwp} &nbsp;|&nbsp; {wp_sector}</div>
                <div style="margin-top:8px;">
                    <span style="font-size:0.8rem; color:#555;">Skor Risiko Maks:</span>
                    &nbsp;<strong style="font-size:1.2rem;">{max_score}</strong>
                    &nbsp;<span class="{badge_cls}">{max_category}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # 3-year trend chart
        fig_trend = go.Figure()
        years = wp_data["tahun_pajak"].tolist()

        fig_trend.add_trace(go.Bar(
            x=years,
            y=(wp_data["btd_ratio"] * 100).tolist(),
            name="BTD Ratio (%)",
            marker_color="#1a6bb5",
            yaxis="y",
            hovertemplate="BTD Ratio: %{y:.2f}%<extra></extra>",
        ))
        fig_trend.add_trace(go.Scatter(
            x=years,
            y=(wp_data["gaap_etr"].fillna(0) * 100).tolist(),
            name="GAAP ETR (%)",
            mode="lines+markers",
            line=dict(color="#d35400", width=2.5),
            marker=dict(size=8),
            yaxis="y",
            hovertemplate="GAAP ETR: %{y:.2f}%<extra></extra>",
        ))
        fig_trend.add_trace(go.Scatter(
            x=years,
            y=wp_data["risk_score"].tolist(),
            name="Risk Score",
            mode="lines+markers",
            line=dict(color="#c0392b", width=2, dash="dot"),
            marker=dict(size=8, symbol="diamond"),
            yaxis="y2",
            hovertemplate="Risk Score: %{y}<extra></extra>",
        ))
        fig_trend.add_hline(
            y=STATUTORY_PCT,
            line_dash="dash",
            line_color="#aaaaaa",
            annotation_text="22%",
            annotation_font_size=10,
            yref="y",
        )
        fig_trend.update_layout(
            height=280,
            margin=dict(l=10, r=10, t=10, b=10),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            yaxis=dict(title="% (ETR / BTD)", gridcolor="#e8ecf1"),
            yaxis2=dict(
                title="Risk Score",
                overlaying="y",
                side="right",
                range=[0, 110],
                gridcolor="#f0f0f0",
                showgrid=False,
            ),
            xaxis=dict(tickmode="array", tickvals=years),
            plot_bgcolor="#fafbfd",
            paper_bgcolor="#ffffff",
        )
        st.plotly_chart(fig_trend, use_container_width=True)

        # Fiscal reconciliation waterfall
        st.markdown("**Rekonsiliasi Fiskal (Rata-rata 3 Tahun)**")
        avg_kom  = wp_data["laba_komersial"].mean()
        avg_kfp  = wp_data["koreksi_fiskal_positif"].mean()
        avg_kfn  = wp_data["koreksi_fiskal_negatif"].mean()
        avg_fis  = wp_data["laba_fiskal"].mean()

        wf_fig = go.Figure(go.Waterfall(
            orientation="v",
            measure=["absolute", "relative", "relative", "total"],
            x=["Laba Komersial", "+ Koreksi Positif", "- Koreksi Negatif", "Laba Fiskal"],
            y=[avg_kom, avg_kfp, -avg_kfn, 0],
            connector=dict(line=dict(color="#cccccc")),
            decreasing=dict(marker_color="#c0392b"),
            increasing=dict(marker_color="#1a6bb5"),
            totals=dict(marker_color="#1e8449"),
            text=[
                fmt_idr(avg_kom, short=True),
                fmt_idr(avg_kfp, short=True),
                fmt_idr(avg_kfn, short=True),
                fmt_idr(avg_fis, short=True),
            ],
            textposition="outside",
        ))
        wf_fig.update_layout(
            height=240,
            margin=dict(l=10, r=10, t=10, b=10),
            showlegend=False,
            plot_bgcolor="#fafbfd",
            paper_bgcolor="#ffffff",
            yaxis=dict(gridcolor="#e8ecf1"),
        )
        st.plotly_chart(wf_fig, use_container_width=True)

# ---- SP2DK Draft ----
with dd_col2:
    if wp_options:
        st.markdown(f"**Draf Poin Klarifikasi SP2DK — {selected_npwp}**")
        st.markdown(
            "<div style='background:#fef9f0; border:1px solid #f0d9a0; border-radius:6px; "
            "padding:14px 16px; font-size:0.82rem; color:#333;'>"
            "<p style='margin:0 0 8px 0; font-size:0.88rem; font-weight:700; color:#0d2340;'>"
            "SURAT PERMINTAAN PENJELASAN ATAS DATA DAN/ATAU KETERANGAN (SP2DK)</p>"
            "<hr style='border:0; border-top:1px solid #e0d0a0; margin:6px 0 10px 0;'>",
            unsafe_allow_html=True,
        )

        # Build bullet points per year
        spdk_lines: list[str] = []
        for _, row in wp_data.iterrows():
            yr = int(row["tahun_pajak"])
            cat = row["risk_category"]
            score = int(row["risk_score"])
            flags_raw = str(row.get("catatan_red_flag", ""))

            spdk_lines.append(
                f"**Tahun Pajak {yr}** "
                f"(Skor Risiko: {score} | Kategori: {cat})"
            )
            if flags_raw and flags_raw != "Tidak ada indikasi anomali signifikan.":
                bullets = flags_raw.split(" | ")
                for b in bullets:
                    spdk_lines.append(f"- {b}")
            else:
                spdk_lines.append("- Tidak ada indikasi anomali signifikan.")
            spdk_lines.append("")  # blank line between years

        # Additional standard SP2DK questions based on max risk
        if max_score >= 70:
            spdk_lines += [
                "---",
                "**Permintaan Dokumen Wajib (HIGH RISK):**",
                "- Rekonsiliasi fiskal lengkap (Formulir 1771-I s.d. 1771-VI)",
                "- Rincian biaya yang diklaim sebagai koreksi fiskal negatif",
                "- Laporan arus kas operasi vs. SPT PPh Badan 3 tahun terakhir",
                "- Daftar pihak afiliasi dan dokumen transfer pricing (bila ada)",
                "- Konfirmasi penggunaan fasilitas tax holiday / supertax deduction",
            ]
        elif max_score >= 40:
            spdk_lines += [
                "---",
                "**Permintaan Dokumen (MEDIUM RISK):**",
                "- Rekonsiliasi fiskal Tahun Pajak terkait",
                "- Penjelasan perbedaan antara laba komersial dan laba fiskal",
                "- Bukti potong PPh Pasal 25/29 dan realisasi angsuran",
            ]

        full_spdk = "\n".join(spdk_lines)
        st.markdown(full_spdk)
        st.markdown("</div>", unsafe_allow_html=True)

        # Copy-ready text area
        spdk_plain = full_spdk.replace("**", "").replace("---", "─" * 50)
        st.text_area(
            "📋 Salin Teks SP2DK:",
            value=spdk_plain,
            height=180,
            help="Blok semua teks di atas lalu Ctrl+C untuk menyalin.",
        )

# ===========================================================================
# EXCEL EXPORT
# ===========================================================================

st.divider()
st.markdown('<p class="section-title">📥 Ekspor Kertas Kerja Penelitian</p>', unsafe_allow_html=True)

exp_col1, exp_col2 = st.columns([3, 5])

with exp_col1:
    if len(df_view) > 0:
        xlsx_bytes = build_excel_export(df_view)
        st.download_button(
            label="📥  Export Kertas Kerja Penelitian (.xlsx)",
            data=xlsx_bytes,
            file_name="kertas_kerja_penelitian_pajak.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            type="primary",
            help=(
                "Mengunduh workbook Excel berisi:\n"
                "• Sheet 1: Ringkasan Risiko (semua data terfilter)\n"
                "• Sheet 2: High Risk (rekaman HIGH RISK saja)\n"
                "• Sheet 3: Statistik Sektor"
            ),
        )
    else:
        st.warning("Tidak ada data untuk diekspor. Sesuaikan filter Anda.")

with exp_col2:
    st.info(
        "**Konten workbook Excel:**\n"
        "- **Ringkasan Risiko** — semua rekaman terfilter beserta skor risiko dan catatan SP2DK\n"
        "- **High Risk** — daftar khusus rekaman berkategori HIGH RISK\n"
        "- **Statistik Sektor** — agregasi jumlah WP, rata-rata ETR, dan total BTD per sektor-tahun"
    )

# ===========================================================================
# FOOTER
# ===========================================================================

st.markdown(
    """
    <hr style="margin-top:40px; border:0; border-top:1px solid #e5e7eb;">
    <div style="text-align:center; color:#57606a; font-size:0.78rem; padding:10px 0 20px 0;">
        Tax Anomaly &amp; BTD Profiler &nbsp;|&nbsp; Capstone Project — UNSIA &nbsp;|&nbsp;
        Data bersifat sintetis &amp; hanya untuk keperluan akademis &nbsp;|&nbsp;
        Built with Streamlit · Pandas · Plotly
    </div>
    """,
    unsafe_allow_html=True,
)
