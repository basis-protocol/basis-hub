"""
APIRouter with all Squads Guard endpoints.
Can be mounted into the hub or used standalone via main.py.
"""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .config import BASIS_API_URL
from .extractor import extract_instructions, extract_stablecoins, extract_protocols
from .scorer import score_transaction, score_by_ids
from .formatter import format_assessment

logger = logging.getLogger("squads-guard")

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok", "service": "basis-squads-guard", "version": "1.0.0"}


@router.post("/webhook")
async def squads_webhook(request: Request):
    """
    Receive a Squads transaction proposal webhook.
    Score all stablecoins and protocols in the transaction.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})

    logger.info(f"Webhook received: {list(body.keys())}")

    instructions = extract_instructions(body)
    stablecoin_mints = extract_stablecoins(instructions)
    protocol_programs = extract_protocols(instructions)

    sii_scores, psi_scores, cqi_scores = await score_transaction(
        stablecoin_mints, protocol_programs
    )

    assessment = format_assessment(sii_scores, psi_scores, cqi_scores)

    logger.info(
        f"Assessment: status={assessment['status']}, "
        f"stablecoins={len(sii_scores)}, "
        f"protocols={len(psi_scores)}, "
        f"cqi_pairs={len(cqi_scores)}"
    )

    return assessment


@router.post("/score")
async def score_manual(request: Request):
    """
    Manual scoring — pass stablecoin IDs and/or protocol slugs directly.
    Body: {"stablecoins": ["usdc", "usdt"], "protocols": ["drift"]}
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})

    coin_ids = body.get("stablecoins", [])
    slugs = body.get("protocols", [])

    sii_scores, psi_scores, cqi_scores = await score_by_ids(coin_ids, slugs)
    return format_assessment(sii_scores, psi_scores, cqi_scores)


@router.get("/demo/drift")
async def demo_drift():
    """Demo — USDC/USDT + Drift, no input needed."""
    sii_scores, psi_scores, cqi_scores = await score_by_ids(
        ["usdc", "usdt"], ["drift"]
    )
    return format_assessment(sii_scores, psi_scores, cqi_scores)
