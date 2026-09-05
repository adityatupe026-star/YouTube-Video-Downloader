"""
app.py
FastAPI layer around downloader.py (yt-dlp).

Run:
    uvicorn app:app --reload --host 0.0.0.0 --port 8000

Then open http://127.0.0.1:8000/docs for interactive API docs.
"""

import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

import downloader

app = FastAPI(
    title="YouTube Downloader API",
    description="Download YouTube videos as MP4 or MP3 using yt-dlp.",
    version="1.0.0",
)

# Allow a browser-based frontend (on any origin) to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "Content-Length"],
)


@app.get("/")
def root():
    return {
        "message": "YouTube Downloader API",
        "endpoints": {
            "GET /formats": "List available video/audio qualities for a URL",
            "GET /download/mp4": "Download video as MP4 at a chosen quality",
            "GET /download/mp3": "Download audio as MP3 at a chosen bitrate",
            "GET /download/playlist": "Download a playlist as a ZIP of MP4 or audio files",
        },
        "docs": "/docs",
    }


AUDIO_MEDIA_TYPES = {
    "mp3": "audio/mpeg",
    "m4a": "audio/mp4",
    "opus": "audio/opus",
    "wav": "audio/wav",
    "flac": "audio/flac",
    "vorbis": "audio/ogg",
}


@app.get("/formats")
def formats(url: str = Query(..., description="Full YouTube video URL")):
    """
    Return full video metadata plus EVERY available quality option:
    - video_qualities: deduplicated best pick per resolution+fps+codec (e.g. "2160p60 AV1", "1080p H.264")
    - all_video_formats: every raw video-capable format yt-dlp found (advanced/power-user view)
    - all_audio_formats: every raw audio-only stream (for MP3/M4A/Opus/etc. extraction)
    - audio_bitrates_kbps / audio_formats_supported: choices for the audio-extraction UI
    """
    try:
        info = downloader.get_video_info(url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not fetch video info: {e}")
    return info


@app.get("/download/mp4")
def download_mp4(
    url: str = Query(..., description="Full YouTube video URL"),
    height: int | None = Query(
        None, description="Max resolution height (e.g. 4320, 2160, 1440, 1080, 720, 480, 360). Omit for best available."
    ),
    codec: str | None = Query(
        None, description="Preferred codec family: 'av1', 'vp9', or 'h264'. Omit for best available."
    ),
    format_id: str | None = Query(
        None, description="Exact yt-dlp format_id from /formats for full manual control. Overrides height/codec."
    ),
):
    """Download the video (any resolution up to 8K, any codec) and return it as an MP4 file."""
    try:
        filepath = downloader.download_video_mp4(url, height=height, format_id=format_id, codec=codec)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Download failed: {e}")

    if not os.path.exists(filepath):
        raise HTTPException(status_code=500, detail="File not found after download.")

    return FileResponse(
        filepath,
        media_type="video/mp4",
        filename=os.path.basename(filepath),
    )


@app.get("/download/audio")
def download_audio(
    url: str = Query(..., description="Full YouTube video URL"),
    bitrate: str = Query("192", description="Target bitrate in kbps: 320, 256, 192, 160, 128, 96, or 64"),
    audio_format: str = Query("mp3", description="Output format: mp3, m4a, opus, wav, flac, or vorbis"),
    format_id: str | None = Query(
        None, description="Exact yt-dlp audio format_id from /formats to pick a specific source stream."
    ),
):
    """Download audio and return it converted to the requested format (mp3/m4a/opus/wav/flac/vorbis)."""
    audio_format = audio_format.lower()
    if audio_format not in AUDIO_MEDIA_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported audio_format. Choose one of {list(AUDIO_MEDIA_TYPES)}.")

    try:
        filepath = downloader.download_audio(url, bitrate=bitrate, audio_format=audio_format, format_id=format_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Download failed: {e}")

    if not os.path.exists(filepath):
        raise HTTPException(status_code=500, detail="File not found after download.")

    return FileResponse(
        filepath,
        media_type=AUDIO_MEDIA_TYPES[audio_format],
        filename=os.path.basename(filepath),
    )


@app.get("/download/mp3")
def download_mp3(
    url: str = Query(..., description="Full YouTube video URL"),
    bitrate: str = Query("192", description="MP3 bitrate in kbps: 320, 256, 192, 160, 128, 96, or 64"),
):
    """Convenience shortcut for MP3 (kept for backwards compatibility). Use /download/audio for other formats."""
    return download_audio(url=url, bitrate=bitrate, audio_format="mp3", format_id=None)


@app.get("/download/playlist")
def download_playlist(
    url: str = Query(..., description="Full YouTube playlist URL"),
    media_type: str = Query("mp4", description="mp4 or audio"),
    bitrate: str = Query("192", description="Audio bitrate in kbps"),
    audio_format: str = Query("mp3", description="Audio output format"),
):
    """Download a playlist and return its contents as a ZIP archive."""
    if media_type not in {"mp4", "audio"}:
        raise HTTPException(status_code=400, detail="media_type must be 'mp4' or 'audio'.")
    if audio_format.lower() not in AUDIO_MEDIA_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported audio_format. Choose one of {list(AUDIO_MEDIA_TYPES)}.")
    try:
        filepath, filename = downloader.download_playlist(
            url, media_type=media_type, bitrate=bitrate, audio_format=audio_format
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Playlist download failed: {e}")

    return FileResponse(filepath, media_type="application/zip", filename=filename)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
