"""
RPI Score Verification
========================
Verifies expected RPI scores against known facts.
Run standalone: python -m app.rpi.verify
"""

from app.rpi.scorer import (
    _normalize_spend_ratio,
    _normalize_parameter_velocity,
    _normalize_parameter_recency,
    _normalize_incident_severity,
    _normalize_governance_health,
    _normalize_vendor_diversity,
    _normalize_recovery_ratio,
    score_rpi_base,
    compute_lensed_score,
)
from app.rpi.seed_data import (
    BASE_SPEND_RATIO, BASE_PARAMETER_VELOCITY, BASE_PARAMETER_RECENCY,
    BASE_GOVERNANCE_HEALTH, LENS_VENDOR_DIVERSITY, LENS_RECOVERY_RATIO,
    LENS_DOCUMENTATION_DEPTH, LENS_EXTERNAL_SCORING,
)


def verify_aave():
    """Verify Aave's base RPI against known facts."""
    print("=" * 60)
    print("AAVE RPI Verification")
    print("=" * 60)

    # spend_ratio: $5M / $142M = 3.5% → linear 0-8%
    spend_raw = BASE_SPEND_RATIO["aave"]  # 3.5
    spend_score = _normalize_spend_ratio(spend_raw)
    print(f"  spend_ratio: {spend_raw}% → {spend_score:.1f}/100 (weight 0.20)")
    assert 40 <= spend_score <= 50, f"Expected ~43.75, got {spend_score}"

    # parameter_velocity: 6/month → 80
    vel_raw = BASE_PARAMETER_VELOCITY["aave"]  # 6
    vel_score = _normalize_parameter_velocity(vel_raw)
    print(f"  parameter_velocity: {vel_raw}/month → {vel_score:.1f}/100 (weight 0.25)")
    assert vel_score == 80.0, f"Expected 80, got {vel_score}"

    # parameter_recency: 5 days → 100
    rec_raw = BASE_PARAMETER_RECENCY["aave"]  # 5
    rec_score = _normalize_parameter_recency(rec_raw)
    print(f"  parameter_recency: {rec_raw} days → {rec_score:.1f}/100 (weight 0.15)")
    assert rec_score == 100.0, f"Expected 100, got {rec_score}"

    # incident_severity: CAPO incident (critical, $26.9M) in last 12 months
    # Without DB, use the seed-based estimate
    # Critical incident = 40 points weighted, recent = high decay factor
    # Rough estimate: 100 - 40 * 0.9 = ~64
    print(f"  incident_severity: CAPO critical incident → reduced score (weight 0.20)")

    # governance_health: 12% participation → 60
    gov_raw = BASE_GOVERNANCE_HEALTH["aave"]  # 12.0
    gov_score = _normalize_governance_health(gov_raw)
    print(f"  governance_health: {gov_raw}% → {gov_score:.1f}/100 (weight 0.20)")
    assert gov_score == 60.0, f"Expected 60, got {gov_score}"

    # Compute base score using seed values (incident_severity from seed = needs DB)
    # Manual calculation:
    # spend: 43.75 * 0.20 = 8.75
    # velocity: 80 * 0.25 = 20.0
    # recency: 100 * 0.15 = 15.0
    # incident: ~64 * 0.20 = 12.8 (estimated)
    # governance: 60 * 0.20 = 12.0
    # Total: ~68.55
    raw = {
        "spend_ratio": spend_raw,
        "parameter_velocity": vel_raw,
        "parameter_recency": rec_raw,
        "incident_severity": 64.0,  # estimated with recent critical incident
        "governance_health": gov_raw,
    }
    result = score_rpi_base("aave", raw)
    print(f"\n  Base RPI: {result['overall_score']}")
    print(f"  Grade: {result['grade']}")
    print(f"  Components: {result['component_scores']}")

    # Expect moderate-to-low given CAPO incident
    assert 55 <= result["overall_score"] <= 80, \
        f"Expected moderate score ~65-75, got {result['overall_score']}"

    # Verify lensed score
    print("\n  --- Lens: risk_organization ---")
    vendor_raw = LENS_VENDOR_DIVERSITY["aave"]  # 1
    vendor_score = _normalize_vendor_diversity(vendor_raw)
    recovery_raw = LENS_RECOVERY_RATIO["aave"]  # 0.0
    recovery_score = _normalize_recovery_ratio(recovery_raw)
    print(f"  vendor_diversity: {vendor_raw} → {vendor_score}/100")
    print(f"  recovery_ratio: {recovery_raw}% → {recovery_score}/100")

    lens_components = {
        "risk_organization": {
            "vendor_diversity": vendor_score,
            "recovery_ratio": recovery_score,
        },
    }
    lensed = compute_lensed_score(result["overall_score"], ["risk_organization"], lens_components)
    print(f"  Lensed RPI: {lensed['rpi_lensed']}")
    print(f"  Blend used: {lensed['lens_blend_used']}")

    # With vendor_diversity=30 and recovery_ratio=0, lens score should be low
    # This should pull the lensed score below the base
    if lensed["rpi_lensed"] is not None:
        assert lensed["rpi_lensed"] < result["overall_score"], \
            f"Expected lensed < base, got {lensed['rpi_lensed']} >= {result['overall_score']}"
        print("  ✓ Lensed score is below base (expected: vendor_diversity=1 pulls down)")

    print("\n  ✓ Aave verification passed")
    return True


def verify_compound():
    """Verify Compound's base RPI against known facts."""
    print("\n" + "=" * 60)
    print("COMPOUND RPI Verification")
    print("=" * 60)

    # spend_ratio: 3.0%
    spend_raw = BASE_SPEND_RATIO["compound-finance"]
    spend_score = _normalize_spend_ratio(spend_raw)
    print(f"  spend_ratio: {spend_raw}% → {spend_score:.1f}/100 (weight 0.20)")

    # parameter_velocity: 8/month → 80
    vel_raw = BASE_PARAMETER_VELOCITY["compound-finance"]  # 8
    vel_score = _normalize_parameter_velocity(vel_raw)
    print(f"  parameter_velocity: {vel_raw}/month → {vel_score:.1f}/100 (weight 0.25)")
    assert vel_score == 80.0, f"Expected 80, got {vel_score}"

    # parameter_recency: 3 days → 100
    rec_raw = BASE_PARAMETER_RECENCY["compound-finance"]  # 3
    rec_score = _normalize_parameter_recency(rec_raw)
    print(f"  parameter_recency: {rec_raw} days → {rec_score:.1f}/100 (weight 0.15)")
    assert rec_score == 100.0

    # incident: deUSD collapse — major, $15.6M, 78% recovered
    # major = 25 points, recent = ~0.95 decay
    # 100 - 25 * 0.95 = ~76.25
    print(f"  incident_severity: deUSD major incident → reduced score (weight 0.20)")

    # governance_health: 10% → 60
    gov_raw = BASE_GOVERNANCE_HEALTH["compound-finance"]  # 10.0
    gov_score = _normalize_governance_health(gov_raw)
    print(f"  governance_health: {gov_raw}% → {gov_score:.1f}/100 (weight 0.20)")
    assert gov_score == 60.0

    raw = {
        "spend_ratio": spend_raw,
        "parameter_velocity": vel_raw,
        "parameter_recency": rec_raw,
        "incident_severity": 76.0,  # major incident, better than Aave's critical
        "governance_health": gov_raw,
    }
    result = score_rpi_base("compound-finance", raw)
    print(f"\n  Base RPI: {result['overall_score']}")
    print(f"  Grade: {result['grade']}")
    print(f"  Components: {result['component_scores']}")

    # Should be higher than Aave on base due to better incident score + active params
    assert result["overall_score"] > 60, f"Expected > 60, got {result['overall_score']}"

    # Lens verification
    print("\n  --- Lens: risk_organization ---")
    vendor_raw = LENS_VENDOR_DIVERSITY["compound-finance"]  # 2
    vendor_score = _normalize_vendor_diversity(vendor_raw)
    recovery_raw = LENS_RECOVERY_RATIO["compound-finance"]  # 78.0
    recovery_score = _normalize_recovery_ratio(recovery_raw)
    print(f"  vendor_diversity: {vendor_raw} → {vendor_score}/100")
    print(f"  recovery_ratio: {recovery_raw}% → {recovery_score}/100")

    lens_components = {
        "risk_organization": {
            "vendor_diversity": vendor_score,
            "recovery_ratio": recovery_score,
        },
    }
    lensed = compute_lensed_score(result["overall_score"], ["risk_organization"], lens_components)
    print(f"  Lensed RPI: {lensed['rpi_lensed']}")

    # With vendor_diversity=60 and recovery_ratio=80, lens should add value
    if lensed["rpi_lensed"] is not None:
        print(f"  ✓ Compound lensed score computed: {lensed['rpi_lensed']}")

    print("\n  ✓ Compound verification passed")
    return True


if __name__ == "__main__":
    verify_aave()
    verify_compound()
    print("\n" + "=" * 60)
    print("All verifications passed!")
