"""
Unit tests for pure playground functions (DB-dependent tests deferred).

Tests:
- validate_portfolio: boundary conditions, invalid inputs, valid inputs
- compute_content_hash: determinism and idempotency
- _grade: all grade boundaries
- _recompute_aggregate / _recompute_from_scores: weighted average math
- render_basel_sco60_preview: content structure, no DB calls
- compute_aggregate_cqi: mocked DB lookups
- compute_stress_scenarios: mocked via aggregate_cqi
"""

import hashlib
import json
from unittest.mock import patch, MagicMock

import pytest

from app.playground import (
    validate_portfolio,
    compute_content_hash,
    render_basel_sco60_preview,
    _grade,
    _recompute_aggregate,
    _recompute_from_scores,
    ValidationError,
)


# =============================================================================
# validate_portfolio
# =============================================================================

class TestValidatePortfolio:

    def test_empty_portfolio(self):
        errors = validate_portfolio([])
        assert len(errors) == 1
        assert errors[0].field == "portfolio"
        assert "empty" in errors[0].message.lower()

    def test_exceeds_max_positions(self):
        portfolio = [{"asset_symbol": f"TOKEN{i}", "amount": 100} for i in range(51)]
        errors = validate_portfolio(portfolio)
        assert len(errors) == 1
        assert "max 50" in errors[0].message.lower() or "51" in errors[0].message

    def test_exactly_50_positions_valid(self):
        portfolio = [{"asset_symbol": f"TOKEN{i}", "amount": 100} for i in range(50)]
        errors = validate_portfolio(portfolio)
        assert len(errors) == 0

    def test_missing_asset_symbol(self):
        errors = validate_portfolio([{"amount": 100}])
        assert any("asset_symbol" in e.message.lower() for e in errors)

    def test_zero_amount(self):
        errors = validate_portfolio([{"asset_symbol": "USDC", "amount": 0}])
        assert any("amount" in e.field for e in errors)

    def test_negative_amount(self):
        errors = validate_portfolio([{"asset_symbol": "USDC", "amount": -100}])
        assert any("amount" in e.field for e in errors)

    def test_none_amount(self):
        errors = validate_portfolio([{"asset_symbol": "USDC", "amount": None}])
        assert any("amount" in e.field for e in errors)

    def test_valid_single_position(self):
        errors = validate_portfolio([{"asset_symbol": "USDC", "amount": 10000}])
        assert len(errors) == 0

    def test_valid_multi_position(self):
        portfolio = [
            {"asset_symbol": "USDC", "amount": 10000, "protocol_slug": "aave"},
            {"asset_symbol": "USDT", "amount": 5000},
            {"asset_symbol": "DAI", "amount": 3000, "protocol_slug": "morpho"},
        ]
        errors = validate_portfolio(portfolio)
        assert len(errors) == 0

    def test_multiple_errors(self):
        portfolio = [
            {"amount": 100},  # missing symbol
            {"asset_symbol": "USDC", "amount": -50},  # negative amount
        ]
        errors = validate_portfolio(portfolio)
        assert len(errors) >= 2


# =============================================================================
# _grade
# =============================================================================

class TestGrade:

    def test_grade_a(self):
        assert _grade(95) == "A"
        assert _grade(90) == "A"

    def test_grade_b(self):
        assert _grade(85) == "B"
        assert _grade(80) == "B"

    def test_grade_c(self):
        assert _grade(75) == "C"
        assert _grade(70) == "C"

    def test_grade_d(self):
        assert _grade(65) == "D"
        assert _grade(60) == "D"

    def test_grade_f(self):
        assert _grade(59) == "F"
        assert _grade(0) == "F"
        assert _grade(30) == "F"

    def test_boundary_89(self):
        assert _grade(89.9) == "B"

    def test_boundary_100(self):
        assert _grade(100) == "A"


# =============================================================================
# _recompute_aggregate / _recompute_from_scores
# =============================================================================

class TestRecomputeAggregate:

    def test_single_position(self):
        positions = [{"amount": 1000, "cqi_score": 80}]
        result = _recompute_aggregate(positions, 1000)
        assert result == 80.0

    def test_equal_weight_two_positions(self):
        positions = [
            {"amount": 500, "cqi_score": 80},
            {"amount": 500, "cqi_score": 60},
        ]
        result = _recompute_aggregate(positions, 1000)
        assert result == 70.0

    def test_weighted_positions(self):
        positions = [
            {"amount": 900, "cqi_score": 90},
            {"amount": 100, "cqi_score": 50},
        ]
        result = _recompute_aggregate(positions, 1000)
        assert result == 86.0  # 0.9*90 + 0.1*50

    def test_zero_total_value(self):
        result = _recompute_aggregate([{"amount": 0, "cqi_score": 80}], 0)
        assert result == 0

    def test_empty_positions(self):
        result = _recompute_aggregate([], 1000)
        assert result == 0

    def test_none_cqi_score(self):
        positions = [{"amount": 1000, "cqi_score": None}]
        result = _recompute_aggregate(positions, 1000)
        assert result == 0


class TestRecomputeFromScores:

    def test_equal_amounts(self):
        positions = [
            {"amount": 100, "cqi_score": 80},
            {"amount": 100, "cqi_score": 60},
        ]
        result = _recompute_from_scores(positions)
        assert result == 70.0

    def test_zero_total(self):
        positions = [{"amount": 0, "cqi_score": 80}]
        result = _recompute_from_scores(positions)
        assert result == 0


# =============================================================================
# compute_content_hash
# =============================================================================

class TestContentHash:

    def test_deterministic(self):
        portfolio = [{"asset_symbol": "USDC", "amount": 1000}]
        ts = "2026-04-20T00:00:00Z"
        h1 = compute_content_hash(portfolio, ts)
        h2 = compute_content_hash(portfolio, ts)
        assert h1 == h2

    def test_different_portfolios(self):
        p1 = [{"asset_symbol": "USDC", "amount": 1000}]
        p2 = [{"asset_symbol": "USDT", "amount": 1000}]
        ts = "2026-04-20T00:00:00Z"
        assert compute_content_hash(p1, ts) != compute_content_hash(p2, ts)

    def test_different_timestamps(self):
        portfolio = [{"asset_symbol": "USDC", "amount": 1000}]
        h1 = compute_content_hash(portfolio, "2026-04-20T00:00:00Z")
        h2 = compute_content_hash(portfolio, "2026-04-21T00:00:00Z")
        assert h1 != h2

    def test_returns_hex_string(self):
        h = compute_content_hash([{"asset_symbol": "USDC", "amount": 1}], "ts")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


# =============================================================================
# render_basel_sco60_preview
# =============================================================================

class TestRenderBaselPreview:

    def _make_cqi(self, aggregate=82.5, grade="B", positions=None):
        if positions is None:
            positions = [
                {"asset": "USDC", "weight": 60, "sii_score": 85, "cqi_score": 82, "amount": 6000},
                {"asset": "USDT", "weight": 30, "sii_score": 80, "cqi_score": 78, "amount": 3000},
                {"asset": "DAI", "weight": 10, "sii_score": 75, "cqi_score": 72, "amount": 1000},
            ]
        return {
            "aggregate_cqi": aggregate,
            "grade": grade,
            "position_count": len(positions),
            "total_value": sum(p["amount"] for p in positions),
            "positions": positions,
        }

    def test_contains_classification(self):
        cqi = self._make_cqi(aggregate=85)
        result = render_basel_sco60_preview([], cqi)
        assert "Group 1a" in result

    def test_moderate_classification(self):
        cqi = self._make_cqi(aggregate=65)
        result = render_basel_sco60_preview([], cqi)
        assert "Group 1b" in result

    def test_high_risk_classification(self):
        cqi = self._make_cqi(aggregate=45)
        result = render_basel_sco60_preview([], cqi)
        assert "Group 2" in result

    def test_contains_aggregate_score(self):
        cqi = self._make_cqi(aggregate=82.5)
        result = render_basel_sco60_preview([], cqi)
        assert "82.5" in result

    def test_contains_position_table(self):
        cqi = self._make_cqi()
        result = render_basel_sco60_preview([], cqi)
        assert "USDC" in result
        assert "| Asset |" in result

    def test_is_preview_not_full(self):
        cqi = self._make_cqi()
        result = render_basel_sco60_preview([], cqi)
        assert "preview" in result.lower() or "Preview" in result
        assert "request the full report" in result.lower()

    def test_valid_markdown(self):
        cqi = self._make_cqi()
        result = render_basel_sco60_preview([], cqi)
        assert result.startswith("##")
        assert "|" in result  # has table


# =============================================================================
# compute_aggregate_cqi (mocked DB)
# =============================================================================

class TestComputeAggregateCqi:

    @patch("app.playground.fetch_one")
    def test_single_position_sii_only(self, mock_fetch):
        mock_fetch.return_value = {"overall_score": 85.0}
        portfolio = [{"asset_symbol": "USDC", "amount": 10000}]

        from app.playground import compute_aggregate_cqi
        result = compute_aggregate_cqi(portfolio)

        assert "error" not in result
        assert result["aggregate_cqi"] == 85.0
        assert len(result["positions"]) == 1

    @patch("app.playground.fetch_one")
    def test_position_with_protocol(self, mock_fetch):
        # First call: SII lookup returns score
        # Second call: PSI lookup returns score
        mock_fetch.side_effect = [
            {"overall_score": 85.0},  # SII
            {"overall_score": 75.0},  # PSI
        ]
        portfolio = [{"asset_symbol": "USDC", "amount": 10000, "protocol_slug": "aave"}]

        from app.playground import compute_aggregate_cqi
        result = compute_aggregate_cqi(portfolio)

        assert "error" not in result
        pos = result["positions"][0]
        assert pos["sii_score"] == 85.0
        assert pos["psi_score"] == 75.0
        assert pos["cqi_score"] is not None

    @patch("app.playground.fetch_one")
    def test_missing_sii_score(self, mock_fetch):
        mock_fetch.return_value = None
        portfolio = [{"asset_symbol": "UNKNOWN", "amount": 1000}]

        from app.playground import compute_aggregate_cqi
        result = compute_aggregate_cqi(portfolio)

        assert result["aggregate_cqi"] == 0

    @patch("app.playground.fetch_one")
    def test_zero_value_portfolio(self, mock_fetch):
        portfolio = [{"asset_symbol": "USDC", "amount": 0}]

        from app.playground import compute_aggregate_cqi
        result = compute_aggregate_cqi(portfolio)

        assert "error" in result


# =============================================================================
# compute_stress_scenarios (mocked via aggregate_cqi)
# =============================================================================

class TestComputeStressScenarios:

    @patch("app.playground.compute_aggregate_cqi")
    def test_returns_three_scenarios(self, mock_cqi):
        mock_cqi.return_value = {
            "aggregate_cqi": 80,
            "grade": "B",
            "total_value": 10000,
            "positions": [
                {"asset": "USDC", "amount": 7000, "sii_score": 85, "cqi_score": 82, "protocol": "aave"},
                {"asset": "USDT", "amount": 3000, "sii_score": 80, "cqi_score": 78, "protocol": None},
            ],
        }

        from app.playground import compute_stress_scenarios
        result = compute_stress_scenarios([])

        assert len(result["scenarios"]) == 3
        assert result["total_count"] == 3
        names = [s["name"] for s in result["scenarios"]]
        assert "Single-issuer depeg" in names
        assert "Algorithmic collapse" in names
        assert "Protocol contagion" in names

    @patch("app.playground.compute_aggregate_cqi")
    def test_strong_portfolio_passes_all(self, mock_cqi):
        mock_cqi.return_value = {
            "aggregate_cqi": 90,
            "grade": "A",
            "total_value": 10000,
            "positions": [
                {"asset": "USDC", "amount": 5000, "sii_score": 90, "cqi_score": 88, "protocol": "aave"},
                {"asset": "USDT", "amount": 5000, "sii_score": 88, "cqi_score": 86, "protocol": "compound"},
            ],
        }

        from app.playground import compute_stress_scenarios
        result = compute_stress_scenarios([])

        assert result["pass_count"] >= 2  # diversified portfolio should pass most

    @patch("app.playground.compute_aggregate_cqi")
    def test_error_propagates(self, mock_cqi):
        mock_cqi.return_value = {"error": "Portfolio total value is zero"}

        from app.playground import compute_stress_scenarios
        result = compute_stress_scenarios([])

        assert "error" in result
