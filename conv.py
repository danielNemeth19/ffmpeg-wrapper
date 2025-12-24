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
# ffmpeg -i input.mp4 -c:v copy -filter:a "loudnorm=I=-16:TP=-1.5:LRA=11" output.mp4
# ```
# - `I` = Integrated loudness target (in LUFS, e.g., -16 for YouTube, -23 for broadcast)
# - `LRA` = Loudness range target

# **Summary:**
# `loudnorm` is a smart, standards-based way to make your audio consistently loud and clear, without unwanted distortion.

# test:
# ffmpeg -i input.mp4 -af loudnorm=I=-16:TP=-1.5:LRA=11:print_format=summary -f null -


logging.basicConfig(level=logging.INFO)
__logger__ = logging.getLogger("converter")


class FileInfo(TypedDict):
    count: int
    audio_bitrate: str | None
    original_files: list[str]
    new_files: list[str]
    decibel_bump: str
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
    return stem[:-3]


def get_new_file_name(filename_base: Path, decibel_value: str, index: int) -> str:
    return Path(f"{filename_base}-dB{decibel_value}-{index:03d}").with_suffix(".mp4").as_posix()


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


def get_loudnorm_summary(file_map: dict[str, FileInfo]):
    for video, video_data in file_map.items():
        __logger__.info("Processing: %s", video)
        for input_file in video_data["original_files"]:
            command = [
                "ffmpeg",
                "-i",
                input_file,
                "-af",
                "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json",
                "-f",
                "null",
                "-"
            ]
            __logger__.debug(command)
            try:
                raw_output = subprocess.run(command, text=True, check=True, capture_output=True)
                summary = parse_loudnorm_summary(raw_output.stderr)
                __logger__.info("loudness for %s: %s", input_file, summary['input_i'])
            except subprocess.CalledProcessError as exc:
                __logger__.error("Error converting %s: %s", input_file, exc.stderr)


def convert(file_map: dict[str, FileInfo], dry_run: bool):
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
                f"volume={video_data['decibel_bump']}dB",
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


def create_file_map(source: str, target: str, pattern: str, decibel: str) -> dict[str, FileInfo]:
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
                    get_new_file_name(filename_base=new_fn_base, decibel_value=decibel, index=count)
                ],
                'decibel_bump': decibel,
                'done': False
            }
        elif stem in file_map:
            count = file_map[stem].get("count") + 1
            file_map[stem]["count"] = count
            file_map[stem]['original_files'].append(original_fn)
            new_file = get_new_file_name(
                filename_base=new_fn_base, decibel_value=decibel, index=count
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
        "--dB", type=str, help="Audio volume adjustment in dB (e.g., 20 for +20dB)."
    )
    parser.add_argument(
        "--pattern", type=str, nargs="?", help="Pattern to match in MP4 filenames.", default=""
    )
    parser.add_argument(
        "--clear-first", action="store_true", help="Clear target folder first"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print ffmpeg commands without executing them."
    )
    args = parser.parse_args()
    return args.dB, args.pattern, args.clear_first, args.dry_run


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
    decibel, pattern, clear_first, dry_run = get_args()
    pattern = _normalize_pattern(pattern)
    if clear_first:
        clear_target_directory(tp=target_path, pattern=pattern, dry_run=dry_run)
    fm = create_file_map(source=source_path, target=target_path, pattern=pattern, decibel=decibel)
    get_loudnorm_summary(file_map=fm)
    # convert(file_map=fm, dry_run=dry_run)
