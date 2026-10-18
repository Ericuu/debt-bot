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

# 直接從系統環境變數讀取
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

# 初始化日誌
logging.basicConfig(level=logging.INFO)

# 初始化 Bot 與 Dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
scheduler = AsyncIOScheduler(timezone="Asia/Taipei")

# 模擬資料庫與狀態管理 (總債務 $874,000，每月目標 $50,000)
db = {
    "total_debt": 874000,
    "monthly_target": 50000,
    "monthly_income": 0,
    "expense_limit": 0,
    "current_expense": 0,
}

# 記錄用戶目前的操作狀態
user_states = {}


# 精準計算以「每月 10 號」為週期的剩餘天數與每日可用額度
def get_financial_summary():
    remaining_budget = db["expense_limit"] - db["current_expense"]

    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    current_year = now.year
    current_month = now.month
    current_day = now.day

    if current_day >= 10:
        start_date = datetime.date(current_year, current_month, 10)
        if current_month == 12:
            end_date = datetime.date(current_year + 1, 1, 10)
        else:
            end_date = datetime.date(current_year, current_month + 1, 10)
    else:
        if current_month == 1:
            start_date = datetime.date(current_year - 1, 12, 10)
        else:
            start_date = datetime.date(current_year, current_month - 1, 10)
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


# 計算打怪血量百分比視覺條 (修正百分比符號跳脫)
def get_hp_bar():
    initial_debt = 874000
    current_debt = max(0, db["total_debt"])
    percentage = min(1.0, current_debt / initial_debt)
    filled_blocks = int(percentage * 10)
    empty_blocks = 10 - filled_blocks
    bar = "█" * filled_blocks + "░" * empty_blocks
    return bar, int(percentage * 100)


# 產生主選單按鈕
def get_main_keyboard():
    keyboard = InlineKeyboardMarkup(
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
    return keyboard


# ==================== 1. Telegram 機器人指令與按鈕互動 ====================


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    user_states[user_id] = None
    fin = get_financial_summary()
    bar, hp_pct = get_hp_bar()

    await message.reply(
        f"🎮 **【RPG 討伐 87萬巨獸系統（10號週期版）啟動！】**\n\n"
        f"👹 **巨獸血量 (總債務)**：${db['total_debt']:,}\n" f"[{bar}] {hp_pct}\%\n\n" f"🎯 每月還款目標：**${db['monthly_target']:,}**\n" f"💸 本月已花費：**${db['current_expense']:,}**\n" f"💡 剩餘可用：**${fin['remaining_budget']:,}** (至 {fin['cycle_end']} 止，約 ${fin['daily_allowance']:,.0f}/天，剩 {fin['days_left']} 天)\n\n"
        f"📌 **直接輸入數字記錄開銷，或點擊下方按鈕操作！**",
        reply_markup=get_main_keyboard(),
    )


@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    fin = get_financial_summary()
    bar, hp_pct = get_hp_bar()
    await message.reply(
        f"📊 **【巨獸戰鬥狀態 (10號週期)】**\n"
        f"👹 剩餘血量：${db['total_debt']:,}\n"
        f"[{bar}] {hp_pct}%\n\n"
        f"• 每月還款目標：${db['monthly_target']:,}\n"
        f"• 本月收入：${db['monthly_income']:,}\n"
        f"• 可用開銷上限：${db['expense_limit']:,}\n"
        f"• 已花費：${db['current_expense']:,}\n" f"• 剩餘可用：**${fin['remaining_budget']:,}** (至 {fin['cycle_end']} 止，約 ${fin['daily_allowance']:,.0f}/天，剩 {fin['days_left']} 天)",
        reply_markup=get_main_keyboard(),
    )


@dp.message(Command("income"))
async def cmd_income(message: types.Message):
    user_id = message.from_user.id
    user_states[user_id] = "set_income"
    await message.reply(
        "💰 請回傳你**本月的總收入金額**（例如：`70000`）："
    )


@dp.message(Command("edit"))
async def cmd_edit(message: types.Message):
    user_id = message.from_user.id
    user_states[user_id] = "edit_expense"
    await message.reply(
        f"✏️ 目前本月已花費為 **${db['current_expense']:,}**。\n"
        f"請直接傳送你想**修正後的正確總金額**（例如：`3500`）："
    )


@dp.callback_query(F.data.startswith("btn_"))
async def handle_callback_query(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    action = callback.data

    if action == "btn_status":
        fin = get_financial_summary()
        bar, hp_pct = get_hp_bar()
        await callback.message.edit_text(
            f"📊 **【巨獸戰鬥狀態 (10號週期)】**\n"
            f"👹 剩餘血量：${db['total_debt']:,}\n"
            f"[{bar}] {hp_pct}%\n\n"
            f"• 每月還款目標：${db['monthly_target']:,}\n"
            f"• 本月收入：${db['monthly_income']:,}\n"
            f"• 可用開銷上限：${db['expense_limit']:,}\n"
            f"• 已花費：${db['current_expense']:,}\n" f"• 剩餘可用：**${fin['remaining_budget']:,}** (至 {fin['cycle_end']} 止，約 ${fin['daily_allowance']:,.0f}/天，剩 {fin['days_left']} 天)",
            reply_markup=get_main_keyboard(),
        )
    elif action == "btn_repay":
        user_states[user_id] = "do_repay"
        await callback.message.reply(
            f"⚔️ **準備對巨獸發動還款攻擊！**\n"
            f"目前巨獸血量：${db['total_debt']:,}\n"
            f"請直接傳送你這次**還款的金額**（例如：`50000`）："
        )
    elif action == "btn_income":
        user_states[user_id] = "set_income"
        await callback.message.reply(
            "💰 請回傳你**本月的總收入金額**（例如：`70000`）："
        )
    elif action == "btn_edit_exp":
        user_states[user_id] = "edit_expense"
        await callback.message.reply(
            f"✏️ 目前本月已花費為 **${db['current_expense']:,}**。\n"
            f
