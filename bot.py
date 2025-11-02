import asyncio
import os
import logging
from pybalt import download
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram import F
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types import CallbackQuery
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

# Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN", "8587325148:AAEte0wJsoHP_4k5XVp1UZQ5pwtN7hN4eUQ")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "https://telegram-bot-t.onrender.com")  # Your domain
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

# Web app settings
WEB_SERVER_HOST = "0.0.0.0"
WEB_SERVER_PORT = int(os.getenv("PORT", 8080))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

user_data = {}

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    await message.reply(
        "Salom! Menga YouTube yoki Instagram havolasini yuboring.\n\n"
        "🎥 YouTube: Video yoki audio yuklab olish\n"
        "📸 Instagram: Post, Reel yoki Story yuklab olish"
    )

def create_download_keyboard(url: str):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎥 Video (720p)", callback_data=f"video_720_{url[:50]}"),
            InlineKeyboardButton(text="🎬 Video (1080p)", callback_data=f"video_1080_{url[:50]}")
        ],
        [
            InlineKeyboardButton(text="🎵 Audio (MP3)", callback_data=f"audio_{url[:50]}")
        ]
    ])
    return keyboard

@dp.message(F.text)
async def message_handler(message: types.Message):
    url = message.text.strip()
    
    is_youtube = url.startswith("https://youtube.com/") or url.startswith("https://www.youtube.com/") or url.startswith("https://youtu.be/")
    is_instagram = url.startswith("https://instagram.com/") or url.startswith("https://www.instagram.com/")
    
    if not is_youtube and not is_instagram:
        await message.reply("❌ Iltimos, to'g'ri YouTube yoki Instagram havolasini yuboring.")
        return

    user_data[message.from_user.id] = url
    
    if is_youtube:
        keyboard = create_download_keyboard(url)
        await message.reply("Yuklab olish turini tanlang:", reply_markup=keyboard)
    else:
        await download_content(message, url, "video", "720")

@dp.callback_query(F.data.startswith("video_") | F.data.startswith("audio_"))
async def callback_handler(callback: CallbackQuery):
    user_id = callback.from_user.id
    
    # Get full URL from user_data
    if user_id not in user_data:
        await callback.answer("❌ Havola topilmadi. Qaytadan yuboring.", show_alert=True)
        return
    
    url = user_data[user_id]
    data_parts = callback.data.split("_", 2)
    download_type = data_parts[0]
    
    if download_type == "video":
        quality = data_parts[1]
        await callback.message.edit_text("🎥 Videoni yuklab olinmoqda...")
        await download_content(callback.message, url, "video", quality)
    else:
        await callback.message.edit_text("🎵 Audioni yuklab olinmoqda...")
        await download_content(callback.message, url, "audio", None)
    
    await callback.answer()

async def download_content(message: types.Message, url: str, content_type: str, quality: str):
    abs_path = None
    try:
        if content_type == "audio":
            file_path = await download(
                url,
                audioFormat="mp3",
                filenameStyle="pretty",
                downloadMode="audio"
            )
        else:
            file_path = await download(
                url,
                videoQuality=quality,
                filenameStyle="pretty",
                remux=True
            )

        abs_path = os.path.abspath(file_path)
        logger.info(f"✅ Yuklab olindi: {abs_path}")

        if os.path.exists(abs_path):
            await message.reply("📤 Yuborilmoqda...")
            
            if content_type == "audio":
                audio_file = FSInputFile(abs_path)
                await bot.send_audio(
                    chat_id=message.chat.id,
                    audio=audio_file,
                    caption="🎵 @SnapTubeXBot"
                )
            else:
                video_file = FSInputFile(abs_path)
                await bot.send_video(
                    chat_id=message.chat.id,
                    video=video_file,
                    caption="🎬 @SnapTubeXBot "
                )
            
            logger.info("✅ Fayl muvaffaqiyatli yuborildi!")
        else:
            await message.reply("❌ Fayl topilmadi!")
    
    except Exception as e:
        logger.error(f"❌ Xato yuz berdi: {e}")
        await message.reply(f"❌ Yuklab olishda xato: {e}")
    
    finally:
        if abs_path and os.path.exists(abs_path):
            try:
                os.remove(abs_path)
                logger.info("🗑️ Fayl o'chirildi.")
            except Exception as e:
                logger.error(f"⚠️ Faylni o'chirishda xato: {e}")

async def on_startup(app):
    """Set webhook on startup"""
    webhook_info = await bot.get_webhook_info()
    if webhook_info.url != WEBHOOK_URL:
        await bot.set_webhook(
            url=WEBHOOK_URL,
            drop_pending_updates=True
        )
        logger.info(f"✅ Webhook o'rnatildi: {WEBHOOK_URL}")
    else:
        logger.info(f"✅ Webhook allaqachon o'rnatilgan: {WEBHOOK_URL}")

async def on_shutdown(app):
    """Remove webhook on shutdown"""
    await bot.delete_webhook()
    logger.info("🛑 Webhook o'chirildi")
    await bot.session.close()

def main():
    """Run the bot with webhook"""
    # Create aiohttp application
    app = web.Application()
    
    # Setup webhook handler
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    )
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    
    # Setup startup and shutdown
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    
    # Health check endpoint
    async def health_check(request):
        return web.Response(text="Bot is running!")
    
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    
    # Run app
    logger.info(f"🚀 Bot ishga tushmoqda: {WEB_SERVER_HOST}:{WEB_SERVER_PORT}")
    web.run_app(
        app,
        host=WEB_SERVER_HOST,
        port=WEB_SERVER_PORT,
    )

if __name__ == "__main__":
    main()
