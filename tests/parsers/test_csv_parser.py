import pytest
from pathlib import Path
from backend.parsers.csv_parser import parse_csv

FIXTURES = Path(__file__).parent / "fixtures"

def test_parse_chase_csv():
    txs = parse_csv(FIXTURES / "chase_sample.csv", source="chase")
    expenses = [t for t in txs if t.amount < 0]
    assert len(expenses) == 2
    assert expenses[0].description == "WHOLE FOODS #123"
    assert expenses[0].amount == -84.20
    assert expenses[0].source == "chase"

def test_parse_discover_csv():
    txs = parse_csv(FIXTURES / "discover_sample.csv", source="discover")
    expenses = [t for t in txs if t.amount < 0]
    assert len(expenses) == 2
    assert expenses[0].description == "UBER EATS"
    assert expenses[0].amount == -32.50

def test_parse_amex_csv():
    txs = parse_csv(FIXTURES / "amex_sample.csv", source="amex")
    assert len(txs) == 2
    assert txs[0].description == "DELTA AIR LINES"
    assert txs[0].amount == -420.00

def test_transaction_id_is_deterministic():
    txs1 = parse_csv(FIXTURES / "chase_sample.csv", source="chase")
    txs2 = parse_csv(FIXTURES / "chase_sample.csv", source="chase")
    assert txs1[0].id == txs2[0].id

def test_transaction_id_is_unique_per_transaction():
    txs = parse_csv(FIXTURES / "chase_sample.csv", source="chase")
    ids = [t.id for t in txs]
    assert len(ids) == len(set(ids))
