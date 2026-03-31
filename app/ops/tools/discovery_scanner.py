"""
Discovery scanner — queries discovery_signals table, ranks by content-worthiness,
cross-references with ops_targets for engagement relevance.
"""
import json
import logging
from app.database import fetch_all, fetch_one

logger = logging.getLogger(__name__)

# Map signal domains to target types for cross-referencing
DOMAIN_TARGET_MAP = {
    "sii": ["curator", "protocol", "advisory", "dao_treasury"],
    "wallets": ["dao_treasury", "curator"],
    "psi": ["protocol", "curator"],
    "cda": ["issuer", "advisory"],
    "pulse": ["protocol", "curator", "dao_treasury"],
    "divergence": ["curator", "protocol"],
    "graph": ["dao_treasury", "curator", "protocol"],
}


def scan_discovery(limit: int = 20, min_magnitude: float = 0.0) -> dict:
    """
    Scan recent discovery signals, rank by content-worthiness,
    and cross-reference with ops_targets.

    Returns ranked list of signals with:
    - content_potential: how content-worthy this signal is
    - target_relevance: which targets this signal is relevant to
    - suggested_action: what to do with it
    """
    signals = fetch_all(
        """SELECT * FROM discovery_signals
           WHERE detected_at > NOW() - INTERVAL '7 days'
             AND magnitude >= %s
           ORDER BY magnitude DESC, detected_at DESC
           LIMIT %s""",
        (min_magnitude, limit),
    )

    if not signals:
        return {"signals": [], "summary": "No discovery signals in the last 7 days."}

    # Load all targets for cross-referencing
    targets = fetch_all("SELECT id, name, type, tier, pipeline_stage FROM ops_targets")
    targets_by_type = {}
    for t in targets:
        targets_by_type.setdefault(t["type"], []).append(t)

    results = []
    for sig in signals:
        domain = sig.get("domain", "unknown")
        signal_type = sig.get("signal_type", "unknown")
        magnitude = float(sig.get("magnitude", 0))
        title = sig.get("title", "")
        description = sig.get("description", "")
        entities = sig.get("entities", [])

        # Score content-worthiness
        content_score = _score_content_worthiness(sig)

        # Find relevant targets
        relevant_targets = []
        target_types = DOMAIN_TARGET_MAP.get(domain, [])
        for ttype in target_types:
            for t in targets_by_type.get(ttype, []):
                # Higher priority for Tier 1 targets
                priority = 3 - min(t["tier"], 3) + 1
                relevant_targets.append({
                    "id": t["id"],
                    "name": t["name"],
                    "tier": t["tier"],
                    "priority": priority,
                })

        # Check if any entities in the signal match target names
        if entities:
            entity_list = entities if isinstance(entities, list) else [entities]
            for t in targets:
                for entity in entity_list:
                    if isinstance(entity, str) and t["name"].lower() in entity.lower():
                        relevant_targets.append({
                            "id": t["id"],
                            "name": t["name"],
                            "tier": t["tier"],
                            "priority": 5,  # direct mention = highest priority
                        })

        # Deduplicate targets
        seen = set()
        unique_targets = []
        for rt in sorted(relevant_targets, key=lambda x: -x["priority"]):
            if rt["id"] not in seen:
                seen.add(rt["id"])
                unique_targets.append(rt)

        # Suggest action
        action = _suggest_action(sig, content_score, unique_targets)

        results.append({
            "signal_id": sig["id"],
            "domain": domain,
            "signal_type": signal_type,
            "title": title,
            "description": description,
            "magnitude": magnitude,
            "detected_at": sig["detected_at"].isoformat() if sig.get("detected_at") else None,
            "content_score": content_score,
            "relevant_targets": unique_targets[:5],  # top 5
            "suggested_action": action,
            "entities": entities,
        })

    # Sort by content_score
    results.sort(key=lambda x: -x["content_score"])

    return {
        "signals": results,
        "total": len(results),
        "summary": f"{len(results)} signals found. Top signal: {results[0]['title'] if results else 'none'} (score: {results[0]['content_score']:.2f})" if results else "No signals.",
    }


def _score_content_worthiness(sig: dict) -> float:
    """
    Score 0-1 how content-worthy a discovery signal is.
    High scores → worth writing about.
    """
    score = 0.0
    magnitude = float(sig.get("magnitude", 0))
    domain = sig.get("domain", "")
    novelty = float(sig.get("novelty_score", 0))

    # Magnitude contributes 0-0.4
    score += min(magnitude / 10.0, 0.4)

    # Novelty contributes 0-0.3
    score += min(novelty * 0.3, 0.3)

    # Domain bonus: some domains are inherently more content-worthy
    domain_bonus = {
        "divergence": 0.15,  # quality-flow disconnects are great content
        "sii": 0.1,          # score movers are straightforward content
        "pulse": 0.1,        # daily changes are timely
        "graph": 0.1,        # network topology is visually interesting
        "wallets": 0.05,     # whale movements can be content
        "cda": 0.05,         # disclosure gaps are niche but important
        "psi": 0.05,         # protocol changes
    }
    score += domain_bonus.get(domain, 0)

    # Direction bonus: negative signals are more newsworthy
    if sig.get("direction") == "negative":
        score += 0.05

    return min(score, 1.0)


def _suggest_action(sig: dict, content_score: float, targets: list) -> str:
    """Suggest what to do with a signal based on its score and target relevance."""
    if content_score >= 0.7:
        if targets and targets[0]["tier"] == 1:
            return "draft_dm_and_tweet"
        return "draft_tweet_thread"
    elif content_score >= 0.4:
        if targets and targets[0]["tier"] <= 2:
            return "dm_trigger"
        return "queue_for_weekly"
    elif content_score >= 0.2:
        return "note_for_reference"
    else:
        return "skip"
