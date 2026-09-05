# YouTube Downloader (yt-dlp + FastAPI)

Download YouTube videos as **MP4** (with resolution choice) or **MP3** (with bitrate choice).

## Files
- `downloader.py` — core yt-dlp logic (get formats, download mp4, download mp3)
- `app.py` — FastAPI app exposing that logic over HTTP
- `requirements.txt` — dependencies

## Setup

```bash
pip install -r requirements.txt
```

You also need **ffmpeg** installed on your system (required for muxing video/audio and converting to mp3):

```bash
# Ubuntu/Debian
sudo apt install ffmpeg

# macOS
brew install ffmpeg

# Windows
choco install ffmpeg
```

## Run the API

```bash
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

Open **http://127.0.0.1:8000/docs** for interactive Swagger docs.

## Endpoints

### 1. List ALL available qualities
```
GET /formats?url=https://www.youtube.com/watch?v=VIDEO_ID
```
Returns:
- `video_qualities` — a deduplicated, ready-to-use dropdown list: the best
  stream per resolution+framerate+codec combo, e.g. `"2160p60 AV1"`,
  `"1440p VP9"`, `"1080p H.264"`, `"720p60 AV1"`, down to `"144p"`. Includes
  HDR flag, exact bitrate, filesize, and codec for each.
- `all_video_formats` — **every** raw video-capable format yt-dlp found
  (nothing deduplicated), for power users who want to pick an exact stream —
  each with `format_id`, `resolution`, `fps`, `vcodec`, `dynamic_range`
  (HDR/SDR), `tbr_kbps`, `filesize`.
- `all_audio_formats` — every raw audio-only stream (different codecs/bitrates
  YouTube offers), each with `format_id`, `acodec`, `abr_kbps`, `asr_hz`.
- `audio_bitrates_kbps` — standard bitrate choices: `320, 256, 192, 160, 128, 96, 64`.
- `audio_formats_supported` — `mp3, m4a, opus, wav, flac, vorbis`.

### 2. Download as MP4 — any resolution up to 8K, any codec
```
GET /download/mp4?url=...&height=2160
GET /download/mp4?url=...&height=1080&codec=av1
GET /download/mp4?url=...&format_id=399          # exact stream from /formats
```
- `height` — cap on resolution (e.g. `4320`, `2160`, `1440`, `1080`, `720`, `480`, `360`, `240`, `144`). Omit for best available.
- `codec` — restrict to a codec family: `av1`, `vp9`, or `h264`. Omit for best available.
- `format_id` — pick the *exact* format from `/formats` → `all_video_formats` for full manual control (overrides `height`/`codec`). If it's video-only, best audio is auto-merged.
- Always remuxed/merged to a single `.mp4` on output, even if the source streams are WebM/Opus.

### 3. Download as audio — MP3, M4A, Opus, WAV, FLAC, or Vorbis
```
GET /download/audio?url=...&audio_format=mp3&bitrate=320
GET /download/audio?url=...&audio_format=flac
GET /download/audio?url=...&audio_format=opus&format_id=251   # exact source stream
```
- `audio_format` — `mp3` (default), `m4a`, `opus`, `wav`, `flac`, or `vorbis`.
- `bitrate` — target kbps (ignored for lossless `wav`/`flac`). Standard values: `320, 256, 192, 160, 128, 96, 64`.
- `format_id` — pick the exact source stream from `/formats` → `all_audio_formats` instead of yt-dlp's automatic best pick.
- `GET /download/mp3?url=...&bitrate=192` is kept as a shortcut for backwards compatibility.

## Notes
- Downloaded files are cached in a local `downloads/` folder before being served.
- Respect YouTube's Terms of Service and copyright law — only download content
  you have the right to download (your own uploads, Creative Commons/public
  domain content, or videos you have explicit permission to save).
- For very high resolutions (4K/8K), yt-dlp downloads separate video and audio
  streams and merges them with ffmpeg, which can take longer.
