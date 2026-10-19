import pytest
from pathlib import Path
from backend.parsers.csv_parser import classify_kind, parse_csv, parse_csv_detailed

FIXTURES = Path(__file__).parent / "fixtures"

def test_parse_chase_csv():
    txs = parse_csv(FIXTURES / "chase_sample.csv", source="chase")
    expenses = [t for t in txs if t.amount > 0]
    assert len(expenses) == 2
    assert expenses[0].description == "WHOLE FOODS #123"
    assert expenses[0].amount == 84.20
    assert expenses[0].original_amount == -84.20
    assert expenses[0].source == "chase"

def test_parse_discover_csv():
    txs = parse_csv(FIXTURES / "discover_sample.csv", source="discover")
    expenses = [t for t in txs if t.amount > 0]
    assert len(expenses) == 2
    assert expenses[0].description == "UBER EATS"
    assert expenses[0].amount == 32.50

def test_parse_amex_csv():
    txs = parse_csv(FIXTURES / "amex_sample.csv", source="amex")
    assert len(txs) == 2
    assert txs[0].description == "DELTA AIR LINES"
    assert txs[0].amount == 420.00

def test_transaction_id_is_deterministic():
    txs1 = parse_csv(FIXTURES / "chase_sample.csv", source="chase")
    txs2 = parse_csv(FIXTURES / "chase_sample.csv", source="chase")
    assert txs1[0].id == txs2[0].id

def test_transaction_id_is_unique_per_transaction():
    txs = parse_csv(FIXTURES / "chase_sample.csv", source="chase")
    ids = [t.id for t in txs]
    assert len(ids) == len(set(ids))


def test_kind_uses_normalized_sign_and_ignores_merchant_substrings():
    assert classify_kind("THE RETURN BOOKSHOP", amount=18.00) == "purchase"
    assert classify_kind("REWARDING MOMENTS", amount=27.00) == "purchase"
    assert classify_kind("APARTMENT PAYMENT", "Sale", amount=1200.00) == "purchase"
    assert classify_kind("CITY WATER PAYMENT", "Sale", amount=145.00) == "purchase"
    assert classify_kind("CITY UTILITIES PAYMENT", amount=140.00) == "purchase"
    assert classify_kind("NEIGHBORHOOD MARKET", amount=-5.00) == "refund"
    assert classify_kind("PAYMENT THANK YOU", amount=-50.00) == "payment"
    assert classify_kind("PAYMENT THANK YOU", "Payment", amount=-50.00) == "payment"
    assert classify_kind("PAYMENT THANK YOU", "Credit", amount=-50.00) == "payment"
    assert classify_kind("BALANCE TRANSFER", amount=-200.00) == "transfer"


def test_explicit_csv_and_ofx_types_agree_with_normalized_sign():
    assert classify_kind("WHOLE FOODS", "Sale", amount=84.20) == "purchase"
    assert classify_kind("WHOLE FOODS", "DEBIT", amount=84.20) == "purchase"
    assert classify_kind("STORE CREDIT", "CREDIT", amount=-12.00) == "refund"
    with pytest.raises(ValueError, match="positive normalized amount"):
        classify_kind("STORE", "Refund", amount=12.00)
    with pytest.raises(ValueError, match="negative normalized amount"):
        classify_kind("STORE", "Sale", amount=-12.00)


def test_csv_rejects_type_sign_contradiction_and_preserves_other_rows(tmp_path):
    path = tmp_path / "chase.csv"
    path.write_text(
        "Transaction Date,Description,Category,Type,Amount,Memo\n"
        "05/14/2025,THE RETURN BOOKSHOP,Shopping,Sale,-12.00,\n"
        "05/14/2025,WHOLE FOODS,Shopping,Sale,12.00,\n"
    )
    parsed = parse_csv_detailed(path, "chase")
    assert parsed.parsed_rows == 1
    assert parsed.transactions[0].kind == "purchase"
    assert parsed.transactions[0].amount == 12.00
    assert parsed.errors[0]["reason"] == "purchase type has a negative normalized amount"
