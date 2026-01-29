
# Video Normalization and Processing with FFmpeg

## Quick Audio Normalization Example

```sh
ffmpeg -i input.mp4 -c:v copy -filter:a "loudnorm=I=-16:TP=-1.5:LRA=7:linear=true" output.mp4
```

**Parameter explanations:**
- `I=-16`: Target integrated loudness, -16 LUFS (good for speech, matches YouTube and streaming standards).
- `TP=-1.5`: True peak limit, -1.5 dBTP (prevents digital clipping).
- `LRA=7`: Loudness range, 7 LU (keeps dynamics natural but not too wide for speech).
- `linear=true`: Use linear normalization (better for speech).

---

## Normalizing Videos for Concatenation

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

## Cutting and Normalizing a Video Segment

```sh
ffmpeg -ss 00:01:23 -i input.mp4 \
  -vf "scale=1280:720,fps=30" \
  -c:v libx264 -preset fast -crf 23 \
  -c:a aac -b:a 192k -ar 48000 -ac 2 \
  -af "loudnorm=I=-16:TP=-1.5:LRA=11" \
  -t 30 \
  output.mp4
```
