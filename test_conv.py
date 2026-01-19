from argparse import Namespace
import unittest
from unittest.mock import patch

from conv import Converter


class TestConvert(unittest.TestCase):
    def setUp(self):
        self.path_exists_pather = patch("pathlib.Path.exists")
        self.path_exists = self.path_exists_pather.start()
        self.path_exists.return_value = True
        self.default_env = {
            "SOURCE": "/home/user/Videos",
            "TARGET": "/home/user/Videos/done"
        }
        self.default_ns = Namespace(
            lufs="-16",
            pattern="test",
            check_loudness=False,
            normalize=False,
            cuts=10,
            re_encode=False,
            clear_first=False,
            dry_run=False
        )
        self.converter = Converter(self.default_env, self.default_ns)
        self.addCleanup(self.path_exists.stop)

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
