from backend.ofx.banks import BANK_CONFIG


def test_all_banks_configured():
    for bank in ("chase", "amex", "discover"):
        assert bank in BANK_CONFIG
        cfg = BANK_CONFIG[bank]
        assert cfg["url"].startswith("https://")
        assert cfg["fid"]
        assert cfg["org"]
