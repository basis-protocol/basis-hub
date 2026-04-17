"""
Backfill the last 30 days of consequential events into
`track_record_commitments` (Bucket A1 acceptance criteria).

This sweeps the existing source tables (deviation_events, scores history,
rpi_scores history, coherence_reports) and writes any qualifying event
that isn't already present. The keeper picks them up in its next cycle
and anchors them on-chain.

Run:
    python scripts/backfill_track_record_events.py --days 30
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone

from app.database import init_pool
from app.track_record import (
    detect_coherence_drops,
    detect_divergence_signals,
    detect_rpi_delta_events,
    detect_score_change_events,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("backfill_track_record")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=30, help="lookback window")
    p.add_argument("--min-score-delta", type=float, default=5.0)
    p.add_argument("--min-rpi-delta", type=float, default=10.0)
    args = p.parse_args()

    init_pool()

    hours = args.days * 24
    counts = {
        "divergence":     detect_divergence_signals(lookback_hours=hours),
        "rpi_delta":      detect_rpi_delta_events(min_delta=args.min_rpi_delta, lookback_days=args.days),
        "coherence_drop": detect_coherence_drops(lookback_hours=hours),
        "score_change":   detect_score_change_events(min_delta=args.min_score_delta, lookback_hours=hours),
    }
    total = sum(counts.values())
    logger.info("Backfill complete: %s (total=%d)", counts, total)

    if total < 10:
        logger.warning(
            "Detected %d events — fewer than the 10 required by the A1 acceptance "
            "criteria. Either widen the window or relax the thresholds.", total,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
