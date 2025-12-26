import sys
import argparse
import json
import logging
import subprocess
from pathlib import Path
from typing import TypedDict

from dotenv import dotenv_values

# The `loudnorm` filter in `ffmpeg` applies **EBU R128 loudness normalization** to your audio. Here’s what it does:

# - **Measures and adjusts loudness** so that the output matches a target loudness level (default: -23 LUFS, but you can set your own).
# - **Balances perceived loudness** across different audio files, making them sound equally loud to listeners.
# - **Optionally corrects true peak levels** to avoid digital clipping.
# - **Handles short-term and momentary loudness** for more consistent results.

# **In practice:**
# - It analyzes the audio to determine its current loudness.
# - It applies gain (boost or reduction) so the output matches your target loudness.
# - It can also limit peaks to prevent distortion.

# **Typical usage:**
# ```
# ffmpeg -i input.mp4 -c:v copy -filter:a "loudnorm=I=-16:TP=-1.5:LRA=7:linear=true" output.mp4
# ```
# - I=-16 -> Target integrated loudness: -16 LUFS (good for speech, matches YouTube and streaming standards).
# - TP=-1.5 -> True peak limit: -1.5 dBTP (prevents digital clipping).
# - LRA=7 -> Loudness range: 7 LU (keeps dynamics natural but not too wide for speech).
# - linear=true -> Use linear normalization (better for speach)

# test:
# ffmpeg -i input.mp4 -af loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json -f null -

# To **formalize** (normalize) all your videos for concatenation, you should:
# - **Re-encode both video and audio** to a common format, resolution, frame rate, and audio settings.
# - Apply the `loudnorm` filter to the audio.
# **Recommended ffmpeg command:**
# ```
# ffmpeg -i input.mp4 \
# -vf "scale=1280:720,fps=30" \
# -c:v libx264 -preset fast -crf 23 \
# -c:a aac -b:a 192k -ar 48000 -ac 2 \
# -af "loudnorm=I=-16:TP=-1.5:LRA=11" \
# output.mp4


logging.basicConfig(level=logging.INFO)
__logger__ = logging.getLogger("converter")


class FileInfo(TypedDict):
    count: int
    audio_bitrate: str | None
    original_files: list[str]
    new_files: list[str]
    target_lufs: str
    done: bool


def sanitize_file_name(filename: str) -> str:
    parts = filename.split('-')
    path_parts = _get_new_path_parts(parts)
    stem = path_parts.removesuffix(".mp4").removesuffix(" .mp4")
    stem = _trim_index_if_exists(stem)
    return stem


def _get_new_path_parts(parts: list) -> str:
    if len(parts) < 6:
        return Path("".join(parts).strip()).stem
    return Path("".join(parts[6:]).strip()).stem


def _trim_index_if_exists(stem: str) -> str:
    suffix = stem[-3:]
    try:
        int(suffix)
    except ValueError:
        __logger__.debug("suffix %s is not int for %s", suffix, stem)
        return stem
    if stem[-4] == "_":
        return stem[:-4]
    return stem[:-3]


def get_new_file_name(filename_base: Path, lufs_value: str, index: int) -> str:
    return Path(f"{filename_base}lufs{lufs_value}_{index:03d}").with_suffix(".mp4").as_posix()


def extract_audio_bitrate(filename: str) -> str:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=bit_rate",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        filename
    ]
    try:
        raw_bit_rate = subprocess.run(command, check=True, capture_output=True, text=True)
        bitrate = raw_bit_rate.stdout.strip()
    except subprocess.CalledProcessError as exc:
        __logger__.error("Error extracting bitrate from %s: %s", filename, exc.stderr)
        raise
    return bitrate


def parse_loudnorm_summary(text: str) -> dict:
    parse_flag = False
    captured = ""
    for row in text.split('\n'):
        if row.startswith("{"):
            parse_flag = True
        if parse_flag:
            captured += row
        if row.startswith("}"):
            parse_flag = False

    summary = json.loads(captured)
    return summary


def get_loudnorm_summary(file_map: dict[str, FileInfo], target: str):
    for video, video_data in file_map.items():
        __logger__.info("Processing: %s", video)
        for input_file in video_data["original_files"]:
            command = [
                "ffmpeg",
                "-i",
                input_file,
                "-af",
                f"loudnorm=I={target}:TP=-1.5:LRA=11:print_format=json",
                "-f",
                "null",
                "-"
            ]
            __logger__.debug(command)
            try:
                raw_output = subprocess.run(command, text=True, check=True, capture_output=True)
                summary = parse_loudnorm_summary(raw_output.stderr)
                __logger__.info("current loudness for %s: %s - target: %s (offset %s) ",
                                input_file, summary['input_i'], target, summary["target_offset"])
            except subprocess.CalledProcessError as exc:
                __logger__.error("Error converting %s: %s", input_file, exc.stderr)


def convert(file_map: dict[str, FileInfo], target: str, dry_run: bool):
    for video, video_data in file_map.items():
        __logger__.info("Processing: %s", video)
        for input_file, new_file in zip(video_data["original_files"], video_data["new_files"]):
            if not video_data["audio_bitrate"]:
                bitrate = extract_audio_bitrate(input_file)
                video_data["audio_bitrate"] = bitrate
                __logger__.info("Got audio bit_rate for: %s -- %s", input_file, bitrate)
            command = [
                "ffmpeg",
                "-y",
                "-i",
                input_file,
                "-c:v",
                "copy",
                "-af",
                f"loudnorm=I={target}:TP=-1.5:LRA=5:linear=true",
                "-c:a",
                "aac",
                "-b:a",
                video_data["audio_bitrate"],
                new_file
            ]
            __logger__.info(command)
            if not dry_run:
                try:
                    subprocess.run(command, text=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                    __logger__.info("%s -> %s converted", input_file, new_file)
                except subprocess.CalledProcessError as exc:
                    __logger__.error("Error converting %s: %s", input_file, exc.stderr)
                    video_data['done'] = False
        video_data['done'] = True
        print(f"Setting vide data: {video_data['done']}")
    return file_map


def create_file_map(source: str, target: str, pattern: str, lufs: str) -> dict[str, FileInfo]:
    file_map: dict[str, FileInfo] = {}
    for item in Path(source).glob(pattern):
        original_fn = Path(source, item.name).as_posix()
        stem = sanitize_file_name(item.name)
        new_fn_base = Path(target, stem)
        if stem not in file_map:
            count = 1
            file_map[stem] = {
                'count': count,
                'audio_bitrate': None,
                'original_files': [original_fn],
                'new_files': [
                    get_new_file_name(filename_base=new_fn_base, lufs_value=lufs, index=count)
                ],
                'target_lufs': lufs,
                'done': False
            }
        elif stem in file_map:
            count = file_map[stem].get("count") + 1
            file_map[stem]["count"] = count
            file_map[stem]['original_files'].append(original_fn)
            new_file = get_new_file_name(
                filename_base=new_fn_base, lufs_value=lufs, index=count
            )
            file_map[stem]['new_files'].append(new_file)
    return file_map


def clear_target_directory(tp: str, pattern: str, dry_run: bool) -> None:
    counter = 0
    for f in Path(tp).glob(pattern):
        if f.is_file() or f.is_symlink():
            counter += 1
            if not dry_run:
                f.unlink()
    action_log_msg = "Deleted" if not dry_run else "Would delete"
    __logger__.info("%s %d# files from target folder with pattern %s", action_log_msg, counter, pattern)


def get_args() -> tuple[str, str, bool]:
    parser = argparse.ArgumentParser(
        description="Batch adjust audio volume and re-encode MP4 files."
    )
    parser.add_argument(
        "--lufs", type=str, help="Target integrated loudness in LUFS", default="-16"
    )
    parser.add_argument(
        "--pattern", type=str, nargs="?", help="Pattern to match in MP4 filenames.", default=""
    )
    parser.add_argument(
        "--check-loudness", action="store_true", help="Check current loudness levels"
    )
    parser.add_argument(
        "--clear-first", action="store_true", help="Clear target folder first"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print ffmpeg commands without executing them."
    )
    args = parser.parse_args()
    return args.lufs, args.pattern, args.check_loudness, args.clear_first, args.dry_run


def _validate_paths(sp: str, tp: str) -> bool:
    if not sp or not tp:
        __logger__.error("Source and target needs to be defined, got %s and %s", sp, tp)
        return False
    if not Path(sp).exists():
        __logger__.error("Source folder %s doesn't exists, quiting...", sp)
        return False
    if not Path(tp).exists():
        __logger__.info("Target folder %s doesn't exists... creating", sp)
        Path(tp).mkdir()
    return True


def _normalize_pattern(pattern: str) -> str:
    if not pattern:
        return "*.mp4"
    return f"*{pattern}*.mp4"


if __name__ == '__main__':
    envs = dotenv_values()
    source_path = envs.get("SOURCE", None)
    target_path = envs.get("TARGET", None)
    if not _validate_paths(sp=source_path, tp=target_path):
        sys.exit()
    lufs, pattern, check_loudness, clear_first, dry_run = get_args()
    pattern = _normalize_pattern(pattern)
    if clear_first:
        clear_target_directory(tp=target_path, pattern=pattern, dry_run=dry_run)
    fm = create_file_map(source=source_path, target=target_path, pattern=pattern, lufs=lufs)
    if check_loudness:
        get_loudnorm_summary(file_map=fm, target=lufs)
    convert(file_map=fm, target=lufs, dry_run=dry_run)
