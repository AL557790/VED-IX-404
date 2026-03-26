import os
import json
import gc
import io
import uuid
import asyncio
import threading
import traceback
from datetime import datetime
from typing import Dict, Optional

from telegram import Update, InputFile, BotCommand
from telegram.ext import Application, CommandHandler, ContextTypes
from flask import Flask
import aiohttp

# ═══════════════════════════════════════════════════════════
# الإعدادات المباشرة (بدون .env)
# ═══════════════════════════════════════════════════════════

TOKEN = "8765969078:AAF0n0KlZ4ids7pTeDpAOlulsfaM1E-k1SI"
PORT = 10000
API_URL = "http://raw.thug4ff.xyz/info"
GENERATE_URL = "http://profile.thug4ff.xyz/api/profile"
CONFIG_FILE = "info_channels.json"

# ═══════════════════════════════════════════════════════════
# Flask للـ Health Check (لـ Render)
# ═══════════════════════════════════════════════════════════

app = Flask(__name__)
bot_name = "Loading..."

@app.route('/')
def home():
    return f"Bot {bot_name} is operational"

def run_flask():
    app.run(host='0.0.0.0', port=PORT)

# ═══════════════════════════════════════════════════════════
# كلاس أوامر Free Fire
# ═══════════════════════════════════════════════════════════

class FreeFireBot:
    def __init__(self):
        self.application = Application.builder().token(TOKEN).build()
        self.session: Optional[aiohttp.ClientSession] = None  # ← لا ننشئه هنا
        self.config_data = self.load_config()
        self.cooldowns: Dict[int, datetime] = {}
        
        self._register_handlers()
    
    def _register_handlers(self):
        """تسجيل جميع الأوامر"""
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("help", self.cmd_help))
        self.application.add_handler(CommandHandler("ping", self.cmd_ping))
        self.application.add_handler(CommandHandler("info", self.player_info))
        self.application.add_handler(CommandHandler("infochannels", self.list_info_channels))
        self.application.add_handler(CommandHandler("setinfochannel", self.set_info_channel))
        self.application.add_handler(CommandHandler("removeinfochannel", self.remove_info_channel))
        self.application.add_error_handler(self.error_handler)

    def convert_unix_timestamp(self, timestamp) -> str:
        """تحويل Unix timestamp إلى تاريخ مقروء"""
        try:
            if isinstance(timestamp, str):
                timestamp = int(timestamp)
            return datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
        except:
            return "غير معروف"

    def load_config(self):
        """تحميل الإعدادات"""
        default_config = {
            "servers": {},
            "global_settings": {
                "default_cooldown": 30,
                "default_daily_limit": 30
            }
        }
        
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                    loaded_config.setdefault("global_settings", {})
                    loaded_config["global_settings"].setdefault("default_cooldown", 30)
                    loaded_config.setdefault("servers", {})
                    return loaded_config
            except Exception as e:
                print(f"Error loading config: {e}")
                return default_config
        return default_config

    def save_config(self):
        """حفظ الإعدادات"""
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config_data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving config: {e}")

    def is_channel_allowed(self, chat_id: int) -> bool:
        """التحقق من السماح بالدردشة"""
        try:
            chat_id_str = str(chat_id)
            allowed_chats = self.config_data["servers"].get(chat_id_str, {}).get("info_channels", [])
            return len(allowed_chats) == 0 or chat_id_str in allowed_chats
        except Exception as e:
            print(f"Error checking channel: {e}")
            return True

    async def is_admin(self, update: Update) -> bool:
        """التحقق من المشرف"""
        try:
            if update.effective_chat.type == "private":
                return True
            
            user_id = update.effective_user.id
            chat_id = update.effective_chat.id
            member = await self.application.bot.get_chat_member(chat_id, user_id)
            return member.status in ["administrator", "creator"]
        except Exception as e:
            print(f"Error checking admin: {e}")
            return False

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """بدء البوت"""
        welcome_text = f"""
👋 **أهلاً بك في Free Fire Info Bot!**

🎮 **ما يمكنني فعله:**
• عرض معلومات أي لاعب Free Fire
• عرض الرتب والمستويات
• معلومات العشيرة والحيوان
• إنشاء صورة البروفايل

📌 **ابدأ باستخدام:** `/info <UID>`

مثال: `/info 123456789`
        """
        await update.message.reply_text(welcome_text, parse_mode='Markdown')

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """المساعدة"""
        help_text = """
🤖 **الأوامر المتاحة:**

📋 **عامة:**
/start - بدء البوت
/help - عرض المساعدة
/ping - فحص سرعة البوت

🎮 **Free Fire:**
/info `<UID>` - معلومات اللاعب
/infochannels - الدردشات المفعلة

⚙️ **للمشرفين:**
/setinfochannel - تفعيل البوت هنا
/removeinfochannel - إلغاء التفعيل

💡 **نصيحة:** 
الـ UID يجب أن يكون 6 أرقام على الأقل.
        """
        await update.message.reply_text(help_text, parse_mode='Markdown')

    async def cmd_ping(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """فحص السرعة"""
        import time
        start = time.time()
        msg = await update.message.reply_text("🏓 Pong!")
        ping = round((time.time() - start) * 1000, 2)
        await msg.edit_text(f"🏓 **Pong!** `{ping}ms`", parse_mode='Markdown')

    async def set_info_channel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """تفعيل البوت في الدردشة"""
        if not await self.is_admin(update):
            return await update.message.reply_text("❌ للمشرفين فقط!")
        
        chat_id = str(update.effective_chat.id)
        self.config_data["servers"].setdefault(chat_id, {"info_channels": [], "config": {}})
        
        if chat_id not in self.config_data["servers"][chat_id]["info_channels"]:
            self.config_data["servers"][chat_id]["info_channels"].append(chat_id)
            self.save_config()
            await update.message.reply_text("✅ تم تفعيل البوت في هذه الدردشة")
        else:
            await update.message.reply_text("ℹ️ البوت مفعل بالفعل")

    async def remove_info_channel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """إلغاء تفعيل البوت"""
        if not await self.is_admin(update):
            return await update.message.reply_text("❌ للمشرفين فقط!")
        
        chat_id = str(update.effective_chat.id)
        if chat_id in self.config_data["servers"]:
            channels = self.config_data["servers"][chat_id].get("info_channels", [])
            if chat_id in channels:
                channels.remove(chat_id)
                self.save_config()
                await update.message.reply_text("✅ تم إلغاء التفعيل")
            else:
                await update.message.reply_text("ℹ️ البوت غير مفعل هنا")

    async def list_info_channels(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """عرض القنوات المفعلة"""
        chat_id = str(update.effective_chat.id)
        
        if chat_id in self.config_data["servers"]:
            channels = self.config_data["servers"][chat_id].get("info_channels", [])
            if channels:
                text = "📋 **الدردشات المفعلة:**\n"
                for ch in channels:
                    text += f"• `{ch}`\n"
                
                cooldown = self.config_data["servers"][chat_id]["config"].get("cooldown", 30)
                text += f"\n⏱ **الانتظار:** {cooldown}ث"
                await update.message.reply_text(text, parse_mode='Markdown')
                return
        
        await update.message.reply_text("📋 **الحالة:** السماح للجميع")

    async def player_info(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """جلب معلومات اللاعب"""
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        
        if not self.is_channel_allowed(chat_id):
            return await update.message.reply_text("❌ غير مسموح هنا")
        
        if not context.args or len(context.args) < 1:
            return await update.message.reply_text(
                "⚠️ **الاستخدام:** `/info <UID>`\n\nمثال: `/info 123456789`",
                parse_mode='Markdown'
            )
        
        uid = context.args[0]
        
        if not uid.isdigit() or len(uid) < 6:
            return await update.message.reply_text(
                "❌ **UID غير صالح!**\nيجب أن يكون 6 أرقام على الأقل",
                parse_mode='Markdown'
            )
        
        cooldown = self.config_data["global_settings"]["default_cooldown"]
        chat_id_str = str(chat_id)
        if chat_id_str in self.config_data["servers"]:
            cooldown = self.config_data["servers"][chat_id_str]["config"].get("cooldown", cooldown)
        
        if user_id in self.cooldowns:
            elapsed = (datetime.now() - self.cooldowns[user_id]).seconds
            if elapsed < cooldown:
                return await update.message.reply_text(f"⏳ انتظر {cooldown - elapsed}ث")
        
        self.cooldowns[user_id] = datetime.now()
        
        processing_msg = await update.message.reply_text("🔍 جاري البحث...")
        
        try:
            async with self.session.get(f"{API_URL}?uid={uid}&key=great") as resp:
                if resp.status == 404:
                    await processing_msg.delete()
                    return await self._send_not_found(update, uid)
                if resp.status != 200:
                    await processing_msg.delete()
                    return await self._send_api_error(update)
                
                data = await resp.json()
            
            basic = data.get('basicInfo', {})
            captain = data.get('captainBasicInfo', {})
            clan = data.get('clanBasicInfo', {})
            credit = data.get('creditScoreInfo', {})
            pet = data.get('petInfo', {})
            profile = data.get('profileInfo', {})
            social = data.get('socialInfo', {})
            
            region = basic.get('region', 'غير موجود')
            
            msg = self._build_message(uid, basic, captain, clan, credit, pet, profile, social, region)
            
            await processing_msg.delete()
            await update.message.reply_text(msg, parse_mode='Markdown')
            
            await self._send_profile_image(update, uid, region)
            
        except Exception as e:
            await processing_msg.delete()
            await update.message.reply_text(f"❌ خطأ: {str(e)[:100]}")
            traceback.print_exc()
        finally:
            gc.collect()

    def _build_message(self, uid, basic, captain, clan, credit, pet, profile, social, region):
        """بناء رسالة المعلومات"""
        msg = f"""
🎮 **معلومات اللاعب**

📋 **الأساسية:**
├─ الاسم: `{basic.get('nickname', 'غير موجود')}`
├─ UID: `{uid}`
├─ المستوى: {basic.get('level', '?')} (XP: {basic.get('exp', '?')})
├─ المنطقة: {region}
├─ الإعجابات: {basic.get('liked', '?')}
├─ نقاط الشرف: {credit.get('creditScore', '?')}
└─ التوقيع: {social.get('signature', 'لا يوجد') or 'لا يوجد'}

📊 **النشاط:**
├─ الإصدار: {basic.get('releaseVersion', '?')}
├─ شارات BP: {basic.get('badgeCnt', '?')}
├─ رتبة BR: {basic.get('rankingPoints', '?') if basic.get('showBrRank') else 'مخفية'}
├─ رتبة CS: {basic.get('csRankingPoints', '?') if basic.get('showCsRank') else 'مخفية'}
├─ الإنشاء: {self.convert_unix_timestamp(basic.get('createAt', 0))}
└─ آخر دخول: {self.convert_unix_timestamp(basic.get('lastLoginAt', 0))}

👤 **البروفايل:**
├─ Avatar: {profile.get('avatarId', '?')}
├─ Banner: {basic.get('bannerId', '?')}
├─ Pin: {captain.get('pinId', '?') if captain else 'افتراضي'}
└─ المهارات: {profile.get('equipedSkills', '?')}

🐾 **الحيوان:**
├─ مجهز: {'نعم' if pet.get('isSelected') else 'لا'}
├─ الاسم: {pet.get('name', '?')}
├─ XP: {pet.get('exp', '?')}
└─ المستوى: {pet.get('level', '?')}
"""
        
        if clan:
            msg += f"""
🏰 **العشيرة:**
├─ الاسم: `{clan.get('clanName', '?')}`
├─ ID: `{clan.get('clanId', '?')}`
├─ المستوى: {clan.get('clanLevel', '?')}
└─ الأعضاء: {clan.get('memberNum', '?')}/{clan.get('capacity', '?')}
"""
            if captain:
                msg += f"""
👑 **القائد:**
├─ الاسم: `{captain.get('nickname', '?')}`
├─ UID: `{captain.get('accountId', '?')}`
├─ المستوى: {captain.get('level', '?')}
└─ آخر دخول: {self.convert_unix_timestamp(captain.get('lastLoginAt', 0))}
"""
        
        msg += "\n🔧 **DEVELOPED BY THUG**"
        return msg

    async def _send_profile_image(self, update: Update, uid: str, region: str):
        """إرسال صورة البروفايل"""
        if not region:
            return
        
        try:
            url = f"{GENERATE_URL}?uid={uid}"
            print(f"جاري جلب الصورة: {url}")
            
            async with self.session.get(url) as resp:
                if resp.status == 200:
                    img_data = await resp.read()
                    img_file = io.BytesIO(img_data)
                    img_file.name = f"profile_{uid}.png"
                    
                    await update.message.reply_photo(photo=img_file)
                    print("✅ تم إرسال الصورة")
                else:
                    print(f"❌ خطأ في الصورة: {resp.status}")
        except Exception as e:
            print(f"❌ فشل الصورة: {e}")

    async def _send_not_found(self, update: Update, uid: str):
        """رسالة اللاعب غير موجود"""
        await update.message.reply_text(f"""
❌ **اللاعب غير موجود**

UID `{uid}` غير موجود.

⚠️ ملاحظة: خوادم IND لا تعمل حالياً.
""", parse_mode='Markdown')

    async def _send_api_error(self, update: Update):
        """رسالة خطأ API"""
        await update.message.reply_text("⚠️ **خطأ في API**\n\nجرب مرة أخرى لاحقاً", parse_mode='Markdown')

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        """معالج الأخطاء"""
        print(f"⚠️ خطأ: {context.error}")
        traceback.print_exc()
        
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text("❌ حدث خطأ غير متوقع")

    # ═══════════════════════════════════════════════════════
    # تشغيل البوت - تم التعديل هنا
    # ═══════════════════════════════════════════════════════

    async def on_startup(self, app: Application):
        """عند بدء التشغيل - ننشئ الـ session هنا"""
        global bot_name
        
        # ← إنشاء الـ session هنا حيث يوجد event loop
        self.session = aiohttp.ClientSession()
        
        me = await app.bot.get_me()
        bot_name = me.username
        
        print(f"\n✅ Bot started: @{bot_name}")
        print(f"🆔 ID: {me.id}")
        
        # تشغيل Flask
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        print(f"🌐 Flask running on port {PORT}")
        
        # تعيين الأوامر
        await app.bot.set_my_commands([
            BotCommand("start", "بدء البوت"),
            BotCommand("help", "المساعدة"),
            BotCommand("ping", "فحص السرعة"),
            BotCommand("info", "معلومات لاعب"),
            BotCommand("infochannels", "القنوات المفعلة"),
            BotCommand("setinfochannel", "تفعيل البوت (للمشرفين)"),
            BotCommand("removeinfochannel", "إلغاء التفعيل (للمشرفين)"),
        ])

    async def on_shutdown(self, app: Application):
        """عند الإيقاف"""
        if self.session:
            await self.session.close()
        print("👋 Bot stopped")

    def run(self):
        """تشغيل البوت"""
        self.application.post_init = self.on_startup
        self.application.post_shutdown = self.on_shutdown
        
        print("🚀 Starting bot...")
        self.application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    bot = FreeFireBot()
    bot.run()
