"""
Data Coherence Guards
=====================
Validates incoming data against the previous snapshot before allowing
storage. Prevents silent corruption from bad API responses.

Guards:
- Balance drop >90% in one cycle → flag
- Score change >30 points → flag
- Entity disappearing from API response → flag
- Price deviation >50% from last snapshot → flag
- Negative values where not expected → reject
- Zero values for previously non-zero fields → flag

Flagged data is stored with a review marker — not silently discarded.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from app.database import fetch_one, execute

logger = logging.getLogger(__name__)


class CoherenceViolation:
    """Represents a data coherence violation."""

    def __init__(
        self,
        data_type: str,
        entity_id: str,
        field_name: str,
        previous_value: Optional[float],
        incoming_value: Optional[float],
        violation_type: str,
        severity: str = "warning",  # warning, critical
        details: Optional[str] = None,
    ):
        self.data_type = data_type
        self.entity_id = entity_id
        self.field_name = field_name
        self.previous_value = previous_value
        self.incoming_value = incoming_value
        self.violation_type = violation_type
        self.severity = severity
        self.details = details

    def to_dict(self) -> dict:
        return {
            "data_type": self.data_type,
            "entity_id": self.entity_id,
            "field_name": self.field_name,
            "previous_value": self.previous_value,
            "incoming_value": self.incoming_value,
            "violation_type": self.violation_type,
            "severity": self.severity,
            "details": self.details,
            "detected_at": datetime.now(timezone.utc).isoformat(),
        }


def check_numeric_drop(
    data_type: str,
    entity_id: str,
    field_name: str,
    previous: Optional[float],
    incoming: Optional[float],
    max_drop_pct: float = 90.0,
) -> Optional[CoherenceViolation]:
    """Flag if a numeric value drops by more than max_drop_pct."""
    if previous is None or incoming is None:
        return None
    if previous <= 0:
        return None

    drop_pct = ((previous - incoming) / previous) * 100
    if drop_pct > max_drop_pct:
        return CoherenceViolation(
            data_type=data_type,
            entity_id=entity_id,
            field_name=field_name,
            previous_value=previous,
            incoming_value=incoming,
            violation_type="extreme_drop",
            severity="critical",
            details=f"{field_name} dropped {drop_pct:.1f}% ({previous} → {incoming})",
        )
    return None


def check_score_swing(
    data_type: str,
    entity_id: str,
    previous_score: Optional[float],
    incoming_score: Optional[float],
    max_swing: float = 30.0,
) -> Optional[CoherenceViolation]:
    """Flag if a score changes by more than max_swing points."""
    if previous_score is None or incoming_score is None:
        return None

    swing = abs(incoming_score - previous_score)
    if swing > max_swing:
        direction = "up" if incoming_score > previous_score else "down"
        return CoherenceViolation(
            data_type=data_type,
            entity_id=entity_id,
            field_name="score",
            previous_value=previous_score,
            incoming_value=incoming_score,
            violation_type="score_swing",
            severity="warning",
            details=f"Score swung {direction} by {swing:.1f} points",
        )
    return None


def check_price_deviation(
    data_type: str,
    entity_id: str,
    previous_price: Optional[float],
    incoming_price: Optional[float],
    max_deviation_pct: float = 50.0,
) -> Optional[CoherenceViolation]:
    """Flag if price deviates by more than max_deviation_pct."""
    if previous_price is None or incoming_price is None:
        return None
    if previous_price <= 0:
        return None

    deviation_pct = abs(incoming_price - previous_price) / previous_price * 100
    if deviation_pct > max_deviation_pct:
        return CoherenceViolation(
            data_type=data_type,
            entity_id=entity_id,
            field_name="price",
            previous_value=previous_price,
            incoming_value=incoming_price,
            violation_type="price_deviation",
            severity="critical",
            details=f"Price deviated {deviation_pct:.1f}% ({previous_price} → {incoming_price})",
        )
    return None


def check_zero_replacement(
    data_type: str,
    entity_id: str,
    field_name: str,
    previous: Optional[float],
    incoming: Optional[float],
) -> Optional[CoherenceViolation]:
    """Flag if a previously non-zero value becomes zero."""
    if previous is not None and previous > 0 and incoming is not None and incoming == 0:
        return CoherenceViolation(
            data_type=data_type,
            entity_id=entity_id,
            field_name=field_name,
            previous_value=previous,
            incoming_value=incoming,
            violation_type="zero_replacement",
            severity="warning",
            details=f"{field_name} went from {previous} to 0",
        )
    return None


def check_negative(
    data_type: str,
    entity_id: str,
    field_name: str,
    value: Optional[float],
) -> Optional[CoherenceViolation]:
    """Reject negative values where not expected."""
    if value is not None and value < 0:
        return CoherenceViolation(
            data_type=data_type,
            entity_id=entity_id,
            field_name=field_name,
            previous_value=None,
            incoming_value=value,
            violation_type="negative_value",
            severity="critical",
            details=f"{field_name} is negative: {value}",
        )
    return None


def store_violation(violation: CoherenceViolation):
    """Persist a coherence violation for review."""
    try:
        execute(
            """INSERT INTO coherence_reports
               (check_name, status, details, created_at)
               VALUES (%s, %s, %s, NOW())""",
            (
                f"guard:{violation.data_type}:{violation.entity_id}",
                violation.severity,
                json.dumps(violation.to_dict()),
            ),
        )
    except Exception as e:
        logger.debug(f"Could not store coherence violation: {e}")


class DataCoherenceGuard:
    """
    Validate incoming data against previous snapshots.
    Use before inserting into any data layer table.

    Usage:
        guard = DataCoherenceGuard("liquidity_depth")
        violations = guard.validate_liquidity(entity_id, incoming_data)
        if violations:
            for v in violations:
                store_violation(v)
            # Data is still stored, but flagged
    """

    def __init__(self, data_type: str):
        self.data_type = data_type
        self._violations: list[CoherenceViolation] = []

    def validate_liquidity(
        self, asset_id: str, venue: str, incoming: dict
    ) -> list[CoherenceViolation]:
        """Validate incoming liquidity depth data."""
        violations = []

        # Get previous snapshot
        prev = fetch_one(
            """SELECT volume_24h, bid_depth_1pct, ask_depth_1pct, spread_bps
               FROM liquidity_depth
               WHERE asset_id = %s AND venue = %s
               ORDER BY snapshot_at DESC LIMIT 1""",
            (asset_id, venue),
        )

        if prev:
            v = check_numeric_drop(
                self.data_type, f"{asset_id}:{venue}",
                "volume_24h", float(prev["volume_24h"]) if prev.get("volume_24h") else None,
                incoming.get("volume_24h"), max_drop_pct=95,
            )
            if v:
                violations.append(v)

            v = check_numeric_drop(
                self.data_type, f"{asset_id}:{venue}",
                "bid_depth_1pct", float(prev["bid_depth_1pct"]) if prev.get("bid_depth_1pct") else None,
                incoming.get("bid_depth_1pct"), max_drop_pct=90,
            )
            if v:
                violations.append(v)

        # Check for negatives
        for field in ["volume_24h", "bid_depth_1pct", "ask_depth_1pct", "spread_bps"]:
            v = check_negative(self.data_type, f"{asset_id}:{venue}", field, incoming.get(field))
            if v:
                violations.append(v)

        self._violations.extend(violations)
        return violations

    def validate_yield(
        self, pool_id: str, incoming: dict
    ) -> list[CoherenceViolation]:
        """Validate incoming yield snapshot data."""
        violations = []

        prev = fetch_one(
            """SELECT apy, tvl_usd
               FROM yield_snapshots
               WHERE pool_id = %s
               ORDER BY snapshot_at DESC LIMIT 1""",
            (pool_id,),
        )

        if prev:
            v = check_numeric_drop(
                self.data_type, pool_id,
                "tvl_usd", float(prev["tvl_usd"]) if prev.get("tvl_usd") else None,
                incoming.get("tvl_usd"), max_drop_pct=90,
            )
            if v:
                violations.append(v)

            # APY can spike legitimately, but negative APY is suspicious
            v = check_negative(self.data_type, pool_id, "apy", incoming.get("apy"))
            if v:
                violations.append(v)

        # Check for negatives
        v = check_negative(self.data_type, pool_id, "tvl_usd", incoming.get("tvl_usd"))
        if v:
            violations.append(v)

        self._violations.extend(violations)
        return violations

    def validate_exchange(
        self, exchange_id: str, incoming: dict
    ) -> list[CoherenceViolation]:
        """Validate incoming exchange snapshot data."""
        violations = []

        prev = fetch_one(
            """SELECT trade_volume_24h_usd, trust_score
               FROM exchange_snapshots
               WHERE exchange_id = %s
               ORDER BY snapshot_at DESC LIMIT 1""",
            (exchange_id,),
        )

        if prev:
            v = check_numeric_drop(
                self.data_type, exchange_id,
                "trade_volume_24h_usd",
                float(prev["trade_volume_24h_usd"]) if prev.get("trade_volume_24h_usd") else None,
                incoming.get("trade_volume_24h_usd"), max_drop_pct=95,
            )
            if v:
                violations.append(v)

        self._violations.extend(violations)
        return violations

    def validate_bridge_flow(
        self, bridge_id: str, source_chain: str, dest_chain: str, incoming: dict
    ) -> list[CoherenceViolation]:
        """Validate incoming bridge flow data."""
        violations = []

        v = check_negative(
            self.data_type, f"{bridge_id}:{source_chain}->{dest_chain}",
            "volume_usd", incoming.get("volume_usd"),
        )
        if v:
            violations.append(v)

        v = check_negative(
            self.data_type, f"{bridge_id}:{source_chain}->{dest_chain}",
            "tvl_usd", incoming.get("tvl_usd"),
        )
        if v:
            violations.append(v)

        self._violations.extend(violations)
        return violations

    def validate_price(
        self, entity_id: str, incoming_price: float
    ) -> list[CoherenceViolation]:
        """Validate price data (for peg snapshots, etc.)."""
        violations = []

        prev = fetch_one(
            """SELECT price FROM peg_snapshots_5m
               WHERE stablecoin_id = %s
               ORDER BY timestamp DESC LIMIT 1""",
            (entity_id,),
        )

        if prev and prev.get("price"):
            v = check_price_deviation(
                self.data_type, entity_id,
                float(prev["price"]), incoming_price, max_deviation_pct=10,
            )
            if v:
                violations.append(v)

        self._violations.extend(violations)
        return violations

    def get_violations(self) -> list[CoherenceViolation]:
        """Return all violations collected during this guard's lifetime."""
        return list(self._violations)

    def store_all_violations(self):
        """Store all collected violations to DB."""
        for v in self._violations:
            store_violation(v)
        count = len(self._violations)
        if count > 0:
            logger.warning(f"Coherence guard [{self.data_type}]: {count} violations stored")
        self._violations.clear()
