import argparse
import logging

logger = logging.getLogger(__name__)

def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "download",
        help="Download a GoAnimate video via the GoAPI.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--endpoint",
        help="The API endpoint to use for downloading the video.",
    )
    
    parser.add_argument(
        "-id",
        "--video-id",
        help="The ID of the GoAnimate video to download.",
        required=True,
    )

    parser.add_argument(
        "-uid",
        "--user-id",
        help="The user ID of the GoAnimate video to download.",
        required=True,
    )

def entry(args: argparse.Namespace) -> int:
    raise NotImplementedError("The download command is not yet implemented.")