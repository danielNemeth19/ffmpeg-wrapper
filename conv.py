import sys
import argparse
import math
import json
import logging
import subprocess
from pathlib import Path
from typing import TypedDict
from collections import OrderedDict

from dotenv import dotenv_values

# ```
# ffmpeg -i input.mp4 -c:v copy -filter:a "loudnorm=I=-16:TP=-1.5:LRA=7:linear=true" output.mp4
# ```
# - I=-16 -> Target integrated loudness: -16 LUFS (good for speech, matches YouTube and streaming standards).
# - TP=-1.5 -> True peak limit: -1.5 dBTP (prevents digital clipping).
# - LRA=7 -> Loudness range: 7 LU (keeps dynamics natural but not too wide for speech).
# - linear=true -> Use linear normalization (better for speach)

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

# cutting
# ffmpeg -ss 00:01:23 -i input.mp4 \
# -vf "scale=1280:720,fps=30" \
# -c:v libx264 -preset fast -crf 23 \
# -c:a aac -b:a 192k -ar 48000 -ac 2 \
# -af "loudnorm=I=-16:TP=-1.5:LRA=11" \
# -t 30 \
# output.mp4


logging.basicConfig(level=logging.INFO)
__logger__ = logging.getLogger("converter")


DEFAULT_RE_ENCODE_OPTS = [
    "-vf", "scale=1280:720,fps=30",
    "-c:a", "aac",
    "-b:a", "192k",
    "-ar", "48000",
    "-ac", "2",
    "-af", "loudnorm=I=-16:TP=-1.5:LRA=5:linear=true",
]


class FileBatchInfo(TypedDict):
    count: int
    audio_bitrate: int
    original_files: list[Path]
    new_files: list[str]
    target_lufs: float
    done: bool


class FileCutInfo(TypedDict):
    # original_file: Path
    stem_index: int
    duration: int
    segments: int
    done: bool


class Converter:
    def __init__(self, envs: OrderedDict[str, str], args: argparse.Namespace):
        self._validate_args(args)
        self.args = args
        self.source_path = self._set_source_path(envs)
        self.target_path = self._set_target_path(envs)
        self.pattern = self._normalize_pattern()
        self.file_map = self._set_file_map()
        self.dry_run = args.dry_run
        self.clear_target_directory()

    @staticmethod
    def _set_source_path(envs):
        sp = envs.get("SOURCE", None)
        if not sp:
            __logger__.error("Source needs to be defined, got %s", sp)
            sys.exit(1)
        if not Path(sp).exists():
            __logger__.error("Source folder doesn't exists,quiting...")
            sys.exit(1)
        return sp

    @staticmethod
    def _set_target_path(envs):
        tp = envs.get("TARGET", None)
        if not Path(tp).exists():
            __logger__.info("Target folder %s doesn't exists... creating", tp)
            Path(tp).mkdir()
        return tp

    def _normalize_pattern(self) -> str:
        if not self.args.pattern:
            return "*.mp4"
        return f"*{self.args.pattern}*.mp4"

    def _set_file_map(self):
        if self.args.check_loudness or self.args.normalize:
            return self.create_file_map()
        if self.args.cuts:
            return self.create_file_cut_map()
        return None

    def _validate_args(self, args):
        return

    def clear_target_directory(self) -> None:
        if not self.args.clear_first:
            return
        counter = 0
        for f in Path(self.target_path).iterdir():
            if f.is_file() or f.is_symlink():
                counter += 1
                if not self.dry_run:
                    f.unlink()
        action_log_msg = "Deleted" if not self.dry_run else "Would delete"
        __logger__.info("%s %d# files from target folder with pattern %s", action_log_msg, counter, self.pattern)

    def sanitize_file_name(self, filename: str) -> str:
        parts = filename.split('-')
        path_parts = self._get_new_path_parts(parts)
        stem = path_parts.removesuffix(".mp4").removesuffix(" .mp4")
        stem = self._trim_index_if_exists(stem)
        return stem.replace("  ", "_").replace(" ", "_").replace(".", "_")

    @staticmethod
    def _get_new_path_parts(parts: list) -> str:
        if len(parts) < 6:
            return Path("".join(parts).strip()).stem
        return Path("".join(parts[6:]).strip()).stem

    @staticmethod
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

    @staticmethod
    def get_new_file_name(filename_base: Path, lufs_value: float, index: int) -> str:
        return Path(f"{filename_base}_lufs{int(lufs_value)}_{index:03d}").with_suffix(".mp4").as_posix()

    def create_file_map(self) -> dict[str, FileBatchInfo]:
        file_map: dict[str, FileBatchInfo] = {}
        for item in Path(self.source_path).glob(self.pattern):
            original_fn = Path(item)
            stem = self.sanitize_file_name(item.name)
            new_fn_base = Path(self.target_path, stem)
            if stem not in file_map:
                count = 1
                file_map[stem] = {
                    'count': count,
                    'audio_bitrate': 0,
                    'original_files': [original_fn],
                    'new_files': [
                        self.get_new_file_name(
                            filename_base=new_fn_base, lufs_value=self.args.lufs, index=count
                        )
                    ],
                    'target_lufs': self.args.lufs,
                    'done': False
                }
            elif stem in file_map:
                count = file_map[stem].get("count") + 1
                file_map[stem]["count"] = count
                file_map[stem]['original_files'].append(original_fn)
                new_file = self.get_new_file_name(
                    filename_base=new_fn_base, lufs_value=self.args.lufs, index=count
                )
                file_map[stem]['new_files'].append(new_file)
        __logger__.info("Found %d files", len(file_map.keys()))
        return file_map

    @staticmethod
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
        for key, value in summary.items():
            if key != "normalization_type":
                summary[key] = float(value)
        return summary

    def get_loudnorm_summary(self):
        for video, video_data in self.file_map.items():
            __logger__.info("Processing: %s", video)
            for input_file in video_data["original_files"]:
                command = [
                    "ffmpeg",
                    "-i",
                    input_file.as_posix(),
                    "-af",
                    f"loudnorm=I={self.args.lufs}:TP=-1.5:LRA=11:print_format=json",
                    "-f",
                    "null",
                    "-"
                ]
                __logger__.info(command)
                if not self.dry_run:
                    try:
                        raw_output = subprocess.run(command, text=True, check=True, capture_output=True)
                        summary = self.parse_loudnorm_summary(raw_output.stderr)
                        diff_from_target = summary["input_i"] - self.args.lufs
                        __logger__.info(
                            "current loudness for %s: %.2f - diff from target (%s): %.2f - projected offset from target: %.2f",
                            input_file.name, summary['input_i'], self.args.lufs, diff_from_target, summary["target_offset"]
                        )
                    except subprocess.CalledProcessError as exc:
                        __logger__.error("Error converting %s: %s", input_file, exc.stderr)

    def normalize_loudness(self):
        for video, video_data in self.file_map.items():
            __logger__.info("Processing: %s", video)
            for input_file, new_file in zip(video_data["original_files"], video_data["new_files"]):
                if not video_data["audio_bitrate"]:
                    bitrate = self.extract_audio_bitrate(input_file)
                    video_data["audio_bitrate"] = bitrate
                    __logger__.info("Got audio bit_rate for: %s -- %s", input_file, bitrate)
                command = [
                    "ffmpeg",
                    "-y",
                    "-i",
                    input_file.as_posix(),
                    "-c:v",
                    "copy",
                    "-af",
                    f"loudnorm=I={self.args.lufs}:TP=-1.5:LRA=5:linear=true",
                    "-c:a",
                    "aac",
                    "-b:a",
                    str(video_data["audio_bitrate"]),
                    new_file
                ]
                __logger__.info(command)
                if not self.dry_run:
                    try:
                        subprocess.run(command, text=True, check=True,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                        __logger__.info("%s -> %s converted", input_file, new_file)
                    except subprocess.CalledProcessError as exc:
                        __logger__.error("Error converting %s: %s", input_file, exc.stderr)
                        video_data['done'] = False
            video_data['done'] = True
            __logger__.info("Setting video data: %s", video_data['done'])

    @staticmethod
    def extract_audio_bitrate(file_object: Path) -> int:
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
            file_object.as_posix()
        ]
        try:
            raw_bit_rate = subprocess.run(command, check=True, capture_output=True, text=True)
            bitrate = raw_bit_rate.stdout.strip()
        except subprocess.CalledProcessError as exc:
            __logger__.error("Error extracting bitrate from %s: %s", file_object, exc.stderr)
            raise
        return int(bitrate)

    @staticmethod
    def extract_duration(file_object: Path) -> int:
        command = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            file_object.as_posix()
        ]
        try:
            raw_duration = subprocess.run(command, check=True, capture_output=True, text=True)
            duration = raw_duration.stdout.strip()
        except subprocess.CalledProcessError as exc:
            __logger__.error("Error extracting duration from %s: %s", file_object, exc.stderr)
            raise
        return float(duration)

    def create_cuts(self):
        for media, media_data in self.file_map.items():
            __logger__.info("Duration: %f - will make %d cuts", media_data['duration'], media_data['segments'])
            current_ss = 0
            for i in range(media_data['segments']):
                command = ["ffmpeg", "-y", "-ss", str(current_ss), "-t", str(self.args.cuts)]
                command.extend(["-i", media])
                opts = DEFAULT_RE_ENCODE_OPTS if self.args.re_encode else ["-c", "copy"]
                command.extend(opts)
                command.append(f"{media_data['fn_base']}-{i:03d}.mp4")
                __logger__.info(command)
                if not self.dry_run:
                    try:
                        subprocess.run(
                            command, text=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
                        )
                        __logger__.info("Cut #%d - current_ss: %d", i, current_ss)
                    except subprocess.CalledProcessError as exc:
                        __logger__.error("Error converting %s: %s", media, exc.stderr)
                current_ss += self.args.cuts

    def create_file_cut_map(self):
        mapper = {}

        file_map: dict[str, FileCutInfo] = {}
        for item in Path(self.source_path).glob(self.pattern):
            stem = self.sanitize_file_name(item.name)
            stem_index = mapper.get(stem, 0) + 1
            mapper[stem] = stem_index
            new_stem_base = f"{stem}-{stem_index}"
            duration = self.extract_duration(item)
            segments = math.ceil(duration / self.args.cuts)

            if new_stem_base not in file_map:
                file_map[item.as_posix()] = {
                    'stem_index': stem_index,
                    'fn_base': Path(self.target_path, new_stem_base),
                    'duration': duration,
                    'segments': segments
                }
        return file_map


def get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch adjust audio volume and re-encode MP4 files."
    )
    parser.add_argument(
        "-l", "--lufs", type=float, help="Target integrated loudness in LUFS", default="-16"
    )
    parser.add_argument(
        "-p", "--pattern", type=str, nargs="?", help="Pattern to match in MP4 filenames.", default=""
    )
    parser.add_argument(
        "-cl", "--check-loudness", action="store_true", help="Check current loudness levels"
    )
    parser.add_argument(
        "-n", "--normalize", action="store_true", help="Re-encodes audio of files to normalize loudness"
    )
    parser.add_argument(
        "-c", "--cuts", type=int, help="Split each video into segments of the specified length in seconds"
    )
    parser.add_argument(
        "-re", "--re-encode", action="store_true", help="Re-encode both video and audio stream to sensible defaults"
    )
    parser.add_argument(
        "-cf", "--clear-first", action="store_true", help="Clear target folder first"
    )
    parser.add_argument(
        "-dr", "--dry-run", action="store_true", help="Print ffmpeg commands without executing them."
    )
    args = parser.parse_args()
    return args


if __name__ == "__main__":
    envs = dotenv_values()
    args = get_args()
    conv = Converter(envs=envs, args=args)
    if conv.args.check_loudness:
        conv.get_loudnorm_summary()
    if conv.args.normalize:
        conv.normalize_loudness()
    if conv.args.cuts:
        conv.create_cuts()
