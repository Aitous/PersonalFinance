"""Shared transaction selection and exact amount semantics for reporting."""
from decimal import Decimal

PAYMENT_KEYWORDS = (
    "automatic payment", "directpay", "direct pay", "online payment",
    "payment thank you", "payment received", "payment - thank",
    "thank you - your payment", "epay", "autopay",
)


def amount_decimal(tx) -> Decimal:
    minor = getattr(tx, "amount_minor", None)
    if isinstance(minor, int) and not isinstance(minor, bool):
        return Decimal(minor) / Decimal(100)
    return Decimal(str(getattr(tx, "amount", 0) or 0))


def is_payment(tx) -> bool:
    kind = (getattr(tx, "kind", None) or "").casefold()
    if kind in {"payment", "transfer"}:
        return True
    description = (getattr(tx, "description", None) or "").lower()
    return any(keyword in description for keyword in PAYMENT_KEYWORDS)


def is_refund(tx) -> bool:
    return (getattr(tx, "kind", None) or "").casefold() == "refund" or amount_decimal(tx) < 0


def purchase_amount(tx) -> Decimal:
    if is_payment(tx) or is_refund(tx):
        return Decimal(0)
    amount = amount_decimal(tx)
    return max(amount, Decimal(0))


def refund_amount(tx) -> Decimal:
    if is_payment(tx) or not is_refund(tx):
        return Decimal(0)
    return abs(amount_decimal(tx))


def amount_components(transactions) -> dict:
    gross = sum((purchase_amount(tx) for tx in transactions), Decimal(0))
    refunds = sum((refund_amount(tx) for tx in transactions), Decimal(0))
    return {
        "gross_purchases": round(float(gross), 2),
        "refunds": round(float(refunds), 2),
        "net_spending": round(float(gross - refunds), 2),
    }
