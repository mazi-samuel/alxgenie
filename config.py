"""
config.py — Load and validate all environment variables.
"""
import os
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise EnvironmentError(
            f"Missing required environment variable: {key}\n"
            f"Copy .env.example to .env and fill in your values."
        )
    return val


class Config:
    # Telegram
    BOT_TOKEN: str = _require("TELEGRAM_BOT_TOKEN")
    CHANNEL_ID: str = _require("TELEGRAM_CHANNEL_ID")
    ADMIN_USER_IDS: list[int] = [
        int(x.strip())
        for x in _require("ADMIN_USER_IDS").split(",")
        if x.strip()
    ]

    # Google Sheets
    SHEET_ID: str = _require("GOOGLE_SHEET_ID")
    SHEET_MODE: str = os.getenv("SHEET_MODE", "tabs").lower()  # "tabs" or "column"

    # Column names (lowercased for flexible matching)
    COL_NAME: str = os.getenv("COL_NAME", "Name")
    COL_DATE: str = os.getenv("COL_DATE", "Completion Date")
    COL_WEEK: str = os.getenv("COL_WEEK", "Week")
    COL_PROGRAM: str = os.getenv("COL_PROGRAM", "Program")
    COL_COURSE: str = os.getenv("COL_COURSE", "Course")

    # Weekly schedule
    WEEKLY_POST_DAY: str = os.getenv("WEEKLY_POST_DAY", "mon").lower()
    WEEKLY_POST_TIME: str = os.getenv("WEEKLY_POST_TIME", "09:00")

    # Timezone
    TIMEZONE: str = os.getenv("TIMEZONE", "Africa/Lagos")

    @classmethod
    def weekly_hour(cls) -> int:
        return int(cls.WEEKLY_POST_TIME.split(":")[0])

    @classmethod
    def weekly_minute(cls) -> int:
        return int(cls.WEEKLY_POST_TIME.split(":")[1])
