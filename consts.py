import logging
import os

APP_NAME = "Jellycord"
APP_VERSION = "1.0.0"

# Logging
CONSOLE_LOG_LEVEL = logging.INFO
FILE_LOG_LEVEL = logging.DEBUG

# Paths
DEFAULT_CONFIG_PATH = os.path.join(".", "jellycord.yaml")
DEFAULT_LOG_DIR = os.path.join(".", "logs")

# Other constants
GOOGLE_ANALYTICS_ID = 'UA-174268200-2'
DEFAULT_DATABASE_PATH = "/config/tauticord.db"
GITHUB_REPO = "nwithan8/tauticord"
GITHUB_REPO_FULL_LINK = f"https://github.com/{GITHUB_REPO}"
GITHUB_REPO_MASTER_BRANCH = "master"
FLASK_ADDRESS = "0.0.0.0"
FLASK_PORT = 8283
FLASK_POST = "POST"
FLASK_GET = "GET"
FLASK_DATABASE_PATH = "FLASK_DATABASE_PATH"
