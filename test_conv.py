import unittest

from conv import parse_loudnorm_summary


class TestConver(unittest.TestCase):
    def test_parse(self):
        summary = self._get_example_output()
        result = parse_loudnorm_summary(summary)
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
