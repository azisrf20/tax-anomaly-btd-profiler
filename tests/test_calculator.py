"""Pytest unit tests for tax_calculator and risk_scorer modules.

Covers:
- BTD formula correctness (nominal & ratio)
- GAAP ETR edge cases (zero commercial profit, negative commercial profit,
  normal case, low-ETR anomaly)
- OCF-to-fiscal ratio edge cases
- Peer benchmark column creation
- Risk score threshold boundaries (HIGH RISK / MEDIUM / NORMAL)
- Red-flag narrative generation for each anomaly type
- End-to-end pipeline smoke test against generated dataset

Run::

    pytest tests/test_calculator.py -v
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

# Allow running from project root without package installation
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.tax_calculator import calculate_ratios, add_peer_benchmarks
from src.risk_scorer import (
    _score_btd,
    _score_etr,
    _score_ocf,
    _score_persistence,
    score_taxpayers,
    HIGH_RISK_THRESHOLD,
    MEDIUM_RISK_THRESHOLD,
    STATUTORY_RATE,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_df(**overrides) -> pd.DataFrame:
    """Return a minimal single-row DataFrame with sane defaults.

    Keyword args override specific column values.
    """
    defaults = {
        "npwp_dummy": "WP-TEST",
        "nama_wp": "PT Test",
        "klu_sektor": "Konstruksi",
        "tahun_pajak": 2024,
        "peredaran_usaha": 100_000_000_000,
        "laba_komersial": 10_000_000_000,
        "koreksi_fiskal_positif": 500_000_000,
        "koreksi_fiskal_negatif": 200_000_000,
        "laba_fiskal": 10_300_000_000,
        "pph_terutang": 2_266_000_000,
        "arus_kas_operasi": 11_000_000_000,
        "total_aset": 50_000_000_000,
    }
    defaults.update(overrides)
    return pd.DataFrame([defaults])


@pytest.fixture()
def normal_df() -> pd.DataFrame:
    """Standard single-row DataFrame with no anomalies."""
    return _make_df()


@pytest.fixture()
def multi_sector_df() -> pd.DataFrame:
    """Four-row DataFrame spanning two sectors and two years for benchmarks."""
    rows = [
        {
            "npwp_dummy": f"WP-{i:03d}", "nama_wp": f"PT X{i}",
            "klu_sektor": "Perdagangan Besar" if i <= 2 else "Konstruksi",
            "tahun_pajak": 2023 if i % 2 == 1 else 2024,
            "peredaran_usaha": 100_000_000_000,
            "laba_komersial": 10_000_000_000,
            "koreksi_fiskal_positif": 500_000_000,
            "koreksi_fiskal_negatif": 200_000_000,
            "laba_fiskal": 10_300_000_000,
            "pph_terutang": 2_266_000_000,
            "arus_kas_operasi": 11_000_000_000,
            "total_aset": 50_000_000_000,
        }
        for i in range(1, 5)
    ]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# BTD formula tests
# ---------------------------------------------------------------------------

class TestBtdFormulas:
    """Verify correctness of btd_nominal and btd_ratio calculations."""

    def test_btd_nominal_standard(self, normal_df):
        """btd_nominal = laba_komersial - laba_fiskal."""
        result = calculate_ratios(normal_df)
        expected = 10_000_000_000 - 10_300_000_000
        assert result.loc[0, "btd_nominal"] == expected

    def test_btd_ratio_standard(self, normal_df):
        """btd_ratio = btd_nominal / total_aset."""
        result = calculate_ratios(normal_df)
        expected = (10_000_000_000 - 10_300_000_000) / 50_000_000_000
        assert pytest.approx(result.loc[0, "btd_ratio"], rel=1e-6) == expected

    def test_btd_positive_when_commercial_exceeds_fiscal(self):
        """Positive BTD when laba_komersial > laba_fiskal."""
        df = _make_df(laba_komersial=15_000_000_000, laba_fiskal=5_000_000_000)
        result = calculate_ratios(df)
        assert result.loc[0, "btd_nominal"] == 10_000_000_000

    def test_btd_negative_when_fiscal_exceeds_commercial(self):
        """Negative BTD when laba_fiskal > laba_komersial."""
        df = _make_df(laba_komersial=5_000_000_000, laba_fiskal=10_000_000_000)
        result = calculate_ratios(df)
        assert result.loc[0, "btd_nominal"] == -5_000_000_000

    def test_btd_zero_when_equal(self):
        """BTD is exactly zero when both profit figures are equal."""
        val = 10_000_000_000
        df = _make_df(laba_komersial=val, laba_fiskal=val)
        result = calculate_ratios(df)
        assert result.loc[0, "btd_nominal"] == 0
        assert result.loc[0, "btd_ratio"] == pytest.approx(0.0)

    def test_btd_ratio_nan_when_total_aset_zero(self):
        """btd_ratio must be NaN when total_aset is zero."""
        df = _make_df(total_aset=0)
        result = calculate_ratios(df)
        assert np.isnan(result.loc[0, "btd_ratio"])

    def test_btd_high_ratio_exceeds_10_pct(self):
        """Large BTD (>10 % of total_aset) is correctly captured."""
        df = _make_df(
            laba_komersial=20_000_000_000,
            laba_fiskal=1_000_000_000,
            total_aset=50_000_000_000,
        )
        result = calculate_ratios(df)
        assert result.loc[0, "btd_ratio"] > 0.10


# ---------------------------------------------------------------------------
# GAAP ETR edge-case tests
# ---------------------------------------------------------------------------

class TestGaapEtr:
    """Verify GAAP ETR for normal, zero, and negative commercial profit."""

    def test_etr_standard(self, normal_df):
        """Standard ETR = pph_terutang / laba_komersial."""
        result = calculate_ratios(normal_df)
        expected = 2_266_000_000 / 10_000_000_000
        assert pytest.approx(result.loc[0, "gaap_etr"], rel=1e-6) == expected

    def test_etr_nan_when_zero_commercial_profit(self):
        """gaap_etr must be NaN when laba_komersial is zero (undefined)."""
        df = _make_df(laba_komersial=0, pph_terutang=0)
        result = calculate_ratios(df)
        assert np.isnan(result.loc[0, "gaap_etr"])

    def test_etr_nan_when_negative_commercial_profit(self):
        """gaap_etr must be NaN when laba_komersial is negative (misleading)."""
        df = _make_df(laba_komersial=-5_000_000_000, pph_terutang=0)
        result = calculate_ratios(df)
        assert np.isnan(result.loc[0, "gaap_etr"])

    def test_etr_below_statutory_rate_is_valid(self):
        """ETR can legitimately be computed even when it is below 22 %."""
        df = _make_df(pph_terutang=500_000_000, laba_komersial=10_000_000_000)
        result = calculate_ratios(df)
        assert result.loc[0, "gaap_etr"] == pytest.approx(0.05)

    def test_etr_above_statutory_rate_is_valid(self):
        """ETR above 22 % (e.g. penalties included) is computed correctly."""
        df = _make_df(pph_terutang=3_000_000_000, laba_komersial=10_000_000_000)
        result = calculate_ratios(df)
        assert result.loc[0, "gaap_etr"] == pytest.approx(0.30)


# ---------------------------------------------------------------------------
# OCF / Fiscal ratio tests
# ---------------------------------------------------------------------------

class TestOcfFiscalRatio:
    """Verify ocf_to_fiscal_ratio calculation and edge cases."""

    def test_ocf_standard(self, normal_df):
        result = calculate_ratios(normal_df)
        expected = 11_000_000_000 / 10_300_000_000
        assert pytest.approx(result.loc[0, "ocf_to_fiscal_ratio"], rel=1e-6) == expected

    def test_ocf_nan_when_laba_fiskal_zero(self):
        """ocf_to_fiscal_ratio must be NaN when laba_fiskal is zero."""
        df = _make_df(laba_fiskal=0)
        result = calculate_ratios(df)
        assert np.isnan(result.loc[0, "ocf_to_fiscal_ratio"])

    def test_ocf_nan_when_laba_fiskal_negative(self):
        """ocf_to_fiscal_ratio must be NaN when laba_fiskal is negative."""
        df = _make_df(laba_fiskal=-1_000_000_000)
        result = calculate_ratios(df)
        assert np.isnan(result.loc[0, "ocf_to_fiscal_ratio"])

    def test_ocf_high_ratio_captured(self):
        """Very high OCF/fiscal (> 20x) is correctly computed."""
        df = _make_df(arus_kas_operasi=20_000_000_000, laba_fiskal=500_000_000)
        result = calculate_ratios(df)
        assert result.loc[0, "ocf_to_fiscal_ratio"] == pytest.approx(40.0)


# ---------------------------------------------------------------------------
# Peer benchmark tests
# ---------------------------------------------------------------------------

class TestPeerBenchmarks:
    """Verify sector-year peer benchmark columns are created correctly."""

    def test_peer_columns_exist(self, multi_sector_df):
        df = calculate_ratios(multi_sector_df)
        df = add_peer_benchmarks(df)
        for col in ("peer_etr_median", "peer_etr_q1", "peer_btd_median", "peer_btd_q3"):
            assert col in df.columns, f"Missing benchmark column: {col}"

    def test_peer_etr_median_non_nan(self, multi_sector_df):
        df = calculate_ratios(multi_sector_df)
        df = add_peer_benchmarks(df)
        assert df["peer_etr_median"].notna().all()

    def test_missing_gaap_etr_raises(self, multi_sector_df):
        """add_peer_benchmarks must raise KeyError if gaap_etr is absent."""
        with pytest.raises(KeyError):
            add_peer_benchmarks(multi_sector_df)  # ratios not calculated yet

    def test_missing_source_column_raises(self):
        """calculate_ratios must raise KeyError for missing columns."""
        df = pd.DataFrame([{"laba_komersial": 1}])
        with pytest.raises(KeyError):
            calculate_ratios(df)


# ---------------------------------------------------------------------------
# Risk score sub-scorer tests
# ---------------------------------------------------------------------------

class TestSubScorers:
    """Unit tests for each individual sub-scoring function."""

    # BTD scorer
    def test_btd_score_max_above_20pct(self):
        assert _score_btd(0.25, 0.05) == 25.0

    def test_btd_score_18_between_10_and_20pct(self):
        assert _score_btd(0.15, 0.05) == 18.0

    def test_btd_score_12_above_q3(self):
        assert _score_btd(0.08, 0.05) == 12.0

    def test_btd_score_5_small_positive(self):
        assert _score_btd(0.01, 0.05) == 5.0

    def test_btd_score_0_negative(self):
        assert _score_btd(-0.01, 0.05) == 0.0

    def test_btd_score_0_nan_input(self):
        assert _score_btd(np.nan, 0.05) == 0.0

    # ETR scorer
    def test_etr_score_max_below_5pct(self):
        assert _score_etr(0.03, 0.15) == 25.0

    def test_etr_score_20_between_5_and_10pct(self):
        assert _score_etr(0.07, 0.15) == 20.0

    def test_etr_score_15_below_peer_q1(self):
        assert _score_etr(0.12, 0.15) == 15.0

    def test_etr_score_8_below_statutory(self):
        assert _score_etr(0.18, 0.10) == 8.0

    def test_etr_score_0_at_or_above_statutory(self):
        assert _score_etr(0.22, 0.10) == 0.0

    def test_etr_score_0_nan(self):
        assert _score_etr(np.nan, 0.15) == 0.0

    # OCF scorer
    def test_ocf_score_max_above_20x(self):
        assert _score_ocf(25.0) == 25.0

    def test_ocf_score_20_above_10x(self):
        assert _score_ocf(12.0) == 20.0

    def test_ocf_score_12_above_5x(self):
        assert _score_ocf(7.0) == 12.0

    def test_ocf_score_5_above_2x(self):
        assert _score_ocf(3.0) == 5.0

    def test_ocf_score_0_below_2x(self):
        assert _score_ocf(1.5) == 0.0

    def test_ocf_score_0_nan(self):
        assert _score_ocf(np.nan) == 0.0

    # Persistence scorer
    def test_persistence_bonus_when_prior_btd_high(self):
        history = {("WP-001", 2023): 18.0}
        bonus = _score_persistence("WP-001", 2024, history)
        assert bonus == 15.0

    def test_persistence_zero_when_no_prior(self):
        bonus = _score_persistence("WP-001", 2024, {})
        assert bonus == 0.0

    def test_persistence_zero_when_prior_btd_low(self):
        history = {("WP-001", 2023): 5.0}
        bonus = _score_persistence("WP-001", 2024, history)
        assert bonus == 0.0


# ---------------------------------------------------------------------------
# Risk score threshold tests
# ---------------------------------------------------------------------------

class TestRiskThresholds:
    """Verify that the right category is assigned at boundary scores."""

    def _full_pipeline(self, **overrides) -> pd.Series:
        """Run the full three-stage pipeline and return the first result row."""
        df = _make_df(**overrides)
        df = calculate_ratios(df)
        df = add_peer_benchmarks(df)
        df = score_taxpayers(df)
        return df.iloc[0]

    def test_high_risk_threshold_is_70(self):
        assert HIGH_RISK_THRESHOLD == 70

    def test_medium_risk_threshold_is_40(self):
        assert MEDIUM_RISK_THRESHOLD == 40

    def test_statutory_rate_is_22pct(self):
        assert STATUTORY_RATE == pytest.approx(0.22)

    def test_high_risk_category_for_extreme_btd(self):
        """Large BTD + very low ETR must yield HIGH RISK."""
        row = self._full_pipeline(
            laba_komersial=20_000_000_000,
            laba_fiskal=200_000_000,
            pph_terutang=44_000_000,          # ETR ~ 0.22 % of commercial
            arus_kas_operasi=18_000_000_000,   # OCF ~ 90x fiscal
            total_aset=50_000_000_000,
        )
        assert row["risk_category"] == "HIGH RISK"
        assert row["risk_score"] >= HIGH_RISK_THRESHOLD

    def test_normal_category_for_compliant_taxpayer(self):
        """A taxpayer at the statutory ETR with zero BTD must be NORMAL."""
        fiscal = 10_000_000_000
        row = self._full_pipeline(
            laba_komersial=fiscal,
            laba_fiskal=fiscal,
            pph_terutang=int(fiscal * 0.22),
            arus_kas_operasi=int(fiscal * 1.1),
            total_aset=50_000_000_000,
        )
        assert row["risk_category"] == "NORMAL"

    def test_risk_score_capped_at_100(self):
        """risk_score must never exceed 100."""
        row = self._full_pipeline(
            laba_komersial=20_000_000_000,
            laba_fiskal=1,
            pph_terutang=1,
            arus_kas_operasi=20_000_000_000,
            total_aset=50_000_000_000,
        )
        assert row["risk_score"] <= 100

    def test_risk_score_non_negative(self):
        """risk_score must never be negative."""
        row = self._full_pipeline()
        assert row["risk_score"] >= 0


# ---------------------------------------------------------------------------
# Red-flag narrative tests
# ---------------------------------------------------------------------------

class TestRedFlags:
    """Spot-check catatan_red_flag content for key anomaly types."""

    def _score_df(self, **overrides) -> pd.Series:
        df = _make_df(**overrides)
        df = calculate_ratios(df)
        df = add_peer_benchmarks(df)
        df = score_taxpayers(df)
        return df.iloc[0]

    def test_high_btd_flag_in_catatan(self):
        row = self._score_df(
            laba_komersial=20_000_000_000,
            laba_fiskal=500_000_000,
            total_aset=50_000_000_000,
        )
        assert "BTD" in row["catatan_red_flag"] or "Book-Tax" in row["catatan_red_flag"]

    def test_low_etr_flag_in_catatan(self):
        row = self._score_df(
            laba_komersial=10_000_000_000,
            laba_fiskal=1_000_000_000,
            pph_terutang=100_000_000,     # ETR = 1 % of commercial
        )
        assert "ETR" in row["catatan_red_flag"] or "SP2DK" in row["catatan_red_flag"]

    def test_ocf_flag_in_catatan(self):
        row = self._score_df(
            arus_kas_operasi=20_000_000_000,
            laba_fiskal=500_000_000,
        )
        assert "Arus Kas" in row["catatan_red_flag"] or "AKO" in row["catatan_red_flag"]

    def test_no_flag_for_compliant_taxpayer(self):
        fiscal = 10_000_000_000
        row = self._score_df(
            laba_komersial=fiscal,
            laba_fiskal=fiscal,
            pph_terutang=int(fiscal * 0.22),
            arus_kas_operasi=int(fiscal * 1.1),
        )
        assert row["catatan_red_flag"] == "Tidak ada indikasi anomali signifikan."


# ---------------------------------------------------------------------------
# End-to-end pipeline smoke test
# ---------------------------------------------------------------------------

class TestEndToEndPipeline:
    """Run the full three-stage pipeline against the generated CSV."""

    @pytest.fixture(scope="class", autouse=True)
    def generate_dataset(self):
        """Ensure the synthetic dataset exists before tests run."""
        from src.data_generator import generate_dataset
        generate_dataset()

    def test_csv_has_90_rows(self):
        df = pd.read_csv("data/dummy_wp_dataset.csv")
        assert len(df) == 90

    def test_pipeline_produces_90_scored_rows(self):
        df = pd.read_csv("data/dummy_wp_dataset.csv")
        df = calculate_ratios(df)
        df = add_peer_benchmarks(df)
        df = score_taxpayers(df)
        assert len(df) == 90

    def test_all_risk_categories_present(self):
        """At least one HIGH RISK row must exist due to injected anomalies."""
        df = pd.read_csv("data/dummy_wp_dataset.csv")
        df = calculate_ratios(df)
        df = add_peer_benchmarks(df)
        df = score_taxpayers(df)
        assert "HIGH RISK" in df["risk_category"].values

    def test_no_null_risk_scores(self):
        df = pd.read_csv("data/dummy_wp_dataset.csv")
        df = calculate_ratios(df)
        df = add_peer_benchmarks(df)
        df = score_taxpayers(df)
        assert df["risk_score"].notna().all()

    def test_all_scores_in_valid_range(self):
        df = pd.read_csv("data/dummy_wp_dataset.csv")
        df = calculate_ratios(df)
        df = add_peer_benchmarks(df)
        df = score_taxpayers(df)
        assert (df["risk_score"] >= 0).all()
        assert (df["risk_score"] <= 100).all()

    def test_all_npwp_formats_correct(self):
        """All NPWP dummies must follow WP-NNN format."""
        df = pd.read_csv("data/dummy_wp_dataset.csv")
        assert df["npwp_dummy"].str.match(r"^WP-\d{3}$").all()

    def test_four_sectors_present(self):
        df = pd.read_csv("data/dummy_wp_dataset.csv")
        expected = {
            "Perdagangan Besar", "Industri Pengolahan",
            "Konstruksi", "Energi & Pertambangan",
        }
        assert set(df["klu_sektor"].unique()) == expected

    def test_three_tax_years_present(self):
        df = pd.read_csv("data/dummy_wp_dataset.csv")
        assert set(df["tahun_pajak"].unique()) == {2023, 2024, 2025}
