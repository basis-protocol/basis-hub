"""
Contract Upgrade Delta Tracker (Pipeline 3)
=============================================
Every time a scored contract's bytecode changes, capture and store the
before/after as permanent attested state.  Historical vulnerability deltas
that cannot be reconstructed after the fact.

Runs daily in the slow cycle.  Never raises — all errors logged and skipped.
"""

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.database import fetch_all, fetch_one, execute, get_cursor

logger = logging.getLogger(__name__)

# EIP-1967 implementation storage slot
EIP1967_IMPLEMENTATION_SLOT = (
    "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"
)


# ---------------------------------------------------------------------------
# RPC helpers (reuse pattern from smart_contract.py)
# ---------------------------------------------------------------------------

def _get_rpc_url(chain: str = "ethereum") -> str:
    alchemy_key = os.environ.get("ALCHEMY_API_KEY", "")
    if not alchemy_key:
        return ""
    chain_map = {
        "ethereum": "eth-mainnet",
        "arbitrum": "arb-mainnet",
        "optimism": "opt-mainnet",
        "base": "base-mainnet",
        "polygon": "polygon-mainnet",
    }
    network = chain_map.get(chain, "eth-mainnet")
    return f"https://{network}.g.alchemy.com/v2/{alchemy_key}"


def _get_etherscan_bytecode(address: str) -> str | None:
    """Fallback: fetch bytecode via Etherscan for Ethereum mainnet."""
    api_key = os.environ.get("ETHERSCAN_API_KEY", "")
    if not api_key:
        return None
    try:
        resp = httpx.get(
            "https://api.etherscan.io/api",
            params={
                "module": "proxy",
                "action": "eth_getCode",
                "address": address,
                "tag": "latest",
                "apikey": api_key,
            },
            timeout=15,
        )
        data = resp.json()
        result = data.get("result", "0x")
        if result and result != "0x":
            return result
    except Exception as e:
        logger.debug(f"Etherscan bytecode fetch failed for {address}: {e}")
    return None


def _rpc_get_code(rpc_url: str, address: str) -> str | None:
    """Fetch bytecode via eth_getCode RPC call."""
    if not rpc_url:
        return None
    try:
        resp = httpx.post(
            rpc_url,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "eth_getCode",
                "params": [address, "latest"],
            },
            timeout=15,
        )
        data = resp.json()
        result = data.get("result", "0x")
        if result and result != "0x":
            return result
    except Exception as e:
        logger.debug(f"RPC eth_getCode failed for {address}: {e}")
    return None


def _rpc_get_storage_at(rpc_url: str, address: str, slot: str) -> str:
    """Read a storage slot via RPC."""
    if not rpc_url:
        return "0x" + "00" * 32
    try:
        resp = httpx.post(
            rpc_url,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "eth_getStorageAt",
                "params": [address, slot, "latest"],
            },
            timeout=15,
        )
        data = resp.json()
        return data.get("result", "0x" + "00" * 32)
    except Exception as e:
        logger.debug(f"RPC eth_getStorageAt failed for {address}: {e}")
        return "0x" + "00" * 32


def _hash_bytecode(bytecode: str) -> str:
    """SHA-256 hash of bytecode, returned as 0x-prefixed hex."""
    return "0x" + hashlib.sha256(bytecode.encode()).hexdigest()


def _resolve_implementation(rpc_url: str, proxy_address: str) -> str | None:
    """Resolve EIP-1967 implementation address from storage slot."""
    raw = _rpc_get_storage_at(rpc_url, proxy_address, EIP1967_IMPLEMENTATION_SLOT)
    if raw and raw != "0x" + "00" * 32 and len(raw) >= 42:
        addr = "0x" + raw[-40:]
        if addr != "0x" + "0" * 40:
            return addr
    return None


# ---------------------------------------------------------------------------
# Build contract list from scored entities
# ---------------------------------------------------------------------------

def _load_contract_registry() -> dict:
    registry_path = Path(__file__).parent.parent / "config" / "contract_registry.json"
    try:
        with open(registry_path) as f:
            return json.load(f)
    except Exception as e:
        logger.debug(f"Could not load contract registry: {e}")
        return {"protocols": {}, "bridges": {}}


def _build_contract_targets() -> list[dict]:
    """
    Build list of contract targets from:
      1. stablecoins table (token contracts)
      2. contract_registry.json (protocol + bridge contracts)
    Returns list of {entity_type, entity_id, entity_symbol, contract_address, chain}.
    """
    targets = []

    # Stablecoin token contracts from DB
    try:
        rows = fetch_all(
            "SELECT id, symbol, contract_address FROM stablecoins WHERE contract_address IS NOT NULL"
        )
        for row in rows or []:
            addr = row.get("contract_address", "")
            if addr and len(addr) >= 40:
                targets.append({
                    "entity_type": "stablecoin",
                    "entity_id": row["id"],
                    "entity_symbol": row.get("symbol", ""),
                    "contract_address": addr.lower(),
                    "chain": "ethereum",
                })
    except Exception as e:
        logger.warning(f"Failed to load stablecoin contracts: {e}")

    # Protocol + bridge contracts from registry
    registry = _load_contract_registry()

    # Protocol contracts
    for slug, cfg in registry.get("protocols", {}).items():
        # Look up entity_id from DB
        proto_row = fetch_one(
            "SELECT id FROM psi_scores WHERE protocol_slug = %s ORDER BY computed_at DESC LIMIT 1",
            (slug,),
        )
        entity_id = proto_row["id"] if proto_row else 0

        for contract_key in ("governance_timelock", "multisig", "core_contract"):
            contract_cfg = cfg.get(contract_key)
            if contract_cfg and contract_cfg.get("address"):
                targets.append({
                    "entity_type": "protocol",
                    "entity_id": entity_id,
                    "entity_symbol": slug,
                    "contract_address": contract_cfg["address"].lower(),
                    "chain": contract_cfg.get("chain", "ethereum"),
                })

    # Bridge contracts
    for slug, cfg in registry.get("bridges", {}).items():
        for contract_key in ("guardian_contract", "timelock"):
            contract_cfg = cfg.get(contract_key)
            if contract_cfg and contract_cfg.get("address"):
                targets.append({
                    "entity_type": "bridge",
                    "entity_id": 0,
                    "entity_symbol": slug,
                    "contract_address": contract_cfg["address"].lower(),
                    "chain": contract_cfg.get("chain", "ethereum"),
                })

    return targets


# ---------------------------------------------------------------------------
# Main collector
# ---------------------------------------------------------------------------

def collect_contract_upgrades() -> dict:
    """
    Scan all scored entity contracts for bytecode changes.
    Returns summary: {entities_checked, upgrades_detected, first_captures, errors}.
    """
    targets = _build_contract_targets()
    if not targets:
        logger.info("Contract upgrade tracker: no targets found")
        return {"entities_checked": 0, "upgrades_detected": 0, "first_captures": 0}

    entities_checked = 0
    upgrades_detected = 0
    first_captures = 0
    errors = 0

    for target in targets:
        try:
            address = target["contract_address"]
            chain = target["chain"]
            rpc_url = _get_rpc_url(chain)

            # Fetch current bytecode
            bytecode = _rpc_get_code(rpc_url, address)
            if not bytecode and chain == "ethereum":
                bytecode = _get_etherscan_bytecode(address)
            if not bytecode:
                logger.debug(f"No bytecode for {address} on {chain}")
                continue

            current_hash = _hash_bytecode(bytecode)
            entities_checked += 1

            # Check for proxy and resolve implementation
            impl_address = _resolve_implementation(rpc_url, address)
            is_proxy = impl_address is not None
            impl_bytecode_hash = None
            if impl_address:
                impl_bytecode = _rpc_get_code(rpc_url, impl_address)
                if impl_bytecode:
                    impl_bytecode_hash = _hash_bytecode(impl_bytecode)

            # Look up most recent snapshot
            last_snapshot = fetch_one(
                """SELECT bytecode_hash, implementation_address
                   FROM contract_bytecode_snapshots
                   WHERE contract_address = %s AND chain = %s
                   ORDER BY captured_at DESC LIMIT 1""",
                (address, chain),
            )

            if not last_snapshot:
                # First capture — insert snapshot, no upgrade record
                execute(
                    """INSERT INTO contract_bytecode_snapshots
                        (contract_address, chain, bytecode_hash, implementation_address,
                         is_proxy, is_verified, captured_at)
                       VALUES (%s, %s, %s, %s, %s, FALSE, NOW())
                       ON CONFLICT (contract_address, chain, bytecode_hash) DO NOTHING""",
                    (address, chain, current_hash, impl_address, is_proxy),
                )
                first_captures += 1

            elif last_snapshot["bytecode_hash"] != current_hash:
                # Upgrade detected!
                now = datetime.now(timezone.utc)
                content_data = (
                    f"{target['entity_id']}{address}{chain}"
                    f"{current_hash}{now.isoformat()}"
                )
                content_hash = "0x" + hashlib.sha256(content_data.encode()).hexdigest()

                # Insert new snapshot
                execute(
                    """INSERT INTO contract_bytecode_snapshots
                        (contract_address, chain, bytecode_hash, implementation_address,
                         is_proxy, is_verified, captured_at)
                       VALUES (%s, %s, %s, %s, %s, FALSE, NOW())
                       ON CONFLICT (contract_address, chain, bytecode_hash) DO NOTHING""",
                    (address, chain, current_hash, impl_address, is_proxy),
                )

                # Insert upgrade record
                execute(
                    """INSERT INTO contract_upgrade_history
                        (entity_type, entity_id, entity_symbol, contract_address, chain,
                         previous_bytecode_hash, current_bytecode_hash,
                         previous_implementation, current_implementation,
                         slither_queued, content_hash, attested_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s, NOW())""",
                    (
                        target["entity_type"],
                        target["entity_id"],
                        target["entity_symbol"],
                        address,
                        chain,
                        last_snapshot["bytecode_hash"],
                        current_hash,
                        last_snapshot.get("implementation_address"),
                        impl_address,
                        content_hash,
                    ),
                )

                # Attest
                try:
                    from app.state_attestation import attest_state
                    attest_state("contract_upgrades", [{
                        "entity_id": target["entity_id"],
                        "contract_address": address,
                        "chain": chain,
                        "current_bytecode_hash": current_hash,
                        "upgrade_detected_at": now.isoformat(),
                    }], str(target["entity_id"]))
                except Exception as ae:
                    logger.debug(f"Contract upgrade attestation failed: {ae}")

                logger.warning(
                    f"CONTRACT UPGRADE DETECTED: {target['entity_symbol']} "
                    f"on {chain} ({address})"
                )
                upgrades_detected += 1

            else:
                # No change — update captured_at on latest snapshot
                execute(
                    """UPDATE contract_bytecode_snapshots
                       SET captured_at = NOW()
                       WHERE contract_address = %s AND chain = %s AND bytecode_hash = %s""",
                    (address, chain, current_hash),
                )

            # Rate limit: small sleep between RPC calls
            time.sleep(0.3)

        except Exception as e:
            logger.debug(f"Contract upgrade check failed for {target.get('contract_address')}: {e}")
            errors += 1

    summary = {
        "entities_checked": entities_checked,
        "upgrades_detected": upgrades_detected,
        "first_captures": first_captures,
        "errors": errors,
    }
    logger.info(
        f"Contract upgrade tracker: checked={entities_checked} "
        f"upgrades={upgrades_detected} first_captures={first_captures} errors={errors}"
    )
    return summary
