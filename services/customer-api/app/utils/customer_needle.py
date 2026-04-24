"""
Customer name → email ILIKE needle conversion.

Converts a canonical customer name (GUI selector value) into a PostgreSQL ILIKE
pattern for matching ServiceCore user email addresses.

Example:
    "Boyner"        → '%@%boyner%'
    "Türk Telekom"  → '%@%turk telekom%'  (spaces preserved after normalization)
    "İş Bankası"    → '%@%is bankasi%'
"""
from __future__ import annotations

import re
import unicodedata

_TR_MAP = str.maketrans(
    "çğışöüÇĞİŞÖÜ",
    "cgisouCGISOU",
)
# Handle dotless-i (ı → i) and dotted-I (İ → I) separately via replace,
# since str.maketrans only maps 1-to-1 codepoints.

_NOISE = re.compile(r"[\-_,\.]+")


def customer_to_email_needle(customer_name: str) -> str:
    """
    Return a PostgreSQL ILIKE pattern matching the email domain portion of
    ServiceCore users belonging to *customer_name*.

    Strategy:
      1. Apply Turkish character mapping (ç→c, ğ→g, ı→i, ö→o, ş→s, ü→u …).
      2. Normalize remaining unicode (NFKD → ASCII strip remaining diacritics).
      3. Lower-case, strip leading/trailing whitespace.
      4. Collapse runs of noise chars (-, _, ., ,) to a single space.
      5. Strip any trailing / leading whitespace that appeared after noise collapse.
      6. Wrap as '%@%<needle>%'.

    The result is used as a single %s parameter in psycopg2 queries:
        WHERE email ILIKE %s
    """
    if not customer_name:
        return "%@%%"

    # Handle dotless-i / dotted-I before the char map
    needle = customer_name.replace("ı", "i").replace("İ", "I")
    needle = needle.translate(_TR_MAP)
    needle = unicodedata.normalize("NFKD", needle)
    needle = "".join(c for c in needle if not unicodedata.combining(c))
    needle = needle.lower().strip()
    needle = _NOISE.sub(" ", needle).strip()

    return f"%@%{needle}%"
