from argparse import Namespace
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch, call

from conv import Converter, ConverterError, FileBatchInfo
from command_templates import DEFAULT_COPY_OPTS


class CompletedProcessStub:
    def __init__(self, stdout=None, stderr=None):
        self.stdout = stdout
        self.stderr = stderr


class FileStub:
    def __init__(self, name):
        self.name = name

    def is_file(self):
        return True


class TestConvert(unittest.TestCase):
    def setUp(self):
        self.path_exists_patcher = patch("pathlib.Path.exists")
        self.path_exists = self.path_exists_patcher.start()
        self.path_exists.return_value = True
        self.subprocess_patcher = patch("subprocess.run")
        self.subprocess_run_patch = self.subprocess_patcher.start()
        self.default_env = {
            "SOURCE": "/home/user/Videos",
            "TARGET": "/home/user/Videos/done"
        }
        self.default_ns = Namespace(
            lufs=-16,
            pattern="test",
            check_loudness=False,
            normalize=False,
            cuts=10,
            re_encode=False,
            text="",
            clear_first=False,
            dry_run=False
        )
        self.converter = Converter(self.default_env, self.default_ns)
        self.addCleanup(self.path_exists.stop)
        self.addCleanup(self.subprocess_patcher.stop)

    def test_set_source_path_raises_error(self):
        with self.assertRaises(SystemExit) as cm:
            Converter({}, Namespace())
        self.assertEqual(cm.exception.code, 1)

        self.path_exists.return_value = False
        envs = {"SOURCE": "/no/folder/like/this"}
        with self.assertRaises(SystemExit) as cm:
            Converter(envs, self.default_ns)
        self.assertEqual(cm.exception.code, 1)

    def test_paths_are_set_correctly(self):
        self.assertEqual(self.converter.source_path, "/home/user/Videos")
        self.assertEqual(self.converter.target_path, "/home/user/Videos/done")

    def test_pattern_normalized_based_on_pattern(self):
        setattr(self.default_ns, "pattern", "")
        converter = Converter(self.default_env, self.default_ns)
        self.assertEqual(converter.pattern, "*.mp4")

        self.assertEqual(self.converter.pattern, "*test*.mp4")

    @patch("pathlib.Path.mkdir")
    def test_paths_are_set_correctly_with_creating_target_folder_if_needed(self, mock_make):
        self.path_exists.side_effect = [True, False]
        mock_make.return_value = True
        conv = Converter(self.default_env, self.default_ns)
        self.assertEqual(conv.source_path, "/home/user/Videos")
        self.assertEqual(conv.target_path, "/home/user/Videos/done")
        mock_make.assert_called_once_with()

    def test_normalizing_pattern(self):
        for pattern, normalized in zip(("", "artist_name"), ("*.mp4", "*artist_name*.mp4")):
            with self.subTest(pattern=pattern, normalized=normalized):
                setattr(self.default_ns, "pattern", pattern)
                conv = Converter(self.default_env, self.default_ns)
                self.assertEqual(conv.pattern, normalized)

    @patch("pathlib.Path.glob")
    def test_clear_target_directory_logs_would_be_deleted_count_in_dry_run(self, mock_glob):
        mock_glob.return_value = self._yield_next_path()
        converter = Converter(self.default_env, Namespace(clear_first=True, dry_run=True, pattern=""))
        with self.assertLogs(level="INFO") as cm:
            converter.clear_target_directory()
        self.assertEqual(cm.records[0].message, "Would delete 2# files from target folder with pattern *.mp4")

    @patch("pathlib.Path.unlink")
    @patch("pathlib.Path.glob")
    def test_clear_target_directory(self, mock_glob, mock_unlink):
        self.assertIsNone(self.converter.clear_target_directory())
        self.assertEqual(mock_unlink.call_count, 0)

        mock_glob.return_value = self._yield_next_path()
        converter = Converter(self.default_env, Namespace(clear_first=True, dry_run=False, pattern=""))
        with self.assertLogs(level="INFO") as cm:
            converter.clear_target_directory()
        self.assertEqual(mock_unlink.call_count, 2)
        self.assertEqual(cm.records[0].message, "Deleted 2# files from target folder with pattern *.mp4")

    def test_calculating_segments(self):
        segment_map = [
            {
                "duration": 106,
                "expected": 10,
            },
            {
                "duration": 107,
                "expected": 11,
            },
            {
                "duration": 108,
                "expected": 11,
            },
            {
                "duration": 109,
                "expected": 11,
            }
        ]
        for media in segment_map:
            with self.subTest(original=media['duration'], expected=media['expected']):
                segment = self.converter.calculate_segments(media['duration'])
                self.assertEqual(segment, media['expected'])

    def test_sanitize_file_name(self):
        fns = [
            "vlc-record-2025-12-26-17h50m10s-test.mp4-.mp4",
            "has space  in it.mp4",
            "has.dot.in.it.mp4",
            "has_few_underscores.mp4",
            "has_index_with_leading_underscore_001.mp4",
            "has_index002.mp4",
        ]

        expected = [
            "test",
            "has_space_in_it",
            "has_dot_in_it",
            "has_few_underscores",
            "has_index_with_leading_underscore",
            "has_index",
        ]
        for original, expected in zip(fns, expected):
            with self.subTest(original=original, expected=expected):
                cov = Converter(self.default_env, self.default_ns)
                got = cov.sanitize_file_name(original)
                self.assertEqual(got, expected)

    def test_construct_command_from_template(self):
        template = ["ffmpeg", "-i", "{filename}", "{param_1}",  "{param_2}"]
        command_kwargs = {
            "filename": "/test/media/file.mp3",
            "param_1": "-my-opt-1",
            "param_2": "-my-opt-2",
        }
        command = self.converter.construct_command(template, **command_kwargs)
        expected_command = ["ffmpeg", "-i", "/test/media/file.mp3", "-my-opt-1",  "-my-opt-2"]
        self.assertEqual(command, expected_command)

    def test_construct_command_from_template_can_handle_spaces(self):
        template = ["ffmpeg", "-i", "{filename}", "{param_1}",  "{param_2}"]
        command_kwargs = {
            "filename": "/test/media/my file.mp3",
            "param_1": "-my-opt-1",
            "param_2": "-my-opt-2",
        }
        command = self.converter.construct_command(template, **command_kwargs)
        expected_command = ["ffmpeg", "-i", "/test/media/my file.mp3", "-my-opt-1",  "-my-opt-2"]
        self.assertEqual(command, expected_command)

    def test_construct_command_from_template_can_handle_options_param(self):
        template = ["ffmpeg", "-i", "{filename}", "{opts}"]
        command_kwargs = {
            "filename": "/test/media/my_file.mp3",
            "opts": DEFAULT_COPY_OPTS
        }
        command = self.converter.construct_command(template, **command_kwargs)
        expected_command = ["ffmpeg", "-i", "/test/media/my_file.mp3", "-c",  "copy"]
        self.assertEqual(command, expected_command)

    def test_construct_command_from_template_raises_error_if_any_key_missing(self):
        template = ["ffmpeg", "-i", "{filename}", "{param_1}",  "{param_2}"]
        command_kwargs = {
            "filename": "/test/media/file.mp3",
            "param_2": "-my-opt-2"
        }
        with self.assertLogs(level="ERROR") as cm:
            with self.assertRaises(KeyError):
                self.converter.construct_command(template, **command_kwargs)
        self.assertEqual(cm.records[0].message, f"Key(s) ('param_1',) missing from {template}")

    def test_get_loudnorm_summary(self):
        fp = Path("/home/user/Videos/my_video.mp4")
        self.subprocess_run_patch.return_value = CompletedProcessStub(stderr=self._get_example_output())
        self.converter.get_loudnorm_summary(media_file=fp)
        expected_args = [
            "ffmpeg",
            "-i",
            fp.as_posix(),
            "-af",
            f"loudnorm=I={self.converter.args.lufs}:TP=-1.5:LRA=11:print_format=json",
            "-f",
            "null",
            "-"
        ]
        self.subprocess_run_patch.assert_called_once_with(
            expected_args,
            check=True,
            capture_output=True,
            text=True
        )

    def test_get_loudnorm_summary_returns_none_in_dry_run_mode(self):
        fp = Path("/home/user/Videos/my_video.mp4")
        setattr(self.default_ns, "dry_run", True)
        converter = Converter(self.default_env, self.default_ns)
        self.assertIsNone(converter.get_loudnorm_summary(fp))

    def test_extracting_audio_bitrate(self):
        fp = Path("/home/user/Videos/my_video.mp4")
        self.converter.extract_metadata(datapoint="audio_bitrate", file_object=fp)
        expected_args = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=bit_rate",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            fp.as_posix()
        ]
        self.subprocess_run_patch.assert_called_once_with(
            expected_args,
            check=True,
            capture_output=True,
            text=True
        )

    def test_extract_duration(self):
        fp = Path("/home/user/Videos/my_video.mp4")
        self.converter.extract_metadata(datapoint="duration", file_object=fp)
        expected_args = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            fp.as_posix()
        ]
        self.subprocess_run_patch.assert_called_once_with(
            expected_args,
            check=True,
            capture_output=True,
            text=True
        )

    def test_extract_metadata_returns_none_in_dry_run_mode(self):
        fp = Path("/home/user/Videos/my_video.mp4")
        setattr(self.default_ns, "dry_run", True)
        converter = Converter(self.default_env, self.default_ns)
        self.assertIsNone(converter.extract_metadata(datapoint="audio_bitrate", file_object=fp))

    def test_get_new_file_name(self):
        fn_base = "my_track"
        lufs_target = -23.0
        index = 2
        new_file_name = self.converter.get_new_file_name(fn_base, lufs_target, index)
        self.assertEqual(new_file_name, "my_track_lufs-23_002.mp4")

    def test_parsing_loudnorm_summary(self):
        summary = self._get_example_output()
        result = self.converter.parse_loudnorm_summary(summary)
        expected = {
            "input_i": -44.98,
            "input_tp": -26.88,
            "input_lra": 4.00,
            "input_thresh": -55.76,
            "output_i": -15.61,
            "output_tp": -1.50,
            "output_lra": 4.40,
            "output_thresh": -27.58,
            "normalization_type": "dynamic",
            "target_offset": -0.39
        }
        self.assertEqual(result, expected)

    def test_creating_file_map(self):
        media_audio_bitrate = CompletedProcessStub(stdout="192000")
        self.subprocess_run_patch.return_value = media_audio_bitrate
        with patch("pathlib.Path.glob") as mock_glob:
            mock_glob.return_value = self._yield_next_path()
            file_map = self.converter.create_file_map()
        print(file_map)
        self.assertIn("my_vid", file_map)
        media_data = file_map["my_vid"]
        self.assertEqual(media_data["count"], 2)
        self.assertEqual(media_data["audio_bitrate"], 192000)
        self.assertEqual(media_data["target_lufs"], -16)

    def test_processing_audio_logs_start_and_end_of_processing(self):
        stem = "my_media"
        file_map: dict[str, FileBatchInfo] = self._get_file_batch_info_stub(stem, 2)
        with self.assertLogs(level="INFO") as cm:
            self.converter.processing_audio(file_map=file_map)
        self.assertTrue(file_map[stem]['done'])
        self.assertEqual(len(cm.records), 2)
        self.assertEqual(cm.records[0].message, f"Processing audio: {stem}")
        self.assertEqual(cm.records[1].message, "Processing done")

    def test_processing_audio_loudnorm_summary(self):
        setattr(self.default_ns, "check_loudness", True)
        converter = Converter(self.default_env, self.default_ns)
        stem = "my_media"
        file_map: dict[str, FileBatchInfo] = self._get_file_batch_info_stub(stem, 2)
        self.subprocess_run_patch.return_value = CompletedProcessStub(stderr=self._get_example_output())
        converter.processing_audio(file_map=file_map)
        self.assertEqual(self.subprocess_run_patch.call_count, 2)
        self.assertTrue(file_map['my_media']['done'])

    def test_processing_audio_normalize(self):
        setattr(self.default_ns, "normalize", True)
        converter = Converter(self.default_env, self.default_ns)
        stem = "my_fav"
        file_map: dict[str, FileBatchInfo] = self._get_file_batch_info_stub(stem, 2)
        converter.processing_audio(file_map=file_map)
        self.assertEqual(self.subprocess_run_patch.call_count, 2)
        expected_calls = [
            call([
                "ffmpeg", "-y", "-i",
                f"{file_map[stem]['original_files'][0]}",
                "-c:v", "copy", "-af",
                "loudnorm=I=-16:TP=-1.5:LRA=5:linear=true",
                "-c:a", "aac", "-b:a",
                f"{file_map[stem]['audio_bitrate']}",
                f"{file_map[stem]['new_files'][0]}",
            ], check=True, capture_output=True, text=True),
            call([
                "ffmpeg", "-y", "-i",
                f"{file_map[stem]['original_files'][1]}",
                "-c:v", "copy", "-af",
                "loudnorm=I=-16:TP=-1.5:LRA=5:linear=true",
                "-c:a", "aac", "-b:a",
                f"{file_map[stem]['audio_bitrate']}",
                f"{file_map[stem]['new_files'][1]}",
            ], check=True, capture_output=True, text=True)
        ]
        self.subprocess_run_patch.assert_has_calls(expected_calls)
        self.assertTrue(file_map[stem]['done'])

    def test_creating_file_cut_map(self):
        vid_1_duration = CompletedProcessStub(stdout="60.5")
        vid_2_duration = CompletedProcessStub(stdout="70.5")

        self.subprocess_run_patch.side_effect = [vid_1_duration, vid_2_duration]
        with patch("pathlib.Path.glob") as mock_glob:
            mock_glob.return_value = self._yield_next_path()
            file_cut_map = self.converter.create_file_cut_map()
        self.assertIn("/home/Videos/my_vid_001.mp4", file_cut_map)
        self.assertIn("/home/Videos/my_vid_002.mp4", file_cut_map)

        media_data_1 = file_cut_map["/home/Videos/my_vid_001.mp4"]
        self.assertEqual(media_data_1, {
            'stem_index': 1,
            'fn_base': Path('/home/user/Videos/done/my_vid-1'),
            'duration': 60.5,
            'segments': 6,
            'done': False
        })
        media_data_2 = file_cut_map["/home/Videos/my_vid_002.mp4"]
        self.assertEqual(media_data_2, {
            'stem_index': 2,
            'fn_base': Path('/home/user/Videos/done/my_vid-2'),
            'duration': 70.5,
            'segments': 7,
            'done': False
        })

    def test_create_cuts_sets_status_done_and_logs_start_and_end_of_processing(self):
        stem = "my_media"
        setattr(self.default_ns, "cuts", 90)
        converter = Converter(self.default_env, self.default_ns)
        original_files, file_map = self._get_file_cut_info_stub(stem, 2)
        with self.assertLogs(level="INFO") as cm:
            converter.create_cuts(file_map=file_map)
        self.assertEqual(len(cm.records), 8)
        self.assertTrue(file_map[original_files[0]]['done'])
        self.assertTrue(file_map[original_files[1]]['done'])
        self.assertEqual(cm.records[0].message, f"Processing: {original_files[0]}")
        self.assertEqual(cm.records[1].message, "Cut #0 - current_ss: 0")
        self.assertEqual(cm.records[2].message, "Cut #1 - current_ss: 90")
        self.assertEqual(cm.records[3].message, "Processing done")
        self.assertEqual(cm.records[4].message, f"Processing: {original_files[1]}")
        self.assertEqual(cm.records[5].message, "Cut #0 - current_ss: 0")
        self.assertEqual(cm.records[6].message, "Cut #1 - current_ss: 90")
        self.assertEqual(cm.records[7].message, "Processing done")

    def test_create_cuts_produces_required_segments_without_re_encoding(self):
        setattr(self.default_ns, "cuts", 90)
        converter = Converter(self.default_env, self.default_ns)
        original_files, file_map = self._get_file_cut_info_stub("my_vid", num=2)
        converter.create_cuts(file_map)
        expected_files = [
            "/home/Videos/my_vid-000-000.mp4",
            "/home/Videos/my_vid-000-001.mp4",
            "/home/Videos/my_vid-001-000.mp4",
            "/home/Videos/my_vid-001-001.mp4",
        ]
        self.assertEqual(self.subprocess_run_patch.call_count, 4)
        expected_calls = [
            call([
                "ffmpeg", "-y", "-ss", "0", "-t", "90",
                "-i", original_files[0],
                "-c", "copy", expected_files[0],
            ], check=True, capture_output=True, text=True),
            call([
                "ffmpeg", "-y", "-ss", "90", "-t", "90",
                "-i", original_files[0],
                "-c", "copy", expected_files[1],
            ], check=True, capture_output=True, text=True),
            call([
                "ffmpeg", "-y", "-ss", "0", "-t", "90",
                "-i", original_files[1],
                "-c", "copy", expected_files[2],
            ], check=True, capture_output=True, text=True),
            call([
                "ffmpeg", "-y", "-ss", "90", "-t", "90",
                "-i", original_files[1],
                "-c", "copy", expected_files[3],
            ], check=True, capture_output=True, text=True),
        ]
        self.subprocess_run_patch.assert_has_calls(expected_calls)

    def test_create_cuts_produces_required_segments_with_re_encoding(self):
        setattr(self.default_ns, "cuts", 90)
        setattr(self.default_ns, "re_encode", True)
        converter = Converter(self.default_env, self.default_ns)
        original_files, file_map = self._get_file_cut_info_stub("my_vid", num=1)
        converter.create_cuts(file_map)
        expected_files = [
            "/home/Videos/my_vid-000-000.mp4",
            "/home/Videos/my_vid-000-001.mp4",
        ]
        self.assertEqual(self.subprocess_run_patch.call_count, 2)
        expected_calls = [
            call([
                "ffmpeg", "-y", "-ss", "0", "-t", "90",
                "-i", original_files[0],
                "-vf", "scale=1280:720,fps=30",
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                "-ac", "2", "-af", "loudnorm=I=-16:TP=-1.5:LRA=5:linear=true",
                expected_files[0],
            ], check=True, capture_output=True, text=True),
            call([
                "ffmpeg", "-y", "-ss", "90", "-t", "90",
                "-i", original_files[0],
                "-vf", "scale=1280:720,fps=30",
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                "-ac", "2", "-af", "loudnorm=I=-16:TP=-1.5:LRA=5:linear=true",
                expected_files[1]
            ], check=True, capture_output=True, text=True),
        ]
        self.subprocess_run_patch.assert_has_calls(expected_calls)

    def test_run_command_raises_when_command_results_in_called_process_error(self):
        command = ["testing", "error", "handling"]
        self.subprocess_run_patch.side_effect = subprocess.CalledProcessError(1, cmd=command, stderr="simulated error")
        with self.assertRaises(ConverterError) as cm:
            self.converter._run_command(command)
        self.assertEqual(str(cm.exception), f"Error running: {command}: simulated error")

    @staticmethod
    def _get_file_batch_info_stub(stem: str, num: int) -> dict[str, FileBatchInfo]:
        original_files = [Path(f"/home/Videos/{stem}_{i:03d}.mp4") for i in range(num)]
        new_files = [Path(f"/home/Videos/{stem}_lufs-16_{i:03d}.mp4") for i in range(num)]
        return {
            stem: {
                "count": 2,
                "audio_bitrate": 19200,
                "original_files": original_files,
                "new_files": new_files,
                "target_lufs": -16,
                "done": False
            }
        }

    @staticmethod
    def _get_file_cut_info_stub(stem: str, num: int) -> dict[str, FileBatchInfo]:
        file_map = {}
        original_files = [f"/home/Videos/{stem}_{i:03d}.mp4" for i in range(num)]
        for i, file in enumerate(original_files):
            file_map[file] = {
                "stem_index": i,
                "fn_base": Path(f"/home/Videos/{stem}-{i:03d}"),
                "duration": 180,
                "segments": 2
            }

        return original_files, file_map

    @staticmethod
    def _yield_next_path():
        return (Path(i) for i in ["/home/Videos/my_vid_001.mp4", "/home/Videos/my_vid_002.mp4"])

    @staticmethod
    def _get_example_output():
        output = """
ffmpeg version n8.0.1 Copyright (c) 2000-2025 the FFmpeg developers
built with gcc 15.2.1 (GCC) 20251112
configuration: --prefix=/usr --disable-debug --disable-static --disable-stripping --enable-amf --enable-avisynth --enable-cuda-llvm --enable-lto --enable-fontconfig --enable-frei0r --enable-gmp --enable-gnutls --enable-gpl --enable-ladspa --enable-libaom --enable-libass --enable-libbluray --enable-libbs2b --enable-libdav1d --enable-libdrm --enable-libdvdnav --enable-libdvdread --enable-libfreetype --enable-libfribidi --enable-libglslang --enable-libgsm --enable-libharfbuzz --enable-libiec61883 --enable-libjack --enable-libjxl --enable-libmodplug --enable-libmp3lame --enable-libopencore_amrnb --enable-libopencore_amrwb --enable-libopenjpeg --enable-libopenmpt --enable-libopus --enable-libplacebo --enable-libpulse --enable-librav1e --enable-librsvg --enable-librubberband --enable-libsnappy --enable-libsoxr --enable-libspeex --enable-libsrt --enable-libssh --enable-libsvtav1 --enable-libtheora --enable-libv4l2 --enable-libvidstab --enable-libvmaf --enable-libvorbis --enable-libvpl --enable-libvpx --enable-libwebp --enable-libx264 --enable-libx265 --enable-libxcb --enable-libxml2 --enable-libxvid --enable-libzimg --enable-libzmq --enable-nvdec --enable-nvenc --enable-opencl --enable-opengl --enable-shared --enable-vapoursynth --enable-version3 --enable-vulkan
libavutil      60.  8.100 / 60.  8.100
libavcodec     62. 11.100 / 62. 11.100
libavformat    62.  3.100 / 62.  3.100
libavdevice    62.  1.100 / 62.  1.100
libavfilter    11.  4.100 / 11.  4.100
libswscale      9.  1.100 /  9.  1.100
libswresample   6.  1.100 /  6.  1.100
Input #0, mov,mp4,m4a,3gp,3g2,mj2, from \'/home/daniel/Videos/test.mp4\':
Metadata:
major_brand     : isom
minor_version   : 0
compatible_brands: mp41avc1
creation_time   : 2024-12-03T11:12:15.000000Z
playback_requirements: QuickTime 6.0 or greater
playback_requirements-eng: QuickTime 6.0 or greater
encoder         : vlc 3.0.21 stream output
encoder-eng     : vlc 3.0.21 stream output
Duration: 00:00:06.87, start: 0.000000, bitrate: 4437 kb/s
Stream #0:0[0x1](eng): Audio: aac(LC) (mp4a / 0x6134706D), 48000 Hz, stereo, fltp, 113 kb/s, start 0.019333 (default)    Metadata:
creation_time   : 2024-12-03T11:12:15.000000Z
handler_name    : SoundHandler
vendor_id       : [0][0][0][0]
Stream #0:1[0x2](eng): Video: h264 (Constrained Baseline) (avc1 / 0x31637661), yuv420p(progressive), 1920x1080, 4313 kb/s, 29.97 fps, 29.97 tbr, 299700 tbn (default)
Metadata:
creation_time   : 2024-12-03T11:12:15.000000Z
handler_name    : VideoHandler
vendor_id       : [0][0][0][0]
Stream mapping:
Stream #0:1 -> #0:0 (h264 (native) -> wrapped_avframe (native))
Stream #0:0 -> #0:1 (aac (native) -> pcm_s16le (native))
Press [q] to stop, [?] for help
Output #0, null, to \'pipe:\':
Metadata:
major_brand     : isom
minor_version   : 0
compatible_brands: mp41avc1
encoder         : Lavf62.3.100
playback_requirements: QuickTime 6.0 or greater
playback_requirements-eng: QuickTime 6.0 or greater
Stream #0:0(eng): Video: wrapped_avframe, yuv420p(progressive), 1920x1080, q=2-31, 200 kb/s, 29.97 fps, 29.97 tbn (default)
Metadata:
encoder         : Lavc62.11.100 wrapped_avframe
creation_time   : 2024-12-03T11:12:15.000000Z
handler_name    : VideoHandler
vendor_id       : [0][0][0][0]
Stream #0:1(eng): Audio: pcm_s16le, 192000 Hz, stereo, s16, 6144 kb/s (default)
Metadata:
encoder         : Lavc62.11.100 pcm_s16le
creation_time   : 2024-12-03T11:12:15.000000Z
handler_name    : SoundHandler
vendor_id       : [0][0][0][0]
frame=  170 fps=0.0 q=-0.0 size=N/A time=00:00:03.01 bitrate=N/A speed=6.04x elapsed=0:00:00.50
[Parsed_loudnorm_0 @ 0x7f5b34002bc0]
{
    "input_i" : "-44.98",
    "input_tp" : "-26.88",
    "input_lra" : "4.00",
    "input_thresh" : "-55.76",
    "output_i" : "-15.61",
    "output_tp" : "-1.50",
    "output_lra" : "4.40",
    "output_thresh" : "-27.58",
    "normalization_type" : "dynamic",
    "target_offset" : "-0.39"
}
[out#0/null @ 0x55ae5a9c7f80] video:84KiB audio:5120KiB subtitle:0KiB other streams:0KiB global headers:0KiB muxing overhead: unknown
frame=  206 fps=0.0 q=-0.0 Lsize=N/A time=00:00:06.87 bitrate=N/A speed=  11x elapsed=0:00:00.62
"""
        return output
