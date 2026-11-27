from datetime import UTC, datetime
from decimal import Decimal

from app.validation import canonical_row


def test_canonical_row_is_key_order_independent() -> None:
    left = {"amount": Decimal("10.50"), "at": datetime(2026, 1, 2, tzinfo=UTC), "value": None}
    right = {"value": None, "at": datetime(2026, 1, 2, tzinfo=UTC), "amount": Decimal("10.50")}
    assert canonical_row(left) == canonical_row(right)
