from copy import deepcopy
import sys
import argparse
import json
import logging
import subprocess
from pathlib import Path
from typing import TypedDict
from collections import OrderedDict

from dotenv import dotenv_values


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


LOUDNESS_ANALYSIS_TEMPLATE = [
    "ffmpeg",
    "-i",
    "{filename}",
    "-af",
    "loudnorm=I={lufs}:TP=-1.5:LRA=11:print_format=json",
    "-f",
    "null",
    "-"
]

DURATION_OPTS = [
    "ffprobe",
    "-v",
    "error",
    "-show_entries",
    "format=duration",
    "-of",
    "default=noprint_wrappers=1:nokey=1",
]


AUDIO_BITRATE_OPTS = [
    "ffprobe",
    "-v",
    "error",
    "-select_streams",
    "a:0",
    "-show_entries",
    "stream=bit_rate",
    "-of",
    "default=noprint_wrappers=1:nokey=1",
]


class FileBatchInfo(TypedDict):
    count: int
    audio_bitrate: int
    original_files: list[Path]
    new_files: list[str]
    target_lufs: float
    done: bool


class FileCutInfo(TypedDict):
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
                    'audio_bitrate': self.extract_metadata(datapoint="audio_bitrate", file_object=original_fn),
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
        __logger__.info("Found %d unique stems", len(file_map.keys()))
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

    def get_loudnorm_summary(self, media_file):
        __logger__.info("Processing loudness summary for: %s", media_file.as_posix())
        template = deepcopy(LOUDNESS_ANALYSIS_TEMPLATE)
        command = [c.format(filename=media_file.as_posix(), lufs=self.args.lufs) if "{" in c else c for c in template]
        raw_output = self._run_command(command)
        summary = self.parse_loudnorm_summary(raw_output.stderr)
        diff_from_target = summary["input_i"] - self.args.lufs
        __logger__.info(
            "current loudness: %.2f - diff from target (%s): %.2f - projected offset from target: %.2f",
            summary['input_i'], self.args.lufs, diff_from_target, summary["target_offset"]
        )

    def audio_processing(self, file_map: dict[str, FileBatchInfo]):
        for video, video_data in file_map.items():
            __logger__.info("Processing: %s", video)
            for infile, outfile in zip(video_data["original_files"], video_data["new_files"]):
                if self.args.check_loudness:
                    self.get_loudnorm_summary(infile)
                command = [
                    "ffmpeg",
                    "-y",
                    "-i",
                    infile.as_posix(),
                    "-c:v",
                    "copy",
                    "-af",
                    f"loudnorm=I={self.args.lufs}:TP=-1.5:LRA=5:linear=true",
                    "-c:a",
                    "aac",
                    "-b:a",
                    str(video_data["audio_bitrate"]),
                    outfile
                ]
                __logger__.info(command)
                if not self.dry_run:
                    try:
                        subprocess.run(command, text=True, check=True,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                        __logger__.info("%s -> %s converted", infile, outfile)
                    except subprocess.CalledProcessError as exc:
                        __logger__.error("Error converting %s: %s", infile, exc.stderr)
                        video_data['done'] = False
            video_data['done'] = True
            __logger__.info("Setting video data: %s", video_data['done'])

    def extract_metadata(self, datapoint: str, file_object: Path) -> int:
        command = self._get_extract_command(datapoint)
        command.append(file_object.as_posix())
        raw_metadata = self._run_command(command=command)
        metadata = raw_metadata.stdout.strip()
        __logger__.info("Extracted metadata %s from %s -- %s", datapoint, file_object.as_posix(), metadata)
        return float(metadata)

    @staticmethod
    def _get_extract_command(datapoint: str) -> list:
        command = DURATION_OPTS if datapoint == "duration" else AUDIO_BITRATE_OPTS
        return deepcopy(command)

    @staticmethod
    def _run_command(command):
        try:
            raw_data = subprocess.run(command, check=True, capture_output=True, text=True)
            __logger__.debug("Running command %s", command)
        except subprocess.CalledProcessError as exc:
            __logger__.error("Error running: %s: %s", command, exc.stderr)
            raise
        return raw_data

    def create_cuts(self):
        for media, media_data in self.file_map.items():
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

    def calculate_segments(self, duration: int) -> int:
        quotient, remainder = divmod(duration, self.args.cuts)
        if remainder < self.args.cuts * 0.7:
            __logger__.info("Dropping remainder, duration is: %f seconds", remainder)
            return int(quotient)
        return int(quotient + 1)

    def create_file_cut_map(self):
        mapper = {}

        file_map: dict[str, FileCutInfo] = {}
        for item in Path(self.source_path).glob(self.pattern):
            stem = self.sanitize_file_name(item.name)
            stem_index = mapper.get(stem, 0) + 1
            mapper[stem] = stem_index
            new_stem_base = f"{stem}-{stem_index}"
            duration = self.extract_metadata(datapoint="duration", file_object=item)
            __logger__.info("Duration of %s: %f", item.name, duration)
            segments = self.calculate_segments(duration)
            __logger__.info("Will make %d cuts", segments)

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
        description="Batch adjust audio volume, re-encode and cut MP4 files."
    )
    parser.add_argument(
        "-l", "--lufs", type=float, help="Target integrated loudness in LUFS", default=-16
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
    if conv.args.check_loudness or conv.args.normalize:
        file_map = conv.create_file_map()
        conv.audio_processing(file_map)
    # if conv.args.cuts:
        # conv.create_cuts()
