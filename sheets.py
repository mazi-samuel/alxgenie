"""
sheets.py — Google Sheets reader via gspread service account.

Supports two modes (set SHEET_MODE in .env):
  "tabs"   → each worksheet tab = one course
  "column" → one worksheet, course identified by a column value

Place your Google Service Account JSON key at:
  credentials.json   (in the same folder as this script)
"""
import os
import random
import logging
from typing import Optional
from functools import lru_cache
from datetime import datetime, timedelta

import gspread
from google.oauth2.service_account import Credentials

from config import Config

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

CREDENTIALS_PATH = os.path.join(os.path.dirname(__file__), "credentials.json")

PROGRAM_ABBREVIATIONS = {
    "aice": "AI Career Essentials",
    "va": "Virtual Assistant",
    "da": "Data Analytics",
    "gd": "Graphic Design",
    "cc": "Content Creation",
    "fla": "Freelancer Academy",
    "fa": "Founder Academy",
    "ds": "Data Science",
}

PROGRAM_FINAL_COURSES = {
    "AI Career Essentials": "AiCE-6",
    "Virtual Assistant": "VA-6",
    "Data Analytics": "DA-3",
    "Graphic Design": "GD-5",
    "Content Creation": "CC-4",
    "Freelancer Academy": "FLA-3",
    "Founder Academy": "FA-1",
    "Data Science": "DA-2",
}

PROGRAM_TO_ABBR = {
    "AI Career Essentials": "AICE",
    "Virtual Assistant": "VA",
    "Data Analytics": "DA",
    "Graphic Design": "GD",
    "Content Creation": "CC",
    "Freelancer Academy": "FLA",
    "Founder Academy": "FA",
    "Data Science": "DS",
}


def resolve_course_name(name: str) -> str:
    """Resolve program abbreviations to full names."""
    name_clean = name.strip().lower()
    return PROGRAM_ABBREVIATIONS.get(name_clean, name.strip())


def date_to_week(date_str: str) -> str:
    """Convert a date string to a 'Week of YYYY-MM-DD' label."""
    if not date_str or date_str.startswith("1970-01-01") or date_str.strip().lower() == "n/a":
        return "Unknown Week"
    for fmt_str in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(date_str.split()[0], "%Y-%m-%d")
            monday = dt - timedelta(days=dt.weekday())
            return f"Week of {monday.strftime('%Y-%m-%d')}"
        except Exception:
            continue
    return "Unknown Week"


import json


def _get_client() -> gspread.Client:
    """Authenticate and return a gspread client."""
    creds_json = os.getenv("GOOGLE_CREDS_JSON")
    if creds_json:
        try:
            info = json.loads(creds_json)
            creds = Credentials.from_service_account_info(info, scopes=SCOPES)
            return gspread.authorize(creds)
        except Exception as e:
            logger.error(f"Failed to authenticate using GOOGLE_CREDS_JSON env var: {e}")
            
    creds = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=SCOPES)
    return gspread.authorize(creds)


def _get_spreadsheet() -> gspread.Spreadsheet:
    client = _get_client()
    return client.open_by_key(Config.SHEET_ID)


# ─── Column helpers ──────────────────────────────────────────────────────────

def _find_col(headers: list[str], target: str) -> Optional[int]:
    """Return 0-based column index for a header name (case-insensitive)."""
    target_lower = target.lower().strip()
    for i, h in enumerate(headers):
        if h.lower().strip() == target_lower:
            return i
    return None


def _parse_rows(
    headers: list[str], 
    rows: list[list[str]], 
    filter_val: Optional[str] = None, 
    filter_col: Optional[int] = None,
    is_prefix: bool = False
) -> list[dict]:
    """Parse rows into graduate records, filtering and merging fields where necessary."""
    name_col = _find_col(headers, Config.COL_NAME)
    last_name_col = _find_col(headers, "Last name")
    date_col = _find_col(headers, Config.COL_DATE)
    week_col = _find_col(headers, Config.COL_WEEK)
    is_grad_col = _find_col(headers, "Is course graduated")
    email_col = _find_col(headers, "Email")
    prog_col = _find_col(headers, Config.COL_PROGRAM)
    course_col = _find_col(headers, Config.COL_COURSE)

    if name_col is None:
        logger.warning(f"Name column '{Config.COL_NAME}' not found in headers: {headers}")
        return []

    records = []
    for row in rows:
        if not any(cell.strip() for cell in row):
            continue  # skip blank rows

        # Course/Program filter
        if filter_val is not None and filter_col is not None:
            if filter_col >= len(row):
                continue
            val_in_sheet = row[filter_col].strip().lower()
            if is_prefix:
                if not val_in_sheet.startswith(filter_val.lower()):
                    continue
            else:
                if val_in_sheet != filter_val.lower():
                    continue

        # Filter for actual graduates
        if is_grad_col is not None and is_grad_col < len(row):
            if row[is_grad_col].strip().lower() != "yes":
                continue

        # Get name (merge First and Last if present)
        first_name = row[name_col].strip() if name_col < len(row) else ""
        if last_name_col is not None and last_name_col < len(row):
            last_name = row[last_name_col].strip()
            full_name = f"{first_name} {last_name}".strip()
        else:
            full_name = first_name

        # Date and Week
        grad_date = row[date_col].strip() if date_col is not None and date_col < len(row) else ""
        
        # If no week column, or if week matches the date column, compute dynamically
        if week_col is None or Config.COL_WEEK == Config.COL_DATE:
            grad_week = date_to_week(grad_date)
        else:
            grad_week = row[week_col].strip() if week_col < len(row) else ""

        # Get program and course names
        prog_name_val = row[prog_col].strip() if prog_col is not None and prog_col < len(row) else ""
        course_name_val = row[course_col].strip() if course_col is not None and course_col < len(row) else ""

        records.append({
            "name": full_name,
            "date": grad_date,
            "week": grad_week,
            "email": row[email_col].strip() if email_col is not None and email_col < len(row) else "",
            "program": prog_name_val,
            "course": course_name_val,
        })
    return [r for r in records if r["name"]]


def _parse_worksheet(ws: gspread.Worksheet) -> list[dict]:
    """Parse a worksheet into a list of row dicts."""
    all_rows = ws.get_all_values()
    if not all_rows:
        return []
    return _parse_rows(all_rows[0], all_rows[1:])


# ─── Public API ──────────────────────────────────────────────────────────────

def get_spreadsheet_modified_time() -> str:
    """Return the RFC 3339 datetime string of the spreadsheet's last modification."""
    client = _get_client()
    meta = client.get_file_drive_metadata(Config.SHEET_ID)
    return meta.get("modifiedTime", "")


def get_all_programs() -> list[str]:
    """Return list of all parent program names."""
    if Config.SHEET_MODE == "tabs":
        return []
    ss = _get_spreadsheet()
    ws = ss.sheet1
    all_rows = ws.get_all_values()
    if not all_rows:
        return []
    headers = all_rows[0]
    prog_col = _find_col(headers, Config.COL_PROGRAM)
    if prog_col is None:
        return []
    return sorted(set(
        row[prog_col].strip()
        for row in all_rows[1:]
        if prog_col < len(row) and row[prog_col].strip()
    ))


def get_courses_by_program(program_name: str) -> list[str]:
    """Return list of short course names under a specific program."""
    program_name = resolve_course_name(program_name)
    if Config.SHEET_MODE == "tabs":
        return [program_name]
    ss = _get_spreadsheet()
    ws = ss.sheet1
    all_rows = ws.get_all_values()
    if not all_rows:
        return []
    headers = all_rows[0]
    prog_col = _find_col(headers, Config.COL_PROGRAM)
    course_col = _find_col(headers, Config.COL_COURSE)
    if prog_col is None or course_col is None:
        return []
    return sorted(set(
        row[course_col].strip()
        for row in all_rows[1:]
        if prog_col < len(row) and course_col < len(row) 
        and row[prog_col].strip().lower() == program_name.lower()
        and row[course_col].strip()
    ))


def get_all_courses() -> list[str]:
    """Return list of all short course names."""
    ss = _get_spreadsheet()
    if Config.SHEET_MODE == "tabs":
        # Each tab = one course (skip any tab named "Summary" or "Overview")
        skip = {"summary", "overview", "readme", "index"}
        return [ws.title for ws in ss.worksheets() if ws.title.lower() not in skip]
    else:
        # Single sheet: collect unique values in the course column
        ws = ss.sheet1
        all_rows = ws.get_all_values()
        if not all_rows:
            return []
        headers = all_rows[0]
        course_col = _find_col(headers, Config.COL_COURSE)
        if course_col is None:
            return []
        return sorted(set(
            row[course_col].strip()
            for row in all_rows[1:]
            if course_col < len(row) and row[course_col].strip()
        ))


def get_graduates(course: str, week: Optional[str] = None) -> list[dict]:
    """
    Return graduates for a program or short course.
    Each item: {"name": ..., "date": ..., "week": ...}
    """
    resolved_course = resolve_course_name(course)
    ss = _get_spreadsheet()
    
    if Config.SHEET_MODE == "tabs":
        try:
            ws = ss.worksheet(resolved_course)
        except gspread.WorksheetNotFound:
            logger.error(f"Worksheet '{resolved_course}' not found.")
            return []
        records = _parse_worksheet(ws)
    else:
        ws = ss.sheet1
        all_rows = ws.get_all_values()
        if not all_rows:
            return []
        headers = all_rows[0]
        prog_col = _find_col(headers, Config.COL_PROGRAM)
        course_col = _find_col(headers, Config.COL_COURSE)
        
        # Check if the query refers to a program (like 'AI Career Essentials')
        is_program = False
        if prog_col is not None:
            unique_programs = set(r[prog_col].strip().lower() for r in all_rows[1:] if prog_col < len(r))
            if resolved_course.lower() in unique_programs:
                is_program = True

        if is_program and prog_col is not None:
            records = _parse_rows(headers, all_rows[1:], filter_val=resolved_course, filter_col=prog_col)
        elif course_col is not None:
            records = _parse_rows(headers, all_rows[1:], filter_val=resolved_course, filter_col=course_col, is_prefix=True)
        else:
            records = []

    if week:
        records = [r for r in records if r["week"].lower() == week.lower()]
    return records


def get_stats(program_name: Optional[str] = None) -> dict[str, int]:
    """Return {name: total_graduate_count} for courses or programs."""
    if program_name:
        courses = get_courses_by_program(program_name)
        return {course: len(get_graduates(course)) for course in courses}
    else:
        programs = get_all_programs()
        # Fallback to courses if programs list is empty
        if not programs:
            courses = get_all_courses()
            return {course: len(get_graduates(course)) for course in courses}
        return {prog: len(get_graduates(prog)) for prog in programs}


def get_all_weeks(course: str) -> list[str]:
    """Return sorted list of unique week labels for a course."""
    graduates = get_graduates(course)
    weeks = sorted(set(r["week"] for r in graduates if r["week"] and r["week"] != "Unknown Week"))
    return weeks


def get_latest_week(course: str) -> Optional[str]:
    """Return the latest week label available for a course."""
    weeks = get_all_weeks(course)
    return weeks[-1] if weeks else None


def get_program_weeks(program: str) -> list[str]:
    """Return sorted list of unique week labels for a program."""
    graduates = get_graduates(program)
    weeks = sorted(set(r["week"] for r in graduates if r["week"] and r["week"] != "Unknown Week"))
    return weeks


def get_program_latest_week(program: str) -> Optional[str]:
    """Return the latest week label available for a program."""
    weeks = get_program_weeks(program)
    return weeks[-1] if weeks else None


def get_all_graduates() -> list[dict]:
    """Return all graduates from the spreadsheet."""
    ss = _get_spreadsheet()
    if Config.SHEET_MODE == "tabs":
        records = []
        skip = {"summary", "overview", "readme", "index"}
        for ws in ss.worksheets():
            if ws.title.lower() in skip:
                continue
            for r in _parse_worksheet(ws):
                r["course"] = ws.title
                r["program"] = ws.title
                records.append(r)
        return records
    else:
        ws = ss.sheet1
        all_rows = ws.get_all_values()
        if not all_rows:
            return []
        headers = all_rows[0]
        return _parse_rows(headers, all_rows[1:])


def get_random_top10(course: str, week: Optional[str] = None) -> dict:
    """
    Pick a random selection of up to 10 graduates for a course/week.
    """
    if week is None:
        week = get_latest_week(course)

    week_grads = get_graduates(course, week=week) if week else []
    all_grads = get_graduates(course)

    names = [r["name"] for r in week_grads]
    selected = random.sample(names, min(10, len(names))) if names else []

    return {
        "course": course,
        "week": week,
        "selected": selected,
        "week_total": len(week_grads),
        "course_total": len(all_grads),
    }
