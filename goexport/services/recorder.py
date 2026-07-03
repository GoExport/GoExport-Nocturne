import argparse
import logging

from recap import Recorder, RecordingConfig
from selenium.webdriver.remote.webdriver import WebDriver

from goexport import config
from goexport.services.browser import BrowserService
from goexport.services.flash import await_player_ready, await_started, await_stopped

logger = logging.getLogger(__name__)


class RecordingService:
    def __init__(self, args: argparse.Namespace):
        self.args = args

    def _create_recording_config(self) -> RecordingConfig:
        return RecordingConfig(
            ffmpeg=config.FFMPEG_PATH,
            output=self.args.output.with_suffix(f".{self.args.format}"),
            crop_width=self.args.resolution[0],
            crop_height=self.args.resolution[1],
            crop_position="top-left",
            overwrite=True,
            fps=config.FPS,
        )

    def _create_browser_service(self) -> BrowserService:
        return BrowserService(
            chrome_path=config.CHROME_PATH,
            chromedriver_path=config.CHROMEDRIVER_PATH,
            flash_path=config.FLASH_PLUGIN_PATH,
            flash_version=config.FLASH_PLUGIN_VERSION,
            width=self.args.resolution[0],
            height=self.args.resolution[1],
        )

    def _build_replacements(self) -> dict[str, object]:
        return {
            "PLAYER_WIDTH": self.args.resolution[0],
            "PLAYER_HEIGHT": self.args.resolution[1],
            "PLAYER_SWF_URL": self.args.swf_url,
            "IS_WIDE": int(self.args.is_wide),
            "API_SERVER": self.args.api_url,
            "STORE_PATH": self.args.store_path,
            "CLIENT_THEME_PATH": self.args.client_theme_path,
            "MOVIE_ID": self.args.movie_id,
            "USER_ID": self.args.user_id,
        }

    def run(self) -> int:
        recorder_config = self._create_recording_config()
        browser_service = self._create_browser_service()

        driver = None

        try:
            driver = browser_service.create_driver(kiosk=True)

            driver.get(self.args.url)

            browser_service.validate_screen_resolution(driver)

            browser_service.enable_flash(driver)

            browser_service.inject_dom(
                driver,
                config.TEMPLATE_HTML_PATH,
                self._build_replacements(),
            )

            recorder_config.window_title = f"{driver.title} - Chromium"
            recorder = Recorder(recorder_config)

            await_player_ready(driver)

            driver.execute_script("player.pause();")

            await_started(driver)

            recorder.start()

            driver.execute_script("player.play();")

            await_stopped(driver)

            recorder.stop()
            recorder.wait(timeout=30)

        finally:
            if driver is not None:
                driver.quit()

            browser_service.stop_display()

        return 0