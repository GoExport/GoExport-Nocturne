from pathlib import Path
import subprocess
import logging

from goexport.models.audio_clip import AudioClip
from goexport.services.asset_resolver import AssetResolver

logger = logging.getLogger(__name__)

class FFmpegVideoEncoder:
    def __init__(
        self,
        ffmpeg_path: str,
        output_file: str,
        fps: int = 24,
    ):
        self.process = subprocess.Popen(
            [
                ffmpeg_path,
                "-y",
                "-f", "image2pipe",
                "-framerate", str(fps),
                "-vcodec", "png",
                "-i", "-",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-crf", "18",
                "-preset", "medium",
                output_file,
            ],
            stdin=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )

    def write_frame(self, png_bytes):
        self.process.stdin.write(png_bytes)

    def close(self):
        self.process.stdin.close()
        self.process.wait()

class FFmpegAudioEncoder:
    def __init__(
        self,
        ffmpeg_path: Path,
        resolver: AssetResolver,
        fps: int = 24,
        audio_offset_frames: int = 2,
    ):
        self.ffmpeg_path = ffmpeg_path
        self.resolver = resolver
        self.fps = fps
        self.audio_offset_frames = audio_offset_frames

    def encode(
        self,
        clips: list[AudioClip],
        output_file: Path,
        frame_count: int,
    ) -> None:
        movie_duration = frame_count / self.fps

        if not clips:
            # Keep muxing stable by emitting a silent track when no clips exist.
            command = [
                str(self.ffmpeg_path),
                "-y",
                "-f", "lavfi",
                "-i", "anullsrc=r=44100:cl=stereo",
                "-t", f"{max(movie_duration, 0):.6f}",
                "-c:a", "pcm_s16le",
                str(output_file),
            ]

            logger.info(
                "No audio clips found; generating silent track (%s seconds)",
                f"{max(movie_duration, 0):.6f}",
            )
            logger.info("FFmpeg command: %s", " ".join(command))

            subprocess.run(
                command,
                check=True,
            )
            return

        command = [
            str(self.ffmpeg_path),
            "-y",
        ]

        filters = []
        mix_inputs = []

        offset_ms = round(
            self.audio_offset_frames * 1000 / self.fps
        )

        for index, clip in enumerate(clips):
            command.extend([
                "-i",
                str(
                    self.resolver.resolve(
                        clip.asset_id,
                    )
                ),
            ])

            delay = round(
                (clip.start_frame - 1) * 1000 / self.fps
            )

            if clip.has_trim:
                trim_start = (
                    clip.trim_start_frame / self.fps
                )

                trim_end = min(
                    clip.trim_end_frame,
                    clip.trim_start_frame
                    + clip.duration_frames,
                ) / self.fps

                filter_chain = (
                    f"[{index}:a]"
                    f"atrim=start={trim_start:.6f}:"
                    f"end={trim_end:.6f},"
                    f"adelay={delay}|{delay}"
                    f"[a{index}]"
                )
            else:
                clip_duration = (
                    clip.duration_frames / self.fps
                )

                filter_chain = (
                    f"[{index}:a]"
                    f"atrim=end={clip_duration:.6f},"
                    f"adelay={delay}|{delay}"
                    f"[a{index}]"
                )

            filters.append(filter_chain)
            mix_inputs.append(f"[a{index}]")

        filters.append(
            "".join(mix_inputs)
            + (
                f"amix=inputs={len(clips)}:normalize=0,"
                f"adelay={offset_ms}|{offset_ms},"
                f"atrim=end={movie_duration:.6f}"
            )
        )

        command.extend([
            "-filter_complex",
            ";".join(filters),
            "-c:a",
            "pcm_s16le",
            str(output_file),
        ])

        logger.info("FFmpeg command: %s", " ".join(command))

        subprocess.run(
            command,
            check=True,
        )

class FFmpegMuxer:
    def __init__(self, ffmpeg_path: Path):
        self.ffmpeg_path = ffmpeg_path

    def mux(
        self,
        video_file: Path,
        audio_file: Path,
        output_file: Path,
    ) -> None:
        subprocess.run(
            [
                str(self.ffmpeg_path),
                "-y",
                "-i", str(video_file),
                "-i", str(audio_file),
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                str(output_file),
            ],
            check=True,
        )

        # Clean up temporary files
        video_file.unlink(missing_ok=True)
        audio_file.unlink(missing_ok=True)

    def append_outro(
        self,
        main_video_file: Path,
        outro_file: Path,
        output_file: Path,
        width: int,
        height: int,
    ) -> None:
        if output_file.suffix.lower() == ".gif":
            raise ValueError(
                "Appending an outro with audio is not supported for GIF output. "
                "Use --no-outro or choose a different output format."
            )

        if not main_video_file.is_file():
            raise FileNotFoundError(
                f"Main video file does not exist: {main_video_file}"
            )

        if not outro_file.is_file():
            raise FileNotFoundError(
                f"Outro video file does not exist: {outro_file}"
            )

        temp_output_file = output_file.with_name(
            f"{output_file.stem}.with_outro{output_file.suffix}"
        )

        filter_complex = (
            f"[1:v]"
            f"scale=w={width}:h={height}:force_original_aspect_ratio=decrease,"
            f"pad=w={width}:h={height}:x=(ow-iw)/2:y=(oh-ih)/2:color=black"
            f"[outro_v];"
            f"[0:v][0:a][outro_v][1:a]"
            f"concat=n=2:v=1:a=1[v][a]"
        )

        command = [
            str(self.ffmpeg_path),
            "-y",
            "-i", str(main_video_file),
            "-i", str(outro_file),
            "-filter_complex", filter_complex,
            "-map", "[v]",
            "-map", "[a]",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            str(temp_output_file),
        ]

        logger.info("FFmpeg command: %s", " ".join(command))

        subprocess.run(
            command,
            check=True,
        )

        temp_output_file.replace(output_file)