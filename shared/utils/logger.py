"""
shared/utils/logger.py — Merkezi Loglama (Centralized Logging) Modülü

Tüm mikroservislerin ortak log formatını kullanmasını sağlar.

Kullanım (sadece servis entry-point'inde — main.py veya app.py):
    from shared.utils.logger import setup_logger
    logger = setup_logger("query-service")

Modüllerde (değişiklik gerekmez, Python hiyerarşisi otomatik devralır):
    import logging
    logger = logging.getLogger(__name__)   # örn: "src.tasks.sampler"

Mimari notlar:
  - Named logger kullanılır (root logger değil): logging.getLogger(service_name)
    → "query-service" logger'ı, "src.*" alt logger'larının hiyerarşik ebeveynidir.
    → setup_logger() bir kez çağrıldığında tüm modüller formatı otomatik miras alır.
  - Handler idempotency: handlers listesi kontrol edilir; aynı logger birden fazla
    çağrılsa bile duplicate handler eklenmez (Dash hot-reload güvenliği).
  - stdout kullanılır (stderr değil): Docker/Kubernetes log sürücüleri stdout'u
    standart çıktı olarak toplar; stderr yalnızca kritik sistem hatalarına ayrılır.
  - Log seviyesi env değişkeniyle override edilebilir: LOG_LEVEL=DEBUG
"""

import logging
import os
import sys

# Log formatı — kurumsal standart
_FORMAT = "[%(asctime)s] [%(levelname)-8s] [%(name)s] - %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logger(
    service_name: str,
    level: int | None = None,
) -> logging.Logger:
    """
    Merkezi log yapılandırmasını başlatır ve servis root logger'ını döndürür.

    Args:
        service_name: Servisin adı — log mesajlarında [%(name)s] alanında görünür.
                      Örnekler: "query-service", "gui-service", "db-service"
        level:        Opsiyonel log seviyesi. None ise LOG_LEVEL env değişkenine
                      bakılır; o da yoksa INFO kullanılır.

    Returns:
        Yapılandırılmış logging.Logger nesnesi.

    Tasarım kararı:
        Bu fonksiyon servis başlangıcında (main.py / app.py) bir kez çağrılır.
        Modüller kendi logger'larını logging.getLogger(__name__) ile açmaya devam
        eder; Python'un hiyerarşik logging sistemi formatı otomatik yayar.
    """
    # ── Log seviyesini belirle ─────────────────────────────────────────────────
    if level is None:
        env_level = os.getenv("LOG_LEVEL", "INFO").upper()
        level = getattr(logging, env_level, logging.INFO)

    # ── Named logger al (idempotent) ───────────────────────────────────────────
    logger = logging.getLogger(service_name)

    # Handler zaten varsa tekrar ekleme (hot-reload / test güvenliği)
    if logger.handlers:
        return logger

    logger.setLevel(level)

    # ── stdout StreamHandler ───────────────────────────────────────────────────
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(
        logging.Formatter(fmt=_FORMAT, datefmt=_DATE_FORMAT)
    )
    logger.addHandler(handler)

    # Root logger'ın "No handlers could be found" uyarısını bastır
    # (propagation kapatılmaz — sadece root'un kendi handler'ı devre dışı)
    logging.getLogger().setLevel(logging.WARNING)

    logger.info(
        "Logger başlatıldı — service=%s level=%s",
        service_name,
        logging.getLevelName(level),
    )
    return logger
