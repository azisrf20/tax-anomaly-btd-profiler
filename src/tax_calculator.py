"""Fiscal ratio calculator for corporate tax compliance analysis.

Computes derived tax ratios from raw taxpayer financial data and enriches
each row with peer-group benchmark statistics (median/quartile per sector
and tax year).

Typical usage::

    import pandas as pd
    from src.tax_calculator import calculate_ratios, add_peer_benchmarks

    df = pd.read_csv("data/dummy_wp_dataset.csv")
    df = calculate_ratios(df)
    df = add_peer_benchmarks(df)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Public ratio calculators
# ---------------------------------------------------------------------------

EPSILON = 1.0  # 1 IDR — avoids true zero-division while keeping semantics


def calculate_ratios(df: pd.DataFrame) -> pd.DataFrame:
    """Add four core fiscal ratios to *df* in-place and return it.

    Ratios added:

    - ``btd_nominal``       : laba_komersial − laba_fiskal
    - ``btd_ratio``         : btd_nominal / total_aset
    - ``gaap_etr``          : pph_terutang / laba_komersial  (NaN when
                              laba_komersial ≤ 0, because a negative or zero
                              commercial profit makes ETR meaningless)
    - ``ocf_to_fiscal_ratio``: arus_kas_operasi / laba_fiskal  (NaN when
                              laba_fiskal ≤ 0)

    Args:
        df: Raw taxpayer DataFrame.  Must contain the columns
            ``laba_komersial``, ``laba_fiskal``, ``total_aset``,
            ``pph_terutang``, and ``arus_kas_operasi``.

    Returns:
        The same DataFrame with four new ratio columns appended.

    Raises:
        KeyError: If a required source column is absent.
    """
    required = {
        "laba_komersial", "laba_fiskal", "total_aset",
        "pph_terutang", "arus_kas_operasi",
    }
    missing = required - set(df.columns)
    if missing:
        raise KeyError(f"Missing required columns: {sorted(missing)}")

    df = df.copy()

    df["btd_nominal"] = df["laba_komersial"] - df["laba_fiskal"]

    # btd_ratio — total_aset should never realistically be zero; guard anyway
    df["btd_ratio"] = df["btd_nominal"] / df["total_aset"].replace(0, np.nan)

    # gaap_etr — undefined / misleading for non-positive commercial profit
    laba_kom_safe = df["laba_komersial"].where(df["laba_komersial"] > 0, np.nan)
    df["gaap_etr"] = df["pph_terutang"] / laba_kom_safe

    # ocf_to_fiscal_ratio — undefined for non-positive taxable income
    laba_fis_safe = df["laba_fiskal"].where(df["laba_fiskal"] > 0, np.nan)
    df["ocf_to_fiscal_ratio"] = df["arus_kas_operasi"] / laba_fis_safe

    return df


def add_peer_benchmarks(df: pd.DataFrame) -> pd.DataFrame:
    """Augment *df* with sector-year peer-group benchmark columns.

    For each unique (``klu_sektor``, ``tahun_pajak``) group the following
    statistics are computed and merged back as new columns:

    - ``peer_etr_median``    : median GAAP ETR of the peer group
    - ``peer_etr_q1``        : 25th-percentile GAAP ETR of the peer group
    - ``peer_btd_median``    : median BTD ratio of the peer group
    - ``peer_btd_q3``        : 75th-percentile BTD ratio of the peer group

    Args:
        df: DataFrame that already contains ``gaap_etr`` and ``btd_ratio``
            columns (i.e. output of :func:`calculate_ratios`).

    Returns:
        A new DataFrame with four additional peer-benchmark columns.

    Raises:
        KeyError: If ``gaap_etr`` or ``btd_ratio`` are absent.
    """
    for col in ("gaap_etr", "btd_ratio", "klu_sektor", "tahun_pajak"):
        if col not in df.columns:
            raise KeyError(f"Column '{col}' is required but not found.")

    df = df.copy()

    group_keys = ["klu_sektor", "tahun_pajak"]

    benchmarks = (
        df.groupby(group_keys, observed=True)
        .agg(
            peer_etr_median=("gaap_etr", "median"),
            peer_etr_q1=("gaap_etr", lambda s: s.quantile(0.25)),
            peer_btd_median=("btd_ratio", "median"),
            peer_btd_q3=("btd_ratio", lambda s: s.quantile(0.75)),
        )
        .reset_index()
    )

    df = df.merge(benchmarks, on=group_keys, how="left")
    return df
