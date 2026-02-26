"""
trusted_network.py — IP tabanlı ağ kısıtlama middleware'i.

Starlette BaseHTTPMiddleware ile implemente edilir.
ALLOWED_SUBNETS env var ile yapılandırılır (virgülle ayrılmış CIDR listesi).
Varsayılan: Docker bridge aralıkları (172.16.0.0/12, 10.0.0.0/8) + localhost.

Kullanım (FastAPI main.py):
    from shared.utils.trusted_network import TrustedNetworkMiddleware
    app.add_middleware(TrustedNetworkMiddleware)
"""

import ipaddress
import logging
import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

_DEFAULT_SUBNETS = "172.16.0.0/12,10.0.0.0/8,127.0.0.1/32"


def _load_networks() -> list[ipaddress.IPv4Network]:
    raw = os.getenv("ALLOWED_SUBNETS", _DEFAULT_SUBNETS)
    networks = []
    for cidr in raw.split(","):
        cidr = cidr.strip()
        if cidr:
            try:
                networks.append(ipaddress.IPv4Network(cidr, strict=False))
            except ValueError:
                logger.warning("ALLOWED_SUBNETS: geçersiz CIDR atlandı: %s", cidr)
    return networks


class TrustedNetworkMiddleware(BaseHTTPMiddleware):
    """
    Gelen isteğin kaynak IP'sini ALLOWED_SUBNETS listesiyle karşılaştırır.
    /health endpoint'i her zaman geçer (Docker healthcheck için).
    """

    def __init__(self, app, **kwargs):
        super().__init__(app, **kwargs)
        self._networks = _load_networks()
        logger.info(
            "TrustedNetworkMiddleware aktif — izin verilen ağlar: %s",
            [str(n) for n in self._networks],
        )

    async def dispatch(self, request: Request, call_next):
        # /health endpoint'i her zaman açık (Docker healthcheck)
        if request.url.path == "/health":
            return await call_next(request)

        client_host = request.client.host if request.client else None
        if client_host is None:
            logger.warning("IP bilgisi alınamadı — istek reddedildi")
            return JSONResponse(
                status_code=403,
                content={"detail": "Forbidden: client IP unavailable."},
            )

        try:
            client_ip = ipaddress.IPv4Address(client_host)
        except ValueError:
            logger.warning("Geçersiz client IP: %s — istek reddedildi", client_host)
            return JSONResponse(
                status_code=403,
                content={"detail": "Forbidden: invalid client IP."},
            )

        for network in self._networks:
            if client_ip in network:
                return await call_next(request)

        logger.warning(
            "Yetkisiz erişim denemesi — IP: %s, path: %s", client_host, request.url.path
        )
        return JSONResponse(
            status_code=403,
            content={"detail": f"Forbidden: {client_host} is not in the trusted network."},
        )
