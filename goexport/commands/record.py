import argparse
import logging
from pathlib import Path

from goexport import config
from goexport.helpers import (
    parse_resolution,
    resolve_output_path,
)
from goexport.services.browser import BrowserService
from goexport.services.flash import await_started
from goexport.services.recorder import Recorder

logger = logging.getLogger(__name__)


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "record",
        help="Export a video with the WYSIWYG screen-recording pipeline.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.set_defaults(func=entry)


def entry(args: argparse.Namespace) -> int:
    return 0