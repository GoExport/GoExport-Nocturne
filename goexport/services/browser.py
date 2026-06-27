import logging
from pathlib import Path
import urllib.parse
import time

from pyvirtualdisplay import Display

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys

logger = logging.getLogger(__name__)

from goexport import config

THRESHOLD_WIDTH = 980
NARROW_TABS = 11
WIDE_TABS = 19

class BrowserService:
    def __init__(
        self,
        chrome_path: Path,
        chromedriver_path: Path,
        flash_path: Path,
        flash_version: str,
        width: int = config.WIDTH,
        height: int = config.HEIGHT,
    ):
        self.chrome_path = chrome_path
        self.chromedriver_path = chromedriver_path
        self.flash_path = flash_path
        self.flash_version = flash_version
        self.width = width
        self.height = height
        self.display = None

    def create_driver(self):
        self.start_display()
        options = Options()

        options.binary_location = str(self.chrome_path)

        options.add_argument("--high-dpi-support=1")
        options.add_argument("--force-device-scale-factor=1")
        options.add_argument("--allow-running-insecure-content")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-bookmarks-bar")

        options.add_argument(
            f"--ppapi-flash-path={str(self.flash_path)}"
        )

        options.add_argument(
            f"--ppapi-flash-version={self.flash_version}"
        )

        if config.SYSTEM == "Linux":
            options.add_argument("--no-sandbox")

        options.add_experimental_option(
            "excludeSwitches",
            ["enable-automation"]
        )

        return webdriver.Chrome(
            service=Service(str(self.chromedriver_path)),
            options=options,
        )

    def start_display(self):
        if config.SYSTEM != "Linux":
            return

        try:
            self.display = Display(
                visible=False,
                size=(self.width, self.height),
                color_depth=24,
            )
            self.display.start()

            logger.info("Started virtual display.")

        except Exception as e:
            self.display = None
            logger.warning(
                "Could not start virtual display (%s). "
                "Falling back to the current display.",
                e,
            )

    def stop_display(self):
        if self.display is not None:
            self.display.stop()
            self.display = None

    @staticmethod
    def set_viewport_size(driver, width, height):
        driver.set_window_size(width, height)

        actual = driver.execute_script("""
            return {
                width: window.innerWidth,
                height: window.innerHeight
            };
        """)

        extra_width = (
            driver.get_window_size()["width"]
            - actual["width"]
        )

        extra_height = (
            driver.get_window_size()["height"]
            - actual["height"]
        )

        driver.set_window_size(
            width + extra_width,
            height + extra_height,
        )

    @staticmethod
    def inject_dom(
        driver,
        html_file: str,
        replacements: dict[str, str] | None = None,
    ) -> None:
        html = Path(html_file).read_text(
            encoding="utf-8"
        )

        if replacements:
            for key, value in replacements.items():
                html = html.replace(
                    f"{{{{{key}}}}}",
                    str(value),
                )

        driver.execute_script("""
            document.open();
            document.write(arguments[0]);
            document.close();
        """, html)
        
    @staticmethod
    def enable_flash(driver):
        current_url = driver.current_url

        driver.get(
            "chrome://settings/content/siteDetails?site="
            + urllib.parse.quote(current_url)
        )

        # Give the settings page a moment to render.
        time.sleep(0.5)
        
        width = driver.execute_script("""
            return window.innerWidth;
        """)

        is_narrow = width < THRESHOLD_WIDTH

        if is_narrow:
            logger.info("Detected narrow toolbar layout.")
            tab_count = NARROW_TABS
        else:
            logger.info("Detected wide toolbar layout.")
            tab_count = WIDE_TABS

        actions = ActionChains(driver)

        for _ in range(tab_count):
            actions.send_keys(Keys.TAB).perform()
            time.sleep(0.05)

        actions.send_keys(Keys.SPACE).perform()
        actions.send_keys(Keys.ARROW_DOWN).perform()
        actions.send_keys(Keys.ENTER).perform()

        driver.get(current_url)