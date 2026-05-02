"""
RPI Snapshot Collector
=======================
Scrapes governance proposals from Snapshot GraphQL API.
Classifies proposals as risk-related via keyword matching.
Extracts budget amounts where possible.
"""

import logging
import time
from datetime import datetime, timezone

import requests

from app.database import execute, fetch_one, fetch_one_async, fetch_all_async, execute_async
from app.index_definitions.rpi_v2 import RPI_TARGET_PROTOCOLS

logger = logging.getLogger(__name__)

SNAPSHOT_API = "https://hub.snapshot.org/graphql"

# Snapshot space IDs for each protocol
# Reuses the same mapping from psi_collector where available, extended for RPI
SNAPSHOT_SPACES = {
    "aave": "aavedao.eth",
    "lido": "lido-snapshot.eth",
    "compound-finance": "comp-vote.eth",
    "uniswap": "uniswapgovernance.eth",
    "curve-finance": "curve.eth",
    "convex-finance": "cvx.eth",
    "eigenlayer": "eigenlayer-community.eth",
    "morpho": "morpho.eth",
    "sky": "makerdao.eth",
    # Solana protocols use Realms, not Snapshot
    # spark uses Sky/MakerDAO governance
}

# Keywords that indicate a proposal is risk-related
RISK_KEYWORDS = [
    "risk", "security", "audit", "vulnerability", "exploit", "hack",
    "incident", "parameter", "collateral", "liquidation", "oracle",
    "vendor", "gauntlet", "chaos", "llamarisk", "warden", "immunefi",
    "bug bounty", "insurance", "safety", "reserve", "cap", "threshold",
    "borrow rate", "supply cap", "debt ceiling", "ltv", "loan-to-value",
    "bad debt", "shortfall", "recovery", "compensation", "budget",
    "risk manager", "risk service", "risk provider",
]

# Keywords suggesting a budget/spend amount
BUDGET_PATTERNS = [
    "budget", "compensation", "payment", "funding", "grant",
    "renewal", "stream", "allocation",
]


def _classify_risk_related(title: str, body_excerpt: str) -> tuple[bool, list[str]]:
    """Check if a proposal is risk-related. Returns (is_risk, matched_keywords)."""
    text = f"{title} {body_excerpt}".lower()
    matched = [kw for kw in RISK_KEYWORDS if kw in text]
    return len(matched) > 0, matched


def _extract_budget_usd(title: str, body_excerpt: str) -> float | None:
    """Try to extract a USD budget amount from proposal text."""
    import re
    text = f"{title} {body_excerpt}"
    # Look for patterns like $1,000,000 or $1M or 1,000,000 USDC
    patterns = [
        r'\$[\d,]+(?:\.\d+)?(?:\s*[MmKk])?',
        r'[\d,]+(?:\.\d+)?\s*(?:USDC|USDT|DAI|USD)',
        r'[\d,]+(?:\.\d+)?\s*(?:million|Million|M)\s*(?:USD|USDC|dollars)?',
    ]
    for pat in patterns:
        match = re.search(pat, text)
        if match:
            raw = match.group()
            # Extract numeric value
            num_str = re.sub(r'[^\d.,]', '', raw.split()[0] if ' ' in raw else raw)
            num_str = num_str.replace(',', '')
            try:
                val = float(num_str)
                if 'M' in raw or 'million' in raw.lower():
                    val *= 1_000_000
                elif 'K' in raw or 'k' in raw:
                    val *= 1_000
                # Only return reasonable budget amounts ($1K - $100M)
                if 1_000 <= val <= 100_000_000:
                    return val
            except ValueError:
                continue
    return None


def fetch_snapshot_proposals(space_id: str, since_days: int = 90) -> list[dict]:
    """Fetch proposals from Snapshot for a given space."""
    if not space_id:
        return []

    since_ts = int(datetime.now(timezone.utc).timestamp()) - since_days * 86400

    query = """
    query ($space: String!, $since: Int!) {
      proposals(
        first: 100,
        skip: 0,
        where: {space: $space, created_gte: $since},
        orderBy: "created",
        orderDirection: desc
      ) {
        id
        title
        body
        state
        scores_total
        scores
        quorum
        votes
        created
        end
      }
    }
    """

    time.sleep(0.5)  # rate limit
    try:
        resp = requests.post(
            SNAPSHOT_API,
            json={
                "query": query,
                "variables": {"space": space_id, "since": since_ts},
            },
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("data", {}).get("proposals", [])
    except Exception as e:
        logger.warning(f"Snapshot fetch failed for {space_id}: {e}")
    return []


async def collect_snapshot_proposals():
    """Collect governance proposals from Snapshot for all RPI protocols."""
    total_stored = 0

    for slug in RPI_TARGET_PROTOCOLS:
        space_id = SNAPSHOT_SPACES.get(slug)
        if not space_id:
            continue

        proposals = fetch_snapshot_proposals(space_id)
        logger.info(f"RPI Snapshot: {slug} ({space_id}) — {len(proposals)} proposals")

        for prop in proposals:
            title = prop.get("title", "")
            body = prop.get("body", "")
            body_excerpt = body[:500] if body else ""

            is_risk, risk_kws = _classify_risk_related(title, body_excerpt)
            budget = _extract_budget_usd(title, body_excerpt) if is_risk else None

            # Compute participation rate
            scores_total = prop.get("scores_total", 0) or 0
            quorum = prop.get("quorum", 0) or 0
            participation = (scores_total / quorum * 100) if quorum > 0 else None

            # Vote breakdown (Snapshot returns scores as array matching choices)
            scores = prop.get("scores", [])
            vote_for = scores[0] if len(scores) > 0 else None
            vote_against = scores[1] if len(scores) > 1 else None
            vote_abstain = scores[2] if len(scores) > 2 else None

            created_ts = prop.get("created")
            end_ts = prop.get("end")

            try:
                await execute_async("""
                    INSERT INTO governance_proposals
                        (protocol_slug, proposal_id, source, title, body_excerpt,
                         is_risk_related, risk_keywords, budget_amount_usd,
                         vote_for, vote_against, vote_abstain,
                         quorum_reached, participation_rate,
                         proposal_state, created_at, closed_at, scraped_at)
                    VALUES (%s, %s, 'snapshot', %s, %s,
                            %s, %s, %s,
                            %s, %s, %s,
                            %s, %s,
                            %s, %s, %s, NOW())
                    ON CONFLICT (protocol_slug, proposal_id, source) DO UPDATE SET
                        is_risk_related = EXCLUDED.is_risk_related,
                        risk_keywords = EXCLUDED.risk_keywords,
                        budget_amount_usd = EXCLUDED.budget_amount_usd,
                        vote_for = EXCLUDED.vote_for,
                        vote_against = EXCLUDED.vote_against,
                        vote_abstain = EXCLUDED.vote_abstain,
                        quorum_reached = EXCLUDED.quorum_reached,
                        participation_rate = EXCLUDED.participation_rate,
                        proposal_state = EXCLUDED.proposal_state,
                        closed_at = EXCLUDED.closed_at,
                        scraped_at = NOW()
                """, (
                    slug, prop.get("id", ""), title, body_excerpt,
                    is_risk, risk_kws, budget,
                    vote_for, vote_against, vote_abstain,
                    quorum > 0 and scores_total >= quorum,
                    participation,
                    prop.get("state"),
                    datetime.fromtimestamp(created_ts, tz=timezone.utc) if created_ts else None,
                    datetime.fromtimestamp(end_ts, tz=timezone.utc) if end_ts else None,
                ))
                total_stored += 1
            except Exception as e:
                logger.warning(f"Failed to store proposal {prop.get('id', '?')} for {slug}: {e}")

    logger.info(f"RPI Snapshot collector: {total_stored} proposals stored/updated")
    return total_stored
