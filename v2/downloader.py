"""
downloader.py
Core YouTube download logic built on top of yt-dlp.

Exposes:
    get_video_info(url)        -> metadata + list of available video/audio qualities
    download_video_mp4(url, height=None) -> downloads video, muxes to .mp4
    download_audio_mp3(url, bitrate="192") -> downloads audio, converts to .mp3
"""

import os
import re
import shutil
import unicodedata
import uuid
from typing import Any, Dict, List, Optional

import yt_dlp

DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def sanitize_filename(name: str) -> str:
    """Strip characters that are unsafe for filenames across OSes."""
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    name = re.sub(r'[\\/*?:"<>|]', "", name).strip()
    return name[:150] if len(name) > 150 else name


def _fmt_size(num_bytes: Optional[float]) -> Optional[str]:
    if not num_bytes:
        return None
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024:
            return f"{num_bytes:.1f}{unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f}TB"


def get_video_info(url: str) -> Dict[str, Any]:
    """
    Fetch metadata for a YouTube URL without downloading, and return the FULL
    set of formats yt-dlp exposes — every resolution (up to 4K/8K), every
    codec variant (AV1 / VP9 / H.264), HDR streams, exact frame rates and
    bitrates — plus a de-duplicated "best pick per resolution" list and every
    audio-only stream for MP3/M4A/Opus extraction.
    """
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    formats = info.get("formats", []) or []

    raw_video: List[Dict[str, Any]] = []
    raw_audio: List[Dict[str, Any]] = []

    for f in formats:
        vcodec = f.get("vcodec")
        acodec = f.get("acodec")
        is_video = vcodec not in (None, "none")
        is_audio = acodec not in (None, "none")

        if is_video:
            height = f.get("height")
            fps = f.get("fps") or 0
            raw_video.append({
                "format_id": f["format_id"],
                "ext": f.get("ext"),
                "resolution": f.get("resolution") or (f"{f.get('width')}x{height}" if height else None),
                "height": height,
                "width": f.get("width"),
                "fps": fps,
                "vcodec": vcodec,
                "acodec": acodec,
                "has_audio": is_audio,  # progressive (video+audio in one file) vs video-only
                "dynamic_range": f.get("dynamic_range"),  # e.g. "HDR" / "SDR"
                "tbr_kbps": f.get("tbr"),
                "filesize": f.get("filesize") or f.get("filesize_approx"),
                "filesize_human": _fmt_size(f.get("filesize") or f.get("filesize_approx")),
                "format_note": f.get("format_note"),
            })
        elif is_audio:
            raw_audio.append({
                "format_id": f["format_id"],
                "ext": f.get("ext"),
                "acodec": acodec,
                "abr_kbps": f.get("abr"),
                "asr_hz": f.get("asr"),
                "filesize": f.get("filesize") or f.get("filesize_approx"),
                "filesize_human": _fmt_size(f.get("filesize") or f.get("filesize_approx")),
                "format_note": f.get("format_note"),
            })

    # Sort: highest resolution/fps/bitrate first
    raw_video.sort(key=lambda x: (x["height"] or 0, x["fps"] or 0, x["tbr_kbps"] or 0), reverse=True)
    raw_audio.sort(key=lambda x: (x["abr_kbps"] or 0), reverse=True)

    # --- Convenience: one best entry per (height, fps, codec-family) label ---
    def codec_family(vcodec: Optional[str]) -> str:
        if not vcodec:
            return "unknown"
        if vcodec.startswith("av01"):
            return "AV1"
        if vcodec.startswith("vp9") or vcodec.startswith("vp09"):
            return "VP9"
        if vcodec.startswith("avc1") or vcodec.startswith("h264"):
            return "H.264"
        return vcodec.split(".")[0]

    best_per_quality: Dict[str, Dict[str, Any]] = {}
    for v in raw_video:
        if not v["height"]:
            continue
        fam = codec_family(v["vcodec"])
        fps_tag = f"{int(v['fps'])}" if v["fps"] and v["fps"] > 30 else ""
        label = f"{v['height']}p{fps_tag} {fam}"
        existing = best_per_quality.get(label)
        if existing is None or (v["tbr_kbps"] or 0) > (existing["tbr_kbps"] or 0):
            best_per_quality[label] = {**v, "label": label, "codec_family": fam}

    video_qualities = sorted(
        best_per_quality.values(),
        key=lambda x: (x["height"] or 0, x["fps"] or 0, x["tbr_kbps"] or 0),
        reverse=True,
    )

    return {
        "id": info.get("id"),
        "title": info.get("title"),
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "uploader": info.get("uploader"),

        # Simple, deduplicated dropdown: every resolution/codec combo available (e.g. "2160p60 AV1", "1080p VP9", "1080p H.264")
        "video_qualities": video_qualities,

        # Every raw video-capable format yt-dlp found (advanced/power-user view)
        "all_video_formats": raw_video,

        # Every raw audio-only format available (for MP3/M4A/Opus/etc. extraction)
        "all_audio_formats": raw_audio,

        # Standard bitrate choices to offer for audio extraction
        "audio_bitrates_kbps": [320, 256, 192, 160, 128, 96, 64],

        # Supported output containers for audio extraction
        "audio_formats_supported": ["mp3", "m4a", "opus", "wav", "flac", "vorbis"],
    }


def download_video_mp4(
    url: str,
    height: Optional[int] = None,
    format_id: Optional[str] = None,
    codec: Optional[str] = None,
) -> str:
    """
    Download video+audio and mux/convert to a single .mp4 file.

    Three ways to select quality (checked in this priority order):
      - format_id: an exact yt-dlp format id from /formats (e.g. "399"), for
        full manual control. If it's video-only, best audio is auto-merged.
      - height + codec: cap on vertical resolution (e.g. 2160, 1080, 720),
        optionally restricted to a codec family: "av1", "vp9", or "h264".
      - neither: best available quality/codec.

    Returns the absolute path to the resulting .mp4 file.
    """
    if format_id:
        fmt = f"{format_id}+bestaudio/best"
    else:
        codec_filters = {
            "av1": "[vcodec^=av01]",
            "vp9": "[vcodec^=vp9]",
            "h264": "[vcodec^=avc1]",
        }
        vcodec_filter = codec_filters.get((codec or "").lower(), "")
        height_filter = f"[height<={height}]" if height else ""

        fmt = (
            f"bestvideo{height_filter}{vcodec_filter}+bestaudio/"
            f"best{height_filter}{vcodec_filter}/"
            f"bestvideo{height_filter}+bestaudio/"
            f"best{height_filter}/best"
        )

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "format": fmt,
        "merge_output_format": "mp4",
        "outtmpl": os.path.join(DOWNLOAD_DIR, "%(title).150B [%(id)s].%(ext)s"),
        # ensures final container is mp4 even if source video/audio are webm/opus
        "postprocessors": [{"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}],
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filepath = ydl.prepare_filename(info)

    base, _ = os.path.splitext(filepath)
    mp4_path = base + ".mp4"
    return mp4_path if os.path.exists(mp4_path) else filepath


AUDIO_FORMAT_CODECS = {
    "mp3": "mp3",
    "m4a": "m4a",
    "opus": "opus",
    "wav": "wav",
    "flac": "flac",
    "vorbis": "vorbis",
}


def download_audio(
    url: str,
    bitrate: str = "192",
    audio_format: str = "mp3",
    format_id: Optional[str] = None,
) -> str:
    """
    Download audio and convert it to the requested format via ffmpeg.

    bitrate: target bitrate in kbps (ignored for lossless formats like wav/flac).
    audio_format: one of "mp3", "m4a", "opus", "wav", "flac", "vorbis".
    format_id: optional exact yt-dlp audio format id from /formats, for
        picking a specific source stream instead of yt-dlp's automatic best pick.

    Returns the absolute path to the resulting audio file.
    """
    audio_format = audio_format.lower()
    if audio_format not in AUDIO_FORMAT_CODECS:
        raise ValueError(f"Unsupported audio_format '{audio_format}'. Choose one of {list(AUDIO_FORMAT_CODECS)}.")

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "format": format_id if format_id else "bestaudio/best",
        "outtmpl": os.path.join(DOWNLOAD_DIR, "%(title).150B [%(id)s].%(ext)s"),
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": AUDIO_FORMAT_CODECS[audio_format],
            "preferredquality": str(bitrate),
        }],
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filepath = ydl.prepare_filename(info)

    base, _ = os.path.splitext(filepath)
    return base + f".{audio_format}"


# Backwards-compatible alias
def download_audio_mp3(url: str, bitrate: str = "192") -> str:
    return download_audio(url, bitrate=bitrate, audio_format="mp3")


def download_playlist(
    url: str,
    media_type: str = "mp4",
    bitrate: str = "192",
    audio_format: str = "mp3",
) -> tuple[str, str]:
    """Download every item in a playlist and package the results in a ZIP file."""
    media_type = media_type.lower()
    audio_format = audio_format.lower()
    if media_type not in {"mp4", "audio"}:
        raise ValueError("media_type must be 'mp4' or 'audio'.")
    if audio_format not in AUDIO_FORMAT_CODECS:
        raise ValueError(f"Unsupported audio_format '{audio_format}'.")

    job_dir = os.path.join(DOWNLOAD_DIR, f"playlist-{uuid.uuid4().hex}")
    os.makedirs(job_dir, exist_ok=True)
    output_template = os.path.join(job_dir, "%(playlist_index)03d - %(title).150B [%(id)s].%(ext)s")

    ydl_opts: Dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": False,
        "ignoreerrors": True,
        "outtmpl": output_template,
    }
    if media_type == "mp4":
        ydl_opts.update({
            "format": "bestvideo+bestaudio/best",
            "merge_output_format": "mp4",
            "postprocessors": [{"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}],
        })
    else:
        ydl_opts.update({
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": AUDIO_FORMAT_CODECS[audio_format],
                "preferredquality": str(bitrate),
            }],
        })

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    files = [
        entry.path for entry in os.scandir(job_dir)
        if entry.is_file() and not entry.name.endswith((".part", ".ytdl"))
    ]
    if not files:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise RuntimeError("No downloadable videos were found in this playlist.")

    playlist_title = sanitize_filename((info or {}).get("title") or "playlist")
    archive_base = os.path.join(DOWNLOAD_DIR, f"{playlist_title}-{uuid.uuid4().hex[:8]}")
    archive_path = shutil.make_archive(archive_base, "zip", job_dir)
    shutil.rmtree(job_dir, ignore_errors=True)
    return archive_path, f"{playlist_title}.zip"
