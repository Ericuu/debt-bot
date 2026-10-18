import asyncio
import datetime
import logging
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.schedulers.asyncio import AsyncIOScheduler

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
scheduler = AsyncIOScheduler(timezone="Asia/Taipei")

db = {
    "total_debt": 874000,
    "monthly_target": 50000,
    "monthly_income": 0,
    "expense_limit": 0,
    "current_expense": 0,
}

user_states = {}


def get_financial_summary():
    remaining_budget = db["expense_limit"] - db["current_expense"]
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    current_year, current_month, current_day = now.year, now.month, now.day

    if current_day >= 10:
        start_date = datetime.date(current_year, current_month, 10)
        end_date = (
            datetime.date(current_year + 1, 1, 10)
            if current_month == 12
            else datetime.date(current_year, current_month + 1, 10)
        )
    else:
        start_date = (
            datetime.date(current_year - 1, 12, 10)
            if current_month == 1
            else datetime.date(current_year, current_month - 1, 10)
        )
        end_date = datetime.date(current_year, current_month, 10)

    total_days = (end_date - start_date).days
    days_left = max(1, (end_date - now.date()).days)
    daily_allowance = max(0, remaining_budget / days_left)

    return {
        "remaining_budget": remaining_budget,
        "daily_allowance": daily_allowance,
        "days_left": days_left,
        "cycle_end": end_date.strftime("%m/%d"),
    }


def get_hp_bar():
    initial_debt = 874000
    current_debt = max(0, db["total_debt"])
    percentage = min(1.0, current_debt / initial_debt)
    filled_blocks = int(percentage * 10)
    empty_blocks = 10 - filled_blocks
    bar = "█" * filled_blocks + "░" * empty_blocks
    return bar, int(percentage * 100)


def get_main_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚔️ 執行還款攻擊", callback_data="btn_repay"
                ),
                InlineKeyboardButton(
                    text="📊 查看血量狀態", callback_data="btn_status"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="💰 設定本月收入", callback_data="btn_income"
                ),
                InlineKeyboardButton(
                    text="✏️ 修正已花費", callback_data="btn_edit_exp"
                ),
            ],
        ]
    )


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_states[message.from_user.id] = None
    fin = get_financial_summary()
    bar, hp_pct = get_hp_bar()
    text = (
        f"🎮 **【RPG 討伐 87萬巨獸系統（10號週期版）】**\n\n"
        f"👹 血量：${db['total_debt']:,} ([{bar}] {hp_pct}%)\n"
        f"🎯 還款目標：${db['monthly_target']:,}\n"
        f"💸 已花費：${db['current_expense']:,}\n" f"💡 剩餘可用：**${fin['remaining_budget']:,}** (至 {fin['cycle_end']} 止，約 ${fin['daily_allowance']:,.0f}/天，剩 {fin['days_left']} 天)"
    )
    await message.reply(text, reply_markup=get_main_keyboard())


@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    fin = get_financial_summary()
    bar, hp_pct = get_hp_bar()
    text = (
        f"📊 **【巨獸戰鬥狀態 (10號週期)】**\n"
        f"👹 血量：${db['total_debt']:,} ([{bar}] {hp_pct}%)\n"
        f"• 還款目標：${db['monthly_target']:,}\n"
        f"• 收入：${db['monthly_income']:,}\n"
        f"• 上限：${db['expense_limit']:,}\n"
        f"• 已花費：${db['current_expense']:,}\n" f"• 剩餘可用：**${fin['remaining_budget']:,}** (至 {fin['cycle_end']} 止，約 ${fin['daily_allowance']:,.0f}/天，剩 {fin['days_left']} 天)"
    )
    await message.reply(text, reply_markup=get_main_keyboard())


@dp.message(Command("income"))
async def cmd_income(message: types.Message):
    user_states[message.from_user.id] = "set_income"
    await message.reply("💰 請輸入你**本月的總收入金額**（例如：`70000`）：")


@dp.message(Command("edit"))
async def cmd_edit(message: types.Message):
    user_states[message.from_user.id] = "edit_expense"
    await message.reply(
        f"✏️ 目前本月已花費為 **${db['current_expense']:,}**。\n"
        f"請輸入**修正後的正確總金額**（例如：`3500`）："
    )


@dp.callback_query(F.data.startswith("btn_"))
async def handle_callback_query(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    action = callback.data

    if action == "btn_status":
        fin = get_financial_summary()
        bar, hp_pct = get_hp_bar()
        text = (
            f"📊 **【巨獸戰鬥狀態 (10號週期)】**\n"
            f"👹 血量：${db['total_debt']:,} ([{bar}] {hp_pct}%)\n"
            f"• 還款目標：${db['monthly_target']:,}\n"
            f"• 收入：${db['monthly_income']:,}\n"
            f"• 上限：${db['expense_limit']:,}\n"
            f"• 已花費：${db['current_expense']:,}\n" f"• 剩餘可用：**${fin['remaining_budget']:,}** (至 {fin['cycle_end']} 止，約 ${fin['daily_allowance']:,.0f}/天，剩 {fin['days_left']} 天)"
        )
        await callback.message.edit_text(
            text, reply_markup=get_main_keyboard()
        )
    elif action == "btn_repay":
        user_states[user_id] = "do_repay"
        await callback.message.reply(
            f"⚔️ **準備發動還款攻擊！**\n"
            f"目前血量：${db['total_debt']:,}\n"
            f"請輸入這次**還款金額**（例如：`50000`）："
        )
    elif action == "btn_income":
        user_states[user_id] = "set_income"
        await callback.message.reply("💰 請輸入你**本月的總收入金額**：")
    elif action == "btn_edit_exp":
        user_states[user_id] = "edit_expense"
        await callback.message.reply(
            f"✏️ 目前已花費 **${db['current_expense']:,}**，請輸入修正後金額："
        )

    await callback.answer()


@dp.message(F.text)
async def handle_text_message(message: types.Message):
    user_id = message.from_user.id
    text = message.text.strip()
    current_state = user_states.get(user_id)

    if current_state == "do_repay":
        numbers = re.findall(r"\d+", text)
        if numbers:
            repay_amt = int("".join(numbers))
            db["total_debt"] = max(0, db["total_debt"] - repay_amt)
            user_states[user_id] = None
            bar, hp_pct = get_hp_bar()
            reply_text = (
                f"💥 **【暴擊！強力還款斬擊！】**\n"
                f"⚔️ 造成傷害：-${repay_amt:,}\n"
                f"👹 剩餘血量：**${db['total_debt']:,}** ([{bar}] {hp_pct}%)\n"
                f"🔥 太神啦！離自由更近一步！"
            )
            await message.reply(
                reply_text, reply_markup=get_main_keyboard()
            )
            return

    elif current_state == "set_income":
        numbers = re.findall(r"\d+", text)
        if numbers:
            income = int("".join(numbers))
            db["monthly_income"] = income
            db["expense_limit"] = max(0, income - db["monthly_target"])
            user_states[user_id] = None
            fin = get_financial_summary()
            reply_text = (
                f"✅ **【收入更新成功】**\n"
                f"💵 收入: ${income:,} \vert{} 扣除還款: ${db['monthly_target']:,}\n"
                f"📁 可用上限：${db['expense_limit']:,}\n"
                f"💡 剩餘可用：**${fin['remaining_budget']:,}** (至 {fin['cycle_end']} 止，約 ${fin['daily_allowance']:,.0f}/天，剩 {fin['days_left']} 天)" ) await message.reply( reply_text, reply_markup=get_main_keyboard() ) return      elif current_state == "edit_expense": numbers = re.findall(r"\d+", text) if numbers: exp = int("".join(numbers)) db["current_expense"] = exp user_states[user_id] = None fin = get_financial_summary() reply_text = ( f"✅ **【已花費修正為：${exp:,}】**\n" f"💡 剩餘可用：**${fin['remaining_budget']:,}** (至 {fin['cycle_end']} 止，約 ${fin['daily_allowance']:,.0f}/天，剩 {fin['days_left']} 天)"
            )
            await message.reply(
                reply_text, reply_markup=get_main_keyboard()
            )
            return

    numbers = re.findall(r"\d+", text)
    if numbers:
        amount = int("".join(numbers))
        db["current_expense"] += amount
        fin = get_financial_summary()
        reply_text = (
            f"📥 已記帳：+${amount:,}\n"
            f"💸 本月累計：${db['current_expense']:,}\n" f"💡 剩餘可用：**${fin['remaining_budget']:,}** (至 {fin['cycle_end']} 止，約 ${fin['daily_allowance']:,.0f}/天，剩 {fin['days_left']} 天)"
        )
        await message.reply(reply_text, reply_markup=get_main_keyboard())
    else:
        await message.reply(
            "🤖 請直接傳送數字記帳，或點擊下方按鈕操作。",
            reply_markup=get_main_keyboard(),
        )


async def job_daily_expense_reminder():
    if ADMIN_CHAT_ID:
        fin = get_financial_summary()
        bar, hp_pct = get_hp_bar()
        try:
            reminder_text = (
                f"⏰ **【每日財務打卡提醒】**\n"
                f"👹 血量：${db['total_debt']:,} ([{bar}] {hp_pct}%)\n"
                f"• 累計花費：${db['current_expense']:,}\n"
                f"• 剩餘可用：${fin['remaining_budget']:,} (至 {fin['cycle_end']} 止，約 ${fin['daily_allowance']:,.0f}/天，剩 {fin['days_left']} 天)\n"
                f"今天也要克制慾望，準備迎接下次暴擊！"
            )
            await bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=reminder_text,
                reply_markup=get_main_keyboard(),
            )
        except Exception as e:
            logging.error(f"Daily reminder failed: {e}")


class SimpleHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"RPG Debt Bot is alive and running!")


def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    HTTPServer(("0.0.0.0", port), SimpleHandler).serve_forever()


async def main():
    scheduler.add_job(
        job_daily_expense_reminder, "cron", hour=21, minute=0
    )
    scheduler.start()
    threading.Thread(target=run_web_server, daemon=True).start()
    logging.info("🌐 輕量網頁伺服器與機器人已全面啟動...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
