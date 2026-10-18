import asyncio
import logging
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

# 讀取環境變數
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")  # 選填，可用於主動推播

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

# 記錄用戶目前的操作狀態 (例如: "edit_expense", "edit_debt", "set_income")
user_states = {}


def get_financial_summary():
    remaining_budget = db["expense_limit"] - db["current_expense"]
    # 假設以當月剩餘天數計算每日可用 (簡化為當前剩餘可用)
    daily_allowance = max(0, remaining_budget / 30)
    return {
        "remaining_budget": remaining_budget,
        "daily_allowance": daily_allowance,
    }


# ==================== 1. Telegram 機器人指令與互動 ====================


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    user_states[user_id] = None
    fin = get_financial_summary()
    await message.reply(
        f"🎮 **【還款打怪 RPG 機器人啟動成功！】**\n\n"
        f"📊 目前總債務：**${db['total_debt']:,}**\n"
        f"🎯 每月還款目標：**${db['monthly_target']:,}**\n"
        f"💸 本月已花費：**${db['current_expense']:,}**\n"
        f"💡 本月剩餘可用：**${fin['remaining_budget']:,}** (約 ${fin['daily_allowance']:,.0f}/天)\n\n"
        f"📌 **可用指令選單：**\n"
        f"• 直接輸入數字（例如 `150`）來記錄今日開銷\n"
        f"• `/status` - 查看目前財務與打怪進度\n"
        f"• `/income` - 設定本月總收入\n"
        f"• `/edit` - 修正本月已花費金額\n"
        f"• `/debt` - 修改總債務金額"
    )


@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    fin = get_financial_summary()
    await message.reply(
        f"📊 **【目前財務狀態】**\n"
        f"• 總債務：${db['total_debt']:,}\n"
        f"• 每月還款目標：${db['monthly_target']:,}\n"
        f"• 本月收入：${db['monthly_income']:,}\n"
        f"• 可用開銷上限：${db['expense_limit']:,}\n"
        f"• 已花費：${db['current_expense']:,}\n" f"• 剩餘可用：**${fin['remaining_budget']:,}** (約 ${fin['daily_allowance']:,.0f}/天)"
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


@dp.message(Command("debt"))
async def cmd_debt(message: types.Message):
    user_id = message.from_user.id
    user_states[user_id] = "edit_debt"
    await message.reply(
        f"🚨 目前總債務為 **${db['total_debt']:,}**。\n"
        f"請直接傳送你**最新的總債務金額**："
    )


# 處理文字訊息（記帳、狀態輸入）
@dp.message(F.text)
async def handle_text_message(message: types.Message):
    user_id = message.from_user.id
    text = message.text.strip()
    current_state = user_states.get(user_id)

    # 1. 設定本月收入
    if current_state == "set_income":
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
                f"📁 本月可用開銷上限：${db['expense_limit']:,}\n"
                f"💡 剩餘可用：**${fin['remaining_budget']:,}** (約 ${fin['daily_allowance']:,.0f}/天)" 
            ) 
            return      
            # 2. 修正已花費金額 
        elif current_state == "edit_expense": 
            numbers = re.findall(r"\d+", text) 
            if numbers: 
               exp = int("".join(numbers))  
               db["current_expense"] = exp 
               user_states[user_id] = None              
               fin = get_financial_summary() 
               await message.reply( 
                   f"✅ **【本月已花費金額已修正為：${exp:,}】**\n目前剩餘可用：${fin['remaining_budget']:,}"
            )
            return

    # 3. 修改總債務
    elif current_state == "edit_debt":
        numbers = re.findall(r"\d+", text)
        if numbers:
            debt = int("".join(numbers))
            db["total_debt"] = debt
            user_states[user_id] = None

            await message.reply(
                f"🎯 **【總債務金額已更新為：${debt:,}】** 繼續加油打怪！"
            )
            return

    # 4. 預設行為：記錄日常開銷金額
    numbers = re.findall(r"\d+", text)
    if numbers:
        amount = int("".join(numbers))
        db["current_expense"] += amount
        fin = get_financial_summary()
        await message.reply(
            f"📥 已記帳：+${amount:,}\n"
            f"💸 本月累計花費：${db['current_expense']:,}\n"
            f"💡 剩餘可用預算：**${fin['remaining_budget']:,}**"
        )
    else:
        await message.reply(
            "🤖 看不太懂你的指令呢！可以直接傳送數字記帳，或輸入 `/status` 查看狀態。"
        )


# ==================== 2. 定時任務 (apscheduler) ====================


async def job_daily_expense_reminder():
    if ADMIN_CHAT_ID:
        fin = get_financial_summary()
        try:
            await bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=(
                    f"⏰ **【每日財務打卡提醒】**\n"
                    f"• 今日累計花費：${db['current_expense']:,}\n"
                    f"• 剩餘可用預算：${fin['remaining_budget']:,}\n"
                    f"今天也要克制慾望，離解鎖自由更近一步！"
                ),
            )
        except Exception as e:
            logging.error(f"Daily reminder failed: {e}")


# ==================== 3. 假網頁伺服器 (通過 Render Port 檢測) ====================


class SimpleHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Debt Bot is alive and running!")


def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), SimpleHandler)
    server.serve_forever()


# ==================== 4. 主程式啟動入口 ====================


async def main():
    # 啟動定時任務排程
    scheduler.add_job(
        job_daily_expense_reminder, "cron", hour=21, minute=0
    )  # 每天晚上 9 點提醒
    scheduler.start()

    # 啟動背景網頁伺服器（用於滿足 Render Web Service 的 Port 需求）
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    logging.info("🌐 輕量網頁伺服器已在背景啟動...")

    logging.info("🤖 Telegram 還款機器人已成功啟動並開始監聽...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
