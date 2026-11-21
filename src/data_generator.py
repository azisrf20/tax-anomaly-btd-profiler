"""Synthetic Indonesian corporate taxpayer dataset generator.

Generates 90 rows (30 taxpayers × 3 tax years) with 7 intentionally
injected high-risk compliance anomaly cases.

Usage:
    python src/data_generator.py
"""

from __future__ import annotations

import os
import random
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
RANDOM_SEED = 42
NUM_TAXPAYERS = 30
TAX_YEARS = [2023, 2024, 2025]
STATUTORY_TAX_RATE = 0.22  # Indonesia PPh Badan rate

SECTORS = [
    "Perdagangan Besar",
    "Industri Pengolahan",
    "Konstruksi",
    "Energi & Pertambangan",
]

COMPANY_PREFIXES = [
    "PT Maju", "PT Sejahtera", "PT Nusantara", "PT Berkah", "PT Jaya",
    "PT Mandiri", "PT Utama", "PT Prima", "PT Sentosa", "PT Abadi",
]

COMPANY_SUFFIXES = [
    "Perkasa", "Makmur", "Lestari", "Mulia", "Agung",
    "Teknik", "Karya", "Niaga", "Sakti", "Global",
    "Indonesia", "Bersama", "Mitra", "Sejati", "Unggul",
]

OUTPUT_PATH = Path("data") / "dummy_wp_dataset.csv"


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------

def _build_base_row(
    npwp: str,
    nama: str,
    sektor: str,
    tahun: int,
    rng: np.random.Generator,
) -> dict:
    """Build a single *normal* baseline taxpayer-year row.

    Args:
        npwp: Dummy NPWP identifier string.
        nama: Taxpayer company name.
        sektor: Industry sector code.
        tahun: Tax year integer.
        rng: NumPy random generator for reproducibility.

    Returns:
        Dictionary of field values for the taxpayer-year.
    """
    peredaran_usaha = float(rng.integers(5_000_000_000, 500_000_000_000))
    laba_komersial = float(rng.uniform(0.03, 0.18)) * peredaran_usaha

    # Normal books: small positive BTD (koreksi fiskal net ~ 0–5% of laba_komersial)
    koreksi_fiskal_positif = float(rng.uniform(0.01, 0.08)) * laba_komersial
    koreksi_fiskal_negatif = float(rng.uniform(0.005, 0.04)) * laba_komersial
    laba_fiskal = laba_komersial + koreksi_fiskal_positif - koreksi_fiskal_negatif

    pph_terutang = laba_fiskal * STATUTORY_TAX_RATE
    arus_kas_operasi = float(rng.uniform(0.8, 1.4)) * laba_fiskal
    total_aset = float(rng.uniform(2.0, 8.0)) * peredaran_usaha

    return {
        "npwp_dummy": npwp,
        "nama_wp": nama,
        "klu_sektor": sektor,
        "tahun_pajak": tahun,
        "peredaran_usaha": round(peredaran_usaha),
        "laba_komersial": round(laba_komersial),
        "koreksi_fiskal_positif": round(koreksi_fiskal_positif),
        "koreksi_fiskal_negatif": round(koreksi_fiskal_negatif),
        "laba_fiskal": round(laba_fiskal),
        "pph_terutang": round(pph_terutang),
        "arus_kas_operasi": round(arus_kas_operasi),
        "total_aset": round(total_aset),
    }


def _inject_anomaly_persistent_btd(row: dict, rng: np.random.Generator) -> dict:
    """Anomaly type 1 — Persistent large positive BTD > 10 % of total assets.

    Books show high commercial profit but taxable income is dramatically
    reduced via inflated negative fiscal corrections.

    Args:
        row: Baseline row dictionary to mutate.
        rng: NumPy random generator.

    Returns:
        Mutated row with BTD anomaly injected.
    """
    total_aset = row["total_aset"]
    laba_komersial = row["laba_komersial"]
    # Set BTD > 15 % of total_aset by making laba_fiskal near-zero and
    # ensuring laba_komersial is large enough relative to total_aset.
    # Inflate laba_komersial to ~20–30 % of total_aset for a believable base.
    row["laba_komersial"] = round(float(rng.uniform(0.20, 0.30)) * total_aset)
    laba_komersial = row["laba_komersial"]
    # Drive laba_fiskal to near-zero (0.1–0.5 % of total_aset)
    row["laba_fiskal"] = round(float(rng.uniform(0.001, 0.005)) * total_aset)
    large_neg = laba_komersial - row["laba_fiskal"] + row["koreksi_fiskal_positif"]
    row["koreksi_fiskal_negatif"] = round(max(large_neg, 0))
    row["pph_terutang"] = round(row["laba_fiskal"] * STATUTORY_TAX_RATE)
    return row


def _inject_anomaly_low_gaap_etr(row: dict, rng: np.random.Generator) -> dict:
    """Anomaly type 2 — GAAP ETR well below 10 % (statutory 22 %).

    Tax paid is a tiny fraction of commercial profit, suggesting aggressive
    tax sheltering or under-reporting.

    Args:
        row: Baseline row dictionary to mutate.
        rng: NumPy random generator.

    Returns:
        Mutated row with low-ETR anomaly injected.
    """
    laba_komersial = row["laba_komersial"]
    # Set pph_terutang to < 5 % of laba_komersial
    row["pph_terutang"] = round(float(rng.uniform(0.01, 0.049)) * laba_komersial)
    # Reduce laba_fiskal to be consistent with tiny tax
    row["laba_fiskal"] = round(row["pph_terutang"] / STATUTORY_TAX_RATE)
    large_neg = row["laba_komersial"] - row["laba_fiskal"] + row["koreksi_fiskal_positif"]
    row["koreksi_fiskal_negatif"] = round(max(large_neg, 0))
    return row


def _inject_anomaly_high_ocf_zero_fiscal(row: dict, rng: np.random.Generator) -> dict:
    """Anomaly type 3 — High operating cash flow with near-zero taxable income.

    Strong cash generation yet almost no declared taxable profit signals
    potential income concealment or abusive deductions.

    Args:
        row: Baseline row dictionary to mutate.
        rng: NumPy random generator.

    Returns:
        Mutated row with OCF/fiscal mismatch injected.
    """
    peredaran_usaha = row["peredaran_usaha"]
    # High OCF — 20-40 % of revenue
    row["arus_kas_operasi"] = round(float(rng.uniform(0.20, 0.40)) * peredaran_usaha)
    # Near-zero laba_fiskal
    row["laba_fiskal"] = round(float(rng.uniform(0.001, 0.005)) * peredaran_usaha)
    row["pph_terutang"] = round(row["laba_fiskal"] * STATUTORY_TAX_RATE)
    large_neg = row["laba_komersial"] - row["laba_fiskal"] + row["koreksi_fiskal_positif"]
    row["koreksi_fiskal_negatif"] = round(max(large_neg, 0))
    return row


# ---------------------------------------------------------------------------
# Main generation
# ---------------------------------------------------------------------------

def generate_dataset(output_path: Path = OUTPUT_PATH) -> pd.DataFrame:
    """Generate and persist the synthetic taxpayer dataset.

    Creates 90 rows (30 taxpayers × 3 years).  Seven specific rows are
    mutated to inject high-risk compliance anomalies.

    Args:
        output_path: Destination path for the CSV file.

    Returns:
        Generated DataFrame (also saved to *output_path*).
    """
    rng = np.random.default_rng(RANDOM_SEED)
    random.seed(RANDOM_SEED)

    # Build taxpayer master — assign stable sector per company
    taxpayers: list[tuple[str, str, str]] = []
    names_used: set[str] = set()
    for i in range(1, NUM_TAXPAYERS + 1):
        npwp = f"WP-{i:03d}"
        while True:
            prefix = random.choice(COMPANY_PREFIXES)
            suffix = random.choice(COMPANY_SUFFIXES)
            nama = f"{prefix} {suffix}"
            if nama not in names_used:
                names_used.add(nama)
                break
        sektor = SECTORS[(i - 1) % len(SECTORS)]
        taxpayers.append((npwp, nama, sektor))

    # Build all 90 baseline rows
    rows: list[dict] = []
    for npwp, nama, sektor in taxpayers:
        for tahun in TAX_YEARS:
            rows.append(_build_base_row(npwp, nama, sektor, tahun, rng))

    # ----- Inject anomalies into 7 specific rows -----
    # Anomaly indices chosen to spread across different taxpayers and years
    anomaly_map: dict[int, str] = {
        3: "btd",      # WP-002, 2023 — persistent large BTD
        18: "btd",     # WP-007, 2023 — persistent large BTD
        33: "btd",     # WP-012, 2024 — persistent large BTD
        48: "etr",     # WP-017, 2024 — very low GAAP ETR
        63: "etr",     # WP-022, 2025 — very low GAAP ETR
        75: "ocf",     # WP-026, 2026 — high OCF / zero fiscal
        87: "ocf",     # WP-030, 2025 — high OCF / zero fiscal
    }

    anomaly_funcs = {
        "btd": _inject_anomaly_persistent_btd,
        "etr": _inject_anomaly_low_gaap_etr,
        "ocf": _inject_anomaly_high_ocf_zero_fiscal,
    }

    for idx, atype in anomaly_map.items():
        rows[idx] = anomaly_funcs[atype](rows[idx], rng)

    df = pd.DataFrame(rows)

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"[data_generator] Dataset saved -> {output_path}  ({len(df)} rows)")
    return df


if __name__ == "__main__":
    generate_dataset()
