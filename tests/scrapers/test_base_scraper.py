"""OFX client unit tests (replaced scraper tests)."""
from datetime import date
from unittest.mock import patch, MagicMock

from backend.ofx.client import (
    _leaf, _blocks, _parse_ofx_date, _check_signon, get_transactions,
)


def test_leaf_extraction():
    text = "<NAME>WHOLE FOODS\n<TRNAMT>-84.20\n<FITID>abc123"
    assert _leaf(text, "NAME") == "WHOLE FOODS"
    assert _leaf(text, "TRNAMT") == "-84.20"
    assert _leaf(text, "FITID") == "abc123"
    assert _leaf(text, "MISSING") == ""


def test_blocks_extraction():
    text = "<STMTTRN><NAME>A</NAME></STMTTRN><STMTTRN><NAME>B</NAME></STMTTRN>"
    blocks = _blocks(text, "STMTTRN")
    assert len(blocks) == 2
    assert "A" in blocks[0]
    assert "B" in blocks[1]


def test_parse_ofx_date():
    assert _parse_ofx_date("20250115120000") == date(2025, 1, 15)
    assert _parse_ofx_date("20250115") == date(2025, 1, 15)


def test_check_signon_success():
    _check_signon("<CODE>0<SEVERITY>INFO")  # should not raise


def test_check_signon_failure():
    import pytest
    with pytest.raises(ValueError, match="OFX signon failed"):
        _check_signon("<CODE>15500<SEVERITY>ERROR<MESSAGE>Invalid credentials")


def test_get_transactions_parses_response():
    sample_response = """
    <OFX>
    <SIGNONMSGSRSV1><SONRS><STATUS><CODE>0</STATUS></SONRS></SIGNONMSGSRSV1>
    <CREDITCARDMSGSRSV1>
    <CCSTMTTRNRS>
    <CCSTMTRS>
    <BANKTRANLIST>
    <STMTTRN>
    <TRNTYPE>DEBIT
    <DTPOSTED>20250115120000
    <TRNAMT>-84.20
    <FITID>abc123
    <NAME>WHOLE FOODS
    <MEMO>WHOLE FOODS #123
    </STMTTRN>
    <STMTTRN>
    <TRNTYPE>CREDIT
    <DTPOSTED>20250116120000
    <TRNAMT>50.00
    <FITID>def456
    <NAME>PAYMENT THANK YOU
    </STMTTRN>
    </BANKTRANLIST>
    </CCSTMTRS>
    </CCSTMTTRNRS>
    </CREDITCARDMSGSRSV1>
    </OFX>
    """
    with patch("backend.ofx.client._post", return_value=sample_response):
        txs = get_transactions("chase", "user", "pass", "acct1", date(2025, 1, 1))

    assert len(txs) == 2
    wf = next(t for t in txs if "WHOLE FOODS" in t.description)
    assert wf.amount == 84.20
    assert wf.original_amount == -84.20
    assert wf.source == "chase"
    assert wf.date == date(2025, 1, 15)
    payment = next(t for t in txs if "PAYMENT" in t.description)
    assert payment.amount == -50.00
    assert payment.kind == "payment"
