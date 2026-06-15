"""
formatters.py — Build nicely formatted Telegram messages.

All messages use Telegram MarkdownV2 escaping.
"""
import re
from datetime import datetime
from typing import Optional
import pytz
from config import Config


# ─── MarkdownV2 helper ───────────────────────────────────────────────────────

def _escape(text: str) -> str:
    """Escape special chars for Telegram MarkdownV2."""
    special = r"\_*[]()~`>#+-=|{}.!"
    return re.sub(f"([{re.escape(special)}])", r"\\\1", str(text))


# ─── Weekly Top 10 Post ──────────────────────────────────────────────────────

def format_top10_post(result: dict) -> str:
    """
    Format the weekly Top 10 post.
    result keys: course, week, selected, week_total, course_total
    """
    course = _escape(result["course"])
    week = _escape(result["week"] or "Latest")
    week_total = result["week_total"]
    course_total = result["course_total"]
    selected = result["selected"]

    lines = [
        f"🎓 *WEEKLY GRADUATES SPOTLIGHT*",
        f"",
        f"📚 *Course:* {course}",
        f"📅 *{week}*",
        f"",
        f"🏆 *Top {len(selected)} Spotlight Graduates*",
        f"",
    ]

    medals = ["🥇", "🥈", "🥉"] + ["✨"] * 7
    for i, name in enumerate(selected):
        medal = medals[i] if i < len(medals) else "⭐"
        lines.append(f"{medal} {_escape(name)}")

    lines += [
        f"",
        f"📊 *{_escape(str(week_total))} graduates* completed this course this week",
        f"🎯 *{_escape(str(course_total))} total graduates* across all time",
        f"",
        f"Congratulations to all our graduates\\! 🎉",
        f"Keep up the excellent work\\! 💪",
    ]

    return "\n".join(lines)


def format_all_courses_top10(results: list[dict]) -> list[str]:
    """
    Given a list of top10 results (one per course), return a list of
    formatted message strings — one per course.
    """
    return [format_top10_post(r) for r in results]


# ─── Stats Summary ───────────────────────────────────────────────────────────

def format_stats(stats: dict[str, int]) -> str:
    """Format a summary of all courses and their graduate counts."""
    if not stats:
        return "No course data found\\."

    total_all = sum(stats.values())
    lines = [
        "📊 *COURSE STATISTICS*",
        "",
    ]
    for course, count in sorted(stats.items()):
        bar = "█" * min(count // 5, 20)  # simple visual bar
        lines.append(f"📚 *{_escape(course)}*")
        lines.append(f"   👥 {_escape(str(count))} graduates {_escape(bar)}")
        lines.append("")

    lines.append(f"🎯 *Grand Total: {_escape(str(total_all))} graduates*")
    return "\n".join(lines)


# ─── Graduate List ───────────────────────────────────────────────────────────

def format_graduates_list(course: str, graduates: list[dict], page: int = 1, per_page: int = 20) -> str:
    """Paginated graduate list for a course."""
    if not graduates:
        return f"No graduates found for *{_escape(course)}*\\."

    start = (page - 1) * per_page
    end = start + per_page
    page_items = graduates[start:end]
    total_pages = (len(graduates) + per_page - 1) // per_page

    lines = [
        f"📚 *{_escape(course)}* — Graduates",
        f"Page {page}/{total_pages} \\| Total: {_escape(str(len(graduates)))}",
        "",
    ]
    for i, g in enumerate(page_items, start=start + 1):
        week_label = f" \\({_escape(g['week'])}\\)" if g.get("week") else ""
        lines.append(f"{i}\\. {_escape(g['name'])}{week_label}")

    if total_pages > 1:
        lines.append("")
        lines.append(f"_Use /graduates {_escape(course)} {page + 1} for next page_")

    return "\n".join(lines)


# ─── Courses List ────────────────────────────────────────────────────────────

def format_courses_list(courses: list[str]) -> str:
    if not courses:
        return "No courses found in the spreadsheet\\."
    lines = ["📋 *AVAILABLE COURSES*", ""]
    for i, c in enumerate(courses, 1):
        lines.append(f"{i}\\. {_escape(c)}")
    lines += ["", "_Use /graduates \\[course name\\] to view graduates_"]
    return "\n".join(lines)


# ─── Scheduled Feeds List ────────────────────────────────────────────────────

def format_feeds_list(feeds: list, tz_name: str) -> str:
    if not feeds:
        return "No scheduled posts found\\."

    tz = pytz.timezone(tz_name)
    lines = ["📅 *SCHEDULED POSTS*", ""]
    for feed in feeds:
        dt = datetime.fromisoformat(feed["post_at"])
        local_dt = pytz.utc.localize(dt).astimezone(tz) if dt.tzinfo is None else dt.astimezone(tz)
        dt_str = local_dt.strftime("%d %b %Y, %H:%M")
        preview = feed["message"][:60] + ("…" if len(feed["message"]) > 60 else "")
        lines.append(f"🆔 `{feed['id']}` — {_escape(dt_str)}")
        lines.append(f"   _{_escape(preview)}_")
        lines.append("")

    lines.append("_Use /deletefeed \\[id\\] to cancel a post_")
    return "\n".join(lines)


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


def format_program_weekly_report(program_name: str, results_by_course: list[dict]) -> str:
    """
    Format the combined weekly leaderboard report for a program.
    """
    abbr = PROGRAM_TO_ABBR.get(program_name, program_name)
    abbr_esc = _escape(abbr)
    
    lines = [
        f"🏆 *Program Leaderboard Champions*",
        f"",
        f"A huge congratulations to our *{abbr_esc}* learners\\! 🎉",
        f"",
    ]
    
    last_course_results = None
    
    for res in results_by_course:
        course_esc = _escape(res["course"])
        week_total = res["week_total"]
        selected = res["selected"]
        
        if res["is_last"]:
            last_course_results = res
            
        if week_total > 0:
            lines.append(f"📚 *{course_esc}*")
            lines.append(f"An impressive *{_escape(str(week_total))}* learners have already completed this module, proving that steady progress leads to results\\. Check out the leaderboard below to see the Top 10 performers\\:")
            lines.append("")
            medals = ["🥇", "🥈", "🥉"] + ["✨"] * 7
            for i, name in enumerate(selected):
                medal = medals[i] if i < len(medals) else "⭐"
                lines.append(f"{medal} {_escape(name)}")
            lines.append("")
            
    # Program finishers section
    lines.append("🎓 *FINISHERS OF THE PROGRAM*")
    lines.append("")
    if last_course_results:
        week_total = last_course_results["week_total"]
        selected = last_course_results["selected"]
        if week_total > 1:
            names_str = ", ".join(selected)
            lines.append(f"And now to our finishers of the program\\: we had *{_escape(str(week_total))}* finishers this week\\! A huge congratulations to: *{_escape(names_str)}*\\! 🎓")
        elif week_total == 1:
            name = selected[0] if selected else "our learner"
            lines.append(f"And now to our finishers of the program\\: we wish for more finishers but for now congratulations to the *{_escape(name)}*\\! 🎓")
        else:
            lines.append("And now to our finishers of the program\\: We're rooting for you and are sadened you're not here yet\\.")
    else:
        lines.append("And now to our finishers of the program\\: We're rooting for you and are sadened you're not here yet\\.")
        
    lines.append("")
    
    # Motivation section
    lines += [
        f"🎉 Congratulations to everyone progressing from one short course to the next, and a special shoutout to those who have completed their final short course and graduated from their program\\!",
        f"",
        f"While this journey is self\\-paced, the pace is still yours to set\\.",
        f"",
        f"The learners who finish fastest aren't necessarily studying for hours every day\\. They're simply consistent\\. Just 30–60 minutes daily can help you build momentum, graduate sooner and start applying your new skills faster\\.",
        f"",
        f"Also, every extra month spent delaying completion is another month of subscription costs\\. If you're already on the journey, make the most of your investment by keeping your progress moving\\.",
        f"",
        f"This week, challenge yourself to\\:",
        f"",
        f"✅ Complete a module",
        f"✅ Finish an assessment",
        f"✅ Move to the next short course",
        f"",
        f"Small daily actions lead to graduation\\. Keep going; you may be closer than you think\\. 🚀",
    ]
    
    return "\n".join(lines)
