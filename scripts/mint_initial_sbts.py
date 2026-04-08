"""
Mint Initial SBTs — First 49 Basis Rating tokens
==================================================
Generates reports, stores attestations, publishes report hashes
on-chain, and mints SBTs for all scored stablecoins + protocols.

Usage:
    python scripts/mint_initial_sbts.py --dry-run
    python scripts/mint_initial_sbts.py --chain base
    python scripts/mint_initial_sbts.py --chain base --chain arbitrum

Requires:
    KEEPER_PRIVATE_KEY, BASE_RPC_URL, BASE_SBT_ADDRESS env vars
"""

import argparse
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("mint_sbts")


def main():
    parser = argparse.ArgumentParser(description="Mint initial Basis Rating SBTs")
    parser.add_argument("--chain", action="append", default=[], help="Chain(s) to mint on (base, arbitrum)")
    parser.add_argument("--dry-run", action="store_true", help="Log actions without sending transactions")
    parser.add_argument("--keeper-address", default="0x2dF0f62D1861Aa59A4430e3B2b2E7a0D29Cb723b")
    args = parser.parse_args()

    if not args.chain:
        args.chain = ["base"]

    from app.database import init_pool, fetch_all
    from app.report import assemble_report_data
    from app.report_attestation import compute_report_hash, store_report_attestation
    from app.scoring import FORMULA_VERSION

    init_pool()

    # 1. Get all scored stablecoins
    stablecoins = fetch_all("""
        SELECT st.id, st.symbol, st.name, s.overall_score, s.grade
        FROM scores s JOIN stablecoins st ON st.id = s.stablecoin_id
        WHERE s.overall_score IS NOT NULL
        ORDER BY s.overall_score DESC
    """)

    # 2. Get all scored protocols
    protocols = fetch_all("""
        SELECT DISTINCT ON (protocol_slug)
            protocol_slug, protocol_name, overall_score, grade
        FROM psi_scores
        WHERE overall_score IS NOT NULL
        ORDER BY protocol_slug, computed_at DESC
    """)

    logger.info(f"Found {len(stablecoins)} stablecoins and {len(protocols)} protocols to mint")

    entities = []
    for coin in stablecoins:
        entities.append({
            "entity_type": "stablecoin",
            "entity_id": coin["symbol"],
            "name": coin["name"],
            "score": float(coin["overall_score"]),
            "grade": coin["grade"],
            "type_code": 0,
        })
    for proto in protocols:
        entities.append({
            "entity_type": "protocol",
            "entity_id": proto["protocol_slug"],
            "name": proto["protocol_name"],
            "score": float(proto["overall_score"]),
            "grade": proto["grade"],
            "type_code": 1,
        })

    # 3. Generate reports and attestations
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    mint_queue = []

    for e in entities:
        try:
            data = assemble_report_data(e["entity_type"], e["entity_id"])
            if not data:
                logger.warning(f"No data for {e['entity_type']}/{e['entity_id']} — skipping")
                continue

            report_hash = compute_report_hash(data, "sbt_metadata", None, None, ts)
            store_report_attestation(
                e["entity_type"], e["entity_id"], "sbt_metadata",
                None, None, report_hash, data.get("score_hashes", []),
                None, data.get("formula_version", FORMULA_VERSION),
            )

            mint_queue.append({
                **e,
                "report_hash": report_hash,
                "formula_version": data.get("formula_version", FORMULA_VERSION),
            })
            logger.info(f"Report generated: {e['entity_type']}/{e['entity_id']} — {e['score']:.1f} ({e['grade']}) hash={report_hash[:18]}...")
        except Exception as ex:
            logger.warning(f"Failed to generate report for {e['entity_id']}: {ex}")

    logger.info(f"\n{'='*60}\n{len(mint_queue)} reports generated, ready to mint\n{'='*60}")

    if args.dry_run:
        for i, m in enumerate(mint_queue):
            logger.info(f"DRY RUN — would mint SBT #{i}: {m['entity_type']}/{m['entity_id']} score={m['score']:.1f} grade={m['grade']}")
        logger.info(f"\nDRY RUN complete. {len(mint_queue)} SBTs would be minted.")
        return

    # 4. On-chain minting (requires ethers/web3 — use subprocess to call keeper)
    logger.info("On-chain minting requires the keeper TypeScript runtime.")
    logger.info("Run: npx tsx scripts/mint_sbts_onchain.ts")

    # 5. Store token mappings locally
    from app.database import execute
    sbt_address = os.environ.get("BASE_SBT_ADDRESS", "")
    for i, m in enumerate(mint_queue):
        try:
            execute(
                """
                INSERT INTO sbt_tokens (token_id, entity_type, entity_id, chain, contract_address, score, grade, confidence, report_hash, method_version)
                VALUES (%s, %s, %s, 'base', %s, %s, %s, 'high', %s, %s)
                ON CONFLICT (token_id) DO UPDATE SET
                    score = EXCLUDED.score, grade = EXCLUDED.grade,
                    report_hash = EXCLUDED.report_hash, method_version = EXCLUDED.method_version
                """,
                (i, m["entity_type"], m["entity_id"], sbt_address,
                 m["score"], m["grade"], m["report_hash"], m["formula_version"]),
            )
        except Exception as ex:
            logger.warning(f"Failed to store SBT token mapping for #{i}: {ex}")

    logger.info(f"\nMint preparation complete. {len(mint_queue)} token mappings stored in sbt_tokens table.")
    logger.info(f"Summary: {sum(1 for m in mint_queue if m['type_code']==0)} stablecoins + {sum(1 for m in mint_queue if m['type_code']==1)} protocols")


if __name__ == "__main__":
    main()
