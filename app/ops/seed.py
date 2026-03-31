"""
Seed data for the Operations Hub.
Inserts targets, contacts, and investors. Idempotent — skips existing records.
"""
import logging
from app.database import fetch_one, execute

logger = logging.getLogger(__name__)


def seed_all():
    """Run all seed functions. Returns counts of inserted records."""
    counts = {}
    counts["targets"] = _seed_targets()
    counts["contacts"] = _seed_contacts()
    counts["investors"] = _seed_investors()
    return counts


def _seed_targets():
    """Seed ops_targets table with all tiers."""
    targets = [
        # Tier 1: Active pursuit
        {
            "name": "karpatkey",
            "type": "dao_treasury",
            "track": "binding",
            "tier": 1,
            "worldview_summary": "Policy-defined execution. Permissions as enforcement on Safe/Zodiac. Deterministic agents within predefined bounds. Investment Policy Statements as governance standard. DeFi Treasury Network covering every primitive. Stablecoin quality is still ad-hoc across their DAO network.",
            "gap": "Stablecoin quality is the one policy input that's still case-by-case across their entire $2.1B DAO network.",
            "first_wedge": "Review SII scores for one DAO mandate's stablecoin exposure.",
            "landmine": "Sounding like you don't understand Safe/Zodiac or their mandate-specific workflow. Implying replacement rather than input.",
            "positioning": "Missing standardized stablecoin-quality input inside the system they already believe in — policy, permissions, IPS, deterministic execution.",
            "pipeline_stage": "not_started",
        },
        {
            "name": "Re7 Labs",
            "type": "curator",
            "track": "binding",
            "tier": 1,
            "worldview_summary": "Quantitative research focus. Morpho vault curator. Directly exposed in Resolv — disclosed supplyOnBehalf vulnerability. Smaller team, accessible.",
            "gap": "No shared stablecoin pre-allocation check across curators.",
            "first_wedge": "Test one pre-allocation SII check in vault workflow.",
            "landmine": "Implying SII replaces their risk models. Different question: stablecoin quality vs lending market parameters.",
            "pipeline_stage": "not_started",
        },
        {
            "name": "9summits",
            "type": "curator",
            "track": "binding",
            "tier": 1,
            "worldview_summary": "Morpho vault curator. Smallest of Resolv-exposed curators. Most accessible.",
            "gap": "Same as Re7 — no shared pre-allocation check.",
            "pipeline_stage": "not_started",
        },
        {
            "name": "Morpho",
            "type": "protocol",
            "track": "binding",
            "tier": 1,
            "worldview_summary": "Curators are the risk management layer. Permissionless lending. Curation encodes strategy through allocation. Institutional-grade risk is the differentiator.",
            "gap": "The curator ecosystem lacks a shared stablecoin quality standard. Each curator evaluates independently.",
            "pipeline_stage": "not_started",
        },
        {
            "name": "Steakhouse Financial",
            "type": "advisory",
            "track": "credibility",
            "tier": 1,
            "worldview_summary": "Expert advisory. Manual stablecoin reviews (Mountain Protocol USDM). Institutional-grade risk visibility. ENS endowment reporting. Building Grove protocol for credit infrastructure.",
            "gap": "Manual stablecoin evaluation doesn't scale. They do it well but for one stablecoin at a time, by hand.",
            "first_wedge": "React to methodology. Review one stablecoin comparison.",
            "landmine": "Positioning as automation replacing experts. Frame as data layer under expert judgment.",
            "pipeline_stage": "not_started",
        },
        {
            "name": "Aave governance",
            "type": "protocol",
            "track": "credibility",
            "tier": 1,
            "worldview_summary": "Structured proposal lifecycle (ARC->ARFC->AIP). Risk providers complement each other (Gauntlet, Certora, Chaos Labs). Community-driven parameter decisions.",
            "gap": "No standardized stablecoin integrity input for collateral listing decisions. Each listing evaluated ad-hoc.",
            "first_wedge": "Post substantive analysis on governance forum. Get replies.",
            "pipeline_stage": "not_started",
        },
        {
            "name": "AgentKit / Coinbase",
            "type": "agent_infra",
            "track": "velocity",
            "tier": 1,
            "worldview_summary": "Agents need financial autonomy. MCP as tool integration standard. x402 for stablecoin payments.",
            "gap": "Agents can execute but can't evaluate stablecoin risk. No perception layer.",
            "first_wedge": "Publish integration example. Let developers find it.",
            "pipeline_stage": "not_started",
        },
        # Tier 2: Monitoring + opportunistic
        {
            "name": "Lido Earn",
            "type": "protocol",
            "track": "binding",
            "tier": 2,
            "worldview_summary": "Stablecoin vault infrastructure. EarnUSD launched Mar 12, 2026. Routes deposits across Aave, Morpho, Uniswap.",
            "gap": "Which stablecoins are acceptable for vault strategies? No independent quality framework.",
            "pipeline_stage": "not_started",
        },
        {"name": "Compound / GFX Labs", "type": "protocol", "tier": 2, "pipeline_stage": "not_started"},
        {"name": "CoW DAO", "type": "dao_treasury", "tier": 2, "pipeline_stage": "not_started"},
        {"name": "Gauntlet", "type": "analytics", "tier": 2, "pipeline_stage": "not_started"},
        {"name": "Sentora (Chaos Labs)", "type": "analytics", "tier": 2, "pipeline_stage": "not_started"},
        {"name": "MEV Capital", "type": "curator", "tier": 2, "pipeline_stage": "not_started"},
        {"name": "Bitwise", "type": "curator", "tier": 2, "pipeline_stage": "not_started"},
        {"name": "Curve", "type": "protocol", "tier": 2, "pipeline_stage": "not_started"},
        {"name": "MakerDAO / Sky", "type": "protocol", "tier": 2, "pipeline_stage": "not_started"},
        {"name": "Ethena", "type": "protocol", "tier": 2, "pipeline_stage": "not_started"},
        {"name": "DeFiLlama", "type": "analytics", "tier": 2, "pipeline_stage": "not_started"},
        {"name": "CoinGecko", "type": "analytics", "tier": 2, "pipeline_stage": "not_started"},
        # Tier 3: Watch list
        {"name": "Circle", "type": "issuer", "tier": 3, "pipeline_stage": "not_started"},
        {"name": "Paxos", "type": "issuer", "tier": 3, "pipeline_stage": "not_started"},
        {"name": "Nexus Mutual", "type": "insurance", "tier": 3, "pipeline_stage": "not_started"},
        {"name": "Fireblocks", "type": "custody", "tier": 3, "pipeline_stage": "not_started"},
        {"name": "Arbitrum DAO", "type": "protocol", "tier": 3, "pipeline_stage": "not_started"},
        {"name": "Optimism Collective", "type": "protocol", "tier": 3, "pipeline_stage": "not_started"},
        {"name": "Uniswap governance", "type": "protocol", "tier": 3, "pipeline_stage": "not_started"},
        {"name": "ENS governance", "type": "protocol", "tier": 3, "pipeline_stage": "not_started"},
        {"name": "Virtuals Protocol", "type": "protocol", "tier": 3, "pipeline_stage": "not_started"},
    ]

    inserted = 0
    for t in targets:
        existing = fetch_one("SELECT id FROM ops_targets WHERE name = %s", (t["name"],))
        if existing:
            continue
        execute(
            """INSERT INTO ops_targets (name, type, track, tier, worldview_summary, gap,
               first_wedge, landmine, positioning, pipeline_stage)
               VALUES (%(name)s, %(type)s, %(track)s, %(tier)s, %(worldview_summary)s, %(gap)s,
               %(first_wedge)s, %(landmine)s, %(positioning)s, %(pipeline_stage)s)""",
            {
                "name": t["name"],
                "type": t["type"],
                "track": t.get("track"),
                "tier": t["tier"],
                "worldview_summary": t.get("worldview_summary"),
                "gap": t.get("gap"),
                "first_wedge": t.get("first_wedge"),
                "landmine": t.get("landmine"),
                "positioning": t.get("positioning"),
                "pipeline_stage": t.get("pipeline_stage", "not_started"),
            },
        )
        inserted += 1
    logger.info(f"Seeded {inserted} targets")
    return inserted


def _seed_contacts():
    """Seed ops_target_contacts for Tier 1 targets."""
    contacts = [
        # karpatkey
        {"target": "karpatkey", "name": "Marcelo Ruiz de Olano", "role": "CEO", "twitter_handle": "@marceloruizdeolano", "warmth": 1},
        {"target": "karpatkey", "name": "DeFi Foodie", "role": "BD", "twitter_handle": "@DeFiFoodie", "warmth": 1},
        # Morpho
        {"target": "Morpho", "name": "Paul Frambot", "role": "CEO", "twitter_handle": "@PaulFrambot", "warmth": 1},
        # Steakhouse Financial
        {"target": "Steakhouse Financial", "name": "Sebastien Derivaux", "role": "Co-founder", "twitter_handle": "@SebVentures", "warmth": 1},
        # AgentKit
        {"target": "AgentKit / Coinbase", "name": "Erik Reppel", "role": "Head of Eng CDP", "twitter_handle": "@erikreppel", "warmth": 1},
        # Lido Earn
        {"target": "Lido Earn", "name": "Marin Tvrdic", "role": "Head of Earn Partnerships", "warmth": 1},
    ]

    inserted = 0
    for c in contacts:
        target = fetch_one("SELECT id FROM ops_targets WHERE name = %s", (c["target"],))
        if not target:
            continue
        existing = fetch_one(
            "SELECT id FROM ops_target_contacts WHERE target_id = %s AND name = %s",
            (target["id"], c["name"]),
        )
        if existing:
            continue
        execute(
            """INSERT INTO ops_target_contacts (target_id, name, role, twitter_handle, warmth)
               VALUES (%s, %s, %s, %s, %s)""",
            (target["id"], c["name"], c.get("role"), c.get("twitter_handle"), c.get("warmth")),
        )
        inserted += 1
    logger.info(f"Seeded {inserted} contacts")
    return inserted


def _seed_investors():
    """Seed ops_investors table."""
    investors = [
        # Tier 1: Lead
        {
            "name": "Variant",
            "type": "lead_vc",
            "firm": "Variant Fund",
            "tier": 1,
            "key_person": "Jesse Walden",
            "warm_path": "Need intro — search for path",
            "thesis_alignment": "Ownership economy, protocol infrastructure",
        },
        {
            "name": "Dragonfly",
            "type": "strategic_vc",
            "firm": "Dragonfly Capital",
            "tier": 1,
            "key_person": "Haseeb Qureshi, Tom Schmidt",
            "warm_path": "Need intro",
            "thesis_alignment": "DeFi infrastructure thesis. Funded Morpho (a16z + Variant co-led).",
        },
        # Tier 2: Strategic
        {
            "name": "Coinbase Ventures",
            "type": "strategic_vc",
            "firm": "Coinbase",
            "tier": 2,
            "warm_path": "AgentKit product alignment. Base ecosystem.",
        },
        {
            "name": "Polychain",
            "type": "strategic_vc",
            "firm": "Polychain Capital",
            "tier": 2,
            "key_person": "Olaf Carlson-Wee",
            "warm_path": "Need intro",
        },
        {
            "name": "Robot Ventures",
            "type": "strategic_vc",
            "firm": "Robot Ventures",
            "tier": 2,
            "key_person": "Robert Leshner",
            "warm_path": "Need intro",
            "notes": "Compound founder",
        },
        {
            "name": "Village Global",
            "type": "network",
            "firm": "Village Global",
            "tier": 2,
            "key_person": "Ben Casnocha",
            "warm_path": "Accessible — known to founder",
        },
        # Tier 3: Angels
        {
            "name": "Arthur Hayes",
            "type": "angel",
            "tier": 3,
            "stage": "advisor_in_place",
            "notes": "Brother runs Maelstrom. No fund check (conflict). Advisory role.",
        },
        {
            "name": "Nick Johnson",
            "type": "angel",
            "tier": 3,
            "warm_path": "Angel target + karpatkey connector. Dual-purpose.",
            "notes": "ENS founder",
        },
        {"name": "Stani", "type": "angel", "tier": 3, "warm_path": "Need intro", "notes": "Aave founder. Would validate protocol-level relevance."},
        {"name": "Balaji", "type": "angel", "tier": 3, "warm_path": "Need intro", "thesis_alignment": "Thesis alignment on standards/infrastructure"},
        {"name": "Ryan Holiday", "type": "angel", "tier": 3, "warm_path": "Friend", "notes": "Signal booster, not crypto investor. May know crypto-adjacent people."},
        {"name": "Brent Underwood", "type": "angel", "tier": 3, "warm_path": "Friend", "notes": "Same as Ryan Holiday."},
        {"name": "Razat Gaurav", "type": "angel", "tier": 3, "warm_path": "Known", "notes": "Planview CEO. Enterprise credibility signal."},
        {"name": "Alex Wirth", "type": "angel", "tier": 3, "warm_path": "Departure-dependent", "notes": "Former employer CEO (Quorum). Enterprise credibility."},
    ]

    inserted = 0
    for inv in investors:
        existing = fetch_one("SELECT id FROM ops_investors WHERE name = %s", (inv["name"],))
        if existing:
            continue
        execute(
            """INSERT INTO ops_investors (name, type, firm, tier, stage, key_person, warm_path,
               thesis_alignment, notes)
               VALUES (%(name)s, %(type)s, %(firm)s, %(tier)s, %(stage)s, %(key_person)s,
               %(warm_path)s, %(thesis_alignment)s, %(notes)s)""",
            {
                "name": inv["name"],
                "type": inv["type"],
                "firm": inv.get("firm"),
                "tier": inv["tier"],
                "stage": inv.get("stage", "not_started"),
                "key_person": inv.get("key_person"),
                "warm_path": inv.get("warm_path"),
                "thesis_alignment": inv.get("thesis_alignment"),
                "notes": inv.get("notes"),
            },
        )
        inserted += 1
    logger.info(f"Seeded {inserted} investors")
    return inserted
