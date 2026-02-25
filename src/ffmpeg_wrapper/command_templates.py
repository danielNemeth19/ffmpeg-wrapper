DURATION_TEMPLATE = (
    "ffprobe",
    "-v",
    "error",
    "-show_entries",
    "format=duration",
    "-of",
    "default=noprint_wrappers=1:nokey=1",
    "{infile}",
)


AUDIO_BITRATE_TEMPLATE = (
    "ffprobe",
    "-v",
    "error",
    "-select_streams",
    "a:0",
    "-show_entries",
    "stream=bit_rate",
    "-of",
    "default=noprint_wrappers=1:nokey=1",
    "{infile}",
)


DEFAULT_OVERLAY_TEMPLATE = (
    "ffmpeg",
    "-i",
    "{filename}",
    "-vf",
    "drawtext=text='{text}':fontcolor=white:fontsize=120:bordercolor=black:borderw=2:x=(w-text_w)/2:y=(h-text_h)/2",
    "-c:a",
    "copy",
    "{outfile}"
)


LOUDNESS_ANALYSIS_TEMPLATE = (
    "ffmpeg",
    "-i",
    "{filename}",
    "-af",
    "loudnorm=I={lufs}:TP=-1.5:LRA=11:print_format=json",
    "-f",
    "null",
    "-"
)


LOUDNESS_NORMALIZATION_TEMPLATE = (
    "ffmpeg",
    "-y",
    "-i",
    "{filename}",
    "-c:v",
    "copy",
    "-af",
    "loudnorm=I={lufs}:TP=-1.5:LRA=5:linear=true",
    "-c:a",
    "aac",
    "-b:a",
    "{audio_bitrate}",
    "{outfile}",
)


CREATE_CUTS_TEMPLATE = (
    "ffmpeg",
    "-y",
    "-ss",
    "{current_ss}",
    "-t",
    "{cuts}",
    "-i",
    "{filename}",
    "{opts}",
    "{outfile}"
)


DEFAULT_RE_ENCODE_OPTS = (
    "-vf", "scale=1280:720,fps=30",
    "-c:a", "aac",
    "-b:a", "192k",
    "-ar", "48000",
    "-ac", "2",
    "-af", "loudnorm=I=-16:TP=-1.5:LRA=5:linear=true",
)


DEFAULT_COPY_OPTS = (
    "-c", "copy",
)
