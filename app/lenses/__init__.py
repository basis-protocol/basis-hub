"""
Regulatory Lens System
=======================
Each lens maps SII/PSI components to regulatory criteria.
Lenses are JSON configs loaded at startup. The apply_lens()
function classifies an entity against a regulatory framework.
"""

import json
import os
import logging

logger = logging.getLogger(__name__)

_LENS_DIR = os.path.dirname(__file__)
_LENS_CACHE: dict = {}


def load_lens(lens_id: str) -> dict | None:
    """Load a lens config by ID. Returns None if not found."""
    if lens_id in _LENS_CACHE:
        return _LENS_CACHE[lens_id]

    path = os.path.join(_LENS_DIR, f"{lens_id}.json")
    if not os.path.exists(path):
        logger.warning(f"Lens not found: {lens_id}")
        return None

    with open(path) as f:
        config = json.load(f)
    _LENS_CACHE[lens_id] = config
    return config


def list_lenses() -> list[dict]:
    """List all available lenses with metadata."""
    lenses = []
    for fname in sorted(os.listdir(_LENS_DIR)):
        if fname.endswith(".json"):
            config = load_lens(fname.replace(".json", ""))
            if config:
                lenses.append({
                    "lens_id": config.get("lens_id"),
                    "framework": config.get("framework"),
                    "lens_version": config.get("lens_version"),
                })
    return lenses


def apply_lens(lens_config: dict, report_data: dict) -> dict:
    """
    Apply a regulatory lens to assembled report data.
    Returns classification result with per-criterion pass/fail.
    """
    lens_id = lens_config.get("lens_id", "unknown")
    framework = lens_config.get("framework", "Unknown Framework")
    classification = lens_config.get("classification", {})

    results = {}
    overall_pass = True

    for group_id, group in classification.items():
        criteria = group.get("criteria", [])
        all_required = group.get("all_required", True)
        criterion_results = []

        for criterion in criteria:
            passed = _evaluate_criterion(criterion, report_data)
            criterion_results.append({
                "name": criterion["name"],
                "passed": passed,
                "threshold": criterion.get("threshold"),
                "categories": criterion.get("sii_categories", []),
                "logic": criterion.get("logic"),
            })

        group_passed = all(c["passed"] for c in criterion_results) if all_required \
            else any(c["passed"] for c in criterion_results)
        if not group_passed:
            overall_pass = False

        results[group_id] = {
            "passed": group_passed,
            "all_required": all_required,
            "criteria": criterion_results,
        }

    return {
        "lens_id": lens_id,
        "lens_version": lens_config.get("lens_version"),
        "framework": framework,
        "classification": results,
        "overall_pass": overall_pass,
    }


def _evaluate_criterion(criterion: dict, report_data: dict) -> bool:
    """Evaluate a single criterion against report data."""
    logic = criterion.get("logic", "category_score_above")
    threshold = criterion.get("threshold", 0)
    categories = criterion.get("sii_categories", [])

    cat_scores = report_data.get("categories") or report_data.get("category_scores") or {}

    if logic == "category_score_above":
        for cat in categories:
            val = cat_scores.get(cat)
            if isinstance(val, dict):
                val = val.get("score")
            if val is None or float(val) < threshold:
                return False
        return True

    if logic == "sub_score_above":
        sub_cats = criterion.get("sub_categories", [])
        structural = report_data.get("structural_breakdown") or {}
        for sub in sub_cats:
            val = structural.get(sub)
            if isinstance(val, dict):
                val = val.get("score")
            if val is None or float(val) < threshold:
                return False
        return True

    return False
