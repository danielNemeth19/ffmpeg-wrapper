
# Video Normalization and Processing with FFmpeg

A small Python CLI tool to batch-process `.mp4` files with FFmpeg/FFprobe.

It supports:

- Loudness analysis (LUFS)
- Loudness normalization
- Text overlay
- Video cutting into fixed-length segments
- Optional re-encode for cuts
- Dry-run mode to preview commands

> **Note:** This is a naive wrapper script intended for simple batch workflows.  
> For advanced or production-grade video/audio processing, consider established packages such as [ffmpeg-python](https://github.com/kkroening/ffmpeg-python), [moviepy](https://zulko.github.io/moviepy/), or [PyAV](https://github.com/PyAV-Org/PyAV).

## Requirements

- Linux machine
- Python `>=3.14` (as defined in `pyproject.toml`)
- [`uv`](https://docs.astral.sh/uv/)
- `ffmpeg` + `ffprobe` available in `PATH`

## Install / setup (uv)

From project root:

```bash
uv sync
```

This installs runtime + project dependencies from `pyproject.toml`.

## Configuration

Create a `.env` file in the project root:

```env
SOURCE=/absolute/path/to/source
TARGET=/absolute/path/to/target
```

- `SOURCE`: input folder with `.mp4` files
- `TARGET`: output folder (created if missing)

## Usage
If your environment is activated and `ffmpeg_wrapper` is installed as a CLI script, you can run:

```sh
ffmpeg_wrapper [options]
```

### CLI options

- `-l, --lufs` (float, default: `-16`)
  Target integrated loudness.
- `-p, --pattern` (string)
  Filename substring filter (`*{pattern}*.mp4`).
- `-cl, --check-loudness`
  Analyze loudness only.
- `-n, --normalize`
  Normalize audio loudness.
- `-sl, --segment-length` (int)
  Split each video into N-second segments.
- `-re, --re-encode`
  Re-encode cuts with default options.
- `-t, --text` (string)
  Draw centered text overlay.
- `-cf, --clear-first`
  Clear matching files in target first.
- `-dr, --dry-run`
  Print FFmpeg commands without executing them (FFprobe still executes).

## Examples

Check loudness:

```bash
uv run ffmpeg_wrapper -cl
```

Normalize to -16 LUFS:

```bash
uv run ffmpeg_wrapper -n -l -16
```

Normalize only files matching pattern:

```bash
uv run ffmpeg_wrapper -n -p session1
```

Add overlay text:

```bash
uv run ffmpeg_wrapper -t "DRAFT"
```

Cut into 60-second segments:

```bash
uv run ffmpeg_wrapper -sl 60
```

Cut into 60-second segments with re-encode:

```bash
uv run ffmpeg_wrapper -sl 60 -re
```

Dry run:

```bash
uv run ffmpeg_wrapper -n -sl 60 -dr
```

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
