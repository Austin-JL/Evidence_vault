from __future__ import annotations

import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Any


try:
    from PIL import ExifTags, Image
except ImportError:  # pragma: no cover - exercised when optional dependency is absent.
    ExifTags = None
    Image = None

try:
    import pillow_heif
except ImportError:  # pragma: no cover - exercised when optional dependency is absent.
    pillow_heif = None


DATETIME_TAGS = ("DateTimeOriginal", "DateTimeDigitized", "DateTime")


def extract_file_metadata(path: Path) -> dict[str, Any]:
    if pillow_heif is not None:
        pillow_heif.register_heif_opener()

    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    result: dict[str, Any] = {
        "captured_at": None,
        "gps_lat": None,
        "gps_lng": None,
        "device_model": None,
        "device_software": None,
        "file_size": path.stat().st_size,
        "mime_type": mime_type,
    }

    if Image is None:
        return result

    try:
        with Image.open(path) as image:
            exif = image.getexif()
            if not exif:
                return result
            named_exif = _named_exif(exif)
            result["captured_at"] = _extract_datetime(named_exif)
            result["device_model"] = _clean_string(named_exif.get("Model"))
            result["device_software"] = _clean_string(named_exif.get("Software"))
            gps = _extract_gps(exif)
            if gps is not None:
                result["gps_lat"], result["gps_lng"] = gps
    except Exception:
        return result

    return result


def metadata_json(
    *,
    record_date: str,
    direction: str,
    original_filename: str,
    stored_path: str,
    file_hash: str,
    imported_at: str,
    extracted: dict[str, Any],
    note: str | None,
) -> dict[str, Any]:
    return {
        "record_date": record_date,
        "direction": direction,
        "original_filename": original_filename,
        "stored_path": stored_path,
        "sha256": file_hash,
        "captured_at": extracted.get("captured_at"),
        "imported_at": imported_at,
        "gps": {
            "lat": extracted.get("gps_lat"),
            "lng": extracted.get("gps_lng"),
        },
        "device": {
            "model": extracted.get("device_model"),
            "software": extracted.get("device_software"),
        },
        "file": {
            "size": extracted.get("file_size"),
            "mime_type": extracted.get("mime_type"),
        },
        "note": note,
    }


def _named_exif(exif: Any) -> dict[str, Any]:
    if ExifTags is None:
        return {}
    return {
        ExifTags.TAGS.get(tag, tag): value
        for tag, value in exif.items()
    }


def _extract_datetime(exif: dict[str, Any]) -> str | None:
    for tag in DATETIME_TAGS:
        value = exif.get(tag)
        if value:
            parsed = _parse_exif_datetime(str(value))
            if parsed:
                return parsed
    return None


def _parse_exif_datetime(value: str) -> str | None:
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).isoformat()
        except ValueError:
            continue
    return None


def _extract_gps(exif: Any) -> tuple[float, float] | None:
    if ExifTags is None:
        return None
    gps_ifd_id = next((key for key, name in ExifTags.TAGS.items() if name == "GPSInfo"), None)
    if gps_ifd_id is None:
        return None
    try:
        gps_ifd = exif.get_ifd(gps_ifd_id)
    except Exception:
        return None
    if not gps_ifd:
        return None

    named_gps = {
        ExifTags.GPSTAGS.get(tag, tag): value
        for tag, value in gps_ifd.items()
    }
    lat = _gps_to_decimal(named_gps.get("GPSLatitude"), named_gps.get("GPSLatitudeRef"))
    lng = _gps_to_decimal(named_gps.get("GPSLongitude"), named_gps.get("GPSLongitudeRef"))
    if lat is None or lng is None:
        return None
    return lat, lng


def _gps_to_decimal(value: Any, ref: Any) -> float | None:
    if value is None:
        return None
    try:
        degrees, minutes, seconds = value
        decimal = float(degrees) + float(minutes) / 60 + float(seconds) / 3600
        if str(ref).upper() in {"S", "W"}:
            decimal *= -1
        return round(decimal, 6)
    except Exception:
        return None


def _clean_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
