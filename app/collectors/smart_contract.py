"""
Smart Contract & Security Collector
=====================================
Produces components for the smart_contract and security categories:

  - contract_verified:          Etherscan getabi succeeds → source is verified
  - pausability:                ABI contains pause/unpause functions
  - blacklist_capability:       ABI contains blacklist/freeze functions
  - admin_key_risk:             Admin structure analysis (multisig, EOA, governance)
  - bug_bounty_score:           Active bug bounty program (Immunefi etc.)
  - exploit_history:            Past security incidents

Data sources: Etherscan getabi + static config for bounty/exploit history.
"""

import os
import json
import asyncio
import logging
from datetime import datetime, timezone

import httpx

from app.database import fetch_one

logger = logging.getLogger(__name__)

ETHERSCAN_V2_BASE = "https://api.etherscan.io/v2/api"
RATE_LIMIT_DELAY = 0.15

# ============================================================================
# Static security config — updated manually as conditions change
# ============================================================================

# Admin key risk: assessed from on-chain analysis of each token's admin structure.
# Score meaning: 0=EOA with no timelock, 50=2-of-3 multisig, 80=3-of-5+, 95=governance
ADMIN_KEY_RISK = {
    "usdc":   80,   # Circle: 3-of-6 multisig + timelock (FiatTokenV2)
    "usdt":   40,   # Tether: centralized issuer, limited multisig info
    "dai":    90,   # MakerDAO: on-chain governance (DSChief), timelock
    "frax":   75,   # Frax: multisig + governance (veFXS)
    "pyusd":  70,   # PayPal: corporate issuer, multisig admin
    "fdusd":  50,   # First Digital: centralized issuer, 2-of-3 multisig
    "tusd":   35,   # TrueUSD: centralized, ownership disputes history
    "usdd":   30,   # TRON DAO Reserve: centralized reserve management
    "usde":   65,   # Ethena: multisig governance, newer protocol
    "usd1":   45,   # World Liberty Financial: newer, limited governance info
    "gho":    85,   # Aave: on-chain governance (Aave Gov V3)
    "crvusd": 85,   # Curve: on-chain governance (veCRV)
    "dola":   80,   # Inverse Finance: on-chain governance
    "usdp":   60,   # Paxos: regulated issuer, corporate multisig
}

# Bug bounty programs
BUG_BOUNTY = {
    "usdc":   {"active": True, "max_payout": 250_000, "platform": "Immunefi"},
    "usdt":   {"active": False, "max_payout": 0},
    "dai":    {"active": True, "max_payout": 10_000_000, "platform": "Immunefi"},
    "frax":   {"active": True, "max_payout": 500_000, "platform": "Immunefi"},
    "pyusd":  {"active": False, "max_payout": 0},
    "fdusd":  {"active": False, "max_payout": 0},
    "tusd":   {"active": False, "max_payout": 0},
    "usdd":   {"active": False, "max_payout": 0},
    "usde":   {"active": True, "max_payout": 250_000, "platform": "Immunefi"},
    "usd1":   {"active": False, "max_payout": 0},
    "gho":    {"active": True, "max_payout": 15_000_000, "platform": "Immunefi"},
    "crvusd": {"active": True, "max_payout": 250_000, "platform": "Immunefi"},
    "dola":   {"active": True, "max_payout": 500_000, "platform": "Immunefi"},
    "usdp":   {"active": False, "max_payout": 0},
}

# Exploit history — from DeFiLlama hacks + known incidents
# date is approximate, amount in USD
EXPLOIT_HISTORY = {
    "tusd":   [{"date": "2023-10-01", "amount": 0, "desc": "Reserve backing disputes, depegged"}],
    "usdd":   [{"date": "2023-06-15", "amount": 0, "desc": "Sustained depeg below $0.97"}],
    "dola":   [{"date": "2022-06-16", "amount": 1_200_000, "desc": "Inverse Finance oracle manipulation"}],
    # USDC, USDT, DAI, FRAX, PYUSD, FDUSD, USDE, USD1, GHO, CRVUSD, USDP — no direct exploits
}

# Pausability and blacklist capability per token (from ABI analysis)
ABI_FEATURES = {
    "usdc":   {"pausable": True, "blacklist": True},
    "usdt":   {"pausable": True, "blacklist": True},
    "dai":    {"pausable": False, "blacklist": False},
    "frax":   {"pausable": False, "blacklist": False},
    "pyusd":  {"pausable": True, "blacklist": True},
    "fdusd":  {"pausable": True, "blacklist": True},
    "tusd":   {"pausable": True, "blacklist": True},
    "usdd":   {"pausable": False, "blacklist": True},
    "usde":   {"pausable": False, "blacklist": False},
    "usd1":   {"pausable": True, "blacklist": True},
    "gho":    {"pausable": False, "blacklist": False},
    "crvusd": {"pausable": False, "blacklist": False},
    "dola":   {"pausable": False, "blacklist": False},
    "usdp":   {"pausable": True, "blacklist": True},
}


# ============================================================================
# Live ABI verification check
# ============================================================================

async def _check_contract_verified(
    client: httpx.AsyncClient, contract: str, api_key: str
) -> bool:
    """Check if contract source is verified on Etherscan."""
    try:
        resp = await client.get(ETHERSCAN_V2_BASE, params={
            "chainid": 1,
            "module": "contract",
            "action": "getabi",
            "address": contract,
            "apikey": api_key,
        }, timeout=20)
        data = resp.json()
        return data.get("status") == "1" and data.get("result", "").startswith("[")
    except Exception as e:
        logger.warning(f"ABI check failed for {contract}: {e}")
        return False


# ============================================================================
# Normalization helpers
# ============================================================================

def _score_bug_bounty(stablecoin_id: str) -> float:
    """Score bug bounty program. Active with >$100K = 100, <$100K = 70, none = 20."""
    info = BUG_BOUNTY.get(stablecoin_id, {})
    if not info.get("active"):
        return 20.0
    if info.get("max_payout", 0) >= 100_000:
        return 100.0
    return 70.0


def _score_exploit_history(stablecoin_id: str) -> float:
    """Score exploit history. No exploits = 100, >1yr ago = 60, <1yr = 20, <90d = 0."""
    exploits = EXPLOIT_HISTORY.get(stablecoin_id, [])
    if not exploits:
        return 100.0

    now = datetime.now(timezone.utc)
    most_recent = None
    for exp in exploits:
        try:
            d = datetime.strptime(exp["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if most_recent is None or d > most_recent:
                most_recent = d
        except (ValueError, KeyError):
            continue

    if most_recent is None:
        return 100.0

    days_ago = (now - most_recent).days
    if days_ago < 90:
        return 0.0
    if days_ago < 365:
        return 20.0
    return 60.0


def _score_pausability(stablecoin_id: str) -> float:
    """Pausable = 60 (tradeoff), not pausable = 100 (decentralized)."""
    features = ABI_FEATURES.get(stablecoin_id, {})
    return 60.0 if features.get("pausable") else 100.0


def _score_blacklist(stablecoin_id: str) -> float:
    """Blacklist capability = 60, no blacklist = 100."""
    features = ABI_FEATURES.get(stablecoin_id, {})
    return 60.0 if features.get("blacklist") else 100.0


# ============================================================================
# Main collector
# ============================================================================

async def collect_smart_contract_components(
    client: httpx.AsyncClient, stablecoin_id: str
) -> list[dict]:
    """
    Collect smart contract risk components for one stablecoin.
    Returns list of component dicts ready for DB insert.
    """
    api_key = os.environ.get("ETHERSCAN_API_KEY", "")

    # Get contract address
    row = fetch_one(
        "SELECT contract FROM stablecoins WHERE id = %s", (stablecoin_id,)
    )
    contract = row.get("contract", "") if row else ""

    components = []

    # 1. contract_verified — live API check
    if contract and api_key:
        verified = await _check_contract_verified(client, contract, api_key)
        await asyncio.sleep(RATE_LIMIT_DELAY)
        components.append({
            "component_id": "contract_verified",
            "category": "smart_contract",
            "raw_value": 1 if verified else 0,
            "normalized_score": 100.0 if verified else 0.0,
            "data_source": "etherscan",
        })
    else:
        components.append({
            "component_id": "contract_verified",
            "category": "smart_contract",
            "raw_value": 0,
            "normalized_score": 0.0,
            "data_source": "static",
        })

    # 2. pausability — from ABI feature config
    pause_score = _score_pausability(stablecoin_id)
    components.append({
        "component_id": "pausability",
        "category": "smart_contract",
        "raw_value": 1 if ABI_FEATURES.get(stablecoin_id, {}).get("pausable") else 0,
        "normalized_score": pause_score,
        "data_source": "config",
    })

    # 3. blacklist_capability
    bl_score = _score_blacklist(stablecoin_id)
    components.append({
        "component_id": "blacklist_capability",
        "category": "smart_contract",
        "raw_value": 1 if ABI_FEATURES.get(stablecoin_id, {}).get("blacklist") else 0,
        "normalized_score": bl_score,
        "data_source": "config",
    })

    # 4. admin_key_risk — from static analysis config
    admin_score = float(ADMIN_KEY_RISK.get(stablecoin_id, 10))
    components.append({
        "component_id": "admin_key_risk",
        "category": "smart_contract",
        "raw_value": admin_score,
        "normalized_score": admin_score,
        "data_source": "config",
    })

    # 5. bug_bounty_score
    bounty_score = _score_bug_bounty(stablecoin_id)
    bounty_raw = BUG_BOUNTY.get(stablecoin_id, {}).get("max_payout", 0)
    components.append({
        "component_id": "bug_bounty_score",
        "category": "smart_contract",
        "raw_value": bounty_raw,
        "normalized_score": bounty_score,
        "data_source": "config",
    })

    # 6. exploit_history
    exploit_score = _score_exploit_history(stablecoin_id)
    exploits = EXPLOIT_HISTORY.get(stablecoin_id, [])
    components.append({
        "component_id": "exploit_history",
        "category": "smart_contract",
        "raw_value": len(exploits),
        "normalized_score": exploit_score,
        "data_source": "config",
    })

    # Attest smart contract components
    try:
        from app.state_attestation import attest_state
        if components:
            attest_state("smart_contracts", [{"id": c.get("component_id"), "score": c.get("normalized_score")} for c in components], entity_id=stablecoin_id)
    except Exception as ae:
        pass  # attestation is non-critical

    return components


# ============================================================================
# Shared utilities for Circle 7 index collectors
# ============================================================================

# In-memory caches
_contract_analysis_cache: dict[str, tuple[float, dict]] = {}
_CONTRACT_ANALYSIS_TTL = 86400  # 24h — contract properties rarely change

_immunefi_cache: dict[str, tuple[float, dict]] = {}
_IMMUNEFI_TTL = 604800  # 7 days


async def _check_proxy_pattern(
    client: httpx.AsyncClient, contract: str, api_key: str
) -> dict:
    """Detect proxy pattern and implementation verification status.

    Returns dict: {is_proxy, proxy_type, implementation_verified}.
    """
    result = {"is_proxy": False, "proxy_type": "none", "implementation_verified": False}

    try:
        # Check for proxy via getsourcecode (includes implementation address for proxies)
        resp = await client.get(ETHERSCAN_V2_BASE, params={
            "chainid": 1,
            "module": "contract",
            "action": "getsourcecode",
            "address": contract,
            "apikey": api_key,
        }, timeout=20)
        data = resp.json()

        if data.get("status") == "1" and data.get("result"):
            source = data["result"][0] if isinstance(data["result"], list) else {}
            impl = source.get("Implementation", "")
            proxy_val = source.get("Proxy", "0")

            if impl or proxy_val == "1":
                result["is_proxy"] = True

                # Detect proxy type from source code or contract name
                source_code = source.get("SourceCode", "")
                contract_name = source.get("ContractName", "")
                combined = (source_code + contract_name).lower()

                if "uups" in combined:
                    result["proxy_type"] = "uups"
                elif "beacon" in combined:
                    result["proxy_type"] = "beacon"
                elif "transparent" in combined or "proxyadmin" in combined:
                    result["proxy_type"] = "transparent"
                elif "timelock" in combined:
                    result["proxy_type"] = "timelock"
                else:
                    result["proxy_type"] = "unknown"

                # Check if implementation is also verified
                if impl:
                    await asyncio.sleep(RATE_LIMIT_DELAY)
                    impl_verified = await _check_contract_verified(client, impl, api_key)
                    result["implementation_verified"] = impl_verified

    except Exception as e:
        logger.debug(f"Proxy check failed for {contract}: {e}")

    return result


async def _detect_admin_functions(
    client: httpx.AsyncClient, contract: str, api_key: str
) -> dict:
    """Detect admin-related functions from contract ABI.

    Returns dict: {has_owner, has_pause, has_admin, has_timelock, admin_function_count}.
    """
    result = {
        "has_owner": False, "has_pause": False,
        "has_admin": False, "has_timelock": False,
        "admin_function_count": 0,
    }

    try:
        resp = await client.get(ETHERSCAN_V2_BASE, params={
            "chainid": 1,
            "module": "contract",
            "action": "getabi",
            "address": contract,
            "apikey": api_key,
        }, timeout=20)
        data = resp.json()

        if data.get("status") == "1":
            abi_str = data.get("result", "")
            if abi_str and abi_str.startswith("["):
                abi = json.loads(abi_str)
                admin_keywords = ["owner", "admin", "pause", "unpause", "upgrade",
                                  "setAdmin", "transferOwnership", "renounceOwnership",
                                  "timelock", "delay", "guardian", "blacklist", "freeze"]
                admin_count = 0
                for item in abi:
                    if item.get("type") != "function":
                        continue
                    fname = (item.get("name") or "").lower()
                    if any(kw.lower() in fname for kw in admin_keywords):
                        admin_count += 1
                    if "owner" in fname:
                        result["has_owner"] = True
                    if "pause" in fname:
                        result["has_pause"] = True
                    if "admin" in fname:
                        result["has_admin"] = True
                    if "timelock" in fname or "delay" in fname:
                        result["has_timelock"] = True

                result["admin_function_count"] = admin_count
    except Exception as e:
        logger.debug(f"ABI admin detection failed for {contract}: {e}")

    return result


async def analyze_contract_for_index(contract_address: str, chain: str = "ethereum") -> dict:
    """Analyze a contract for index scoring purposes.

    Returns a normalized dict:
        {
            "audit_verified": bool,         # contract source verified on Etherscan
            "admin_key_risk": float,        # 0-100: higher = safer (less admin risk)
            "upgradeability_risk": float,   # 0-100: higher = safer (less upgrade risk)
            "proxy_type": str,              # none, transparent, uups, beacon, timelock, unknown
            "is_proxy": bool,
            "implementation_verified": bool,
        }

    Results cached for 24h per contract address.
    """
    import time as _time

    cache_key = contract_address.lower()
    cached = _contract_analysis_cache.get(cache_key)
    if cached and (_time.time() - cached[0]) < _CONTRACT_ANALYSIS_TTL:
        return cached[1]

    api_key = os.environ.get("ETHERSCAN_API_KEY", "")
    if not api_key or not contract_address:
        return {
            "audit_verified": False, "admin_key_risk": 50,
            "upgradeability_risk": 50, "proxy_type": "unknown",
            "is_proxy": False, "implementation_verified": False,
        }

    result = {}

    async with httpx.AsyncClient(timeout=20) as client:
        # 1. Check verification
        verified = await _check_contract_verified(client, contract_address, api_key)
        await asyncio.sleep(RATE_LIMIT_DELAY)
        result["audit_verified"] = verified

        # 2. Check proxy pattern
        proxy_info = await _check_proxy_pattern(client, contract_address, api_key)
        await asyncio.sleep(RATE_LIMIT_DELAY)
        result.update(proxy_info)

        # 3. Detect admin functions
        admin_info = await _detect_admin_functions(client, contract_address, api_key)
        await asyncio.sleep(RATE_LIMIT_DELAY)

        # Map admin detection to 0-100 risk score (higher = safer)
        admin_count = admin_info["admin_function_count"]
        if admin_count == 0:
            result["admin_key_risk"] = 95.0  # no admin = very safe
        elif admin_count <= 2:
            result["admin_key_risk"] = 80.0
        elif admin_count <= 5:
            result["admin_key_risk"] = 65.0
        elif admin_count <= 10:
            result["admin_key_risk"] = 50.0
        else:
            result["admin_key_risk"] = 30.0  # many admin functions = risky

        # Bonus: timelock reduces risk
        if admin_info["has_timelock"]:
            result["admin_key_risk"] = min(100, result["admin_key_risk"] + 15)

        # Map proxy type to upgradeability risk score (higher = safer / less upgradeable)
        proxy_scores = {
            "none": 100.0,       # no proxy = not upgradeable = safest
            "timelock": 80.0,    # timelock proxy = controlled
            "uups": 60.0,        # UUPS = self-upgrade
            "transparent": 50.0, # transparent = admin-controlled
            "beacon": 45.0,      # beacon = multiple contracts upgraded together
            "unknown": 30.0,     # unidentified proxy = uncertain
        }
        result["upgradeability_risk"] = proxy_scores.get(result.get("proxy_type", "unknown"), 30.0)

        # If verified + proxy with verified implementation, slightly better
        if result["is_proxy"] and result["implementation_verified"]:
            result["upgradeability_risk"] = min(100, result["upgradeability_risk"] + 10)

    _contract_analysis_cache[cache_key] = (_time.time(), result)
    logger.info(
        f"Contract analysis {contract_address[:10]}...: "
        f"verified={verified} proxy={result.get('proxy_type')} "
        f"admin_risk={result['admin_key_risk']} upgrade_risk={result['upgradeability_risk']}"
    )
    return result


def analyze_contract_for_index_sync(contract_address: str, chain: str = "ethereum") -> dict:
    """Synchronous wrapper around analyze_contract_for_index().

    Safe to call from synchronous collector code (runs in thread if needed).
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                asyncio.run,
                analyze_contract_for_index(contract_address, chain),
            )
            return future.result(timeout=60)
    else:
        return asyncio.run(analyze_contract_for_index(contract_address, chain))


def fetch_immunefi_bounty(slug: str) -> dict:
    """Fetch bug bounty info from Immunefi for a protocol.

    Attempts to check the Immunefi API. Returns dict:
        {"active": bool, "max_bounty": float, "source": str}

    Cached for 7 days. Falls back to empty result on failure.
    """
    import time as _time

    cache_key = slug.lower()
    cached = _immunefi_cache.get(cache_key)
    if cached and (_time.time() - cached[0]) < _IMMUNEFI_TTL:
        return cached[1]

    result = {"active": False, "max_bounty": 0, "source": "immunefi"}

    # Try the Immunefi bounties API (public, no key needed)
    try:
        _time.sleep(1)  # rate limit
        resp = httpx.get("https://immunefi.com/api/bounties", timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            bounties = data if isinstance(data, list) else data.get("bounties", [])
            slug_lower = slug.lower()
            for bounty in bounties:
                b_id = (bounty.get("id") or bounty.get("slug") or "").lower()
                b_project = (bounty.get("project") or "").lower()
                if slug_lower in b_id or slug_lower in b_project:
                    result["active"] = True
                    max_reward = bounty.get("maxBounty") or bounty.get("maximumReward") or 0
                    if isinstance(max_reward, str):
                        max_reward = float(max_reward.replace(",", "").replace("$", ""))
                    result["max_bounty"] = float(max_reward)
                    break

        _immunefi_cache[cache_key] = (_time.time(), result)
    except Exception as e:
        logger.debug(f"Immunefi bounty fetch failed for {slug}: {e}")
        _immunefi_cache[cache_key] = (_time.time(), result)

    return result
