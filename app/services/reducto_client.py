"""
Reducto API client.
PDF document parsing with schema-level extraction and confidence scoring.
Used for attestation PDFs (Grant Thornton, BDO, Deloitte reports).
Docs: https://docs.reducto.ai
"""
import os
import httpx
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

REDUCTO_BASE = "https://platform.reducto.ai"


def _get_key():
    return os.getenv("REDUCTO_API_KEY")


def _headers():
    return {
        "Authorization": f"Bearer {_get_key()}",
        "Content-Type": "application/json",
    }


# BRSS attestation schema — one schema for ALL issuers
BRSS_ATTESTATION_SCHEMA = {
    "type": "object",
    "properties": {
        "issuer_name": {"type": "string", "description": "Name of the stablecoin issuer"},
        "asset_name": {"type": "string", "description": "Name of the token (e.g. USDC, USDT)"},
        "attestation_date": {"type": "string", "description": "As-of date of the report"},
        "total_reserves_usd": {"type": "number", "description": "Total reserves in USD"},
        "total_supply": {"type": "number", "description": "Total circulating supply"},
        "reserve_composition": {
            "type": "object",
            "properties": {
                "cash_and_deposits_pct": {"type": "number"},
                "us_treasury_bills_pct": {"type": "number"},
                "us_treasury_bonds_pct": {"type": "number"},
                "reverse_repo_pct": {"type": "number"},
                "commercial_paper_pct": {"type": "number"},
                "money_market_funds_pct": {"type": "number"},
                "corporate_bonds_pct": {"type": "number"},
                "secured_loans_pct": {"type": "number"},
                "crypto_collateral_pct": {"type": "number"},
                "other_pct": {"type": "number"}
            }
        },
        "auditor_name": {"type": "string"},
        "report_type": {"type": "string"},
        "custodians": {"type": "array", "items": {"type": "string"}},
        "jurisdiction": {"type": "string"}
    }
}


async def parse_pdf(pdf_url: str, schema: dict = None) -> dict:
    """
    Parse a PDF and extract structured data matching schema.
    Uses Reducto's /extract endpoint with JSON schema.
    Returns extracted fields with confidence scores per field.
    """
    if not _get_key():
        logger.warning("REDUCTO_API_KEY not set, skipping PDF parse")
        return {"error": "no_api_key"}

    if schema is None:
        schema = BRSS_ATTESTATION_SCHEMA

    async with httpx.AsyncClient(timeout=180) as client:
        try:
            resp = await client.post(
                f"{REDUCTO_BASE}/extract",
                headers=_headers(),
                json={
                    "input": pdf_url,
                    "instructions": {
                        "schema": schema,
                        "system_prompt": "This is a stablecoin reserve attestation report from an accounting firm.",
                    },
                    "settings": {
                        "citations": {"enabled": True},
                    },
                }
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Reducto parse failed for {pdf_url}: {e}")
            return {"error": str(e)}


async def parse_to_markdown(pdf_url: str) -> dict:
    """
    Parse a PDF into markdown chunks without schema extraction.
    Uses Reducto's /parse endpoint.
    Useful when you don't know the document structure.
    """
    if not _get_key():
        return {"error": "no_api_key"}

    async with httpx.AsyncClient(timeout=180) as client:
        try:
            resp = await client.post(
                f"{REDUCTO_BASE}/parse",
                headers=_headers(),
                json={"input": pdf_url}
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Reducto markdown parse failed for {pdf_url}: {e}")
            return {"error": str(e)}
