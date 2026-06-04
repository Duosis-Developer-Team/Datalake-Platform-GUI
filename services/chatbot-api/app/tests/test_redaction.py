from app.services.redaction import redact_mapping, redact_text


def test_redacts_sk_proj_key():
    # Synthetic, non-real token (never use a real secret in fixtures).
    fake = "sk-proj-FAKE0000example0000token0000"
    out = redact_text(f"the key is {fake} ok")
    assert fake not in out
    assert "[REDACTED]" in out


def test_redacts_capitalized_sk_key():
    # Provider keys may be capitalized (e.g. "Sk-proj-..."); redaction is case-insensitive.
    fake = "Sk-proj-FAKE0000example0000token0000"
    assert fake not in redact_text(f"key={fake}")


def test_redacts_bearer_token():
    out = redact_text("Authorization: Bearer abcDEF1234567890token")
    assert "abcDEF1234567890token" not in out


def test_redacts_jwt():
    jwt_like = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.s3cr3tSignaturePart"
    assert jwt_like not in redact_text(f"token={jwt_like}")


def test_redacts_password_kv():
    out = redact_text("db password=SuperSecret123!")
    assert "SuperSecret123" not in out


def test_redacts_connection_string():
    out = redact_text("postgresql://user:pw@host:5432/db")
    assert "user:pw@host" not in out


def test_plain_text_unchanged():
    assert redact_text("DC13 CPU %64, RAM %78") == "DC13 CPU %64, RAM %78"


def test_redact_mapping_masks_sensitive_keys():
    safe = redact_mapping({"api_key": "sk-proj-xyz", "dc": "DC13", "count": 5})
    assert safe["api_key"] == "[REDACTED]"
    assert safe["dc"] == "DC13"
    assert safe["count"] == 5
