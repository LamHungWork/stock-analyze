"""
config.py — Central configuration for VN30 Technical Analysis Tool
"""
import os

# ── VN30 Symbol List ──────────────────────────────────────────────────────────
VN30_SYMBOLS = [
    "ACB", "BID", "BVH", "CTG", "FPT",
    "GAS", "GVR", "HDB", "HPG", "KDH",
    "MBB", "MSN", "MWG", "NVL", "PDR",
    "PLX", "PNJ", "POW", "SAB", "SSI",
    "STB", "TCB", "TPB", "VCB", "VHM",
    "VIC", "VJC", "VNM", "VPB", "VRE",
]

# ── API Rate Limiting ────────────────────────────────────────────────────────
# VCI guest: 20 req/min. Each symbol needs 1 fetch → ~30 req for full VN30 run.
# A 3-second pause keeps us comfortably under the limit.
INTER_SYMBOL_DELAY_SECONDS = 3

# ── Technical Indicator Parameters ───────────────────────────────────────────
SMA_PERIOD = 20
VOLUME_SPIKE_RATIO = 1.2        # volume > 1.2x avg → spike
FIB_LOOKBACK_MONTHS = 6         # look back 6 months for swing detection
SWING_DETECTION_WINDOW = 5      # W=5 bars on each side for swing high/low
FIB_PROXIMITY_PCT = 0.015       # ±1.5% proximity to fib level

# ── Fibonacci Levels ──────────────────────────────────────────────────────────
FIB_LEVELS = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]

# ── File Paths ────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
SUMMARY_CSV_PATH = os.path.join(REPORTS_DIR, "SUMMARY_REPORT.csv")
LOG_PATH = os.path.join(REPORTS_DIR, "run.log")

# ── CSV Column Definitions ────────────────────────────────────────────────────
CSV_COLUMNS = [
    "Ngay",
    "Ma",
    "Gia_Hien_Tai",
    "Du_Doan",
    "Target",
    "Stoploss",
    "RR_Ratio",
    "Ti_Le_Thanh_Cong",
    "Ket_Qua",
]
