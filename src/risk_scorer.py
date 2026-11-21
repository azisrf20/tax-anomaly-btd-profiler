"""Risk scorer and audit red-flag annotator for corporate taxpayers.

Consumes the enriched DataFrame produced by
:mod:`src.tax_calculator` and assigns:

- A numeric ``risk_score`` (0–100)
- A categorical ``risk_category`` label
- An Indonesian-language ``catatan_red_flag`` narrative for SP2DK drafting

Scoring methodology
-------------------
Four independent sub-scores (each 0–25) are summed:

1. **BTD severity**     — absolute BTD ratio vs. peer Q3 and hard thresholds
2. **ETR deviation**    — GAAP ETR vs. statutory 22 % and peer Q1
3. **OCF/Fiscal mismatch** — operating cash flow vs. declared taxable income
4. **Persistent anomaly bonus** — repeated high BTD over multiple years raises
   the score, mirroring OECD BEPS audit guidance on sustained tax-gap patterns

Risk categories::

    HIGH RISK  : risk_score ≥ 70
    MEDIUM     : 40 ≤ risk_score < 70
    NORMAL     : risk_score < 40
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
STATUTORY_RATE = 0.22
HIGH_RISK_THRESHOLD = 70
MEDIUM_RISK_THRESHOLD = 40

# Sub-score caps
_BTD_MAX = 25
_ETR_MAX = 25
_OCF_MAX = 25
_PERSIST_MAX = 25


# ---------------------------------------------------------------------------
# Sub-scorers
# ---------------------------------------------------------------------------

def _score_btd(
    btd_ratio: float,
    peer_btd_q3: float,
) -> float:
    """Score the BTD ratio sub-component (0–25).

    Scoring tiers:

    - btd_ratio > 20 % of assets  → 25
    - btd_ratio > 10 % of assets  → 18
    - btd_ratio > peer Q3         → 12
    - btd_ratio > 0 (any positive)→ 5
    - otherwise                   → 0

    Args:
        btd_ratio: Taxpayer's BTD / total_aset ratio.
        peer_btd_q3: Sector-year 75th-percentile BTD ratio.

    Returns:
        Sub-score float in [0, 25].
    """
    if np.isnan(btd_ratio):
        return 0.0
    if btd_ratio > 0.20:
        return 25.0
    if btd_ratio > 0.10:
        return 18.0
    if not np.isnan(peer_btd_q3) and btd_ratio > peer_btd_q3:
        return 12.0
    if btd_ratio > 0:
        return 5.0
    return 0.0


def _score_etr(
    gaap_etr: float,
    peer_etr_q1: float,
) -> float:
    """Score the GAAP ETR sub-component (0–25).

    Scoring tiers:

    - gaap_etr < 5 %              → 25
    - gaap_etr < 10 %             → 20
    - gaap_etr < peer Q1          → 15
    - gaap_etr < statutory (22 %) → 8
    - otherwise                   → 0

    NaN ETR (non-positive commercial profit) scores 0 — handled upstream.

    Args:
        gaap_etr: Taxpayer's effective tax rate.
        peer_etr_q1: Sector-year 25th-percentile ETR.

    Returns:
        Sub-score float in [0, 25].
    """
    if np.isnan(gaap_etr):
        return 0.0
    if gaap_etr < 0.05:
        return 25.0
    if gaap_etr < 0.10:
        return 20.0
    if not np.isnan(peer_etr_q1) and gaap_etr < peer_etr_q1:
        return 15.0
    if gaap_etr < STATUTORY_RATE:
        return 8.0
    return 0.0


def _score_ocf(ocf_to_fiscal_ratio: float) -> float:
    """Score the OCF-to-fiscal mismatch sub-component (0–25).

    A very high ratio signals that cash operations vastly exceed declared
    taxable income — a classic indicator of income concealment.

    Scoring tiers:

    - ratio > 20  → 25
    - ratio > 10  → 20
    - ratio > 5   → 12
    - ratio > 2   → 5
    - otherwise   → 0

    Args:
        ocf_to_fiscal_ratio: arus_kas_operasi / laba_fiskal.

    Returns:
        Sub-score float in [0, 25].
    """
    if np.isnan(ocf_to_fiscal_ratio):
        return 0.0
    if ocf_to_fiscal_ratio > 20:
        return 25.0
    if ocf_to_fiscal_ratio > 10:
        return 20.0
    if ocf_to_fiscal_ratio > 5:
        return 12.0
    if ocf_to_fiscal_ratio > 2:
        return 5.0
    return 0.0


def _score_persistence(
    npwp: str,
    tahun: int,
    btd_scores: dict[tuple[str, int], float],
) -> float:
    """Add persistence bonus when BTD anomaly spans multiple consecutive years.

    If the same taxpayer scored > 10 on the BTD sub-score in the immediately
    preceding year, award an additional 15 points (capped at ``_PERSIST_MAX``).
    This models the OECD BEPS guidance that *sustained* book-tax gaps are more
    indicative of intentional structuring than a one-off event.

    Args:
        npwp: Taxpayer identifier.
        tahun: Current tax year.
        btd_scores: Mapping of (npwp, year) → btd_sub_score for already
                    processed rows, so only *prior* years are present when
                    this function is called.

    Returns:
        Persistence bonus float in [0, 25].
    """
    prior_score = btd_scores.get((npwp, tahun - 1), 0.0)
    if prior_score > 10:
        return 15.0
    return 0.0


# ---------------------------------------------------------------------------
# Red-flag narrative generator
# ---------------------------------------------------------------------------

_FLAG_TEMPLATES: dict[str, str] = {
    "high_btd": (
        "Teridentifikasi Book-Tax Difference (BTD) positif yang signifikan "
        "sebesar {btd_pct:.1f}% dari total aset (threshold: 10%). Potensi "
        "rekayasa pengurangan fiskal melalui koreksi fiskal negatif yang besar. "
        "Disarankan verifikasi atas rincian koreksi fiskal negatif dan "
        "kewajaran biaya non-deductible."
    ),
    "low_etr": (
        "GAAP ETR tercatat sebesar {etr_pct:.1f}%, jauh di bawah tarif normal "
        "22% (selisih {diff_pct:.1f} poin persentase). Indikasi penghindaran "
        "pajak agresif atau pemanfaatan fasilitas pajak yang perlu dikonfirmasi. "
        "Rekomendasikan permintaan rekonsiliasi fiskal lengkap (SP2DK)."
    ),
    "ocf_mismatch": (
        "Arus Kas Operasi (AKO) terdeteksi {ratio:.1f}x lipat dari Laba Fiskal. "
        "Ketimpangan signifikan antara arus kas dan penghasilan kena pajak dapat "
        "mengindikasikan under-reporting penghasilan atau penggelembungan biaya. "
        "Disarankan cross-check AKO dengan SPT PPh Badan dan laporan keuangan."
    ),
    "peer_btd": (
        "BTD Ratio melampaui Q3 peer group sektor {sektor} tahun {tahun} "
        "({btd_pct:.1f}% vs. benchmark Q3 {q3_pct:.1f}%). Perlu analisis "
        "komparatif dengan industri sejenis."
    ),
    "peer_etr": (
        "GAAP ETR ({etr_pct:.1f}%) berada di bawah Q1 peer group sektor "
        "{sektor} ({q1_pct:.1f}%). Potensi perencanaan pajak agresif relatif "
        "terhadap pelaku usaha sebanding."
    ),
    "persistent": (
        "Pola BTD tinggi terdeteksi selama lebih dari satu tahun pajak "
        "berturut-turut (tahun {prev_year}–{tahun}). Anomali berulang "
        "meningkatkan risiko struktural; prioritas pemeriksaan mendalam."
    ),
}


def _build_red_flag(row: pd.Series, persist_bonus: float) -> str:
    """Compose the Indonesian-language red-flag narrative for a taxpayer-year.

    Args:
        row: Single row from the enriched DataFrame (must include all ratio
             and benchmark columns).
        persist_bonus: Pre-computed persistence bonus score for this row.

    Returns:
        Multi-sentence audit annotation string, or ``"Tidak ada indikasi
        anomali signifikan."`` when no flags are triggered.
    """
    flags: list[str] = []

    btd_ratio: float = row.get("btd_ratio", np.nan)
    gaap_etr: float = row.get("gaap_etr", np.nan)
    ocf_ratio: float = row.get("ocf_to_fiscal_ratio", np.nan)
    peer_btd_q3: float = row.get("peer_btd_q3", np.nan)
    peer_etr_q1: float = row.get("peer_etr_q1", np.nan)
    sektor: str = row.get("klu_sektor", "")
    tahun: int = int(row.get("tahun_pajak", 0))

    # Flag: High BTD (absolute)
    if not np.isnan(btd_ratio) and btd_ratio > 0.10:
        flags.append(
            _FLAG_TEMPLATES["high_btd"].format(btd_pct=btd_ratio * 100)
        )
    # Flag: Peer-relative BTD
    elif (
        not np.isnan(btd_ratio)
        and not np.isnan(peer_btd_q3)
        and btd_ratio > peer_btd_q3
        and btd_ratio > 0
    ):
        flags.append(
            _FLAG_TEMPLATES["peer_btd"].format(
                sektor=sektor,
                tahun=tahun,
                btd_pct=btd_ratio * 100,
                q3_pct=peer_btd_q3 * 100,
            )
        )

    # Flag: Low GAAP ETR (absolute)
    if not np.isnan(gaap_etr) and gaap_etr < 0.10:
        diff = STATUTORY_RATE - gaap_etr
        flags.append(
            _FLAG_TEMPLATES["low_etr"].format(
                etr_pct=gaap_etr * 100, diff_pct=diff * 100
            )
        )
    # Flag: Peer-relative low ETR
    elif (
        not np.isnan(gaap_etr)
        and not np.isnan(peer_etr_q1)
        and gaap_etr < peer_etr_q1
    ):
        flags.append(
            _FLAG_TEMPLATES["peer_etr"].format(
                sektor=sektor,
                etr_pct=gaap_etr * 100,
                q1_pct=peer_etr_q1 * 100,
            )
        )

    # Flag: OCF / Fiscal mismatch
    if not np.isnan(ocf_ratio) and ocf_ratio > 5:
        flags.append(
            _FLAG_TEMPLATES["ocf_mismatch"].format(ratio=ocf_ratio)
        )

    # Flag: Persistent anomaly
    if persist_bonus > 0:
        flags.append(
            _FLAG_TEMPLATES["persistent"].format(
                prev_year=tahun - 1, tahun=tahun
            )
        )

    if not flags:
        return "Tidak ada indikasi anomali signifikan."
    return " | ".join(flags)


# ---------------------------------------------------------------------------
# Main public scorer
# ---------------------------------------------------------------------------

def score_taxpayers(df: pd.DataFrame) -> pd.DataFrame:
    """Compute risk scores and audit annotations for all taxpayer-year rows.

    Expects *df* to have been processed by :func:`src.tax_calculator.calculate_ratios`
    and :func:`src.tax_calculator.add_peer_benchmarks`.

    New columns added:

    - ``risk_score``       : integer 0–100
    - ``risk_category``    : ``"HIGH RISK"`` | ``"MEDIUM"`` | ``"NORMAL"``
    - ``catatan_red_flag`` : Indonesian-language audit annotation

    Args:
        df: Enriched DataFrame with ratio and benchmark columns.

    Returns:
        New DataFrame with three additional scoring columns.

    Raises:
        KeyError: If required ratio/benchmark columns are missing.
    """
    required_cols = {
        "npwp_dummy", "tahun_pajak",
        "btd_ratio", "gaap_etr", "ocf_to_fiscal_ratio",
        "peer_btd_q3", "peer_etr_q1",
    }
    missing = required_cols - set(df.columns)
    if missing:
        raise KeyError(f"Missing columns required for scoring: {sorted(missing)}")

    df = df.copy().sort_values(["npwp_dummy", "tahun_pajak"]).reset_index(drop=True)

    risk_scores: list[float] = []
    risk_categories: list[str] = []
    red_flags: list[str] = []

    # Track per-(npwp, year) BTD sub-scores to compute persistence
    btd_score_history: dict[tuple[str, int], float] = {}

    for _, row in df.iterrows():
        npwp: str = str(row["npwp_dummy"])
        tahun: int = int(row["tahun_pajak"])

        # --- Sub-scores ---
        s_btd = _score_btd(row["btd_ratio"], row["peer_btd_q3"])
        s_etr = _score_etr(row["gaap_etr"], row["peer_etr_q1"])
        s_ocf = _score_ocf(row["ocf_to_fiscal_ratio"])
        s_persist = _score_persistence(npwp, tahun, btd_score_history)

        total = min(s_btd + s_etr + s_ocf + s_persist, 100.0)

        # Store for next-year persistence check
        btd_score_history[(npwp, tahun)] = s_btd

        # Category
        if total >= HIGH_RISK_THRESHOLD:
            category = "HIGH RISK"
        elif total >= MEDIUM_RISK_THRESHOLD:
            category = "MEDIUM"
        else:
            category = "NORMAL"

        risk_scores.append(round(total))
        risk_categories.append(category)
        red_flags.append(_build_red_flag(row, s_persist))

    df["risk_score"] = risk_scores
    df["risk_category"] = risk_categories
    df["catatan_red_flag"] = red_flags

    return df
