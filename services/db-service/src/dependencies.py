"""
dependencies.py — Servisler arası güvenlik guard'ı.

Tüm veri endpoint'leri (/ health hariç) bu dependency'yi kullanır.
İstek, X-Internal-Key header'ında INTERNAL_API_KEY env var değerini taşımalıdır.
"""

import os

from fastapi import Header, HTTPException, status


async def verify_internal_key(
    x_internal_key: str = Header(..., description="Servisler arası API anahtarı"),
) -> None:
    expected = os.getenv("INTERNAL_API_KEY", "")
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="INTERNAL_API_KEY is not configured on the server.",
        )
    if x_internal_key != expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing X-Internal-Key header.",
        )
