import hashlib
import re
import uuid
from datetime import date, datetime, timezone
from typing import List

import requests

from backend.db.models import Transaction
from backend.ofx.banks import BANK_CONFIG

_OFX_HEADER = (
    "OFXHEADER:100\r\n"
    "DATA:OFXSGML\r\n"
    "VERSION:151\r\n"
    "SECURITY:NONE\r\n"
    "ENCODING:USASCII\r\n"
    "CHARSET:1252\r\n"
    "COMPRESSION:NONE\r\n"
    "OLDFILEUID:NONE\r\n"
    "NEWFILEUID:NONE\r\n"
    "\r\n"
)

_HEADERS = {
    "Content-Type": "application/x-ofx",
    "Accept": "application/x-ofx",
    "User-Agent": "Quicken/2700",
}


# ── request builders ──────────────────────────────────────────────────────────

def _signon_block(username: str, password: str, fid: str, org: str) -> str:
    now = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return (
        f"<SIGNONMSGSRQV1>"
        f"<SONRQ>"
        f"<DTCLIENT>{now}</DTCLIENT>"
        f"<USERID>{username}</USERID>"
        f"<USERPASS>{password}</USERPASS>"
        f"<LANGUAGE>ENG</LANGUAGE>"
        f"<FI><ORG>{org}</ORG><FID>{fid}</FID></FI>"
        f"<APPID>QWIN</APPID><APPVER>2700</APPVER>"
        f"</SONRQ>"
        f"</SIGNONMSGSRQV1>"
    )


def _acct_info_body(username: str, password: str, fid: str, org: str) -> str:
    trnuid = uuid.uuid4().hex[:8]
    return (
        f"<OFX>"
        f"{_signon_block(username, password, fid, org)}"
        f"<SIGNUPMSGSRQV1>"
        f"<ACCTINFOTRNRQ>"
        f"<TRNUID>{trnuid}</TRNUID>"
        f"<ACCTINFORQ><DTACCTUP>19700101000000</DTACCTUP></ACCTINFORQ>"
        f"</ACCTINFOTRNRQ>"
        f"</SIGNUPMSGSRQV1>"
        f"</OFX>"
    )


def _statement_body(
    username: str, password: str, fid: str, org: str, acct_id: str, since: date
) -> str:
    trnuid = uuid.uuid4().hex[:8]
    dt_start = since.strftime("%Y%m%d")
    return (
        f"<OFX>"
        f"{_signon_block(username, password, fid, org)}"
        f"<CREDITCARDMSGSRQV1>"
        f"<CCSTMTTRNRQ>"
        f"<TRNUID>{trnuid}</TRNUID>"
        f"<CCSTMTRQ>"
        f"<CCACCT><ACCTID>{acct_id}</ACCTID></CCACCT>"
        f"<INCTRAN><DTSTART>{dt_start}</DTSTART><INCLUDE>Y</INCLUDE></INCTRAN>"
        f"</CCSTMTRQ>"
        f"</CCSTMTTRNRQ>"
        f"</CREDITCARDMSGSRQV1>"
        f"</OFX>"
    )


# ── low-level OFX SGML parser ─────────────────────────────────────────────────

def _leaf(text: str, tag: str) -> str:
    """Extract first leaf value: <TAG>value (no closing tag in OFX SGML)."""
    m = re.search(rf"<{tag}>\s*([^<\r\n]+)", text, re.IGNORECASE)
    return m.group(1).strip() if m else ""


def _blocks(text: str, tag: str) -> List[str]:
    """Extract all container blocks: <TAG>...</TAG>."""
    return re.findall(rf"<{tag}>(.*?)</{tag}>", text, re.DOTALL | re.IGNORECASE)


def _parse_ofx_date(dt_str: str) -> date:
    return datetime.strptime(dt_str.strip()[:8], "%Y%m%d").date()


def _check_signon(response_text: str) -> None:
    code = _leaf(response_text, "CODE")
    if code and code != "0":
        severity = _leaf(response_text, "SEVERITY")
        message = _leaf(response_text, "MESSAGE") or f"OFX error code {code}"
        raise ValueError(f"OFX signon failed ({severity}): {message}")


# ── public API ────────────────────────────────────────────────────────────────

def _post(url: str, body: str) -> str:
    resp = requests.post(
        url,
        data=(_OFX_HEADER + body).encode("ascii", errors="replace"),
        headers=_HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.text


def get_account_ids(bank: str, username: str, password: str) -> List[str]:
    """Return credit-card account IDs for this bank login."""
    cfg = BANK_CONFIG[bank]
    body = _acct_info_body(username, password, cfg["fid"], cfg["org"])
    text = _post(cfg["url"], body)
    _check_signon(text)

    acct_ids = []
    for acct_block in _blocks(text, "ACCTINFO"):
        cc_block = _blocks(acct_block, "CCACCT")
        if cc_block:
            aid = _leaf(cc_block[0], "ACCTID")
            if aid:
                acct_ids.append(aid)
    return acct_ids


def get_transactions(
    bank: str, username: str, password: str, acct_id: str, since: date
) -> List[Transaction]:
    cfg = BANK_CONFIG[bank]
    body = _statement_body(username, password, cfg["fid"], cfg["org"], acct_id, since)
    text = _post(cfg["url"], body)
    _check_signon(text)

    txs: List[Transaction] = []
    for trn in _blocks(text, "STMTTRN"):
        try:
            fitid = _leaf(trn, "FITID")
            dt_posted = _parse_ofx_date(_leaf(trn, "DTPOSTED"))
            amount = float(_leaf(trn, "TRNAMT"))
            name = _leaf(trn, "NAME") or _leaf(trn, "MEMO") or "Unknown"
            memo = _leaf(trn, "MEMO")
            trn_type = _leaf(trn, "TRNTYPE")

            tx_id = hashlib.sha256(
                f"{bank}{dt_posted}{amount}{name}".encode()
            ).hexdigest()[:16]

            import json
            metadata = json.dumps({
                "fitid": fitid,
                "trntype": trn_type,
                "memo": memo,
                "acct_id": acct_id,
            })

            txs.append(Transaction(
                id=tx_id,
                source=bank,
                date=dt_posted,
                description=name,
                amount=amount,
                metadata_=metadata,
                raw_csv_row=trn.strip(),
            ))
        except (ValueError, KeyError):
            continue

    return txs


def download_transactions(
    bank: str, username: str, password: str, since: date
) -> List[Transaction]:
    """Full flow: discover accounts then fetch transactions for all of them."""
    acct_ids = get_account_ids(bank, username, password)
    if not acct_ids:
        raise ValueError(f"No credit card accounts found for {bank}")

    all_txs: List[Transaction] = []
    for acct_id in acct_ids:
        all_txs.extend(get_transactions(bank, username, password, acct_id, since))
    return all_txs
