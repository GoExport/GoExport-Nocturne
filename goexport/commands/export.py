import argparse
import logging
from pathlib import Path

from goexport import config
from goexport.helpers import (
    existing_directory,
    existing_file,
    parse_resolution,
    resolve_output_path,
)

from goexport.services.asset_resolver import AssetResolver
from goexport.services.browser import BrowserService
from goexport.services.flash import await_started
from goexport.services.ffmpeg import FFmpegAudioEncoder, FFmpegMuxer, FFmpegVideoEncoder
from goexport.services.renderer import Renderer
from goexport.services.audio import AudioProcessor
from goexport.services.timeline_builder import TimelineBuilder

logger = logging.getLogger(__name__)


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "export",
        help="Export a GoAnimate video.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "-r",
        "--resolution",
        type=parse_resolution,
        default=(
            config.WIDTH,
            config.HEIGHT,
        ),
        help="Resolution of the exported video (e.g., 1920x1080).",
    )

    parser.add_argument(
        "--skip-screen-resolution-check",
        action="store_false",
        dest="check_screen_resolution",
        help="Skip validating that selected resolution fits the display.",
    )

    parser.add_argument(
        "--skip-frame-resolution-check",
        action="store_false",
        dest="check_frame_resolution",
        help="Skip validating viewport resolution before each captured frame.",
    )

    parser.add_argument(
        "--no-wide",
        action="store_false",
        dest="is_wide",
        help="Disable GoAnimate widescreen mode.",
    )

    parser.add_argument(
        "-u",
        "--url",
        default=config.URL,
        help="The URL of the Wrapper: Offline instance.",
    )

    parser.add_argument(
        "-api",
        "--api-url",
        default=config.API_URL,
        help="The URL of the Wrapper: Offline API instance.",
    )

    parser.add_argument(
        "-swf",
        "--swf-url",
        default=config.SWF_URL,
        help="The URL of the SWF file to be used in the export.",
    )

    parser.add_argument(
        "-store",
        "--store-path",
        default=config.STORE_PATH,
        help="The URL of the store path to be used in the export.",
    )

    parser.add_argument(
        "-theme",
        "--client-theme-path",
        default=config.CLIENT_THEME_PATH,
        help="The URL of the client theme path to be used in the export.",
    )

    parser.add_argument(
        "-id",
        "--movie-id",
        help="The ID of the movie to be exported.",
        required=True
    )

    parser.add_argument(
        "-uid",
        "--user-id",
        help="The ID of the user associated with the movie.",
    )

    parser.add_argument(
        "-xml",
        "--movie-xml",
        type=existing_file,
        help="The path to the movie XML file.",
        required=True
    )

    parser.add_argument(
        "-ugc",
        "--ugc-path",
        type=existing_directory,
        help="The path to the folder containing UGC assets.",
        required=True
    )

    parser.add_argument(
        "-as",
        "--assets",
        type=existing_directory,
        help="The path to the folder containing theme assets (The files located inside of 3a981f5cb2739137).",
        required=True
    )

    parser.add_argument(
        "-f",
        "--format",
        choices=sorted(config.SUPPORTED_FORMATS),
        default=config.OUTPUT_FORMAT,
        help="Format of the exported video.",
    )

    parser.add_argument(
        "-out",
        "--output",
        type=Path,
        default=Path("final_output"),
        help="Output video filename (default: final_output)",
    )

    parser.set_defaults(
        func=entry,
        is_wide=True,
        check_screen_resolution=True,
        check_frame_resolution=True,
    )


def entry(args: argparse.Namespace) -> int:
    return export_video(args)


def export_video(args: argparse.Namespace) -> int:
    final_output_path = resolve_output_path(
        Path(args.output),
        args.format,
    )

    # Start the video encoder
    encoder = FFmpegVideoEncoder(
        ffmpeg_path=config.FFMPEG_PATH,
        output_file=f"output.{args.format}",
        fps=config.FPS,
    )

    # Start the audio processor
    resolver = AssetResolver(
        args.ugc_path,
        args.assets,
    )

    audio_encoder = FFmpegAudioEncoder(
        ffmpeg_path=config.FFMPEG_PATH,
        resolver=resolver,
        fps=config.FPS,
    )

    muxer = FFmpegMuxer(config.FFMPEG_PATH)

    audio_processor = AudioProcessor(
        audio_encoder,
    )

    if args.movie_xml is None:
        raise FileNotFoundError("No movie XML file was provided.")

    # Start the timeline builder
    timeline_builder = TimelineBuilder(args.movie_xml)

    # Open web browser
    browser_service = BrowserService(
        chrome_path=config.CHROME_PATH,
        chromedriver_path=config.CHROMEDRIVER_PATH,
        flash_path=config.FLASH_PLUGIN_PATH,
        flash_version=config.FLASH_PLUGIN_VERSION,
        width=args.resolution[0],
        height=args.resolution[1],
        check_screen_resolution=args.check_screen_resolution,
        check_frame_resolution=args.check_frame_resolution,
    )

    driver = None

    try:
        driver = browser_service.create_driver()

        driver.get(args.url)

        browser_service.validate_screen_resolution(driver)

        browser_service.set_viewport_size(
            driver,
            args.resolution[0],
            args.resolution[1],
        )

        browser_service.enable_flash(driver)

        browser_service.inject_dom(driver, config.TEMPLATE_HTML_PATH, {
            "PLAYER_WIDTH": args.resolution[0],
            "PLAYER_HEIGHT": args.resolution[1],
            "PLAYER_SWF_URL": args.swf_url,
            "IS_WIDE": int(args.is_wide),
            "API_SERVER": args.api_url,
            "STORE_PATH": args.store_path,
            "CLIENT_THEME_PATH": args.client_theme_path,
            "MOVIE_ID": args.movie_id,
            "USER_ID": args.user_id,
            "MOVIE_XML": str(args.movie_xml),
        })

        await_started(driver)

        # Render video
        renderer = Renderer(
            driver=driver,
            encoder=encoder,
            resolution_guard=browser_service.assert_full_resolution,
        )

        renderer.render()

        timeline = timeline_builder.build()
        audio = audio_processor.process(
            timeline,
            renderer.duration_frames,
        )

        muxer.mux(
            video_file=Path(f"output.{args.format}"),
            audio_file=audio,
            output_file=final_output_path,
        )

    finally:
        if driver is not None:
            driver.quit()

        browser_service.stop_display()
    return 0