import argparse
import logging
import subprocess
from pathlib import Path

from dotenv import dotenv_values


logging.basicConfig(level=logging.INFO)
__logger__ = logging.getLogger("converter")


def sanitize_file_name(filename: str) -> str:
    parts = filename.split('-')
    path_parts = _get_new_path_parts(parts)
    stem = path_parts.removesuffix(".mp4").removesuffix(" .mp4")
    return stem


def get_new_file_name(filename: str, index: int) -> str:
    parts = filename.split('-')
    path_parts = _get_new_path_parts(parts)
    new_stem = path_parts.removesuffix(".mp4").removesuffix(" .mp4")
    new_fn = Path(f"{new_stem}-{index}").with_suffix(".mp4")
    return new_fn.name


def _get_new_path_parts(parts: list) -> str:
    if len(parts) < 6:
        return Path("".join(parts).strip()).stem
    return Path("".join(parts[6:]).strip()).stem


def extract_audio_bitrate(filename: str):
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
        __logger__.info(f"Got bitrate as {bitrate}")
    except subprocess.CalledProcessError as exc:
        __logger__.error(f"Error extracting bitrate from {filename}: {exc.stderr}")
        raise
    return bitrate


def convert(sp: str, newdB: str, pattern: str, dry_run: bool):
    audio_bitrate = None
    for index, item in enumerate(Path(sp).glob(f"*{pattern}*.mp4")):
        if not audio_bitrate:
            audio_bitrate = extract_audio_bitrate(item.name)
        new_file_name = get_new_file_name(item.name, index=index)
        command = [
            "ffmpeg",
            "-i",
            item.name,
            "-c:v",
            "copy",
            "-af",
            f"volume={newdB}dB",
            "-c:a",
            "aac",
            "-b:a",
            audio_bitrate,
            new_file_name
        ]
        __logger__.debug(command)
        if not dry_run:
            try:
                subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except subprocess.CalledProcessError as exc:
                __logger__.error(f"Error converting {item.name}- {exc.stderr}")
            __logger__.info(f"{item.name} -> {new_file_name} converted")


def collect(folder: str, pattern: str) -> dict:
    file_map = {}
    for item in Path(folder).glob(f"*{pattern}*.mp4"):
        stem = sanitize_file_name(item.name)
        if stem not in file_map:
            count = 1
            file_map[stem] = {
                'count': count,
                'audio_bitrate': None,
                'original_files': [item.name],
                'new_files': [Path(f"{stem}-{str(count)}").with_suffix(".mp4").as_posix()]
            }
        if stem in file_map:
            count = file_map[stem].get("count") + 1
            file_map[stem]["count"] = count
            file_map[stem]['original_files'].append(item.name)
            new_file = Path(f'{stem}-{str(count)}').with_suffix(".mp4").as_posix()
            file_map[stem]['new_files'].append(new_file)
    return file_map


def get_args():
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
        "--dry-run", action="store_true", help="Print ffmpeg commands without executing them."
    )
    args = parser.parse_args()
    return args


if __name__ == '__main__':
    envs = dotenv_values()
    source_path = envs.get("SOURCE", None)
    if not source_path:
        __logger__.error("Source path needs to be defined")
    run_args = get_args()
    fm = collect(folder=source_path, pattern=run_args.pattern)
    print(fm)
    for k, v in fm.items():
        for x, y in zip(v["original_files"], v["new_files"]):
            print(x, y)
    convert(sp=source_path, newdB=run_args.dB, pattern=run_args.pattern, dry_run=run_args.dry_run)
