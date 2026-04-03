"""
Parse Squads webhook payloads and extract stablecoin mints / protocol programs.
Handles multiple payload shapes since Squads format isn't fully standardized.
"""

from .config import STABLECOIN_MINTS, PROTOCOL_PROGRAMS


def extract_instructions(body: dict) -> list[dict]:
    """Try multiple payload shapes to find instructions."""
    return (
        body.get("instructions")
        or body.get("message", {}).get("instructions")
        or body.get("transaction", {}).get("message", {}).get("instructions")
        or []
    )


def _collect_pubkeys(instructions: list[dict]) -> set[str]:
    """Gather all pubkeys from instruction accounts and program IDs."""
    pubkeys: set[str] = set()
    for ix in instructions:
        program_id = ix.get("programId", "")
        if program_id:
            pubkeys.add(program_id)
        for account in ix.get("accounts", []):
            if isinstance(account, dict):
                pk = account.get("pubkey", "")
            else:
                pk = str(account)
            if pk:
                pubkeys.add(pk)
        # Also scan data field for mint addresses
        data = str(ix.get("data", ""))
        for mint in STABLECOIN_MINTS:
            if mint in data:
                pubkeys.add(mint)
    return pubkeys


def extract_stablecoins(instructions: list[dict]) -> list[str]:
    """Return list of stablecoin mint addresses found in instructions."""
    pubkeys = _collect_pubkeys(instructions)
    return [pk for pk in pubkeys if pk in STABLECOIN_MINTS]


def extract_protocols(instructions: list[dict]) -> list[str]:
    """Return list of protocol program IDs found in instructions."""
    pubkeys = _collect_pubkeys(instructions)
    return [pk for pk in pubkeys if pk in PROTOCOL_PROGRAMS]
