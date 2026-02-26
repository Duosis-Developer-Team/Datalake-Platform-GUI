"""
shared/tests/test_logger.py — shared.utils.logger birim testleri

Test kapsamı:
  1. Logger format: [%(asctime)s] [%(levelname)-8s] [%(name)s] - %(message)s
  2. Idempotency: Aynı isimle birden fazla setup_logger() → tek handler
  3. Level: Varsayılan INFO, LOG_LEVEL env ile override edilebilir
  4. stdout: Handler StreamHandler(sys.stdout) kullanıyor
"""

import logging
import sys

import pytest

from shared.utils.logger import setup_logger


def _get_fresh_logger(name: str) -> logging.Logger:
    """
    Test izolasyonu: Her test için logger'ı sıfırla.
    Python logging modülü logger'ları global registry'de tutar;
    test çalıştırması arasında handler'ların temizlenmesi gerekir.
    """
    logger = logging.getLogger(name)
    logger.handlers.clear()
    return logger


class TestLoggerFormat:
    """Logger format string doğrulamaları."""

    def test_format_contains_levelname(self):
        """Log format string'i %(levelname) içermeli."""
        _get_fresh_logger("fmt-test-1")
        logger = setup_logger("fmt-test-1")
        handler = logger.handlers[0]
        fmt = handler.formatter._fmt
        assert "%(levelname)" in fmt, f"Format string 'levelname' içermiyor: {fmt}"

    def test_format_contains_name(self):
        """Log format string'i %(name)s içermeli (servis adı)."""
        _get_fresh_logger("fmt-test-2")
        logger = setup_logger("fmt-test-2")
        handler = logger.handlers[0]
        fmt = handler.formatter._fmt
        assert "%(name)s" in fmt, f"Format string 'name' içermiyor: {fmt}"

    def test_format_contains_asctime(self):
        """Log format string'i %(asctime)s içermeli (zaman damgası)."""
        _get_fresh_logger("fmt-test-3")
        logger = setup_logger("fmt-test-3")
        handler = logger.handlers[0]
        fmt = handler.formatter._fmt
        assert "%(asctime)s" in fmt, f"Format string 'asctime' içermiyor: {fmt}"

    def test_format_uses_bracket_style(self):
        """Kurumsal bracket formatı: '%(asctime)s] [%(levelname)' sırası."""
        _get_fresh_logger("fmt-test-4")
        logger = setup_logger("fmt-test-4")
        handler = logger.handlers[0]
        fmt = handler.formatter._fmt
        # Bracket formatı: [tarih] [seviye] [isim] - mesaj
        assert "%(asctime)s]" in fmt or "[%(asctime)s]" in fmt, \
            f"Bracket format yok: {fmt}"


class TestLoggerIdempotency:
    """Handler duplicate eklenmemeli."""

    def test_single_handler_after_one_call(self):
        """setup_logger tek çağrıda 1 handler eklemeli."""
        _get_fresh_logger("idem-test-1")
        logger = setup_logger("idem-test-1")
        assert len(logger.handlers) == 1

    def test_single_handler_after_two_calls(self):
        """Aynı isimle 2. setup_logger çağrısı yeni handler EKLEMEMELİ."""
        _get_fresh_logger("idem-test-2")
        setup_logger("idem-test-2")
        setup_logger("idem-test-2")  # 2. çağrı
        logger = logging.getLogger("idem-test-2")
        assert len(logger.handlers) == 1, \
            f"Duplicate handler eklendi! handler sayısı: {len(logger.handlers)}"

    def test_single_handler_after_three_calls(self):
        """3 çağrıda da tek handler."""
        _get_fresh_logger("idem-test-3")
        for _ in range(3):
            setup_logger("idem-test-3")
        logger = logging.getLogger("idem-test-3")
        assert len(logger.handlers) == 1


class TestLoggerLevel:
    """Log seviyesi doğrulamaları."""

    def test_default_level_is_info(self):
        """Varsayılan log seviyesi INFO olmalı."""
        _get_fresh_logger("level-test-1")
        logger = setup_logger("level-test-1")
        assert logger.level == logging.INFO

    def test_explicit_level_debug(self):
        """Explicit level=DEBUG parametresi uygulanmalı."""
        _get_fresh_logger("level-test-2")
        logger = setup_logger("level-test-2", level=logging.DEBUG)
        assert logger.level == logging.DEBUG


class TestLoggerHandler:
    """StreamHandler stdout doğrulaması."""

    def test_handler_is_stream_handler(self):
        """Handler StreamHandler türünde olmalı."""
        _get_fresh_logger("handler-test-1")
        logger = setup_logger("handler-test-1")
        assert isinstance(logger.handlers[0], logging.StreamHandler)

    def test_handler_uses_stdout(self):
        """Handler sys.stdout kullanmalı (stderr değil)."""
        _get_fresh_logger("handler-test-2")
        logger = setup_logger("handler-test-2")
        handler = logger.handlers[0]
        assert handler.stream is sys.stdout, \
            f"stdout beklendi, {handler.stream} geldi"
