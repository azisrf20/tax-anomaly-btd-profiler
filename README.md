# 🔍 Tax Anomaly & BTD Profiler

> **Capstone Project — UNSIA**  
> Sistem Analitik Skrining Kepatuhan Pajak Badan Berbasis *Book-Tax Difference* dan *Effective Tax Rate*

---

## Daftar Isi

1. [Ringkasan Eksekutif](#1-ringkasan-eksekutif-latar-belakang-masalah)
2. [Arsitektur Sistem & Struktur Direktori](#2-arsitektur-sistem-struktur-direktori)
3. [Metodologi Analisis Fiskal & Risk Scoring](#3-metodologi-analisis-fiskal-risk-scoring)
4. [Panduan Instalasi & Menjalankan Aplikasi](#4-panduan-instalasi-menjalankan-aplikasi)
5. [Panduan Penggunaan Dashboard](#5-panduan-penggunaan-dashboard)
6. [Tata Kelola Keamanan & Privasi Data](#6-tata-kelola-keamanan-privasi-data)
7. [Hasil Pengujian Otomatis](#7-hasil-pengujian-otomatis)

---

## 1. Ringkasan Eksekutif & Latar Belakang Masalah

### Tantangan

Fiskus Direktorat Jenderal Pajak (DJP) menghadapi tantangan struktural dalam menyaring ribuan laporan pajak Wajib Pajak (WP) Badan secara manual sebelum menerbitkan **SP2DK** (*Surat Permintaan Penjelasan atas Data dan/atau Keterangan*). Proses ini rentan terhadap tiga kelemahan utama:

| Kelemahan | Dampak Operasional |
|---|---|
| Analisis spreadsheet ad-hoc | Tidak reprodusibel, rawan kesalahan manusia |
| Tidak ada benchmark peer-group | Penilaian risiko bersifat absolut, mengabaikan konteks industri |
| Narasi SP2DK ditulis manual | Membutuhkan waktu lama; inkonsistensi antar pemeriksa |

### Solusi

**Tax Anomaly & BTD Profiler** adalah sistem analitik berbasis Python + Streamlit yang secara otomatis:

- Menghitung empat rasio fiskal utama dari data SPT PPh Badan
- Membandingkan setiap WP terhadap *peer-group* sektoral (berdasarkan KLU)
- Menghasilkan **skor risiko 0–100** per WP per tahun pajak
- Menyusun **narasi SP2DK** dalam Bahasa Indonesia secara otomatis
- Mengekspor *kertas kerja penelitian* ke format `.xlsx` siap pakai

### Ruang Lingkup Dataset Demo

| Parameter | Nilai |
|---|---|
| Jumlah Wajib Pajak | 30 WP (WP-001 s.d. WP-030) |
| Tahun Pajak | 2023, 2024, 2025 |
| Total Rekaman | 90 baris |
| Anomali yang Disuntikkan | 7 kasus high-risk (3 BTD besar, 2 ETR rendah, 2 OCF/fiskal mismatch) |
| Sektor KLU | 4 sektor (lihat §3) |

---

## 2. Arsitektur Sistem & Struktur Direktori

```
CAPSTONE PROJECT/
│
├── app.py                      ← Dashboard Streamlit (UI utama)
├── run_app.bat                 ← Launcher Windows (auto-install + start)
├── requirements.txt            ← Dependensi Python
├── .bobignore                  ← Isolasi file data & kredensial
│
├── src/
│   ├── __init__.py
│   ├── data_generator.py       ← Generator dataset sintetis 90 baris
│   ├── tax_calculator.py       ← Kalkulasi rasio fiskal & peer benchmark
│   └── risk_scorer.py          ← Mesin skor risiko & generator narasi SP2DK
│
├── tests/
│   ├── __init__.py
│   └── test_calculator.py      ← 60 unit test (pytest)
│
└── data/
    └── dummy_wp_dataset.csv    ← Dataset sintetis (di-generate otomatis)
```

### Deskripsi Modul

#### `src/data_generator.py`
Menghasilkan dataset sintetis 90 baris dengan seed deterministik (`RANDOM_SEED = 42`) sehingga reproducible. Tiga fungsi injeksi anomali menyuntikkan kasus *high-risk* pada indeks baris terpilih:

| Fungsi | Jenis Anomali | Jumlah Kasus |
|---|---|---|
| `_inject_anomaly_persistent_btd()` | BTD Ratio > 20% dari total aset | 3 baris |
| `_inject_anomaly_low_gaap_etr()` | GAAP ETR < 5% (jauh di bawah 22%) | 2 baris |
| `_inject_anomaly_high_ocf_zero_fiscal()` | Rasio OCF/Fiskal > 50x | 2 baris |

#### `src/tax_calculator.py`
Dua fungsi publik yang dapat diimpor secara independen:

- **`calculate_ratios(df)`** — Menambahkan 4 kolom rasio (lihat §3). NaN-safe: ETR = NaN jika laba komersial ≤ 0; OCF/Fiskal = NaN jika laba fiskal ≤ 0.
- **`add_peer_benchmarks(df)`** — Menghitung statistik agregat per grup `(klu_sektor, tahun_pajak)` dan melakukan `merge` kembali ke DataFrame utama.

#### `src/risk_scorer.py`
Tiga komponen utama:

- **Sub-scorer functions** (`_score_btd`, `_score_etr`, `_score_ocf`, `_score_persistence`) — masing-masing mengembalikan nilai 0–25
- **`_build_red_flag()`** — Menyusun narasi audit dalam Bahasa Indonesia dari 6 template flag
- **`score_taxpayers(df)`** — Fungsi publik utama; mengembalikan DataFrame dengan kolom `risk_score`, `risk_category`, dan `catatan_red_flag`

#### `app.py`
Dashboard Streamlit 700+ baris dengan arsitektur rendering satu arah:

```
Sidebar controls → run_pipeline() [cached] → df_full
    → apply_filters → df_view
        → KPI strip → Charts → Audit table → Drill-down → Export
```

---

## 3. Metodologi Analisis Fiskal & Risk Scoring

### 3.1 Empat Rasio Fiskal Utama

#### Book-Tax Difference (BTD) Nominal

```
BTD_nominal = Laba_Komersial - Laba_Fiskal
```

Selisih antara laba menurut standar akuntansi (PSAK/IFRS) dan laba menurut fiskal. BTD positif menunjukkan bahwa perusahaan melaporkan laba lebih rendah secara fiskal dibanding akuntansi.

#### BTD Ratio (Dinormalisasi terhadap Total Aset)

```
BTD_ratio = BTD_nominal / Total_Aset
```

Normalisasi terhadap total aset memungkinkan perbandingan lintas ukuran perusahaan. Ambang batas kritis:

| BTD Ratio | Interpretasi |
|---|---|
| > 20% | Sangat signifikan — potensi rekayasa fiskal agresif |
| 10% – 20% | Signifikan — perlu verifikasi koreksi fiskal negatif |
| > Q3 peer group | Di atas 75th persentil industri — anomali relatif |
| > 0% | BTD positif wajar — skor rendah |

#### GAAP Effective Tax Rate (ETR)

```
GAAP_ETR = PPh_Terutang / Laba_Komersial
```

> **Catatan:** ETR ditetapkan sebagai `NaN` (tidak terdefinisi) bila `Laba_Komersial ≤ 0` untuk mencegah interpretasi yang menyesatkan.

Perbandingan terhadap tarif statutori PPh Badan Indonesia:

| GAAP ETR | Sub-skor ETR | Interpretasi |
|---|---|---|
| < 5% | 25 | Sangat rendah — indikasi penghindaran agresif |
| 5% – 10% | 20 | Rendah — jauh di bawah tarif normal |
| < Q1 peer | 15 | Di bawah 25th persentil industri |
| < 22% (statutori) | 8 | Sedikit di bawah tarif normal |
| ≥ 22% | 0 | Wajar |

#### Operating Cash Flow to Fiscal Income Ratio (OCF/Fiskal)

```
OCF_to_Fiscal = Arus_Kas_Operasi / Laba_Fiskal
```

> **Catatan:** Rasio ditetapkan `NaN` bila `Laba_Fiskal ≤ 0`.

Ketimpangan besar antara arus kas operasi yang tinggi dengan laba fiskal yang sangat rendah mengindikasikan kemungkinan *under-reporting* penghasilan atau penggelembungan biaya non-deductible.

| OCF/Fiskal Ratio | Sub-skor OCF | Interpretasi |
|---|---|---|
| > 20x | 25 | Ketimpangan ekstrem |
| 10x – 20x | 20 | Ketimpangan tinggi |
| 5x – 10x | 12 | Ketimpangan signifikan |
| 2x – 5x | 5 | Perlu perhatian |
| ≤ 2x | 0 | Wajar |

### 3.2 Peer-Group KLU Benchmarking

Empat sektor Klasifikasi Lapangan Usaha (KLU) yang didukung:

| Kode Sektor | Nama Sektor |
|---|---|
| `Perdagangan Besar` | Perdagangan besar, impor-ekspor |
| `Industri Pengolahan` | Manufaktur, pengolahan bahan baku |
| `Konstruksi` | Jasa konstruksi, EPC |
| `Energi & Pertambangan` | Migas, pertambangan mineral, kelistrikan |

Untuk setiap kombinasi `(klu_sektor, tahun_pajak)`, sistem menghitung:

| Statistik | Kolom Output | Digunakan Oleh |
|---|---|---|
| Median ETR peer | `peer_etr_median` | Chart 2 (box plot) |
| Q1 ETR peer (P25) | `peer_etr_q1` | Sub-skor ETR |
| Median BTD Ratio peer | `peer_btd_median` | Referensi |
| Q3 BTD Ratio peer (P75) | `peer_btd_q3` | Sub-skor BTD |

### 3.3 Sistem Skor Risiko (0–100)

#### Formula Agregasi

```
Risk_Score = min(S_BTD + S_ETR + S_OCF + S_Persistence, 100)
```

Masing-masing sub-skor memiliki rentang **0–25**, dengan total maksimum 100:

| Komponen | Rentang | Sumber |
|---|---|---|
| `S_BTD` | 0–25 | BTD Ratio vs. threshold absolut & peer Q3 |
| `S_ETR` | 0–25 | GAAP ETR vs. 22% & peer Q1 |
| `S_OCF` | 0–25 | Rasio OCF/Fiskal |
| `S_Persistence` | 0–25 | Bonus bila BTD tinggi selama ≥ 2 tahun berturut-turut |

#### Klasifikasi Risiko

| Kategori | Ambang Batas `Risk_Score` | Tindakan Rekomendasi |
|---|---|---|
| 🔴 **HIGH RISK** | ≥ 70 | Prioritas SP2DK + pemeriksaan mendalam |
| 🟡 **MEDIUM** | 40 – 69 | SP2DK konfirmasi + permintaan rekonsiliasi fiskal |
| 🟢 **NORMAL** | < 40 | Monitoring berkala |

#### Bonus Persistensi (OECD BEPS Alignment)

Terinspirasi panduan OECD BEPS Action 11, sistem memberikan bonus **+15 poin** apabila BTD sub-skor WP yang sama melebihi 10 pada tahun pajak sebelumnya. Anomali berulang lebih mengindikasikan strukturasi pajak yang disengaja dibandingkan kejadian satu kali.

### 3.4 Template Narasi Red Flag (SP2DK)

Sistem menghasilkan narasi audit dalam Bahasa Indonesia dari 6 template:

| Flag | Trigger Condition |
|---|---|
| `high_btd` | BTD Ratio > 10% dari total aset |
| `peer_btd` | BTD Ratio > Q3 peer group (tapi ≤ 10%) |
| `low_etr` | GAAP ETR < 10% |
| `peer_etr` | GAAP ETR < Q1 peer group (tapi ≥ 10%) |
| `ocf_mismatch` | OCF/Fiskal Ratio > 5x |
| `persistent` | BTD sub-skor > 10 selama ≥ 2 tahun berturut-turut |

---

## 4. Panduan Instalasi & Menjalankan Aplikasi

### Prasyarat

| Komponen | Versi Minimum |
|---|---|
| Python | 3.9+ (direkomendasikan 3.10+) |
| pip | 23.0+ |
| OS | Windows 10/11, macOS 12+, Ubuntu 22.04+ |

### Opsi A — Launcher Windows (Direkomendasikan)

Klik dua kali file **`run_app.bat`** di root direktori proyek.

Launcher akan secara otomatis:
1. Mendeteksi instalasi Python
2. Menginstall semua dependensi dari `requirements.txt`
3. Membuat dataset sintetis bila belum ada
4. Menjalankan aplikasi Streamlit di `http://localhost:8501`

### Opsi B — Terminal Manual

```bash
# 1. Clone atau ekstrak proyek ke direktori pilihan
cd "CAPSTONE PROJECT"

# 2. (Opsional) Buat virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# 3. Install dependensi
pip install -r requirements.txt

# 4. Generate dataset sintetis
python src/data_generator.py

# 5. Jalankan unit test untuk memverifikasi instalasi
pytest tests/test_calculator.py -v

# 6. Jalankan aplikasi dashboard
streamlit run app.py
```

Aplikasi akan tersedia di browser pada: **`http://localhost:8501`**

### Dependensi (`requirements.txt`)

| Package | Fungsi |
|---|---|
| `streamlit` | Framework UI dashboard interaktif |
| `pandas` | Manipulasi dan analisis data tabular |
| `numpy` | Komputasi numerik, operasi array |
| `plotly` | Visualisasi interaktif (scatter, box, waterfall) |
| `openpyxl` | Export kertas kerja ke format `.xlsx` |
| `pytest` | Framework unit testing otomatis |

---

## 5. Panduan Penggunaan Dashboard

### 5.1 Sidebar — Kontrol & Sumber Data

| Kontrol | Fungsi |
|---|---|
| **Sumber Data** | Pilih dataset bawaan (demo) atau unggah CSV/Excel sendiri |
| **Unduh Template CSV** | Download template 12 kolom dengan 1 baris contoh |
| **Tahun Pajak** | Filter multi-select: 2023, 2024, 2025 |
| **Sektor KLU** | Filter multi-select: 4 sektor industri |
| **Status Risiko** | Filter multi-select: HIGH RISK / MEDIUM / NORMAL |
| **Cari NPWP / Nama WP** | Pencarian substring, tidak case-sensitive |

### 5.2 KPI Strip (4 Kartu Metrik)

| Kartu | Metrik |
|---|---|
| **Total WP Dianalisis** | `nunique(npwp_dummy)` pada data terfilter |
| **Jumlah HIGH RISK** | Jumlah rekaman `risk_category == "HIGH RISK"` |
| **Total BTD Positif** | Jumlah `btd_nominal` di mana BTD > 0 (format IDR singkat) |
| **Rata-rata GAAP ETR** | Mean ETR + selisih ±pp terhadap tarif 22% |

### 5.3 Visualisasi Chart

| Chart | Jenis | Sumbu |
|---|---|---|
| **Chart 1** | Scatter plot | X: GAAP ETR (%), Y: BTD Ratio (%), Ukuran bubble: Risk Score |
| **Chart 2** | Box plot per sektor | X: Sektor KLU, Y: GAAP ETR (%), garis referensi 22% |

### 5.4 Drill-Down WP & Generator SP2DK

1. Pilih WP dari dropdown (diurutkan berdasarkan skor risiko tertinggi)
2. Lihat **trend 3 tahun** (BTD Ratio, GAAP ETR, Risk Score)
3. Lihat **waterfall rekonsiliasi fiskal** (Laba Komersial → Laba Fiskal)
4. Salin **draf poin SP2DK** dari text area

### 5.5 Export Kertas Kerja (.xlsx)

Klik tombol **"Export Kertas Kerja Penelitian (.xlsx)"** untuk mengunduh workbook berisi:

| Sheet | Konten |
|---|---|
| `Ringkasan Risiko` | Semua rekaman terfilter + skor + catatan SP2DK |
| `High Risk` | Hanya rekaman berkategori HIGH RISK |
| `Statistik Sektor` | Agregasi per sektor-tahun (jumlah WP, avg ETR, median BTD) |

### 5.6 Format File Upload

Kolom wajib dalam file CSV/Excel yang diunggah:

| Kolom | Tipe | Keterangan |
|---|---|---|
| `npwp_dummy` | String | Identifikasi WP (contoh: `WP-001`) |
| `nama_wp` | String | Nama perusahaan |
| `klu_sektor` | String | Salah satu dari 4 sektor yang didukung |
| `tahun_pajak` | Integer | Tahun pajak (contoh: `2024`) |
| `peredaran_usaha` | Numerik (IDR) | Total omset/peredaran usaha |
| `laba_komersial` | Numerik (IDR) | Laba sebelum koreksi fiskal |
| `koreksi_fiskal_positif` | Numerik (IDR) | Total koreksi fiskal yang menambah PKP |
| `koreksi_fiskal_negatif` | Numerik (IDR) | Total koreksi fiskal yang mengurangi PKP |
| `laba_fiskal` | Numerik (IDR) | Penghasilan Kena Pajak (PKP) |
| `pph_terutang` | Numerik (IDR) | PPh Badan terutang |
| `arus_kas_operasi` | Numerik (IDR) | Arus kas dari aktivitas operasi |
| `total_aset` | Numerik (IDR) | Total aset neraca |

> **Catatan Sanitasi:** Sistem secara otomatis membersihkan simbol mata uang (`Rp`, `IDR`), pemisah ribuan (`,`), dan spasi pada nilai numerik, sehingga data dari berbagai format spreadsheet dapat diterima.

---

## 6. Tata Kelola Keamanan & Privasi Data

### 6.1 Dataset Sintetis

Seluruh data yang digunakan dalam aplikasi demo bersifat **100% sintetis** dan dihasilkan secara prosedural oleh `src/data_generator.py` dengan menggunakan:

- **NumPy random generator** dengan seed tetap (`RANDOM_SEED = 42`) untuk reproducibility
- Nama perusahaan dari kombinasi prefix-suffix yang bersifat generik
- NPWP dalam format dummy (`WP-001` s.d. `WP-030`) — **bukan NPWP aktual**
- Semua nilai moneter dihasilkan dari distribusi acak dalam rentang realistis

**Tidak ada data wajib pajak nyata yang digunakan, disimpan, atau ditransmisikan.**

### 6.2 Isolasi File Data via `.bobignore`

File `.bobignore` mengecualikan aset sensitif dari indeks Bob/IDE:

```
data/*.csv      ← Dataset (nyata maupun sintetis) tidak diindeks
*.xlsx          ← File kertas kerja yang diekspor tidak diindeks
.env            ← Variabel lingkungan / kredensial tidak diindeks
```

### 6.3 Keamanan Aplikasi

| Aspek | Implementasi |
|---|---|
| **Tidak ada API eksternal berbayar** | Semua kalkulasi dilakukan lokal, tanpa koneksi ke layanan pihak ketiga |
| **Caching data** | `@st.cache_data` mencegah rekomputasi dan memori leak |
| **Validasi skema upload** | Kolom wajib diverifikasi sebelum pipeline dijalankan; pesan error eksplisit bila kolom tidak sesuai |
| **Sanitasi input** | `_sanitize_df()` membersihkan tipe data dan simbol sebelum kalkulasi aritmetika |
| **Tidak ada penyimpanan file** | File yang diunggah hanya diproses dalam memori (`io.BytesIO`), tidak ditulis ke disk |

### 6.4 Rekomendasi untuk Deployment Produksi

Bila sistem ini dikembangkan lebih lanjut untuk lingkungan produksi DJP, direkomendasikan:

1. **Enkripsi data at-rest** menggunakan AES-256 untuk penyimpanan dataset
2. **Autentikasi berbasis LDAP/SSO** DJP untuk kontrol akses
3. **Audit logging** setiap akses dan export kertas kerja
4. **Penyimpanan data** di lingkungan *on-premise* atau *private cloud* sesuai kebijakan keamanan informasi DJP
5. **Anonimisasi NPWP** di lingkungan development dan staging

---

## 7. Hasil Pengujian Otomatis

### Ringkasan Test Suite

```
pytest tests/test_calculator.py -v
```

| Kelas Pengujian | Jumlah Test | Status |
|---|---|---|
| `TestBtdFormulas` | 7 | ✅ Passed |
| `TestGaapEtr` | 5 | ✅ Passed |
| `TestOcfFiscalRatio` | 4 | ✅ Passed |
| `TestPeerBenchmarks` | 4 | ✅ Passed |
| `TestSubScorers` | 21 | ✅ Passed |
| `TestRiskThresholds` | 7 | ✅ Passed |
| `TestRedFlags` | 4 | ✅ Passed |
| `TestEndToEndPipeline` | 8 | ✅ Passed |
| **TOTAL** | **60** | **✅ 60/60 Passed** |

### Cakupan Pengujian

| Area | Skenario yang Diuji |
|---|---|
| Formula BTD | Nominal, ratio, positif/negatif/nol, NaN saat total aset = 0 |
| GAAP ETR | Standar, laba komersial = 0, laba komersial negatif, di atas/bawah statutori |
| OCF/Fiskal | Standar, laba fiskal = 0, laba fiskal negatif, rasio sangat tinggi |
| Peer benchmark | Kolom output hadir, median non-NaN, error handling kolom hilang |
| Sub-scorer BTD | 6 tier skor (0, 5, 12, 18, 25, NaN input) |
| Sub-scorer ETR | 6 tier skor (0, 8, 15, 20, 25, NaN input) |
| Sub-scorer OCF | 5 tier skor (0, 5, 12, 20, 25, NaN input) |
| Persistence | Bonus aktif, bonus nol tanpa prior, bonus nol saat prior rendah |
| Threshold kategori | HIGH RISK ≥ 70, MEDIUM 40–69, NORMAL < 40, skor capped 100 |
| Red flag | Narasi BTD tinggi, ETR rendah, OCF mismatch, kondisi normal |
| Pipeline E2E | 90 baris, semua kategori hadir, skor valid, format NPWP, 4 sektor, 3 tahun |

---

## Lisensi & Atribusi

Proyek ini dikembangkan sebagai **Capstone Project** program studi **Universitas Siber Indonesia (UNSIA)**.  
Dataset sepenuhnya sintetis. Metodologi risk scoring terinspirasi dari:

- **PMK-18/PMK.03/2021** tentang Pelaksanaan UU Cipta Kerja di bidang Perpajakan
- **OECD BEPS Action 11** — Measuring and Monitoring BEPS
- **Hanlon & Heitzman (2010)** — A Review of Tax Research

---

*Dibuat dengan IBM Bob · Python 3.9+ · Streamlit · Pandas · Plotly*
