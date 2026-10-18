import asyncio
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


def get_financial_summary():
    remaining_budget = db["expense_limit"] - db["current_expense"]
    daily_allowance = max(0, remaining_budget / 30)
    return {
        "remaining_budget": remaining_budget,
        "daily_allowance": daily_allowance,
    }


# 計算打怪血量百分比視覺條
def get_hp_bar():
    initial_debt = 874000
    current_debt = max(0, db["total_debt"])
    percentage = min(1.0, current_debt / initial_debt)
    filled_blocks = int(percentage * 10)
    empty_blocks = 10 - filled_blocks
    bar = "█" * filled_blocks + "░" * empty_blocks
    return bar, int(percentage * 100)


# 產生主選單按鈕 (加入 RPG 還款與記帳按鈕)
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
        f"🎮 **【RPG 討伐 87萬巨獸系統啟動！】**\n\n"
        f"👹 **巨獸血量 (總債務)**：${db['total_debt']:,}\n" f"[{bar}] {hp_pct}\%\n\n" f"🎯 每月還款目標：**${db['monthly_target']:,}**\n" f"💸 本月已花費：**${db['current_expense']:,}**\n" f"💡 本月剩餘可用：**${fin['remaining_budget']:,}** (約 ${fin['daily_allowance']:,.0f}/天)\n\n"
        f"📌 **直接輸入數字（例如 `150`）記錄日常開銷，或點擊下方按鈕展開冒險！**",
        reply_markup=get_main_keyboard(),
    )


@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    fin = get_financial_summary()
    bar, hp_pct = get_hp_bar()
    await message.reply(
        f"📊 **【巨獸戰鬥狀態】**\n"
        f"👹 剩餘血量：${db['total_debt']:,}\n"
        f"[{bar}] {hp_pct}%\n\n"
        f"• 每月還款目標：${db['monthly_target']:,}\n"
        f"• 本月收入：${db['monthly_income']:,}\n"
        f"• 可用開銷上限：${db['expense_limit']:,}\n"
        f"• 已花費：${db['current_expense']:,}\n" f"• 剩餘可用：**${fin['remaining_budget']:,}** (約 ${fin['daily_allowance']:,.0f}/天)",
        reply_markup=get_main_keyboard(),
    )


@dp.message(Command("income"))
async def cmd_income(message: types.Message):
    user_id = message.from_user.id
    user_states[user_id] = "set_income"
    await message.reply(
        "💰 請回傳你**本月的總收入金額**（例如：`60000`）："
    )


@dp.message(Command("edit"))
async def cmd_edit(message: types.Message):
    user_id = message.from_user.id
    user_states[user_id] = "edit_expense"
    await message.reply(
        f"✏️ 目前本月已花費為 **${db['current_expense']:,}**。\n"
        f"請直接傳送你想**修正後的正確總金額**（例如：`3500`）："
    )


# 處理按鈕點擊事件 (Callback Query)
@dp.callback_query(F.data.startswith("btn_"))
async def handle_callback_query(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    action = callback.data

    if action == "btn_status":
        fin = get_financial_summary()
        bar, hp_pct = get_hp_bar()
        await callback.message.edit_text(
            f"📊 **【巨獸戰鬥狀態】**\n"
            f"👹 剩餘血量：${db['total_debt']:,}\n"
            f"[{bar}] {hp_pct}%\n\n"
            f"• 每月還款目標：${db['monthly_target']:,}\n"
            f"• 本月收入：${db['monthly_income']:,}\n"
            f"• 可用開銷上限：${db['expense_limit']:,}\n"
            f"• 已花費：${db['current_expense']:,}\n" f"• 剩餘可用：**${fin['remaining_budget']:,}** (約 ${fin['daily_allowance']:,.0f}/天)",
            reply_markup=get_main_keyboard(),
        )
    elif action == "btn_repay":
        user_states[user_id] = "do_repay"
        await callback.message.reply(
            f"⚔️ **準備對巨獸發動還款攻擊！**\n"
            f"目前巨獸血量：${db['total_debt']:,}\n"
            f"請直接傳送你這次**還款的金額**（例如：`10000`）："
        )
    elif action == "btn_income":
        user_states[user_id] = "set_income"
        await callback.message.reply(
            "💰 請回傳你**本月的總收入金額**（例如：`60000`）："
        )
    elif action == "btn_edit_exp":
        user_states[user_id] = "edit_expense"
        await callback.message.reply(
            f"✏️ 目前本月已花費為 **${db['current_expense']:,}**。\n"
            f"請直接傳送你想**修正後的正確總金額**（例如：`3500`）："
        )

    await callback.answer()


# 處理文字訊息（記帳、還款攻擊、狀態輸入）
@dp.message(F.text)
async def handle_text_message(message: types.Message):
    user_id = message.from_user.id
    text = message.text.strip()
    current_state = user_states.get(user_id)

    # 1. 執行還款攻擊 (自動從總債務扣除)
    if current_state == "do_repay":
        numbers = re.findall(r"\d+", text)
        if numbers:
            repay_amt = int("".join(numbers))
            db["total_debt"] = max(0, db["total_debt"] - repay_amt)
            user_states[user_id] = None
            bar, hp_pct = get_hp_bar()

            await message.reply(
                f"💥 **【暴擊！對巨獸使出強力還款斬擊！】**\n"
                f"⚔️ 造成傷害：-${repay_amt:,}\n"
                f"👹 巨獸剩餘血量：**${db['total_debt']:,}**\n"
                f"[{bar}] {hp_pct}%\n"
                f"太神啦！離解鎖完全自由又更近了一步！🔥",
                reply_markup=get_main_keyboard(),
            )
            return

    # 2. 設定本月收入
    elif current_state == "set_income":
        numbers = re.findall(r"\d+", text)
        if numbers:
            income = int("".join(numbers))
            db["monthly_income"] = income
            db["expense_limit"] = max(0, income - db["monthly_target"])
            user_states[user_id] = None

            fin = get_financial_summary()
            await message.reply(
                f"✅ **【本月收入更新成功】**\n"
                f"💵 登記收入：${income:,}\n"
                f"❌ 預定扣除還款：${db['monthly_target']:,}\n"
                f"--------------------\n"
                f"📁 本月可用開銷上限：${db['expense_limit']:,}\n" f"💡 剩餘可用：**${fin['remaining_budget']:,}** (約 ${fin['daily_allowance']:,.0f}/天)",
                reply_markup=get_main_keyboard(),
            )
            return

    # 3. 修正已花費金額
    elif current_state == "edit_expense":
        numbers = re.findall(r"\d+", text)
        if numbers:
            exp = int("".join(numbers))
            db["current_expense"] = exp
            user_states[user_id] = None

            fin = get_financial_summary()
            await message.reply(
                f"✅ **【本月已花費金額已修正為：${exp:,}】**\n"
                f"目前剩餘可用：${fin['remaining_budget']:,}",
                reply_markup=get_main_keyboard(),
            )
            return

    # 4. 預設行為：記錄日常開銷金額 (一般記帳)
    numbers = re.findall(r"\d+", text)
    if numbers:
        amount = int("".join(numbers))
        db["current_expense"] += amount
        fin = get_financial_summary()
        await message.reply(
            f"📥 已記帳：+${amount:,}\n"
            f"💸 本月累計花費：${db['current_expense']:,}\n"
            f"💡 剩餘可用預算：**${fin['remaining_budget']:,}**",
            reply_markup=get_main_keyboard(),
        )
    else:
        await message.reply(
            "🤖 看不太懂你的指令呢！可以直接傳送數字記帳，或點擊下方按鈕操作。",
            reply_markup=get_main_keyboard(),
        )


# ==================== 2. 定時任務 (apscheduler) ====================


async def job_daily_expense_reminder():
    if ADMIN_CHAT_ID:
        fin = get_financial_summary()
        bar, hp_pct = get_hp_bar()
        try:
            await bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=(
                    f"⏰ **【每日財務打卡提醒】**\n"
                    f"👹 巨獸目前血量：${db['total_debt']:,} [{bar}] {hp_pct}%\n"
                    f"• 今日累計花費：${db['current_expense']:,}\n"
                    f"• 剩餘可用預算：${fin['remaining_budget']:,}\n"
                    f"今天也要克制慾望，準備迎來下次的還款暴擊！"
                ),
                reply_markup=get_main_keyboard(),
            )
        except Exception as e:
            logging.error(f"Daily reminder failed: {e}")


# ==================== 3. 假網頁伺服器 (通過 Render Port 檢測) ====================


class SimpleHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"RPG Debt Bot is alive and running!")


def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHandler)
    server.serve_forever()


# ==================== 4. 主程式啟動入口 ====================


async def main():
    scheduler.add_job(
        job_daily_expense_reminder, "cron", hour=21, minute=0
    )
    scheduler.start()

    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    logging.info("🌐 輕量網頁伺服器已在背景啟動...")

    logging.info("🤖 RPG 還款機器人已成功啟動並開始監聽...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
