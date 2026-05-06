"""
Log dosyası okuyucu.

`logs/alfapro.log` ve `logs/trades.log` dosyalarının son N satırını
filtreli olarak okur. Loguru dosya rotasyonu yaptığı için sadece
AKTİF log dosyaları okunur (zip'lenmişler değil).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from app.config import get_settings


LogFile = Literal["alfapro", "trades"]


# Loguru format: "2026-04-22 06:51:36.829 | WARNING | module:function:line | message"
LOG_LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?)\s*\|\s*"
    r"(?P<level>[A-Z]+)\s*\|\s*(?P<source>[^|]+?)\s*\|\s*(?P<message>.*)$"
)


def _log_path(which: LogFile) -> Path:
    settings = get_settings()
    if which == "trades":
        return Path(settings.log_dir) / "trades.log"
    return Path(settings.log_dir) / "alfapro.log"


def read_tail(
    which: LogFile = "alfapro",
    limit: int = 200,
    level: str | None = None,
    contains: str | None = None,
) -> list[dict]:
    """
    Log dosyasının son satırlarını filtreli olarak döndür.

    - `limit`: max satır sayısı (en yeniden eski, başta en yeni)
    - `level`: INFO / WARNING / ERROR / DEBUG (case-insensitive)
    - `contains`: mesajda arama (case-insensitive substring)
    """
    path = _log_path(which)
    if not path.exists():
        return []

    level_norm = (level or "").strip().upper() or None
    needle = (contains or "").strip().lower() or None

    # Geriye doğru tail okuma (büyük dosyalar için buffered)
    lines = _tail_file(path, max_lines=max(limit * 4, 1000))

    result: list[dict] = []
    for raw in lines:
        parsed = _parse_line(raw)
        if parsed is None:
            # Format dışı satır — stack trace'lerin bir parçası olabilir; atla
            continue

        if level_norm and parsed["level"] != level_norm:
            continue
        if needle and needle not in parsed["message"].lower():
            continue

        result.append(parsed)
        if len(result) >= limit:
            break

    return result


def _tail_file(path: Path, max_lines: int = 1000) -> list[str]:
    """
    Dosyanın son max_lines kadar satırını döndür (en yeni başta).
    Büyük dosyalar için chunked okuma.
    """
    try:
        with path.open("rb") as f:
            f.seek(0, 2)  # End
            file_size = f.tell()
            if file_size == 0:
                return []

            # Son ~256KB'ı oku, satırlara parçala
            chunk_size = min(256 * 1024, file_size)
            f.seek(file_size - chunk_size)
            chunk = f.read()

        text = chunk.decode("utf-8", errors="replace")
        lines = text.splitlines()
        # İlk satır kesik olabilir
        if len(lines) > 1 and file_size > chunk_size:
            lines = lines[1:]
        lines = [ln for ln in lines if ln.strip()]
        lines.reverse()  # En yeni başta
        return lines[:max_lines]
    except OSError:
        return []


def _parse_line(raw: str) -> dict | None:
    """Loguru satırını yapılandırılmış dict'e çevir."""
    m = LOG_LINE_RE.match(raw)
    if m is None:
        return None
    gd = m.groupdict()
    return {
        "ts": gd["ts"],
        "level": gd["level"].strip().upper(),
        "source": gd["source"].strip(),
        "message": gd["message"].strip(),
    }


def log_files_info() -> dict:
    """Log dosyalarının durumu — varlık, boyut."""
    info: dict = {}
    for name in ("alfapro", "trades"):
        p = _log_path(name)  # type: ignore[arg-type]
        info[name] = {
            "path": str(p),
            "exists": p.exists(),
            "size_bytes": p.stat().st_size if p.exists() else 0,
        }
    return info
