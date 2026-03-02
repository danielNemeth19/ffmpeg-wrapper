
# Video Normalization and Processing with FFmpeg

This tool automates batch processing of MP4 files using FFmpeg, including loudness normalization, overlaying text,
segment cutting, and optional re-encoding.
It is configurable via command-line arguments and environment variables.

> **Note:** This is a naive wrapper script intended for simple batch workflows.  
> For advanced or production-grade video/audio processing, consider established packages such as [ffmpeg-python](https://github.com/kkroening/ffmpeg-python), [moviepy](https://zulko.github.io/moviepy/), or [PyAV](https://github.com/PyAV-Org/PyAV).

## Usage
If your environment is activated and `ffmpeg_wrapper` is installed as a CLI script, you can run:

```sh
ffmpeg_wrapper [options]
```

## Features

- **Batch loudness normalization** to target LUFS
- **Cut videos into segments** of specified length
- **Re-encode video and audio** to standard formats
- **Dry-run mode** to preview commands without execution
- **Clear target directory** before processing
- **Overlay text** on videos

### Options

- `-l, --lufs FLOAT`  
  Target integrated loudness in LUFS (default: -16)
- `-p, --pattern STR`  
  Pattern to match in MP4 filenames (default: all `.mp4`)
- `-cl, --check-loudness`  
  Check current loudness levels
- `-n, --normalize`  
  Normalize loudness (re-encode audio)
- `-sl, --segment-length INT`  
  Split each video into segments of specified length (seconds)
- `-re, --re-encode`  
  Re-encode video and audio streams to standard settings
- `-t, --text STR`  
  Overlay text on video
- `-cf, --clear-first`  
  Clear target folder before processing
- `-dr, --dry-run`  
  Print ffmpeg commands without executing

### Example: Normalize and Overlay Text

```sh
python -m ffmpeg_wrapper.conv -n -t "Sample Text"
```

### Example: Cut Videos into 30s Segments and Re-encode

```sh
python -m ffmpeg_wrapper.conv -sl 30 -re
```

### Example: Check Loudness Only

```sh
python -m ffmpeg_wrapper.conv -cl
```

## Environment Variables

Set these in a `.env` file or your environment:

- `SOURCE` — Path to source directory with MP4 files
- `TARGET` — Path to target output directory

## FFmpeg Command Reference

See below for manual ffmpeg commands similar to what this script automates.

### Quick Audio Normalization Example

```sh
ffmpeg -i input.mp4 -c:v copy -filter:a "loudnorm=I=-16:TP=-1.5:LRA=7:linear=true" output.mp4
```

**Parameter explanations:**
- `I=-16`: Target integrated loudness, -16 LUFS (good for speech, matches YouTube and streaming standards).
- `TP=-1.5`: True peak limit, -1.5 dBTP (prevents digital clipping).
- `LRA=7`: Loudness range, 7 LU (keeps dynamics natural but not too wide for speech).
- `linear=true`: Use linear normalization (better for speech).

---

### Normalizing Videos for Concatenation

To **normalize** all your videos for concatenation, you should:
- **Re-encode both video and audio** to a common format, resolution, frame rate, and audio settings.
- Apply the `loudnorm` filter to the audio.

**Recommended ffmpeg command:**

```sh
ffmpeg -i input.mp4 \
  -vf "scale=1280:720,fps=30" \
  -c:v libx264 -preset fast -crf 23 \
  -c:a aac -b:a 192k -ar 48000 -ac 2 \
  -af "loudnorm=I=-16:TP=-1.5:LRA=11" \
  output.mp4
```

---

### Cutting and Normalizing a Video Segment

```sh
ffmpeg -ss 00:01:23 -i input.mp4 \
  -vf "scale=1280:720,fps=30" \
  -c:v libx264 -preset fast -crf 23 \
  -c:a aac -b:a 192k -ar 48000 -ac 2 \
  -af "loudnorm=I=-16:TP=-1.5:LRA=11" \
  -t 30 \
  output.mp4
```
