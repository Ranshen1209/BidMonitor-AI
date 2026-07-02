"""项目内浏览器二进制缓存路径。"""
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


BINARY_ROOT_ENV = "BIDMONITOR_BROWSER_BINARIES"
PLAYWRIGHT_BROWSERS_ENV = "PLAYWRIGHT_BROWSERS_PATH"
CLOAKBROWSER_CACHE_ENV = "CLOAKBROWSER_CACHE_DIR"
DEFAULT_BINARY_DIR = ".browser-binaries"


@dataclass(frozen=True)
class BrowserBinaryPaths:
    root: Path
    cloakbrowser: Path
    playwright: Path
    webdriver_manager: Path
    selenium: Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def configure_browser_binary_environment(root: Optional[Path] = None) -> BrowserBinaryPaths:
    """确保浏览器二进制使用项目内目录,并返回各后端路径。"""
    base = Path(os.environ.get(BINARY_ROOT_ENV) or (root or project_root()) / DEFAULT_BINARY_DIR)
    cloakbrowser = Path(os.environ.get(CLOAKBROWSER_CACHE_ENV) or base / "cloakbrowser")
    playwright = Path(os.environ.get(PLAYWRIGHT_BROWSERS_ENV) or base / "playwright")
    webdriver_manager = base / "webdriver-manager"
    selenium = base / "selenium"

    for path in (base, cloakbrowser, playwright, webdriver_manager, selenium):
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

    os.environ[BINARY_ROOT_ENV] = str(base)
    os.environ[CLOAKBROWSER_CACHE_ENV] = str(cloakbrowser)
    os.environ[PLAYWRIGHT_BROWSERS_ENV] = str(playwright)
    return BrowserBinaryPaths(
        root=base,
        cloakbrowser=cloakbrowser,
        playwright=playwright,
        webdriver_manager=webdriver_manager,
        selenium=selenium,
    )


def _first_existing(candidates):
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return path
    return None


def find_selenium_chrome_binary(root: Optional[Path] = None) -> Optional[Path]:
    paths = configure_browser_binary_environment(root)
    return _first_existing(
        [
            paths.selenium / "chrome",
            paths.selenium / "chrome-linux64" / "chrome",
            paths.selenium / "chromium",
            paths.selenium / "chromium-browser",
            paths.selenium / "Google Chrome for Testing.app" / "Contents" / "MacOS" / "Google Chrome for Testing",
            paths.selenium / "Google Chrome.app" / "Contents" / "MacOS" / "Google Chrome",
        ]
    )


def find_chromedriver_binary(root: Optional[Path] = None) -> Optional[Path]:
    paths = configure_browser_binary_environment(root)
    return _first_existing(
        [
            paths.selenium / "chromedriver",
            paths.selenium / "chromedriver-linux64" / "chromedriver",
            paths.selenium / "chromedriver-mac-arm64" / "chromedriver",
            paths.selenium / "chromedriver-mac-x64" / "chromedriver",
            paths.selenium / "chromedriver.exe",
        ]
    )
