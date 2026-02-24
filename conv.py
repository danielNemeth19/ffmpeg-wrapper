import sys
import argparse
import json
import logging
import subprocess
from pathlib import Path
from typing import TypedDict
from collections import OrderedDict

from dotenv import dotenv_values

from command_templates import DURATION_TEMPLATE, AUDIO_BITRATE_TEMPLATE, DEFAULT_RE_ENCODE_OPTS, \
    LOUDNESS_ANALYSIS_TEMPLATE, LOUDNESS_NORMALIZATION_TEMPLATE, CREATE_CUTS_TEMPLATE, DEFAULT_OVERLAY_TEMPLATE


logging.basicConfig(level=logging.INFO)
__logger__ = logging.getLogger("converter")


RED = "\033[31m"
GREEN = "\033[32m"
RESET = "\033[0m"


class ConverterError(Exception):
    pass


class FileBatchInfo(TypedDict):
    count: int
    audio_bitrate: int
    original_files: list[Path]
    new_files: list[str]
    target_lufs: float
    done: bool


class FileCutInfo(TypedDict):
    stem_index: int
    fn_base: Path
    duration: int
    segments: int
    done: bool


class Converter:
    COMMAND_SEPARATOR = "|"

    def __init__(self, envs: OrderedDict[str, str], args: argparse.Namespace):
        self.args = args
        self.source_path = self._set_source_path(envs)
        self.target_path = self._set_target_path(envs)
        self.pattern = self._normalize_pattern()
        self.dry_run = args.dry_run

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

    def clear_target_directory(self) -> None:
        if not self.args.clear_first:
            return
        counter = 0
        for f in Path(self.target_path).glob(self.pattern):
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

    def construct_command(self, template: list, **kwargs):
        opts = kwargs.pop("opts", None)
        if opts:
            kwargs["opts"] = self.COMMAND_SEPARATOR.join(opts)
        temp_command = self.COMMAND_SEPARATOR.join(template)
        try:
            command = temp_command.format(**kwargs)
        except KeyError as exc:
            __logger__.error("Key(s) %s missing from %s", exc.args, template)
            raise
        return command.split(self.COMMAND_SEPARATOR)

    def get_loudnorm_summary(self, media_file):
        params = {
            "filename": media_file.as_posix(),
            "lufs": self.args.lufs
        }
        command = self.construct_command(LOUDNESS_ANALYSIS_TEMPLATE, **params)
        raw_output = self._run_command(command)
        if not raw_output:
            return
        summary = self.parse_loudnorm_summary(raw_output.stderr)
        diff_from_target = summary["input_i"] - self.args.lufs
        hl = GREEN if diff_from_target > 0 else RED
        __logger__.info(
            "current loudness: %.2f - diff from target (%s): %s%.2f%s",
            summary['input_i'], self.args.lufs, hl, diff_from_target, RESET
        )

    def processing_audio(self, file_map: dict[str, FileBatchInfo]):
        for media, media_data in file_map.items():
            __logger__.info("Processing audio: %s", media)
            for infile, outfile in zip(media_data["original_files"], media_data["new_files"]):
                __logger__.info("Processing media: %s", infile.name)
                if self.args.check_loudness:
                    self.get_loudnorm_summary(infile)
                if self.args.normalize:
                    params = {
                        "filename": infile.as_posix(),
                        "lufs": self.args.lufs,
                        "audio_bitrate": media_data['audio_bitrate'],
                        "outfile": outfile
                    }
                    command = self.construct_command(LOUDNESS_NORMALIZATION_TEMPLATE, **params)
                    self._run_command(command)
            media_data['done'] = True
            __logger__.info("Processing done")

    def processing_overlay(self, file_map: dict[str, FileBatchInfo]):
        for media, media_data in file_map.items():
            __logger__.info("Processing overlay: %s", media)
            for infile, outfile in zip(media_data["original_files"], media_data["new_files"]):
                __logger__.info("Processing media: %s", infile.name)
                params = {
                    "filename": infile.as_posix(),
                    "text": self.args.text,
                    "outfile": outfile
                }
                command = self.construct_command(DEFAULT_OVERLAY_TEMPLATE, **params)
                self._run_command(command)
            media_data['done'] = True
            __logger__.info("Processing done")

    def extract_metadata(self, datapoint: str, file_object: Path) -> float | None:
        template = self._get_extract_template(datapoint)
        params = {
            "infile": file_object.as_posix(),
        }
        command = self.construct_command(template, **params)
        raw_metadata = self._run_command(command=command)
        if not raw_metadata:
            return None
        metadata = raw_metadata.stdout.strip()
        __logger__.info("Extracted metadata %s from %s -- %s", datapoint, file_object.as_posix(), metadata)
        return float(metadata)

    @staticmethod
    def _get_extract_template(datapoint: str) -> list:
        command = DURATION_TEMPLATE if datapoint == "duration" else AUDIO_BITRATE_TEMPLATE
        return command

    def create_cuts(self, file_map: dict[str, FileCutInfo]):
        for media, media_data in file_map.items():
            __logger__.info("Processing: %s", media)
            current_ss = 0
            for i in range(media_data['segments']):
                opts = DEFAULT_RE_ENCODE_OPTS if self.args.re_encode else ["-c", "copy"]
                params = {
                    "current_ss": str(current_ss),
                    "cuts": str(self.args.cuts),
                    "filename": media,
                    "opts": opts,
                    "outfile": f"{media_data['fn_base']}-{i:03d}.mp4"
                }
                command = self.construct_command(CREATE_CUTS_TEMPLATE, **params)
                __logger__.info("Cut #%d - current_ss: %d", i, current_ss)
                self._run_command(command)
                current_ss += self.args.cuts
            media_data['done'] = True
            __logger__.info("Processing done")

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

            file_map[item.as_posix()] = {
                'stem_index': stem_index,
                'fn_base': Path(self.target_path, new_stem_base),
                'duration': duration,
                'segments': segments,
                'done': False
            }
        return file_map

    def _run_command(self, command):
        if self.dry_run:
            __logger__.info("Command: %s", command)
            return False
        try:
            raw_data = subprocess.run(command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            raise ConverterError(f"Error running: {command}: {exc.stderr}") from exc
        return raw_data


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
        "-t", "--text", type=str, nargs="?", help="Draws text on media"
    )
    parser.add_argument(
        "-cf", "--clear-first", action="store_true", help="Clear target folder first"
    )
    parser.add_argument(
        "-dr", "--dry-run", action="store_true", help="Print ffmpeg commands without executing them."
    )
    args = parser.parse_args()
    return args


def main():
    envs = dotenv_values()
    args = get_args()
    conv = Converter(envs=envs, args=args)
    conv.clear_target_directory()
    if conv.args.check_loudness or conv.args.normalize:
        file_map = conv.create_file_map()
        conv.processing_audio(file_map)
    if conv.args.text:
        file_map = conv.create_file_map()
        conv.processing_overlay(file_map)
    if conv.args.cuts:
        file_map = conv.create_file_cut_map()
        conv.create_cuts(file_map)


if __name__ == "__main__":
    main()
