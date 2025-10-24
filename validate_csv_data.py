# validate_csv_data.py
from pathlib import Path
import pandas as pd

# --- CONFIG ---
INPUT_FILE = Path(r"infra/data/EURUSD_M15_2025-10-01_to-2025-10-23_UTC.csv.csv")  # <- your actual file
TF_MINUTES = 15
OUT_CLEAN = Path(r"infra/data/eurusd_m15_clean.csv")
OUT_ARTIFACT = Path(r"artifacts/data_quality_EURUSD_REAL.json")

def main():
    p = INPUT_FILE
    if not p.exists():
        raise FileNotFoundError(f"File not found: {p}")

    df = pd.read_csv(p)
    print("Columns found:", list(df.columns))

    # standardize column names
    df.columns = [c.strip().lower() for c in df.columns]

    # try to locate a time column
    time_candidates = ["utc", "datetime", "date", "time", "timestamp"]
    time_col = next((c for c in time_candidates if c in df.columns), None)
    if time_col is None:
        raise ValueError("No recognizable datetime columns found (looked for UTC/Datetime/Date/Time/Timestamp).")

    # parse time → UTC
    # allow many formats; coerce errors to NaT
    df[time_col] = pd.to_datetime(df[time_col], errors="coerce", utc=True)
    df = df.dropna(subset=[time_col])
    df = df.sort_values(time_col)

    # map price/volume columns (case-insensitive)
    def pick(*names):
        for n in names:
            if n in df.columns:
                return n
        return None

    open_col  = pick("open","bidopen","askopen")
    high_col  = pick("high","bidhigh","askhigh")
    low_col   = pick("low","bidlow","asklow")
    close_col = pick("close","bidclose","askclose")
    vol_col   = pick("volume","vol","tickvol","tick_volume")

    needed = [open_col, high_col, low_col, close_col]
    if any(c is None for c in needed):
        raise ValueError("Could not find open/high/low/close columns.")

    # keep only what we need
    keep = [time_col, open_col, high_col, low_col, close_col] + ([vol_col] if vol_col else [])
    clean = df[keep].copy()

    # rename to canonical names
    rename_map = {
        time_col: "timestamp_utc",
        open_col: "open",
        high_col: "high",
        low_col: "low",
        close_col: "close",
    }
    if vol_col:
        rename_map[vol_col] = "volume"
    clean = clean.rename(columns=rename_map)

    # enforce numeric OHLC
    for c in ["open","high","low","close"]:
        clean[c] = pd.to_numeric(clean[c], errors="coerce")
    clean = clean.dropna(subset=["open","high","low","close"])

    # sanity: OHLC relationships
    bad_ohlc = ((clean["high"] < clean[["open","close"]].max(axis=1)) |
                (clean["low"]  > clean[["open","close"]].min(axis=1))).sum()

    # compute gaps (minutes between rows)
    clean = clean.sort_values("timestamp_utc")
    diff_min = clean["timestamp_utc"].diff().dt.total_seconds().div(60).fillna(TF_MINUTES)
    gaps = (diff_min != TF_MINUTES).sum()

    # write outputs
    OUT_CLEAN.parent.mkdir(parents=True, exist_ok=True)
    OUT_ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    clean.to_csv(OUT_CLEAN, index=False)

    artifact = {
        "input_file": str(p),
        "rows_final": int(len(clean)),
        "gaps_detected": int(gaps),
        "bad_ohlc_rows": int(bad_ohlc),
        "first_timestamp_utc": clean["timestamp_utc"].iloc[0].isoformat(),
        "last_timestamp_utc": clean["timestamp_utc"].iloc[-1].isoformat(),
        "timeframe_minutes": TF_MINUTES,
        "columns": list(clean.columns),
        "notes": "Cleaned CSV ready for pipeline ingestion.",
    }
    import json
    with open(OUT_ARTIFACT, "w", encoding="utf-8") as f:
        json.dump(artifact, f, indent=2)

    print(f"✅ Saved clean file: {OUT_CLEAN}")
    print(f"✅ Wrote artifact: {OUT_ARTIFACT}")
    print("\n--- SUMMARY ---")
    print(f"Rows (final): {len(clean)}")
    print(f"Gaps detected: {gaps}")
    print(f"Bad OHLC rows: {bad_ohlc}")

if __name__ == "__main__":
    main()
