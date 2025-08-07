import streamlit as st
import asyncio
import threading
import logging
import datetime
import pandas as pd
import signal
import sys
from datetime import datetime as dt
from typing import Dict, Any

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from telegram.constants import ParseMode
from litellm import completion
from google.oauth2.service_account import Credentials
import gspread
import os

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class RewaqBot:
    def __init__(self):
        self.app = None
        self.is_running = False
        self.loop = None
        self.bot_thread = None
        self.setup_credentials()
        self.setup_sheets()
    
    def setup_credentials(self):
        """Setup Google Sheets credentials"""
        try:
            service_account_info = {
                "type": st.secrets["type"],
                "project_id": st.secrets["project_id"],
                "private_key_id": st.secrets["private_key_id"],
                "private_key": st.secrets["private_key"],
                "client_email": st.secrets["client_email"],
                "client_id": st.secrets["client_id"],
                "auth_uri": st.secrets["auth_uri"],
                "token_uri": st.secrets["token_uri"],
                "auth_provider_x509_cert_url": st.secrets["auth_provider_x509_cert_url"],
                "client_x509_cert_url": st.secrets["client_x509_cert_url"],
                "universe_domain": st.secrets["universe_domain"]
            }
            
            SCOPES = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
            
            credentials = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
            self.client = gspread.authorize(credentials)
            
        except Exception as e:
            logger.error(f"Error setting up credentials: {e}")
            raise
    
    def setup_sheets(self):
        """Setup Google Sheets connections"""
        try:
            # Participants sheet
            participants_spreadsheet = self.client.open("participants application | Rewaq")
            participants_worksheet = participants_spreadsheet.get_worksheet(0)
            participants_sheet = participants_worksheet.get_all_records()
            
            self.participants = pd.DataFrame(
                participants_sheet[1:],
                columns=participants_sheet[0]
            )[['user_id', 'الاسم رباعي']]
            
            # Attendance sheet
            self.attendance_log = self.client.open("Attendance Log | Rewaq")
            
        except Exception as e:
            logger.error(f"Error setting up sheets: {e}")
            raise
    
    def has_checkin(self, sheet_records: list, user_id: str, today: str) -> bool:
        """Check if user has already checked in today"""
        return any(
            str(row['user_id']) == str(user_id) and row['day'] == today
            for row in sheet_records
        )
    
    def today_str(self) -> str:
        """Get today's date as ISO string"""
        return datetime.date.today().isoformat()
    
    def get_user_name(self, user_id: str) -> str:
        """Get user's full name from participants sheet"""
        try:
            return self.participants.loc[
                self.participants['user_id'] == user_id, 'الاسم رباعي'
            ].values[0]
        except (IndexError, KeyError):
            return "مستخدم غير معروف"
    
    async def checkin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle check-in command"""
        try:
            attendance_worksheet = self.attendance_log.get_worksheet(2)
            attendance_sheet = attendance_worksheet.get_all_records()
            
            message = update.message.text.strip()
            parts = message.split()

            if len(parts) != 2 or parts[0] != "/in" or parts[1] == "":
                await update.message.reply_text(
                    "❌ استخدم هذا الشكل: \n`/in 1234`",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

            user_id = parts[1]
            timestamp = dt.now().strftime("%Y-%m-%d %H:%M:%S")
            today = self.today_str()

            if user_id not in self.participants['user_id'].values:
                await update.message.reply_text("❌ هذا المستخدم غير مسجل في رِواق.")
                return

            first_name = self.get_user_name(user_id)

            if not self.has_checkin(attendance_sheet, user_id, today):
                attendance_worksheet.append_row([user_id, timestamp, '', today])
                await update.message.reply_text(
                    f"✅ مرحباً {first_name}، نرجو لكِ يوماً سعيداً ومليئاً بالإنجازات 💙",
                    parse_mode=ParseMode.MARKDOWN
                )
                logger.info(f"User {user_id} checked in at {timestamp}")
            else:
                await update.message.reply_text("⚠️ لقد قمتِ بتسجيل الدخول بالفعل اليوم.")
                
        except Exception as e:
            logger.error(f"Error in checkin_command: {e}")
            await update.message.reply_text("❌ حدث خطأ أثناء تسجيل الدخول. يرجى المحاولة مرة أخرى.")

    async def checkout_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle checkout command"""
        try:
            attendance_worksheet = self.attendance_log.get_worksheet(2)
            attendance_sheet = attendance_worksheet.get_all_records()
            
            message = update.message.text.strip()
            parts = message.split()
            
            if len(parts) != 2 or parts[0] != "/out" or parts[1] == "":
                await update.message.reply_text(
                    "❌ استخدمي الطريقة الصحيحة رجاءً: /out <user_id>",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

            user_id = parts[1]
            timestamp = dt.now().strftime("%Y-%m-%d %H:%M:%S")
            today = self.today_str()

            if user_id not in self.participants['user_id'].values:
                await update.message.reply_text("❌ هذا المستخدم غير مسجل في رِواق.")
                return

            first_name = self.get_user_name(user_id)

            if not self.has_checkin(attendance_sheet, user_id, today):
                await update.message.reply_text(
                    f"⚠️ لم تقومي بتسجيل الدخول اليوم، {first_name}. يرجى تسجيل الدخول أولاً باستخدام /in <user_id>."
                )
                return

            # Find and update the checkout time
            updated = False
            for idx, row in enumerate(attendance_sheet, start=2):
                if str(row['user_id']) == str(user_id) and row['day'] == today:
                    if not row.get('out_time'):  # Only update if not already checked out
                        attendance_worksheet.update_cell(idx, 3, timestamp)
                        await update.message.reply_text(
                            f"✅ تم تسجيل خروجكِ بنجاح، {first_name}. نأمل أن يكون يومكِ مليئاً بالإنجازات. 💙",
                            parse_mode=ParseMode.MARKDOWN
                        )
                        logger.info(f"User {user_id} checked out at {timestamp}")
                        updated = True
                        break
                    else:
                        await update.message.reply_text(
                            f"⚠️ لقد قمتِ بتسجيل الخروج بالفعل اليوم، {first_name}."
                        )
                        updated = True
                        break
            
            if not updated:
                await update.message.reply_text("❌ حدث خطأ أثناء تسجيل الخروج.")
                
        except Exception as e:
            logger.error(f"Error in checkout_command: {e}")
            await update.message.reply_text("❌ حدث خطأ أثناء تسجيل الخروج. يرجى المحاولة مرة أخرى.")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle help command"""
        help_text = (
            "مرحباً بكِ في دليل بوت رِواق: \n"
            "/in <user_id> - تسجيل الدخول.\n"
            "/out <user_id> - تسجيل الخروج.\n"
            "/help - عرض دليل بوت رِواق."
        )
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle start command"""
        welcome_text = """أهلاً وسهلاً بكِ في **رِواق**

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

- لتسجيل **الدخول** (حينما تدخلين رِواق):  
اكتبي الأمر: 
/in RA-0000
- لتسجيل **الخروج** (حينما تغادرين رِواق):  
اكتبي الأمر:
/out RA-0000 

مع استبدال `RA-0000` برقم عضويتكِ.

📧 **تواصل**

- **الإيميل الرسمي لرِواق:**  
  `rewaq.workspace@gmail.com`

- **صفحة إنستجرام:**  
  [instagram.com/rewaq_workspace](https://www.instagram.com/rewaq_workspace/)

- ❓ **لأي استفسارات أُخرى**:  
 
**م. سالم العمصي** على تيليجرام: `@salemimad`
"""
        await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN)

    async def handle_llm(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle LLM responses for general messages"""
        try:
            user_message = update.message.text
            
            # Check for attendance-related keywords
            if any(word in user_message.lower() for word in ["out", "in", "دخول", "خروج"]):
                await update.message.reply_text("❌ يرجى استخدام الأوامر /in و /out فقط.")
                return

            # Set up environment for LLM
            os.environ['GROQ_API_KEY'] = st.secrets['GROQ_API_KEY']
            
            response = completion(
                model="groq/meta-llama/llama-4-scout-17b-16e-instruct",
                messages=[
                    {"role": "user", "content": user_message},
                    {
                        "role": "system",
                        "content": """
أنت بوت مساعد رسمي لمكان اسمه 'رِواق'، وهو مساحة آمنة مخصصة للفتيات في قطاع غزة المتأثرات بالحرب. رِواق يوفر خدمات مثل: الإنترنت، الكهرباء، مكان هادئ وآمن للعمل أو الدراسة. دورك هو الرد بلغة عربية بسيطة ومحترمة على استفسارات الفتيات المشاركات أو المهتمات بالانضمام، بطريقة لبقة وواقعية، مع تقديم روابط أو معلومات عند الحاجة.

مكان رِواق: في غزة - الرمال - اللبابيدي - شرق مفترق اللبابيدي مع شارع النصر - عمارة السعيد - الطابق الرابع.

الروابط المهمة:
- رابط Linktree: https://linktr.ee/rewaq_cwlrcp
- رابط تسجيل العضوية: https://forms.gle/viQwbn1GabLm1sLo6
- رابط تقديم الشكاوى: https://forms.gle/Yuh6dZqv4HQxTb14A
- اسم المستخدم للبوت: @rewaq_hub_bot

فترات الدوام: يومياً من السبت إلى الخميس 9:00 صباحاً - 6:00 مساءً

للتواصل مع منسق رِواق: م. سالم العمصي على تيليجرام: @salemimad
ايميل رِواق الرسمي: rewaq.workspace@gmail.com
صفحة انستجرام: https://www.instagram.com/rewaq_workspace/
"""
                    }
                ]
            )

            await update.message.reply_text(
                response['choices'][0]['message']['content']
            )
            
        except Exception as e:
            logger.error(f"Error in handle_llm: {e}")
            await update.message.reply_text(
                "❌ عذراً، حدث خطأ أثناء معالجة رسالتك. يرجى المحاولة مرة أخرى أو التواصل مع الإدارة."
            )

    def setup_handlers(self):
        """Setup bot command handlers"""
        if not self.app:
            return
            
        self.app.add_handler(CommandHandler("in", self.checkin_command))
        self.app.add_handler(CommandHandler("out", self.checkout_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_llm)
        )
    async def run_bot_async(self):
        """Run bot asynchronously"""
        try:
            bot_token = st.secrets.get("BOT_TOKEN", "your-fallback-bot-token")
            self.app = ApplicationBuilder().token(bot_token).build()
            self.setup_handlers()

            logger.info("Starting bot polling (async)...")
            self.is_running = True

            await self.app.run_polling(
                drop_pending_updates=True,
                close_loop=False,
                stop_signals=None
            )
        except Exception as e:
            logger.error(f"Error running async bot: {e}")
            self.is_running = False
    


# Streamlit Interface
def main():
    st.set_page_config(
        page_title="Rewaq Bot Dashboard",
        page_icon="🤖",
        layout="wide"
    )
    bot = RewaqBot()
    asyncio.run(bot.run_bot_async())

    st.markdown("---")
    
        
    #     try:
    #         # Show participants count
    #         participants_count = len(st.session_state.bot.participants)
    #         st.metric("Total Participants", participants_count)
            
    #         # Show recent attendance (today)
    #         today = st.session_state.bot.today_str()
    #         attendance_worksheet = st.session_state.bot.attendance_log.get_worksheet(2)
    #         attendance_records = attendance_worksheet.get_all_records()
            
    #         today_checkins = [
    #             record for record in attendance_records 
    #             if record.get('day') == today
    #         ]
            
    #         col1, col2 = st.columns(2)
    #         with col1:
    #             st.metric("Today's Check-ins", len(today_checkins))
            
    #         with col2:
    #             checked_out = len([
    #                 record for record in today_checkins 
    #                 if record.get('out_time')
    #             ])
    #             st.metric("Today's Check-outs", checked_out)
            
    #         # Show recent activity
    #         if today_checkins:
    #             st.subheader("📋 Today's Activity")
                
    #             activity_df = pd.DataFrame(today_checkins)
    #             if not activity_df.empty:
    #                 # Get user names
    #                 activity_df['اسم المستخدم'] = activity_df['user_id'].apply(
    #                     lambda x: st.session_state.bot.get_user_name(str(x))
    #                 )
                    
    #                 st.dataframe(
    #                     activity_df[['user_id', 'اسم المستخدم', 'in_time', 'out_time']],
    #                     use_container_width=True
    #                 )
        
    #     except Exception as e:
    #         st.error(f"Error loading statistics: {e}")
    
    # # Bot information
    st.markdown("---")
    st.subheader("ℹ️ Bot Information")
    
    st.markdown("""
    **Available Commands:**
    - `/start` - Welcome message with full information
    - `/help` - Show help menu
    - `/in <user_id>` - Check in to Rewaq
    - `/out <user_id>` - Check out from Rewaq
    
    **Features:**
    - ✅ Attendance tracking with Google Sheets
    - 🤖 AI-powered responses using LLaMA
    - 🔒 User validation against registered participants
    - 📊 Real-time statistics and monitoring
    
    **Bot Status:**
    - When the bot is running, it will respond to messages on Telegram
    - The dashboard updates in real-time with attendance data
    - Use the refresh button to update the status
    """)
    
    # Troubleshooting section
    with st.expander("🔧 Troubleshooting"):
        st.markdown("""
        **If the bot is not responding:**
        1. Make sure the bot token in secrets is correct
        2. Check that the bot is added to your Telegram chat
        3. Try stopping and starting the bot again
        4. Check the browser console for any errors
        
        **Common Issues:**
        - Bot token expired or incorrect
        - Google Sheets permissions not set up properly
        - Network connectivity issues
        - Rate limiting from Telegram
        """)

if __name__ == "__main__":
    main()






