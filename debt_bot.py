import os
import re
import logging
import calendar
from datetime import datetime
import easyocr
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ================= 參數設定 =================
TOKEN = "8914207417:AAGetEpgDvuf--poYSVsR51XFjDanAhGKa4"
ADMIN_CHAT_ID = 5370959021438146805  # 你的 Telegram 數字 ID

# 初始化 Bot 與 Dispatcher
bot = Bot(token=TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone="Asia/Taipei")

# 初始化 EasyOCR (支援繁體中文與英文/數字)
print("正在載入 EasyOCR 模型，請稍候...")
reader = easyocr.Reader(['ch_tra', 'en'])
print("OCR 模型載入完成！")

# 模擬資料庫狀態
db = {
    "total_debt": 874000,          # 總負債 Boss 血量
    "monthly_target": 50000,        # 每月固定還款目標
    "monthly_income": 0,           # 本月收入
    "expense_limit": 0,            # 本月開銷上限 (收入 - 50000)
    "current_expense": 0           # 本月已花費
}

user_states = {}       # 記錄使用者狀態 (如等待修改或輸入收入)
pending_payments = {}  # 暫存 OCR 辨識出來的還款金額

# ================= 核心計算輔助函式 =================
def get_financial_summary():
    progress = (874000 - db["total_debt"]) / 874000
    bar_len = 10
    filled = int(progress * bar_len)
    bar = "█" * filled + "░" * (bar_len - filled)
    
    remaining_budget = db["expense_limit"] - db["current_expense"]
    
    now = datetime.now()
    _, last_day = calendar.monthrange(now.year, now.month)
    remaining_days = max(1, last_day - now.day + 1)
    daily_allowance = remaining_budget / remaining_days
    
    status_emoji = "✨ 安全區內" if remaining_budget >= 0 else "🚨 已超支！"
    
    return {
        "progress": progress,
        "bar": bar,
        "remaining_budget": remaining_budget,
        "remaining_days": remaining_days,
        "daily_allowance": daily_allowance,
        "status_emoji": status_emoji
    }

# ================= 1. 指令與狀態查看 =================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "⚔️ **歡迎來到還款冒險機器人！**\n\n"
        f"🎯 終極 Boss 目標：清償 ${db['total_debt']:,} 負債\n"
        f"📅 每月還款目標：${db['monthly_target']:,}\n\n"
        "💡 **功能特色：**\n"
        "• 每日定時提醒記錄開銷\n"
        "• 每月 5 號/10 號引導輸入收入與試算預算\n"
        "• 傳送匯款截圖，自動 OCR 辨識金額扣血\n"
        "• 支援隨時修改/修正記帳或收入錯誤\n"
        "• 充滿打怪快感的 Boss 傷害特效與激勵回饋！"
    )
    await send_status_report(message.chat.id)

@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    await send_status_report(message.chat.id)

@dp.message(Command("edit"))
async def cmd_edit(message: types.Message):
    """讓使用者選擇要修正哪一個數值"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💵 修改本月收入", callback_data="edit_income"),
            InlineKeyboardButton(text="📉 修改本月已花費", callback_data="edit_expense")
        ],
        [
            InlineKeyboardButton(text="⚔️ 重設總負債(Boss血量)", callback_data="edit_debt")
        ]
    ])
    await message.answer("🛠️ **【數值修正中心】**\n請選擇你想修改的項目：", reply_markup=keyboard, parse_mode="Markdown")

async def send_status_report(chat_id: int):
    fin = get_financial_summary()

    text = (
        f"⚔️ **【對抗負債 Boss 戰報】**\n\n"
        f"目前總進度：[{fin['bar']}] {fin['progress']*100:.1f}%\n"
        f"👾 剩餘負債血量：**${db['total_debt']:,} / $874,000**\n"
        f"───────────────────\n"
        f"📊 **本月財務狀況：**\n"
        f"💵 本月登記收入：${db['monthly_income']:,}\n"
        f"🎯 固定還款目標：${db['monthly_target']:,}\n"
        f"🛍️ 本月花費上限：${db['expense_limit']:,}\n"
        f"📉 目前已花費：${db['current_expense']:,}\n"
        f"💰 本月剩餘可用：**${fin['remaining_budget']:,}** ({fin['status_emoji']})\n"
        f"⏳ 本月剩餘 {fin['remaining_days']} 天\n"
        f"💡 **建議每日可花費：約 ${fin['daily_allowance']:,.0f} / 天**"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 查看目前進度", callback_data="btn_status"),
            InlineKeyboardButton(text="💵 新增收入登記", callback_data="btn_input_income")
        ],
        [
            InlineKeyboardButton(text="🛠️ 修正錯誤數值", callback_data="btn_edit_menu"),
            InlineKeyboardButton(text="💳 上傳還款憑證", callback_data="btn_upload")
        ]
    ])

    await bot.send_message(chat_id, text, reply_markup=keyboard, parse_mode="Markdown")

# ================= 2. 定時推播任務 =================
async def job_daily_expense_reminder():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 查看目前進度", callback_data="btn_status")]
    ])
    await bot.send_message(
        ADMIN_CHAT_ID,
        "🌙 **【每日記帳打卡提醒】**\n今天有產生新的日常開銷嗎？請隨手傳送金額與備註給我（例如：`午餐 150`）！💪",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

async def job_settlement_reminder():
    user_states[ADMIN_CHAT_ID] = "waiting_for_income"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💵 新增收入登記", callback_data="btn_input_income")]
    ])
    await bot.send_message(
        ADMIN_CHAT_ID,
        "🔔 **【5號 / 10號：財務結算與還款日】**\n\n"
        "今天是固定還款與結算日！\n"
        "1️⃣ 請點擊下方按鈕登記本月「總收入金額」。\n"
        "2️⃣ 隨後請上傳銀行轉帳截圖，將自動辨識並扣減 Boss 血量！⚔️",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

# ================= 3. 互動按鈕與修改選單處理 =================
@dp.callback_query(F.data == "btn_status")
async def cb_status(callback: types.CallbackQuery):
    await send_status_report(callback.message.chat.id)
    await callback.answer()

@dp.callback_query(F.data == "btn_input_income")
async def cb_input_income(callback: types.CallbackQuery):
    user_states[callback.from_user.id] = "waiting_for_income"
    await callback.message.answer("💵 請直接回覆輸入你本月的**總收入金額**（例如：`60000`）：")
    await callback.answer()

@dp.callback_query(F.data == "btn_edit_menu")
async def cb_edit_menu(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💵 修改本月收入", callback_data="edit_income"),
            InlineKeyboardButton(text="📉 修改本月已花費", callback_data="edit_expense")
        ],
        [
            InlineKeyboardButton(text="⚔️ 重設總負債(Boss血量)", callback_data="edit_debt")
        ]
    ])
    await callback.message.answer("🛠️ **【數值修正中心】**\n請選擇你想修改的項目：", reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data.in_({"edit_income", "edit_expense", "edit_debt"}))
async def cb_set_edit_state(callback: types.CallbackQuery):
    user_states[callback.from_user.id] = callback.data
    names = {
        "edit_income": "本月總收入",
        "edit_expense": "本月已花費金額",
        "edit_debt": "總負債 (Boss 剩餘血量)"
    }
    await callback.message.answer(f"✏️ 請直接回覆輸入新的 **{names[callback.data]}** 數字：")
    await callback.answer()

@dp.callback_query(F.data == "confirm_pay")
async def cb_confirm_pay(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    amount = pending_payments.get(user_id, 0)

    if amount > 0:
        db["total_debt"] = max(0, db["total_debt"] - amount)
        fin = get_financial_summary()
        
        effect_msg = (
            f"💥 **【CRITICAL HIT! 暴擊傷害！】** 💥\n"
            f"⚡ 釋放神聖還款波動：`- ${amount:,}`\n\n"
            f"👾 **【Boss 慘叫：『可惡...竟然被你還掉了一大筆！』】**\n"
            f"⚔️ 剩餘負債血量：**${db['total_debt']:,} / $874,000**\n"
            f"📈 目前通關進度：`[{fin['bar']}] {fin['progress']*100:.1f}%`\n\n"
            f"🏆 **太帥了！離無債一身輕的傳說又更近了一步！繼續保持！🔥**"
        )
        await callback.message.edit_text(effect_msg, parse_mode="Markdown")
        del pending_payments[user_id]
    await callback.answer()

@dp.callback_query(F.data == "cancel_pay")
async def cb_cancel_pay(callback: types.CallbackQuery):
    await callback.message.edit_text("❌ 已取消本次還款扣血。")
    await callback.answer()

# ================= 4. 訊息與截圖處理 =================
@dp.message(F.photo)
async def handle_screenshot(message: types.Message):
    photo = message.photo[-1]
    file_info = await bot.get_file(photo.file_id)
    file_path = f"temp_{message.from_user.id}.jpg"
    
    await bot.download_file(file_info.file_path, file_path)
    processing_msg = await message.reply("🔍 收到截圖！正在進行 OCR 智慧辨識金額中，請稍候...")

    try:
        results = reader.readtext(file_path, detail=0)
        full_text = " ".join(results)
    except Exception as e:
        full_text = ""
        logging.error(f"OCR Error: {e}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

    matches = re.findall(r'(?:NT\$|\$|\b)\s*([1-9]\d{0,2}(?:,\d{3})+|[1-9]\d{3,6})\s*(?:元|\b)', full_text)
    await bot.delete_message(chat_id=message.chat.id, message_id=processing_msg.message_id)

    if matches:
        detected_amount = int(matches[0].replace(',', ''))
        pending_payments[message.from_user.id] = detected_amount

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text=f"⚔️ 轟炸 Boss 扣血 ${detected_amount:,}", callback_data="confirm_pay"),
                InlineKeyboardButton(text="❌ 取消", callback_data="cancel_pay")
            ]
        ])

        await message.reply(
            f"🎯 **【OCR 辨識成功，準備發動攻擊！】**\n\n"
            f"偵測到轉帳匯款金額：**${detected_amount:,}**\n"
            f"是否要對負債 Boss 發動本次還款攻擊？",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    else:
        await message.reply(
            "⚠️ 抱歉，未能從截圖中自動清晰辨識出金額。\n"
            "請直接回覆數字（例如：`25000`），我將為您手動執行扣血！"
        )

@dp.message(F.text & ~F.text.startswith("/"))
async def handle_text_input(message: types.Message):
    user_id = message.from_user.id
    text = message.text.strip()
    current_state = user_states.get(user_id)

    # 1. 處理狀態：修改收入
    if current_state == "waiting_for_income" or current_state == "edit_income":
        numbers = re.findall(r'\d+', text)
        if numbers:
            income = int("".join(numbers))
            db["monthly_income"] = income
            db["expense_limit"] = max(0, income - db["monthly_target"])
            user_states[user_id] = None

            fin = get_financial_summary()
            await message.reply(
                f"✅ **【本月收入更新成功】**\n"
                f"💵 登記收入：${income:,}\id"
                f"⚔️ 預定扣除還款：${db['monthly_target']:,}\n"
                f"───────────────────\n"
                f"🛍️ 本月可用開銷上限：${db['expense_limit']:,}\n"
                f"💡 剩餘可用：**${fin['remaining_budget']:,}** (約 ${fin['daily_allowance']:,.0f}/天)" ) return      # 2. 處理狀態：修改已花費 elif current_state == "edit_expense": numbers = re.findall(r'\d+', text) if numbers: exp = int("".join(numbers)) db["current_expense"] = exp user_states[user_id] = None              fin = get_financial_summary() await message.reply(f"✅ **【本月已花費金額已修正為：${exp:,}】**\n目前剩餘可用：${fin['remaining_budget']:,}")
            return

    # 3. 處理狀態：修改總負債
    elif current_state == "edit_debt":
        numbers = re.findall(r'\d+', text)
        if numbers:
            debt = int("".join(numbers))
            db["total_debt"] = debt
            user_states[user_id] = None

            fin = get_financial_summary()
            await message.reply(f"✅ **【總負債 Boss 血量已修正為：${debt:,}】**\n目前通關進度：{fin['progress']*100:.1f}%")
            return

    # 4. 一般文字：預設當作「記帳」處理
    numbers = re.findall(r'\d+', text)
    if numbers:
        amount = int(numbers[0])
        db["current_expense"] += amount
        
        fin = get_financial_summary()
        warning = ""
        if fin['remaining_budget'] < 0:
            warning = f"\n\n🚨 **【警告】本月日常開銷已超支！超出金額：${abs(fin['remaining_budget']):,}**"
        else:
            warning = f"\n\n✨ 記帳成功！本月剩餘可用：${fin['remaining_budget']:,} (約可花 ${fin['daily_allowance']:,.0f}/天)"

        await message.reply(f"📝 記錄消費：**${amount}** ({text}){warning}", parse_mode="Markdown")
    else:
        await message.reply("💡 看不太懂這筆消費，直接輸入數字與備註即可記帳（例如：`晚餐 150`），或輸入 /edit 修改資料。")

# ================= 5. 啟動主程式 =================
async def main():
    scheduler.add_job(job_daily_expense_reminder, 'cron', hour=21, minute=0)
    scheduler.add_job(job_settlement_reminder, 'cron', day='5,10', hour=9, minute=0)
    scheduler.start()
    print("🤖 Telegram 還款機器人已成功啟動並開始監聽...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())