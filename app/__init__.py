"""AlfaPro Bot — otomatik kripto al-sat robotu."""

# ---- Sürüm ve Seri Numarası ----
# Her fazda güncellenir. Final sürümde SERIAL = "APB-FINAL-v1.0.0"
__version__ = "1.0.0"
__serial__ = "APB-FINAL-v1.0.0"
__codename__ = "PRODUCTION"
__phase__ = 5


def version_info() -> dict:
    """Panel ve /api/version için tam sürüm bilgisi."""
    return {
        "version": __version__,
        "serial": __serial__,
        "codename": __codename__,
        "phase": __phase__,
        "is_final": __serial__.startswith("APB-FINAL"),
    }
