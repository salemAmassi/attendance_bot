import os
import json
import logging
import datetime
from datetime import timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

import pandas as pd
import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, 
    CommandHandler, 
    MessageHandler, 
    ContextTypes, 
    filters
)
from telegram.constants import ParseMode
from litellm import completion

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


@dataclass
class Config:
    """Configuration class for the bot"""
    SERVICE_ACCOUNT_FILE = 'peerless-aria-466111-h6-b8c14ab44514.json'
    SCOPES = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    TELEGRAM_TOKEN = os.getenv('BOT_TOKEN')
    TIMEZONE_OFFSET = 3  # hours
    
    # Spreadsheet names
    PARTICIPANTS_SPREADSHEET = "participants application | Rewaq"
    ATTENDANCE_SPREADSHEET = "Attendance Log | Rewaq"


class GoogleSheetsManager:
    """Handles all Google Sheets operations"""
    
    def __init__(self, config: Config):
        self.config = config
        self.credentials = Credentials.from_service_account_file(
            config.SERVICE_ACCOUNT_FILE, 
            scopes=config.SCOPES
        )
        self.client = gspread.authorize(self.credentials)
        self._participants_df = None
        
    @property
    def participants_df(self) -> pd.DataFrame:
        """Cached participants dataframe"""
        if self._participants_df is None:
            self._load_participants()
        return self._participants_df
    
    def _load_participants(self):
        """Load participants data from Google Sheets"""
        try:
            spreadsheet = self.client.open(self.config.PARTICIPANTS_SPREADSHEET)
            worksheet = spreadsheet.get_worksheet(0)
            data = worksheet.get_all_records()
            
            if data:
                self._participants_df = pd.DataFrame(data[1:], columns=data[0])
                self._participants_df = self._participants_df[['user_id', 'الاسم رباعي']]
            else:
                self._participants_df = pd.DataFrame(columns=['user_id', 'الاسم رباعي'])
                
        except Exception as e:
            logger.error(f"Error loading participants: {e}")
            self._participants_df = pd.DataFrame(columns=['user_id', 'الاسم رباعي'])
    
    def get_attendance_sheet(self):
        """Get attendance worksheet and records"""
        try:
            attendance_log = self.client.open(self.config.ATTENDANCE_SPREADSHEET)
            attendance_worksheet = attendance_log.get_worksheet(2)
            attendance_sheet = attendance_worksheet.get_all_records()
            return attendance_worksheet, attendance_sheet
        except Exception as e:
            logger.error(f"Error accessing attendance sheet: {e}")
            return None, []
    
    def get_achievements_sheet(self):
        """Get achievements worksheet"""
        try:
            spreadsheet = self.client.open(self.config.PARTICIPANTS_SPREADSHEET)
            return spreadsheet.get_worksheet(1)
        except Exception as e:
            logger.error(f"Error accessing achievements sheet: {e}")
            return None
    
    def get_telegram_chat_ids_sheet(self):
        """Get telegram chat IDs worksheet and data"""
        try:
            spreadsheet = self.client.open(self.config.PARTICIPANTS_SPREADSHEET)
            telegram_chat_ids = spreadsheet.get_worksheet(2)
            values = telegram_chat_ids.get_all_values()
            return telegram_chat_ids, values
        except Exception as e:
            logger.error(f"Error accessing telegram chat IDs sheet: {e}")
            return None, []


class AttendanceManager:
    """Handles attendance-related operations"""
    
    def __init__(self, sheets_manager: GoogleSheetsManager, config: Config):
        self.sheets_manager = sheets_manager
        self.config = config
    
    @staticmethod
    def get_today_str() -> str:
        """Get today's date as string"""
        return datetime.date.today().isoformat()
    
    @staticmethod
    def get_timestamp_with_timezone(hours_offset: int = 3) -> str:
        """Get current timestamp with timezone offset"""
        return (datetime.datetime.now() + timedelta(hours=hours_offset)).strftime("%Y-%m-%d %H:%M:%S")
    
    def has_checkin(self, attendance_sheet: List[Dict], user_id: str, date: str) -> bool:
        """Check if user has already checked in today"""
        return any(
            str(row.get('user_id')) == str(user_id) and row.get('day') == date
            for row in attendance_sheet
        )
    def has_checkout(self, attendance_sheet: List[Dict], user_id: str, timestamp: datetime) -> bool:
        """Check if user has already checked in today"""
        return any(
            str(row.get('user_id')) == str(user_id) and row.get('out') == timestamp
            for row in attendance_sheet
        )
    
    def get_user_name(self, user_id: str) -> Optional[str]:
        """Get user's full name by user_id"""
        try:
            participants = self.sheets_manager.participants_df
            if user_id in participants['user_id'].values:
                return participants.loc[participants['user_id'] == user_id, 'الاسم رباعي'].values[0]
            return None
        except Exception as e:
            logger.error(f"Error getting user name for {user_id}: {e}")
            return None
    
    def is_valid_user(self, user_id: str) -> bool:
        """Check if user_id exists in participants"""
        return user_id in self.sheets_manager.participants_df['user_id'].values
    
    def record_checkin(self, user_id: str) -> tuple[bool, str]:
        """Record user check-in"""
        try:
            attendance_worksheet, attendance_sheet = self.sheets_manager.get_attendance_sheet()
            if not attendance_worksheet:
                return False, "خطأ في الوصول لسجل الحضور"
            
            today = self.get_today_str()
            timestamp = self.get_timestamp_with_timezone(self.config.TIMEZONE_OFFSET)
            
            if self.has_checkin(attendance_sheet, user_id, today):
                user_name = self.get_user_name(user_id)
                return False, f"⚠️ {user_name} لقد قمتِ بتسجيل الدخول بالفعل اليوم."
            
            attendance_worksheet.append_row([user_id, timestamp, '', today])
            user_name = self.get_user_name(user_id)
            return True, f"✅ مرحباً {user_name}، نرجو لكِ يوماً سعيداً ومليئاً بالإنجازات 💙"
            
        except Exception as e:
            logger.error(f"Error recording checkin for {user_id}: {e}")
            return False, "حدث خطأ أثناء تسجيل الدخول"
    
    def record_checkout(self, user_id: str) -> tuple[bool, str]:
        """Record user check-out"""
        try:
            attendance_worksheet, attendance_sheet = self.sheets_manager.get_attendance_sheet()
            if not attendance_worksheet:
                return False, "خطأ في الوصول لسجل الحضور"
            
            today = self.get_today_str()
            timestamp = self.get_timestamp_with_timezone(self.config.TIMEZONE_OFFSET)
            user_name = self.get_user_name(user_id)
            
            if not self.has_checkout(attendance_sheet, user_id, timestamp):
                return False, f"⚠️ لقد قمتِ بتسجيل الخروج بالفعل اليوم، {user_name}."
            
            # Find the row index for the user_id and today
            row_index = next(
                (i + 2 for i, row in enumerate(attendance_sheet)
                 if str(row['user_id']) == str(user_id) and row['day'] == today),
                None
            )
            
            if row_index:
                attendance_worksheet.update_cell(row_index, 3, timestamp)
                return True, f"✅ تم تسجيل خروجكِ بنجاح، {user_name}. نأمل أن يكون يومكِ مليئاً بالإنجازات. 💙"
            else:
                return False, "خطأ في العثور على سجل الدخول"
                
        except Exception as e:
            logger.error(f"Error recording checkout for {user_id}: {e}")
            return False, "حدث خطأ أثناء تسجيل الخروج"


class UserManager:
    """Handles user registration and chat ID management"""
    
    def __init__(self, sheets_manager: GoogleSheetsManager):
        self.sheets_manager = sheets_manager
    
    def get_user_by_chat_id(self, chat_id: str) -> Optional[str]:
        """Get user_id by telegram chat_id"""
        try:
            _, values = self.sheets_manager.get_telegram_chat_ids_sheet()
            user = next((row for row in values if row[0] == chat_id), None)
            return user[1] if user else None
        except Exception as e:
            logger.error(f"Error getting user by chat ID {chat_id}: {e}")
            return None
    
    def is_chat_id_registered(self, chat_id: str) -> bool:
        """Check if chat_id is already registered"""
        try:
            _, values = self.sheets_manager.get_telegram_chat_ids_sheet()
            return any(row[0] == chat_id for row in values)
        except Exception as e:
            logger.error(f"Error checking chat ID registration {chat_id}: {e}")
            return False
    
    def register_chat_id(self, chat_id: str, user_id: str) -> tuple[bool, str]:
        """Register chat_id with user_id"""
        try:
            if self.is_chat_id_registered(chat_id):
                return False, "❌ معرف الدردشة الخاص بك مسجل بالفعل. إذا كنت بحاجة إلى تغييره، يرجى التواصل مع المسؤول."
            
            telegram_sheet, _ = self.sheets_manager.get_telegram_chat_ids_sheet()
            if telegram_sheet:
                telegram_sheet.append_row([chat_id, user_id])
                return True, "✅ تم تسجيل معرف الدردشة الخاص بك بنجاح."
            else:
                return False, "خطأ في الوصول لسجل معرفات الدردشة"
                
        except Exception as e:
            logger.error(f"Error registering chat ID {chat_id} with user {user_id}: {e}")
            return False, "حدث خطأ أثناء التسجيل"


class AchievementManager:
    """Handles achievement recording"""
    
    def __init__(self, sheets_manager: GoogleSheetsManager, attendance_manager: AttendanceManager):
        self.sheets_manager = sheets_manager
        self.attendance_manager = attendance_manager
    
    def record_achievement(self, user_id: str, achievement: str) -> tuple[bool, str]:
        """Record user achievement"""
        try:
            if not self.attendance_manager.is_valid_user(user_id):
                return False, "❌ هذا المستخدم غير مسجل في رِواق."
            
            achievements_sheet = self.sheets_manager.get_achievements_sheet()
            if not achievements_sheet:
                return False, "خطأ في الوصول لسجل الإنجازات"
            
            full_name = self.attendance_manager.get_user_name(user_id)
            date_str = datetime.datetime.now().strftime("%Y-%m-%d")
            
            achievements_sheet.append_row([user_id, achievement, full_name, date_str])
            
            return True, f"✅ تم تسجيل إنجازكِ بنجاح، {full_name}. شكرًا لمشاركتكِ في رِواق!"
            
        except Exception as e:
            logger.error(f"Error recording achievement for {user_id}: {e}")
            return False, "حدث خطأ أثناء تسجيل الإنجاز"


class LLMManager:
    """Handles LLM interactions"""
    
    @staticmethod
    def get_system_prompt() -> str:
        """Get the system prompt for the LLM"""
        return """
أنت بوت مساعد رسمي لمكان اسمه 'رِواق'، وهو مساحة آمنة مخصصة للفتيات في قطاع غزة المتأثرات بالحرب. رِواق يوفر خدمات مثل: الإنترنت، الكهرباء، مكان هادئ وآمن للعمل أو الدراسة. دورك هو الرد بلغة عربية بسيطة ومحترمة على استفسارات الفتيات المشاركات أو المهتمات بالانضمام، بطريقة لبقة وواقعية، مع تقديم روابط أو معلومات عند الحاجة.

مكان رِواق: في غزة - الرمال - اللبابيدي - شرق مفترق اللبابيدي مع شارع النصر -  عمارة السعيد - الطابق الرابع.

الروابط المهمة:
- رابط linktree: https://linktr.ee/rewaq_cwlrcp
- رابط تسجيل العضوية: https://forms.gle/viQwbn1GabLm1sLo6
- رابط لتقديم الشكاوي: https://forms.gle/Yuh6dZqv4HQxTb14A
- اسم المستخدم للبوت: @rewaq_hub_bot

فترات الدوام: 
يومياً من السبت إلى الخميس 9:00 صباحاً - 6:00 مساءً
يتم تقسيم الدوام على المشارِكات إلى 4 فترات: 
السبت، الاثنين، الأربعاء 9:00 صباحاً - 1:30 مساءً
السبت الاثنين، الأربعاء 1:30 مساءً - 6:00 مساءً

لتسجيل الحضور اليومي:
- الدخول: /in RA-0000
- الخروج: /out RA-0000

التواصل:
- الإيميل: rewaq.workspace@gmail.com
- إنستجرام: https://www.instagram.com/rewaq_workspace/
- قناة التحديثات: https://t.me/rewaq_channel
- للاستفسارات: م. سالم العمصي على @salemimad
"""
    
    async def get_llm_response(self, user_message: str) -> str:
        """Get response from LLM"""
        try:
            os.environ['GROQ_API_KEY'] = os.getenv('GROQ_API_KEY')
            
            response = completion(
                model="groq/meta-llama/llama-4-scout-17b-16e-instruct",
                messages=[
                    {"role": "user", "content": user_message},
                    {"role": "system", "content": self.get_system_prompt()}
                ]
            )
            
            return response['choices'][0]['message']['content']
            
        except Exception as e:
            logger.error(f"Error getting LLM response: {e}")
            return "عذراً، حدث خطأ في الرد. يرجى المحاولة مرة أخرى أو التواصل مع المسؤول."


class RewaqBot:
    """Main bot class that handles all commands and interactions"""
    
    def __init__(self):
        self.config = Config()
        self.sheets_manager = GoogleSheetsManager(self.config)
        self.attendance_manager = AttendanceManager(self.sheets_manager, self.config)
        self.user_manager = UserManager(self.sheets_manager)
        self.achievement_manager = AchievementManager(self.sheets_manager, self.attendance_manager)
        self.llm_manager = LLMManager()
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        start_message = """أهلاً وسهلاً بكِ في **رِواق**

**رِواق** هو مساحة آمنة مخصصة للفتيات في **قطاع غزة المتأثرات بالحرب**.  
يوفر خدمات مثل:

- الإنترنت  
- الكهرباء  
- مكان هادئ وآمن للعمل أو الدراسة  

---

📍 **مكان رِواق**

**غزة - الرمال - اللبابيدي - شرق مفترق اللبابيدي مع شارع النصر - عمارة السعيد - الطابق الرابع**

---

🔗 **روابط مهمة**

- [رابط Linktree](https://linktr.ee/rewaq_cwlrcp)
- [رابط تسجيل العضوية](https://forms.gle/viQwbn1GabLm1sLo6)
- [رابط لتقديم الشكاوى](https://forms.gle/Yuh6dZqv4HQxTb14A)
- **اسم المستخدم للبوت:** `@rewaq_hub_bot`

---

⏰ **فترات الدوام**

**يومياً من السبت إلى الخميس: 9:00 صباحاً - 6:00 مساءً**

يتم تقسيم الدوام على المشارِكات إلى 4 فترات:

- السبت، الاثنين، الأربعاء: 9:00 صباحاً - 1:30 مساءً  
- السبت، الاثنين، الأربعاء: 1:30 مساءً - 6:00 مساءً

---

**تسجيل الحضور اليومي (الدخول والخروج)**

- لتسجيل **الدخول**: `/in RA-0000`
- لتسجيل **الخروج**: `/out RA-0000`

مع استبدال `RA-0000` برقم عضويتكِ.

📧 **تواصل**

- **الإيميل الرسمي:** `rewaq.workspace@gmail.com`
- **صفحة إنستجرام:** [instagram.com/rewaq_workspace](https://www.instagram.com/rewaq_workspace/)
- **قناة الإعلانات:** [telegram_channel](https://t.me/rewaq_channel)
- **للاستفسارات:** م. سالم العمصي `@salemimad`
"""
        await update.message.reply_text(start_message, parse_mode=ParseMode.MARKDOWN)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_text = (
            "مرحباً بكِ في دليل بوت رِواق:\n\n"
            "/in <user_id> - تسجيل الدخول\n"
            "/out <user_id> - تسجيل الخروج\n"
            "/help - عرض دليل بوت رِواق\n"
            "/achieve, <user_id>, <achievement> - تسجيل إنجاز\n"
            "/register <user_id> - تسجيل معرف الدردشة الخاص بك\n\n"
            "لأي استفسارات أخرى، يرجى التواصل مع منسق رِواق: م. سالم العمصي على تيليجرام: @salemimad"
        )
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
    
    async def checkin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /in command"""
        try:
            message = update.message.text.strip()
            parts = message.split(" ")
            
            if len(parts) == 2:
                # Admin checkin format: /in user_id
                user_id = parts[1].strip()
            else:
                # User checkin format: /in
                if not message.startswith("/in"):
                    await update.message.reply_text("❌ استخدم هذا الشكل: `/in`", parse_mode=ParseMode.MARKDOWN)
                    return
                
                chat_id = str(update.effective_chat.id)
                user_id = self.user_manager.get_user_by_chat_id(chat_id)
                
                if not user_id:
                    await update.message.reply_text(
                        "❌ لم تقومي بتسجيل معرف الدردشة الخاص بك. يرجى استخدام الأمر /register <user_id> لتسجيل معرف الدردشة."
                    )
                    return
            
            if not self.attendance_manager.is_valid_user(user_id):
                await update.message.reply_text("❌ هذا المستخدم غير مسجل في رِواق.")
                return
            
            success, message_text = self.attendance_manager.record_checkin(user_id)
            await update.message.reply_text(message_text, parse_mode=ParseMode.MARKDOWN)
            
        except Exception as e:
            logger.error(f"Error in checkin command: {e}")
            await update.message.reply_text("حدث خطأ أثناء تسجيل الدخول. يرجى المحاولة مرة أخرى.")
    
    async def checkout_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /out command"""
        try:
            message = update.message.text.strip()
            
            if not message.startswith("/out"):
                await update.message.reply_text("❌ استخدم هذا الشكل: `/out`", parse_mode=ParseMode.MARKDOWN)
                return
            
            chat_id = str(update.effective_chat.id)
            user_id = self.user_manager.get_user_by_chat_id(chat_id)
            
            if not user_id:
                await update.message.reply_text(
                    "❌ لم تقومي بتسجيل معرف الدردشة الخاص بك. يرجى استخدام الأمر /register <user_id> لتسجيل معرف الدردشة."
                )
                return
            
            if not self.attendance_manager.is_valid_user(user_id):
                await update.message.reply_text("❌ هذا المستخدم غير مسجل في رِواق.")
                return
            
            success, message_text = self.attendance_manager.record_checkout(user_id)
            await update.message.reply_text(message_text, parse_mode=ParseMode.MARKDOWN)
            
        except Exception as e:
            logger.error(f"Error in checkout command: {e}")
            await update.message.reply_text("حدث خطأ أثناء تسجيل الخروج. يرجى المحاولة مرة أخرى.")
    
    async def achieve_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /achieve command"""
        try:
            user_message = update.message.text
            parts = user_message.split("-")
            
            if len(parts) != 2:
                await update.message.reply_text(
                    "❌ استخدمي هذا الشكل: `/achieve-YOUR ACHIEVEMENT`",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            chat_id = str(update.effective_chat.id)
            user_id = self.user_manager.get_user_by_chat_id(chat_id)
            achievement = parts[1].strip()
            
            success, message_text = self.achievement_manager.record_achievement(user_id, achievement)
            await update.message.reply_text(message_text, parse_mode=ParseMode.MARKDOWN)
            
        except Exception as e:
            logger.error(f"Error in achieve command: {e}")
            await update.message.reply_text("حدث خطأ أثناء تسجيل الإنجاز. يرجى المحاولة مرة أخرى.")
    
    async def register_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /register command"""
        try:
            message_text = update.message.text.strip()
            chat_id = str(update.effective_chat.id)
            
            if not message_text.startswith("/register"):
                await update.message.reply_text(
                    "❌ يرجى استخدام الأمر بالشكل الصحيح: /register <user_id>."
                )
                return
            
            parts = message_text.split(" ")
            if len(parts) != 2:
                await update.message.reply_text(
                    "❌ يرجى استخدام الأمر بالشكل الصحيح: /register <user_id>."
                )
                return
            
            user_id = parts[1].strip()
            success, message_text = self.user_manager.register_chat_id(chat_id, user_id)
            await update.message.reply_text(message_text)
            
        except Exception as e:
            logger.error(f"Error in register command: {e}")
            await update.message.reply_text("حدث خطأ أثناء التسجيل. يرجى المحاولة مرة أخرى.")
    
    async def handle_llm(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle general text messages with LLM"""
        try:
            user_message = update.message.text
            
            # Prevent using commands incorrectly
            if any(word in user_message.lower() for word in ["out", "in"]):
                await update.message.reply_text("❌ يرجى استخدام الأوامر /in و /out فقط.")
                return
            
            response = await self.llm_manager.get_llm_response(user_message)
            await update.message.reply_text(response)
            
        except Exception as e:
            logger.error(f"Error in LLM handler: {e}")
            await update.message.reply_text(
                "عذراً، حدث خطأ في الرد. يرجى المحاولة مرة أخرى أو التواصل مع المسؤول."
            )
    
    def run(self):
        """Run the bot"""
        try:
            app = ApplicationBuilder().token(self.config.TELEGRAM_TOKEN).build()
            
            # Add command handlers
            app.add_handler(CommandHandler("start", self.start_command))
            app.add_handler(CommandHandler("help", self.help_command))
            app.add_handler(CommandHandler("in", self.checkin_command))
            app.add_handler(CommandHandler("out", self.checkout_command))
            app.add_handler(CommandHandler("achieve", self.achieve_command))
            app.add_handler(CommandHandler("register", self.register_command))
            
            # Add message handler for LLM
            app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_llm))
            
            logger.info("Bot is starting...")
            app.run_polling()
            
        except Exception as e:
            logger.error(f"Error starting bot: {e}")


if __name__ == "__main__":
    bot = RewaqBot()
    bot.run()