from datetime import date
from types import SimpleNamespace

from backend.analysis.transaction_semantics import amount_components, is_payment
from backend.analysis.monthly_report import get_monthly_report_data


def _tx(amount, description="Coffee Shop", category="dining"):
    return SimpleNamespace(
        amount=amount, description=description, category=category,
        date=date(2026, 4, 12), merchant_name="Coffee Shop", id=str(amount), source="test",
    )


def test_shared_amount_components_exclude_card_payments():
    result = amount_components([_tx(100), _tx(-25), _tx(-200, "AUTOMATIC PAYMENT THANK YOU")])
    assert result == {"gross_purchases": 100.0, "refunds": 25.0, "net_spending": 75.0}


def test_monthly_report_labels_gross_refunds_and_net():
    result = get_monthly_report_data([_tx(100), _tx(-25)], year=2026, month=4)
    assert result["total"] == result["gross_purchases"] == 100.0
    assert result["refunds"] == 25.0
    assert result["net_spending"] == 75.0


def test_embedding_representation_and_hash_follow_enriched_fields_without_model_loading():
    from backend.search.embedder import tx_to_text, embedding_input_hash, embedding_is_current
    tx = _tx(100)
    tx.city = "Oakland"
    tx.merchant_type = "Cafe"
    tx.merchant_name = "Local Cafe"
    tx.metadata_ = "{malformed"
    text = tx_to_text(tx)
    assert "Local Cafe" in text and "Oakland" in text and "Cafe" in text
    first_hash = embedding_input_hash(tx)
    tx.embedding = "[0.1]"
    tx.embedding_input_hash = first_hash
    tx.embedding_model_version = "BAAI/bge-small-en-v1.5"
    assert embedding_is_current(tx)
    tx.city = "Berkeley"
    assert not embedding_is_current(tx)
