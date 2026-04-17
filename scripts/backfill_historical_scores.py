"""
Backfill the historical score series for every supported index
(PSI, RPI, LSTI, BRI, DOHI, VSRI, CXRI, TTI) — Bucket A3.

Run:
    python scripts/backfill_historical_scores.py
    python scripts/backfill_historical_scores.py --index psi
    python scripts/backfill_historical_scores.py --index rpi --max-entities 5
"""

from __future__ import annotations

import argparse
import logging
import sys

from app.database import init_pool
from app.historical_score_backfill import (
    DEFINITION_MAP, backfill_all, backfill_index,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("backfill_historical_scores")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--index", choices=sorted(DEFINITION_MAP.keys()), default=None,
                   help="single index to backfill (default: all)")
    p.add_argument("--max-entities", type=int, default=None)
    p.add_argument("--max-weeks-per-entity", type=int, default=None)
    args = p.parse_args()

    init_pool()

    if args.index:
        result = backfill_index(args.index,
                                max_entities=args.max_entities,
                                max_weeks_per_entity=args.max_weeks_per_entity)
        logger.info("%s backfill: wrote rows for %d entities", args.index, len(result))
    else:
        result = backfill_all(max_entities=args.max_entities,
                              max_weeks_per_entity=args.max_weeks_per_entity)
        for kind, per_entity in result.items():
            total_rows = sum(per_entity.values())
            logger.info("%s: %d entities, %d rows", kind, len(per_entity), total_rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
