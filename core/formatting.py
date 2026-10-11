"""Display formatting helpers (pure, no streamlit)."""


def fmt_duration(minutes: float) -> str:
    # H6: rounds the seconds part separately, so 3.999 -> "3:60".
    # Preserved as-is; fix pending decision.
    m = int(minutes)
    s = int(round((minutes - m) * 60))
    return f"{m}:{s:02d}"
