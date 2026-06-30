from __future__ import annotations

import json
import mimetypes
import re
import subprocess
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
VIDEO_MIME_PREFIX = "video/"
VIDEO_DATETIME_TAGS = ("com.apple.quicktime.creationdate", "creation_time")
VIDEO_DEVICE_TAGS = ("com.apple.quicktime.model", "model", "encoder")
VIDEO_SOFTWARE_TAGS = ("com.apple.quicktime.software", "software")
VIDEO_LOCATION_TAG = "com.apple.quicktime.location.iso6709"
ISO6709_PATTERN = re.compile(r"^([+-]\d+(?:\.\d+)?)([+-]\d+(?:\.\d+)?)(?:[+-]\d+(?:\.\d+)?)?/")


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
        "media_type": _media_type(mime_type),
        "duration_seconds": None,
        "width": None,
        "height": None,
    }

    if mime_type.startswith(VIDEO_MIME_PREFIX):
        return _extract_video_metadata(path, result)

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
            "media_type": extracted.get("media_type"),
        },
        "video": {
            "duration_seconds": extracted.get("duration_seconds"),
            "width": extracted.get("width"),
            "height": extracted.get("height"),
        },
        "note": note,
    }


def _media_type(mime_type: str) -> str:
    return mime_type.split("/", 1)[0] if "/" in mime_type else "unknown"


def _extract_video_metadata(path: Path, result: dict[str, Any]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
        probe = json.loads(completed.stdout)
    except (FileNotFoundError, subprocess.SubprocessError, json.JSONDecodeError):
        return result

    format_data = probe.get("format") if isinstance(probe, dict) else {}
    if not isinstance(format_data, dict):
        format_data = {}
    tags = _normalize_tags(format_data.get("tags"))
    result["captured_at"] = _extract_video_datetime(tags)
    result["device_model"] = _extract_first_tag(tags, VIDEO_DEVICE_TAGS)
    result["device_software"] = _extract_first_tag(tags, VIDEO_SOFTWARE_TAGS)
    result["duration_seconds"] = _parse_float(format_data.get("duration"))
    gps = _extract_iso6709_gps(tags.get(VIDEO_LOCATION_TAG))
    if gps is not None:
        result["gps_lat"], result["gps_lng"] = gps

    stream = _first_video_stream(probe.get("streams") if isinstance(probe, dict) else None)
    if stream:
        result["width"] = _parse_int(stream.get("width"))
        result["height"] = _parse_int(stream.get("height"))
        stream_tags = _normalize_tags(stream.get("tags"))
        if result["captured_at"] is None:
            result["captured_at"] = _extract_video_datetime(stream_tags)
        if result["device_model"] is None:
            result["device_model"] = _extract_first_tag(stream_tags, VIDEO_DEVICE_TAGS)
        if result["device_software"] is None:
            result["device_software"] = _extract_first_tag(stream_tags, VIDEO_SOFTWARE_TAGS)

    return result


def _normalize_tags(tags: Any) -> dict[str, Any]:
    if not isinstance(tags, dict):
        return {}
    return {str(key).lower(): value for key, value in tags.items()}


def _extract_video_datetime(tags: dict[str, Any]) -> str | None:
    for tag in VIDEO_DATETIME_TAGS:
        value = tags.get(tag)
        if value:
            parsed = _parse_video_datetime(str(value))
            if parsed:
                return parsed
    return None


def _parse_video_datetime(value: str) -> str | None:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        return datetime.fromisoformat(normalized).isoformat()
    except ValueError:
        return _parse_exif_datetime(normalized)


def _extract_first_tag(tags: dict[str, Any], names: tuple[str, ...]) -> str | None:
    for name in names:
        cleaned = _clean_string(tags.get(name))
        if cleaned:
            return cleaned
    return None


def _extract_iso6709_gps(value: Any) -> tuple[float, float] | None:
    if value is None:
        return None
    match = ISO6709_PATTERN.match(str(value).strip())
    if match is None:
        return None
    try:
        return round(float(match.group(1)), 6), round(float(match.group(2)), 6)
    except ValueError:
        return None


def _first_video_stream(streams: Any) -> dict[str, Any] | None:
    if not isinstance(streams, list):
        return None
    return next(
        (stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "video"),
        None,
    )


def _parse_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return None


def _parse_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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
