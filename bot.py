"""
bot.py — Main Telegram bot entry point.

Run with:  python bot.py
"""
import logging
import pytz
import random
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ParseMode

import database as db
import sheets
import formatters as fmt
from config import Config

# ─── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─── Conversation states for /schedule wizard ─────────────────────────────────
SCHEDULE_MSG, SCHEDULE_TYPE, SCHEDULE_DATE, SCHEDULE_DAYS, SCHEDULE_TIME, SCHEDULE_CONFIRM = range(6)

# ─── Admin guard ─────────────────────────────────────────────────────────────

def _is_admin(update: Update) -> bool:
    user_id = update.effective_user.id if update.effective_user else None
    logger.info(f"Checking admin permission for user_id={user_id}. Allowed admins: {Config.ADMIN_USER_IDS}")
    return update.effective_user and update.effective_user.id in Config.ADMIN_USER_IDS


async def _admin_only(update: Update) -> bool:
    """Reply with error if not admin. Returns True if allowed."""
    if not _is_admin(update):
        await update.message.reply_text("⛔ This command is for the admin only.")
        return False
    return True


# ─── User Tracking ───────────────────────────────────────────────────────────

async def track_user_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Global handler to track active users from messages and status updates."""
    # 1. Track the sender of the message/action
    user = update.effective_user
    if user and not user.is_bot:
        try:
            db.upsert_user(
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
            )
        except Exception as e:
            logger.error(f"Failed to track user {user.id}: {e}")

    # 2. Track new members who joined the group
    if update.message and update.message.new_chat_members:
        for member in update.message.new_chat_members:
            if not member.is_bot:
                try:
                    db.upsert_user(
                        user_id=member.id,
                        username=member.username,
                        first_name=member.first_name,
                        last_name=member.last_name,
                    )
                    logger.info(f"Tracked newly joined user {member.id} ({member.first_name})")
                except Exception as e:
                    logger.error(f"Failed to track joined user {member.id}: {e}")


# ─── /tagall (admin only) ───────────────────────────────────────────────────

async def cmd_tag_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mentions all tracked users in the group (Admin-only)."""
    if not await _admin_only(update):
        return

    chat_id = update.effective_chat.id
    try:
        users = db.get_tracked_users()
        if not users:
            await update.message.reply_text("ℹ️ No tracked users found in database yet\\.", parse_mode=ParseMode.MARKDOWN_V2)
            return

        mentions = []
        for u in users:
            user_id = u["user_id"]
            username = u["username"]
            first_name = u["first_name"]
            
            if username:
                mentions.append(f"@{fmt._escape(username)}")
            else:
                escaped_name = fmt._escape(first_name)
                mentions.append(f"[{escaped_name}](tg://user?id={user_id})")

        # Telegram limits the number of mentions that can reliably trigger notifications.
        # Batching 10 per message is safe and avoids spam/notification limits.
        BATCH_SIZE = 10
        
        await update.message.reply_text(f"📣 *Tagging all {len(users)} tracked members in this group:*", parse_mode=ParseMode.MARKDOWN_V2)
        
        for i in range(0, len(mentions), BATCH_SIZE):
            batch = mentions[i : i + BATCH_SIZE]
            batch_text = " ".join(batch)
            await context.bot.send_message(
                chat_id=chat_id,
                text=batch_text,
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            
    except Exception as e:
        logger.error(f"/tagall error: {e}")
        await update.message.reply_text(f"❌ Error: {fmt._escape(str(e))}", parse_mode=ParseMode.MARKDOWN_V2)



# ─── Helper: send long messages in chunks ────────────────────────────────────

async def _send(context: ContextTypes.DEFAULT_TYPE, chat_id, text: str, parse_mode=ParseMode.MARKDOWN_V2):
    """Send a message, splitting if over Telegram's 4096-char limit."""
    MAX = 4000
    for i in range(0, len(text), MAX):
        await context.bot.send_message(
            chat_id=chat_id,
            text=text[i : i + MAX],
            parse_mode=parse_mode,
        )


# ─── /start ──────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    is_admin = _is_admin(update)
    msg = (
        "👋 *Hello\\! I'm your Personal Assistant Bot\\.*\n\n"
        "I connect to your Google Sheets to track course graduates and post weekly highlights\\.\n\n"
        "📋 *Available Commands:*\n"
        "• /courses — List all courses\n"
        "• /stats — Graduate statistics for all courses\n"
        "• /graduates \\[course\\] — Browse graduates\n"
        "• /top10 \\[course\\] — Show random Top 10 spotlight\n"
    )
    if is_admin:
        msg += (
            "\n🔑 *Admin Commands:*\n"
            "• /postweekly — Manually post weekly highlights\n"
            "• /schedule — Schedule a post to the channel\n"
            "• /listfeeds — View all scheduled posts\n"
            "• /deletefeed \\[id\\] — Cancel a scheduled post\n"
            "• /tagall — Tag all tracked group members\n"
        )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)


# ─── /courses ────────────────────────────────────────────────────────────────

async def cmd_courses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Fetching programs…")
    try:
        programs = sheets.get_all_programs()
        if not programs:
            courses = sheets.get_all_courses()
            await update.message.reply_text(
                fmt.format_courses_list(courses),
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return
        
        buttons = [
            [InlineKeyboardButton(p, callback_data=f"program:{p}")]
            for p in programs
        ]
        await update.message.reply_text(
            "📋 *Select a Program to view its courses:*",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=ParseMode.MARKDOWN_V2,
        )
    except Exception as e:
        logger.error(f"/courses error: {e}")
        await update.message.reply_text(f"❌ Error: {e}")


async def callback_program(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    program = query.data.split(":", 1)[1]
    try:
        courses = sheets.get_courses_by_program(program)
        if not courses:
            await query.edit_message_text(f"No courses found under *{fmt._escape(program)}*\\.", parse_mode=ParseMode.MARKDOWN_V2)
            return
        
        msg = f"📚 *Courses in {fmt._escape(program)}:*\n\n"
        for i, c in enumerate(courses, 1):
            msg += f"{i}\\. {fmt._escape(c)}\n"
        msg += f"\n_Use /graduates \\[course name\\] to view graduates_"
        await query.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN_V2)
    except Exception as e:
        logger.error(f"callback_program error: {e}")
        await query.message.reply_text(f"❌ Error: {e}")


# ─── /stats ──────────────────────────────────────────────────────────────────

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    prog = " ".join(args) if args else None
    await update.message.reply_text("⏳ Loading statistics…")
    try:
        stats = sheets.get_stats(program_name=prog)
        await _send(context, update.effective_chat.id, fmt.format_stats(stats))
    except Exception as e:
        logger.error(f"/stats error: {e}")
        await update.message.reply_text(f"❌ Error: {e}")


# ─── /graduates ──────────────────────────────────────────────────────────────

async def cmd_graduates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        # Show inline keyboard with program selection first
        try:
            programs = sheets.get_all_programs()
            if not programs:
                courses = sheets.get_all_courses()
                if not courses:
                    await update.message.reply_text("No courses found in the spreadsheet.")
                    return
                buttons = [[InlineKeyboardButton(c, callback_data=f"grads:{c}")] for c in courses]
            else:
                buttons = [[InlineKeyboardButton(p, callback_data=f"proggrads:{p}")] for p in programs]
                
            await update.message.reply_text(
                "📚 *Select a Program to view its courses:*",
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")
        return

    # Args: [course_name, optional_page]
    page = 1
    if len(args) >= 2 and args[-1].isdigit():
        page = int(args[-1])
        course = " ".join(args[:-1])
    else:
        course = " ".join(args)

    await update.message.reply_text(f"⏳ Loading graduates for *{course}*…", parse_mode=ParseMode.MARKDOWN_V2)
    try:
        grads = sheets.get_graduates(course)
        await _send(
            context,
            update.effective_chat.id,
            fmt.format_graduates_list(course, grads, page=page),
        )
    except Exception as e:
        logger.error(f"/graduates error: {e}")
        await update.message.reply_text(f"❌ Error: {e}")


async def callback_graduates_program(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    program = query.data.split(":", 1)[1]
    try:
        courses = sheets.get_courses_by_program(program)
        if not courses:
            await query.edit_message_text(f"No courses found under *{fmt._escape(program)}*\\.", parse_mode=ParseMode.MARKDOWN_V2)
            return
        buttons = [
            [InlineKeyboardButton(c, callback_data=f"grads:{c}")]
            for c in courses
        ]
        await query.edit_message_text(
            f"📚 *Select a course in {fmt._escape(program)} to view graduates:*",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=ParseMode.MARKDOWN_V2,
        )
    except Exception as e:
        await query.message.reply_text(f"❌ Error: {e}")


async def callback_graduates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    course = query.data.split(":", 1)[1]
    try:
        grads = sheets.get_graduates(course)
        await _send(context, query.message.chat_id, fmt.format_graduates_list(course, grads))
    except Exception as e:
        await query.message.reply_text(f"❌ Error: {e}")


# ─── /top10 ──────────────────────────────────────────────────────────────────

async def cmd_top10(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        # Inline program picker
        try:
            programs = sheets.get_all_programs()
            if not programs:
                courses = sheets.get_all_courses()
                buttons = [[InlineKeyboardButton(c, callback_data=f"top10:{c}")] for c in courses]
            else:
                buttons = [[InlineKeyboardButton(p, callback_data=f"progtop10:{p}")] for p in programs]
                
            await update.message.reply_text(
                "📚 *Select a Program for Top 10 spotlight:*",
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")
        return

    course = " ".join(args)
    await _do_top10(update.effective_chat.id, course, context)


async def callback_top10_program(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    program = query.data.split(":", 1)[1]
    try:
        courses = sheets.get_courses_by_program(program)
        if not courses:
            await query.edit_message_text(f"No courses found under *{fmt._escape(program)}*\\.", parse_mode=ParseMode.MARKDOWN_V2)
            return
        buttons = [
            [InlineKeyboardButton(c, callback_data=f"top10:{c}")]
            for c in courses
        ]
        await query.edit_message_text(
            f"📚 *Select a course in {fmt._escape(program)} for Top 10 spotlight:*",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=ParseMode.MARKDOWN_V2,
        )
    except Exception as e:
        await query.message.reply_text(f"❌ Error: {e}")


async def callback_top10(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    course = query.data.split(":", 1)[1]
    await _do_top10(query.message.chat_id, course, context)


async def _do_top10(chat_id, course: str, context: ContextTypes.DEFAULT_TYPE):
    try:
        result = sheets.get_random_top10(course)
        if not result["selected"]:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"No graduates found for *{fmt._escape(course)}* this week\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return
        msg = fmt.format_top10_post(result)
        await _send(context, chat_id, msg)
    except Exception as e:
        logger.error(f"top10 error for {course}: {e}")
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Error: {e}")


# ─── /postweekly (admin) ─────────────────────────────────────────────────────

async def cmd_post_weekly(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _admin_only(update):
        return
    await update.message.reply_text("⏳ Fetching all programs and building weekly posts…")
    await do_weekly_post(context)
    await update.message.reply_text("✅ Weekly posts sent to the channel!")


async def do_weekly_post(context: ContextTypes.DEFAULT_TYPE):
    """Core logic for the weekly Top 10 post — called by scheduler and /postweekly."""
    try:
        programs = sheets.get_all_programs()
        if not programs:
            programs = sheets.get_all_courses()
            
        for prog in programs:
            latest_week = sheets.get_program_latest_week(prog)
            if not latest_week:
                logger.info(f"No graduates found for program: {prog}")
                continue
                
            courses = sheets.get_courses_by_program(prog)
            if not courses:
                courses = [prog]
                
            exclude_courses = {"welcome to alx", "n/a"}
            courses = [c for c in courses if c.lower().strip() not in exclude_courses]
            
            results_by_course = []
            final_prefix = sheets.PROGRAM_FINAL_COURSES.get(prog, "").lower()
            
            total_grads_this_week = 0
            for course in courses:
                is_last = False
                if final_prefix and course.lower().strip().startswith(final_prefix):
                    is_last = True
                    
                week_grads = sheets.get_graduates(course, week=latest_week)
                all_grads = sheets.get_graduates(course)
                
                selected_names = [g["name"] for g in week_grads]
                selected = random.sample(selected_names, min(10, len(selected_names)))
                
                results_by_course.append({
                    "course": course,
                    "week_total": len(week_grads),
                    "selected": selected,
                    "is_last": is_last,
                    "course_total": len(all_grads),
                })
                total_grads_this_week += len(week_grads)
                
            if total_grads_this_week > 0:
                msg = fmt.format_program_weekly_report(prog, results_by_course)
                await _send(context, Config.CHANNEL_ID, msg)
                logger.info(f"Posted weekly report for program: {prog} for week: {latest_week}")
            else:
                logger.info(f"No graduates this week ({latest_week}) for program: {prog}")
    except Exception as e:
        logger.error(f"Weekly post error: {e}")


# ─── /schedule wizard (admin) ────────────────────────────────────────────────

async def cmd_schedule_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _admin_only(update):
        return ConversationHandler.END
    await update.message.reply_text(
        "📝 *Schedule a Post*\n\n"
        "Step 1/4: Type the message you want to post to the channel\\.\n"
        "_\\(Send /cancel to abort\\)_",
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    return SCHEDULE_MSG


async def schedule_got_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["feed_msg"] = update.message.text
    
    buttons = [
        [InlineKeyboardButton("📅 One-time Post", callback_data="type_once"),
         InlineKeyboardButton("🔁 Recurring Post", callback_data="type_recur")]
    ]
    await update.message.reply_text(
        "⏰ *Step 2/4: Choose Schedule Type*\n\n"
        "Select whether this post should run once at a specific date, or repeat weekly on particular days:",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    return SCHEDULE_TYPE


async def schedule_got_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "type_once":
        await query.edit_message_text(
            "📅 *Step 3/4: Enter the date*\n\n"
            "Format: `DD/MM/YYYY`\n"
            "_\\(e\\.g\\. 20/06/2026\\)_",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return SCHEDULE_DATE
    else:
        # Recurring post
        await query.edit_message_text(
            "🔁 *Step 3/4: Enter the days of the week*\n\n"
            "Enter comma-separated days (e.g. `mon, wed, fri`) or type `daily`:",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return SCHEDULE_DAYS


async def schedule_got_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        datetime.strptime(text, "%d/%m/%Y")
        context.user_data["feed_date"] = text
    except ValueError:
        await update.message.reply_text("❌ Invalid date format\\. Use `DD/MM/YYYY`", parse_mode=ParseMode.MARKDOWN_V2)
        return SCHEDULE_DATE

    await update.message.reply_text(
        "⏰ *Step 4/4: Enter the time*\n\nFormat: `HH:MM` \\(24\\-hour\\)\n_\\(e\\.g\\. 09:00 or 18:30\\)_",
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    return SCHEDULE_TIME


async def schedule_got_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    
    text_clean = text.lower().replace(" ", "")
    if text_clean == "daily":
        valid_days = "mon,tue,wed,thu,fri,sat,sun"
    else:
        days_map = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
        parts = [p.strip() for p in text_clean.split(",") if p.strip()]
        if not parts or any(p not in days_map for p in parts):
            await update.message.reply_text("❌ Invalid days\\. Use standard short abbreviations separated by commas, e.g., `mon, wed, fri` or `daily`\\.", parse_mode=ParseMode.MARKDOWN_V2)
            return SCHEDULE_DAYS
        valid_days = ",".join(parts)
        
    context.user_data["feed_days"] = valid_days
    await update.message.reply_text(
        "⏰ *Step 4/4: Enter the time*\n\nFormat: `HH:MM` \\(24\\-hour\\)\n_\\(e\\.g\\. 09:00 or 18:30\\)_",
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    return SCHEDULE_TIME


async def schedule_got_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        datetime.strptime(text, "%H:%M")
        context.user_data["feed_time"] = text
    except ValueError:
        await update.message.reply_text("❌ Invalid time\\. Use `HH:MM`", parse_mode=ParseMode.MARKDOWN_V2)
        return SCHEDULE_TIME

    d = context.user_data.get("feed_date")
    days = context.user_data.get("feed_days")
    t = context.user_data["feed_time"]
    msg_preview = context.user_data["feed_msg"][:200]

    buttons = [
        [InlineKeyboardButton("✅ Confirm", callback_data="sched_confirm"),
         InlineKeyboardButton("❌ Cancel", callback_data="sched_cancel")]
    ]
    
    if days:
        schedule_desc = f"Every *{fmt._escape(days.upper())}* at *{t}*"
    else:
        schedule_desc = f"*{d}* at *{t}*"

    await update.message.reply_text(
        f"✅ *Confirm Scheduled Post*\n\n"
        f"📅 *Schedule:* {schedule_desc} \\({fmt._escape(Config.TIMEZONE)}\\)\n\n"
        f"📝 *Message preview:*\n_{fmt._escape(msg_preview)}_",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    return SCHEDULE_CONFIRM


async def schedule_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "sched_cancel":
        await query.edit_message_text("❌ Scheduling cancelled.")
        context.user_data.clear()
        return ConversationHandler.END

    is_recurring = 1 if "feed_days" in context.user_data else 0
    
    if is_recurring:
        days = context.user_data["feed_days"]
        t = context.user_data["feed_time"]
        feed_id = db.add_feed(
            message=context.user_data["feed_msg"],
            is_recurring=1,
            recurrence_days=days,
            recurrence_time=t
        )
        context.user_data.clear()
        await query.edit_message_text(
            f"✅ Recurring post scheduled\\! ID: `{feed_id}`\n\n"
            f"It will be posted every *{days.upper()}* at *{t}* \\({fmt._escape(Config.TIMEZONE)}\\)\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
    else:
        tz = pytz.timezone(Config.TIMEZONE)
        d = context.user_data["feed_date"]
        t = context.user_data["feed_time"]
        local_dt = tz.localize(datetime.strptime(f"{d} {t}", "%d/%m/%Y %H:%M"))
        utc_dt = local_dt.astimezone(pytz.utc).replace(tzinfo=None)
        
        feed_id = db.add_feed(
            message=context.user_data["feed_msg"],
            post_at=utc_dt
        )
        context.user_data.clear()
        await query.edit_message_text(
            f"✅ Post scheduled\\! ID: `{feed_id}`\n\n"
            f"It will be posted on *{d}* at *{t}* \\({fmt._escape(Config.TIMEZONE)}\\)\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        
    return ConversationHandler.END


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END


# ─── /listfeeds (admin) ──────────────────────────────────────────────────────

async def cmd_list_feeds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _admin_only(update):
        return
    feeds = db.get_all_pending_feeds()
    
    if not feeds:
        await update.message.reply_text("No scheduled posts found\\.", parse_mode=ParseMode.MARKDOWN_V2)
        return
        
    tz = pytz.timezone(Config.TIMEZONE)
    lines = ["📅 *SCHEDULED POSTS*", ""]
    for feed in feeds:
        if feed["is_recurring"]:
            sched_str = f"🔁 Every {feed['recurrence_days'].upper()} at {feed['recurrence_time']}"
        else:
            dt = datetime.fromisoformat(feed["post_at"])
            local_dt = pytz.utc.localize(dt).astimezone(tz) if dt.tzinfo is None else dt.astimezone(tz)
            sched_str = f"📅 {local_dt.strftime('%d %b %Y, %H:%M')}"
            
        preview = feed["message"][:60] + ("…" if len(feed["message"]) > 60 else "")
        lines.append(f"🆔 `{feed['id']}` — {fmt._escape(sched_str)}")
        lines.append(f"   _{fmt._escape(preview)}_")
        lines.append("")

    lines.append("_Use /deletefeed \\[id\\] to cancel a post_")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN_V2)


# ─── /deletefeed (admin) ─────────────────────────────────────────────────────

async def cmd_delete_feed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _admin_only(update):
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /deletefeed \\[id\\]", parse_mode=ParseMode.MARKDOWN_V2)
        return
    feed_id = int(context.args[0])
    if db.delete_feed(feed_id):
        await update.message.reply_text(f"✅ Feed `{feed_id}` deleted\\.", parse_mode=ParseMode.MARKDOWN_V2)
    else:
        await update.message.reply_text(f"❌ Feed `{feed_id}` not found or already posted\\.", parse_mode=ParseMode.MARKDOWN_V2)


# ─── Job: check & publish scheduled feeds ────────────────────────────────────

async def job_check_feeds(context: ContextTypes.DEFAULT_TYPE):
    """Called every minute to post any due feeds."""
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    
    # 1. Post due one-time feeds
    pending = db.get_pending_feeds(as_of=now_utc)
    for feed in pending:
        try:
            await context.bot.send_message(
                chat_id=Config.CHANNEL_ID,
                text=feed["message"],
            )
            db.mark_posted(feed["id"])
            logger.info(f"Posted scheduled feed id={feed['id']}")
        except Exception as e:
            logger.error(f"Failed to post feed id={feed['id']}: {e}")

    # 2. Post due recurring feeds
    tz = pytz.timezone(Config.TIMEZONE)
    local_now = datetime.now(timezone.utc).astimezone(tz)
    day_name = local_now.strftime("%a").lower()  # e.g., "mon"
    time_str = local_now.strftime("%H:%M")       # e.g., "10:00"
    
    recurring = db.get_active_recurring_feeds(day_name, time_str)
    for feed in recurring:
        try:
            await context.bot.send_message(
                chat_id=Config.CHANNEL_ID,
                text=feed["message"],
            )
            db.mark_recurring_posted(feed["id"], local_now.strftime("%Y-%m-%d"))
            logger.info(f"Posted recurring feed id={feed['id']} for today")
        except Exception as e:
            logger.error(f"Failed to post recurring feed id={feed['id']}: {e}")


# ─── Job: weekly Top 10 post ─────────────────────────────────────────────────

async def job_weekly_post(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Running scheduled weekly Top 10 post…")
    await do_weekly_post(context)


# ─── Job: poll spreadsheet last modified time & auto-post ────────────────────

async def job_check_sheet_refresh(context: ContextTypes.DEFAULT_TYPE):
    """Polled every 5 minutes to auto-post new graduates when sheet updates."""
    try:
        current_mod_time = sheets.get_spreadsheet_modified_time()
        if not current_mod_time:
            return
            
        last_mod_time = context.bot_data.get("last_sheet_modified")
        
        # 1. Initialization
        if last_mod_time is None:
            logger.info(f"Initializing spreadsheet modifiedTime tracker: {current_mod_time}")
            context.bot_data["last_sheet_modified"] = current_mod_time
            
            # Check if processed_graduates is empty, if so, seed it
            import sqlite3
            conn = sqlite3.connect(db.DB_PATH)
            count = conn.execute("SELECT COUNT(*) FROM processed_graduates").fetchone()[0]
            conn.close()
            
            if count == 0:
                logger.info("Seeding processed_graduates with all current graduates to prevent startup spam...")
                all_grads = sheets.get_all_graduates()
                for g in all_grads:
                    if g.get("email") and g.get("course"):
                        db.mark_graduate_processed(g["email"], g["course"])
            return

        # 2. No changes
        if current_mod_time == last_mod_time:
            return
            
        logger.info(f"Spreadsheet update detected: {last_mod_time} -> {current_mod_time}")
        context.bot_data["last_sheet_modified"] = current_mod_time
        
        # 3. Pull new graduates
        all_grads = sheets.get_all_graduates()
        new_grads = []
        for g in all_grads:
            if g.get("email") and g.get("course"):
                if not db.is_graduate_processed(g["email"], g["course"]):
                    new_grads.append(g)
                    
        if not new_grads:
            return
            
        logger.info(f"Found {len(new_grads)} new graduates in the sheet update.")
        
        # Find unique (program, week) combinations for program leaderboard reports
        program_weeks = {}
        for g in new_grads:
            prog = g.get("program") or g.get("course") or "Unknown Program"
            week = g.get("week") or "Unknown Week"
            if not prog or prog.lower().strip() in {"", "n/a"}:
                continue
            if not week or week == "Unknown Week":
                continue
            if prog not in program_weeks:
                program_weeks[prog] = set()
            program_weeks[prog].add(week)
            
        # Post a combined leaderboard for each program + week
        for prog, weeks in program_weeks.items():
            for week in sorted(list(weeks)):
                courses = sheets.get_courses_by_program(prog)
                if not courses:
                    courses = [prog]
                exclude_courses = {"welcome to alx", "n/a"}
                courses = [c for c in courses if c.lower().strip() not in exclude_courses]
                
                results_by_course = []
                final_prefix = sheets.PROGRAM_FINAL_COURSES.get(prog, "").lower()
                
                total_grads_this_week = 0
                for course in courses:
                    is_last = False
                    if final_prefix and course.lower().strip().startswith(final_prefix):
                        is_last = True
                        
                    week_grads = sheets.get_graduates(course, week=week)
                    all_course_grads = sheets.get_graduates(course)
                    
                    selected_names = [g["name"] for g in week_grads]
                    selected = random.sample(selected_names, min(10, len(selected_names)))
                    
                    results_by_course.append({
                        "course": course,
                        "week_total": len(week_grads),
                        "selected": selected,
                        "is_last": is_last,
                        "course_total": len(all_course_grads),
                    })
                    total_grads_this_week += len(week_grads)
                    
                if total_grads_this_week > 0:
                    msg = fmt.format_program_weekly_report(prog, results_by_course)
                    await _send(context, Config.CHANNEL_ID, msg)
                    logger.info(f"Auto-posted update report for program: {prog} for week: {week}")
                    
        # Mark all new grads as processed in the database
        for g in new_grads:
            db.mark_graduate_processed(g["email"], g["course"])
            
    except Exception as e:
        logger.error(f"Spreadsheet polling error: {e}")


def start_ping_server():
    import http.server
    import socketserver
    import threading
    import os

    class PingHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Bot is alive!")
            
        def log_message(self, format, *args):
            # Suppress logs for basic pings
            return

    port = int(os.getenv("PORT", "8080"))
    try:
        socketserver.TCPServer.allow_reuse_address = True
        server = socketserver.TCPServer(("", port), PingHandler)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        logger.info(f"Started HTTP ping server on port {port} to keep the bot alive on Render Free Tier.")
    except Exception as e:
        logger.warning(
            f"Could not start HTTP ping server on port {port}: {e}. "
            "This is normal when running locally on Windows/PC (you can ignore this warning)."
        )


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    start_ping_server()
    import asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    db.init_db()
    logger.info(f"Loaded ADMIN_USER_IDS: {Config.ADMIN_USER_IDS}")

    app = Application.builder().token(Config.BOT_TOKEN).build()

    # ── Schedule background jobs ──
    tz = pytz.timezone(Config.TIMEZONE)
    jq = app.job_queue

    # Weekly post — e.g. every Monday at 09:00
    day_map = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
    day_num = day_map.get(Config.WEEKLY_POST_DAY, 0)
    jq.run_daily(
        job_weekly_post,
        time=pytz.utc.localize(
            tz.localize(
                datetime.now().replace(
                    hour=Config.weekly_hour(),
                    minute=Config.weekly_minute(),
                    second=0,
                    microsecond=0,
                )
            ).astimezone(pytz.utc).replace(tzinfo=None)
        ),
        days=(day_num,),
        name="weekly_top10",
    )

    # Feed checker — every 60 seconds
    jq.run_repeating(job_check_feeds, interval=60, first=10, name="feed_checker")

    # Spreadsheet polling checker — every 300 seconds (5 minutes)
    jq.run_repeating(job_check_sheet_refresh, interval=300, first=15, name="sheet_checker")

    # ── User tracking handler (group -1 to run for all messages) ──
    app.add_handler(MessageHandler(filters.ALL, track_user_update), group=-1)

    # ── Command handlers ──
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("courses", cmd_courses))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("graduates", cmd_graduates))
    app.add_handler(CommandHandler("top10", cmd_top10))
    app.add_handler(CommandHandler("postweekly", cmd_post_weekly))
    app.add_handler(CommandHandler("listfeeds", cmd_list_feeds))
    app.add_handler(CommandHandler("deletefeed", cmd_delete_feed))
    app.add_handler(CommandHandler("tagall", cmd_tag_all))

    # Schedule conversation wizard
    schedule_conv = ConversationHandler(
        entry_points=[CommandHandler("schedule", cmd_schedule_start)],
        states={
            SCHEDULE_MSG:     [MessageHandler(filters.TEXT & ~filters.COMMAND, schedule_got_msg)],
            SCHEDULE_TYPE:    [CallbackQueryHandler(schedule_got_type, pattern="^type_")],
            SCHEDULE_DATE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, schedule_got_date)],
            SCHEDULE_DAYS:    [MessageHandler(filters.TEXT & ~filters.COMMAND, schedule_got_days)],
            SCHEDULE_TIME:    [MessageHandler(filters.TEXT & ~filters.COMMAND, schedule_got_time)],
            SCHEDULE_CONFIRM: [CallbackQueryHandler(schedule_confirm, pattern="^sched_")],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
    )
    app.add_handler(schedule_conv)

    # Inline button callbacks
    app.add_handler(CallbackQueryHandler(callback_graduates, pattern="^grads:"))
    app.add_handler(CallbackQueryHandler(callback_top10, pattern="^top10:"))
    app.add_handler(CallbackQueryHandler(callback_program, pattern="^program:"))
    app.add_handler(CallbackQueryHandler(callback_graduates_program, pattern="^proggrads:"))
    app.add_handler(CallbackQueryHandler(callback_top10_program, pattern="^progtop10:"))

    logger.info("Bot is running… Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
