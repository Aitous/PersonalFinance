import pytest
from datetime import date
from backend.analysis.subscription_detector import SubscriptionDetector
from backend.db.models import Transaction

def make_tx(id, description, amount, tx_date, merchant_type=None, category=None, merchant_name=None, is_online=None):
    return Transaction(
        id=id, source="chase", date=tx_date,
        description=description, amount=amount,
        merchant_type=merchant_type, category=category, merchant_name=merchant_name, is_online=is_online,
    )

def test_detects_monthly_subscription():
    detector = SubscriptionDetector()
    txs = [
        make_tx("t1", "NETFLIX.COM", 15.99, date(2025, 3, 15)),
        make_tx("t2", "NETFLIX.COM", 15.99, date(2025, 4, 15)),
        make_tx("t3", "NETFLIX.COM", 15.99, date(2025, 5, 15)),
    ]
    subs = detector.detect(txs)
    assert len(subs) == 1
    assert subs[0].description == "NETFLIX.COM"
    assert subs[0].frequency == "monthly"
    assert subs[0].amount == 15.99

def test_detects_annual_subscription():
    detector = SubscriptionDetector()
    txs = [
        make_tx("t1", "AMAZON PRIME", 139.00, date(2024, 5, 1)),
        make_tx("t2", "AMAZON PRIME", 139.00, date(2025, 5, 1)),
    ]
    subs = detector.detect(txs)
    assert len(subs) == 1
    assert subs[0].frequency == "annual"

def test_ignores_non_recurring():
    detector = SubscriptionDetector()
    txs = [
        make_tx("t1", "RANDOM STORE", -50.00, date(2025, 3, 1)),
        make_tx("t2", "ANOTHER STORE", -75.00, date(2025, 4, 15)),
    ]
    subs = detector.detect(txs)
    assert subs == []

def test_amount_tolerance():
    detector = SubscriptionDetector()
    txs = [
        make_tx("t1", "SPOTIFY", 10.99, date(2025, 3, 5)),
        make_tx("t2", "SPOTIFY", 10.99, date(2025, 4, 5)),
        make_tx("t3", "SPOTIFY", 11.49, date(2025, 5, 5)),  # tax variation
    ]
    subs = detector.detect(txs)
    assert len(subs) == 1

def test_rejects_irregular_repeated_purchases_with_monthly_average_gap():
    detector = SubscriptionDetector()
    # The 10- and 50-day gaps average to 30 days, but this is not a monthly
    # billing cadence even though the merchant and amount are identical.
    txs = [
        make_tx("t1", "LOCAL MARKET", 42.00, date(2025, 1, 1)),
        make_tx("t2", "LOCAL MARKET", 42.00, date(2025, 1, 11)),
        make_tx("t3", "LOCAL MARKET", 42.00, date(2025, 3, 2)),
    ]

    assert detector.detect(txs) == []

def test_requires_three_charges_to_infer_monthly_cadence():
    detector = SubscriptionDetector()
    txs = [
        make_tx("t1", "STREAMING SERVICE", 12.99, date(2025, 3, 15)),
        make_tx("t2", "STREAMING SERVICE", 12.99, date(2025, 4, 15)),
    ]

    assert detector.detect(txs) == []

@pytest.mark.parametrize("description, merchant_type, dates", [
    ("SQ *HUMPHRY SLOCOMBE", "ice cream shop", [date(2024, 9, 27), date(2025, 10, 9)]),
    ("SQ *ONO GELATO WHALERS", "ice cream shop", [date(2025, 7, 6), date(2026, 7, 4)]),
    ("CITY OF SM PW PARKING", "parking", [date(2026, 8, 20), date(2026, 9, 18), date(2026, 10, 17)]),
    ("SQ *CREEKSIDE BAKERY", "bakery", [date(2026, 6, 25), date(2026, 7, 25), date(2026, 8, 16)]),
])
def test_rejects_recurring_dates_for_non_billing_merchants(description, merchant_type, dates):
    txs = [make_tx(f"t{i}", description, 14.00, tx_date, merchant_type) for i, tx_date in enumerate(dates)]

    assert SubscriptionDetector().detect(txs) == []

def test_accepts_known_billing_merchant_types():
    txs = [
        make_tx("t1", "COMCAST", 127.82, date(2025, 1, 8), "cable and internet provider"),
        make_tx("t2", "COMCAST", 127.82, date(2025, 2, 8), "cable and internet provider"),
        make_tx("t3", "COMCAST", 127.82, date(2025, 3, 8), "cable and internet provider"),
    ]

    subs = SubscriptionDetector().detect(txs)
    assert len(subs) == 1
    assert subs[0].frequency == "monthly"

def test_groups_recurring_charges_when_enriched_merchant_name_changes():
    rows = [
        make_tx("t1", "COMCAST / XFINITY 800-266-2278 CAABCDEF1234", 127.82,
                date(2026, 1, 8), "internet and cable provider", merchant_name="Xfinity"),
        make_tx("t2", "COMCAST / XFINITY 800-266-2278 CAABCDEF5678", 127.82,
                date(2026, 2, 8), "internet and cable provider", merchant_name="Xfinity"),
        make_tx("t3", "COMCAST / XFINITY 800-266-2278 CAABCDEF9012", 129.82,
                date(2026, 3, 8), "internet and cable provider", merchant_name="Xfinity"),
        make_tx("t4", "COMCAST / XFINITY 800-266-2278 CAABCDEF3456", 129.82,
                date(2026, 4, 7), "internet and cable provider", merchant_name="COMCAST / XFINITY"),
        make_tx("t5", "COMCAST / XFINITY 800-266-2278 CAABCDEF7890", 129.82,
                date(2026, 5, 7), "internet and cable provider", merchant_name="COMCAST / XFINITY"),
    ]

    subs = SubscriptionDetector().detect(rows)

    assert len(subs) == 1
    assert subs[0].last_charged == date(2026, 5, 7)
    assert len(__import__("json").loads(subs[0].supporting_transaction_ids)) == 5


def test_merges_unknown_merchants_when_descriptor_changes_and_duplicates_overlap():
    rows = [
        make_tx("maple-jan", "MAPLE RIDGE WATER 800-555-0101 CA AUTH-A", 52.10,
                date(2026, 1, 15), "water provider", merchant_name="Maple Ridge Water"),
        make_tx("maple-feb-a", "MAPLE RIDGE WATER 800-555-0101 CA AUTH-B", 52.10,
                date(2026, 2, 15), "water provider", merchant_name="Maple Ridge Water"),
        make_tx("maple-mar-a", "MAPLE RIDGE WATER 800-555-0101 CA AUTH-C", 52.10,
                date(2026, 3, 15), "water provider", merchant_name="Maple Ridge Water"),
        make_tx("maple-feb-b", "MAPLE RIDGE WATER SERVICES 800-555-0102 CA REF-X", 52.10,
                date(2026, 2, 15), "water provider", merchant_name="Maple Ridge Water Services"),
        make_tx("maple-mar-b", "MAPLE RIDGE WATER SERVICES 800-555-0102 CA REF-Y", 52.10,
                date(2026, 3, 15), "water provider", merchant_name="Maple Ridge Water Services"),
        make_tx("maple-apr", "MAPLE RIDGE WATER SERVICES 800-555-0102 CA REF-Z", 52.10,
                date(2026, 4, 15), "water provider", merchant_name="Maple Ridge Water Services"),
    ]

    subs = SubscriptionDetector().detect(rows)

    assert len(subs) == 1
    assert subs[0].last_charged == date(2026, 4, 15)
    assert len(__import__("json").loads(subs[0].supporting_transaction_ids)) == 4

def test_groups_google_one_when_google_merchant_label_is_generic():
    rows = [
        make_tx(f"g{i}", f"GOOGLE *GOOGLE ONE G.CO/HELPPAY#CAP1CODE{i:06d}", 1.99,
                date(2026, month, 16), "cloud storage subscription",
                merchant_name="Google One" if i < 3 else "Google")
        for i, month in enumerate((1, 2, 3, 4, 5))
    ]

    subs = SubscriptionDetector().detect(rows)

    assert len(subs) == 1
    assert subs[0].last_charged == date(2026, 5, 16)


def test_detects_variable_monthly_cloud_billing():
    rows = [
        make_tx(f"cloud-{i}", f"GOOGLE *CLOUD {code}", amount, date(2026, month, 1),
                "cloud computing service", category="subscriptions", merchant_name="Google Cloud")
        for i, (month, amount, code) in enumerate(((6, 22.22, "C4ZJB3"), (7, 35.71, "W3VD2X"),
                                                   (8, 65.42, "67WJJ4"), (9, 5.02, "TL8NNL")))
    ]

    subs = SubscriptionDetector().detect(rows)

    assert len(subs) == 1
    assert subs[0].frequency == "monthly"
    assert len(__import__("json").loads(subs[0].supporting_transaction_ids)) == 4


def test_groups_google_colab_billing_descriptions_by_specific_merchant():
    rows = [
        make_tx("colab-1", "GOOGLE *COLAB CC@GOOGLE.COMCAP1EPWM5C", 9.99,
                date(2025, 9, 14), "cloud computing service", category="subscriptions", merchant_name="Google Colab"),
        make_tx("colab-2", "GOOGLE COLAB MOUNTAIN VIEWCA", 9.99,
                date(2025, 10, 14), "cloud computing service", category="subscriptions", merchant_name="Google Colab"),
        make_tx("colab-3", "GOOGLE *COLAB CC@GOOGLE.COMCAP1G8DGBU", 9.99,
                date(2025, 11, 14), "cloud computing service", category="subscriptions", merchant_name="Google Colab"),
    ]

    subs = SubscriptionDetector().detect(rows)

    assert len(subs) == 1
    assert subs[0].last_charged == date(2025, 11, 14)


@pytest.mark.parametrize("description, merchant_type, category", [
    ("COSTCO MEMBERSHIP FEE", "warehouse club", "shopping"),
    ("NETFLIX", "restaurant", "dining"),
])
def test_excludes_in_person_purchases_even_with_billing_wording(description, merchant_type, category):
    rows = [
        make_tx(f"purchase-{i}", description, 19.99, date(2026, month, 15), merchant_type,
                category=category)
        for i, month in enumerate((1, 2, 3))
    ]

    assert SubscriptionDetector().detect(rows) == []


def test_keeps_known_insurance_billing_when_online_flag_is_false():
    rows = [
        make_tx(f"geico-{i}", "GEICO AUTO", 150.0, date(2026, month, 18),
                "auto insurance", category="utilities", merchant_name="GEICO", is_online=False)
        for i, month in enumerate((1, 2, 3))
    ]

    subs = SubscriptionDetector().detect(rows)

    assert len(subs) == 1
    assert subs[0].description == "GEICO"
