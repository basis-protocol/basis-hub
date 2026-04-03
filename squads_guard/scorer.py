"""
Score fetching and CQI computation.
Fetches SII and PSI from the Basis hub API, computes CQI where both exist.
"""

import asyncio
import logging
import math

import httpx

from .config import BASIS_API_URL, STABLECOIN_MINTS, PROTOCOL_PROGRAMS, GRADE_THRESHOLDS

logger = logging.getLogger("squads-guard")


async def _fetch_json(client: httpx.AsyncClient, url: str) -> dict | None:
    """Fetch JSON from a URL, return None on any failure."""
    try:
        resp = await client.get(url, timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        logger.error(f"Fetch failed for {url}: {e}")
    return None


async def fetch_sii_scores(coin_ids: list[str]) -> dict[str, dict]:
    """Fetch SII scores for a list of coin IDs. Returns {coin_id: score_data}."""
    results: dict[str, dict] = {}
    async with httpx.AsyncClient() as client:
        tasks = {
            coin_id: _fetch_json(client, f"{BASIS_API_URL}/api/scores/{coin_id}")
            for coin_id in coin_ids
        }
        responses = await asyncio.gather(*tasks.values())
        for coin_id, data in zip(tasks.keys(), responses):
            if data is not None:
                results[coin_id] = data
    return results


async def fetch_psi_scores(slugs: list[str]) -> dict[str, dict]:
    """Fetch PSI scores for a list of protocol slugs. Returns {slug: score_data}."""
    results: dict[str, dict] = {}
    async with httpx.AsyncClient() as client:
        tasks = {
            slug: _fetch_json(client, f"{BASIS_API_URL}/api/psi/scores/{slug}")
            for slug in slugs
        }
        responses = await asyncio.gather(*tasks.values())
        for slug, data in zip(tasks.keys(), responses):
            if data is not None:
                # Handle both single score and list response
                if isinstance(data, list) and data:
                    results[slug] = data[0]
                else:
                    results[slug] = data
    return results


def get_score_value(score_data: dict) -> float:
    """Extract numeric score from API response (handles different field names)."""
    return score_data.get("score", score_data.get("overall_score", 0))


def compute_cqi(sii_score: float, psi_score: float) -> tuple[float, str]:
    """CQI = sqrt(SII * PSI) on 0-100 scale. Returns (score, grade)."""
    if sii_score <= 0 or psi_score <= 0:
        return 0.0, "F"
    cqi = round(math.sqrt(sii_score * psi_score), 1)
    grade = "F"
    for threshold, g in GRADE_THRESHOLDS:
        if cqi >= threshold:
            grade = g
            break
    return cqi, grade


def grade_from_score(score: float) -> str:
    """Map a 0-100 score to a grade string."""
    for threshold, g in GRADE_THRESHOLDS:
        if score >= threshold:
            return g
    return "F"


async def score_transaction(
    stablecoin_mints: list[str],
    protocol_programs: list[str],
) -> tuple[dict[str, dict], dict[str, dict], dict[str, dict]]:
    """
    Score a transaction. Returns (stablecoin_scores, protocol_scores, cqi_scores).

    Fetches SII and PSI in parallel, computes CQI for every stablecoin x protocol pair.
    Missing scores are omitted, not errored.
    """
    # Map mints/programs to Basis IDs
    coin_ids = [STABLECOIN_MINTS[m] for m in stablecoin_mints if m in STABLECOIN_MINTS]
    slugs = [PROTOCOL_PROGRAMS[p] for p in protocol_programs if p in PROTOCOL_PROGRAMS]

    # Fetch in parallel
    sii_results, psi_results = await asyncio.gather(
        fetch_sii_scores(coin_ids),
        fetch_psi_scores(slugs),
    )

    # Compute CQI for all pairs
    cqi_scores: dict[str, dict] = {}
    for coin_id, sii in sii_results.items():
        sii_val = get_score_value(sii)
        for slug, psi in psi_results.items():
            psi_val = get_score_value(psi)
            if sii_val > 0 and psi_val > 0:
                cqi, grade = compute_cqi(sii_val, psi_val)
                pair_name = f"{coin_id.upper()} \u00d7 {slug.replace('-', ' ').title()}"
                cqi_scores[pair_name] = {
                    "cqi": cqi,
                    "grade": grade,
                    "sii": sii_val,
                    "psi": psi_val,
                }

    return sii_results, psi_results, cqi_scores


async def score_by_ids(
    coin_ids: list[str],
    slugs: list[str],
) -> tuple[dict[str, dict], dict[str, dict], dict[str, dict]]:
    """Score by Basis IDs directly (for /score and /demo endpoints)."""
    sii_results, psi_results = await asyncio.gather(
        fetch_sii_scores(coin_ids),
        fetch_psi_scores(slugs),
    )

    cqi_scores: dict[str, dict] = {}
    for coin_id, sii in sii_results.items():
        sii_val = get_score_value(sii)
        for slug, psi in psi_results.items():
            psi_val = get_score_value(psi)
            if sii_val > 0 and psi_val > 0:
                cqi, grade = compute_cqi(sii_val, psi_val)
                pair_name = f"{coin_id.upper()} \u00d7 {slug.replace('-', ' ').title()}"
                cqi_scores[pair_name] = {
                    "cqi": cqi,
                    "grade": grade,
                    "sii": sii_val,
                    "psi": psi_val,
                }

    return sii_results, psi_results, cqi_scores
