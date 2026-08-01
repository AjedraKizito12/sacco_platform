from app.core.observability.scrubbing import (
    SCRUB_EXTRA_PATTERNS,
    SCRUB_KEYS,
    scrub_event_dict,
    should_scrub,
)


def test_keyset_covers_secrets_and_pii():
    for k in ("password", "jwt_kek", "hashed_password", "national_id_number",
              "email", "phone", "first_name", "last_name", "dob", "token", "secret",
              # financial / identity keys widened in the final egress-hardening pass
              "member_number", "account_number", "card_number", "passport",
              "routing_number"):
        assert k in SCRUB_KEYS


def test_extra_patterns_cover_pii_and_financial_keys():
    for p in ("national_id", "email", "phone", "actor_label", "member_number",
              "account_number", "card_number", "passport", "routing_number"):
        assert p in SCRUB_EXTRA_PATTERNS


def test_amount_is_not_scrubbed():
    assert should_scrub("amount") is False
    assert should_scrub("total_amount") is False


def test_should_scrub_case_insensitive_and_substring():
    assert should_scrub("Email") is True
    assert should_scrub("user_password") is True


def test_scrub_event_dict_redacts_pii_keeps_amount():
    out = scrub_event_dict(None, "info", {
        "event": "loan repaid", "amount": 5000, "email": "a@b.com",
        "hashed_password": "x", "loan_id": "L-1",
    })
    assert out["amount"] == 5000
    assert out["loan_id"] == "L-1"
    assert out["email"] == "[scrubbed]"
    assert out["hashed_password"] == "[scrubbed]"
    assert out["event"] == "loan repaid"
