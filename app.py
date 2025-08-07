import streamlit as st
import logging
import datetime
import pandas as pd
import json
from datetime import datetime as dt
from typing import Dict, Any, Optional

from telegram import Update, Bot
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

class RewaqBotWebhook:
    def __init__(self):
        self.bot = None
        self.setup_credentials()
        self.setup_sheets()
        self.setup_bot()
    
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
    
    def setup_bot(self):
        """Setup bot instance"""
        try:
            bot_token = st.secrets.get("BOT_TOKEN", "8175405891:AAH66-cEzHOo25Irys6Oo6wbR65qYkjAek8")
            self.bot = Bot(token=bot_token)
        except Exception as e:
            logger.error(f"Error setting up bot: {e}")
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
    
    def process_checkin(self, user_id: str) -> str:
        """Process check-in command"""
        try:
            attendance_worksheet = self.attendance_log.get_worksheet(2)
            attendance_sheet = attendance_worksheet.get_all_records()
            
            timestamp = dt.now().strftime("%Y-%m-%d %H:%M:%S")
            today = self.today_str()

            if user_id not in self.participants['user_id'].values:
                return "❌ هذا المستخدم غير مسجل في رِواق."

            first_name = self.get_user_name(user_id)

            if not self.has_checkin(attendance_sheet, user_id, today):
                attendance_worksheet.append_row([user_id, timestamp, '', today])
                logger.info(f"User {user_id} checked in at {timestamp}")
                return f"✅ مرحباً {first_name}، نرجو لكِ يوماً سعيداً ومليئاً بالإنجازات 💙"
            else:
                return "⚠️ لقد قمتِ بتسجيل الدخول بالفعل اليوم."
                
        except Exception as e:
            logger.error(f"Error in process_checkin: {e}")
            return "❌ حدث خطأ أثناء تسجيل الدخول. يرجى المحاولة مرة أخرى."

    def process_checkout(self, user_id: str) -> str:
        """Process checkout command"""
        try:
            attendance_worksheet = self.attendance_log.get_worksheet(2)
            attendance_sheet = attendance_worksheet.get_all_records()
            
            timestamp = dt.now().strftime("%Y-%m-%d %H:%M:%S")
            today = self.today_str()

            if user_id not in self.participants['user_id'].values:
                return "❌ هذا المستخدم غير مسجل في رِواق."

            first_name = self.get_user_name(user_id)

            if not self.has_checkin(attendance_sheet, user_id, today):
                return f"⚠️ لم تقومي بتسجيل الدخول اليوم، {first_name}. يرجى تسجيل الدخول أولاً."

            # Find and update the checkout time
            for idx, row in enumerate(attendance_sheet, start=2):
                if str(row['user_id']) == str(user_id) and row['day'] == today:
                    if not row.get('out_time'):  # Only update if not already checked out
                        attendance_worksheet.update_cell(idx, 3, timestamp)
                        logger.info(f"User {user_id} checked out at {timestamp}")
                        return f"✅ تم تسجيل خروجكِ بنجاح، {first_name}. نأمل أن يكون يومكِ مليئاً بالإنجازات. 💙"
                    else:
                        return f"⚠️ لقد قمتِ بتسجيل الخروج بالفعل اليوم، {first_name}."
            
            return "❌ حدث خطأ أثناء تسجيل الخروج."
                
        except Exception as e:
            logger.error(f"Error in process_checkout: {e}")
            return "❌ حدث خطأ أثناء تسجيل الخروج. يرجى المحاولة مرة أخرى."

    def get_help_text(self) -> str:
        """Get help text"""
        return (
            "مرحباً بكِ في دليل بوت رِواق: \n"
            "/in <user_id> - تسجيل الدخول.\n"
            "/out <user_id> - تسجيل الخروج.\n"
            "/help - عرض دليل بوت رِواق."
        )

    def get_start_text(self) -> str:
        """Get start/welcome text"""
        return """أهلاً وسهلاً بكِ في **رِواق**

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

    def process_llm_response(self, user_message: str) -> str:
        """Process LLM response for general messages"""
        try:
            # Check for attendance-related keywords
            if any(word in user_message.lower() for word in ["out", "in", "دخول", "خروج"]):
                return "❌ يرجى استخدام الأوامر /in و /out فقط."

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

            return response['choices'][0]['message']['content']
            
        except Exception as e:
            logger.error(f"Error in process_llm_response: {e}")
            return "❌ عذراً، حدث خطأ أثناء معالجة رسالتك. يرجى المحاولة مرة أخرى أو التواصل مع الإدارة."

    def process_message(self, message_text: str, chat_id: int) -> str:
        """Process incoming message and return response"""
        message_text = message_text.strip()
        
        # Handle commands
        if message_text.startswith('/start'):
            return self.get_start_text()
        
        elif message_text.startswith('/help'):
            return self.get_help_text()
        
        elif message_text.startswith('/in'):
            parts = message_text.split()
            if len(parts) != 2 or parts[1] == "":
                return "❌ استخدم هذا الشكل: \n`/in 1234`"
            return self.process_checkin(parts[1])
        
        elif message_text.startswith('/out'):
            parts = message_text.split()
            if len(parts) != 2 or parts[1] == "":
                return "❌ استخدمي الطريقة الصحيحة رجاءً: /out <user_id>"
            return self.process_checkout(parts[1])
        
        else:
            # Handle general messages with LLM
            return self.process_llm_response(message_text)

    def send_message(self, chat_id: int, text: str, parse_mode: str = ParseMode.MARKDOWN) -> bool:
        """Send message to chat"""
        try:
            import asyncio
            
            async def _send():
                await self.bot.send_message(
                    chat_id=chat_id, 
                    text=text, 
                    parse_mode=parse_mode
                )
            
            # Run in new event loop to avoid conflicts
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(_send())
            loop.close()
            
            return True
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return False

# Streamlit Interface
def main():
    st.set_page_config(
        page_title="Rewaq Bot Dashboard",
        page_icon="🤖",
        layout="wide"
    )
    
    st.title("🤖 Rewaq Bot Dashboard")
    st.markdown("---")
    
    # Initialize bot in session state
    if 'webhook_bot' not in st.session_state:
        try:
            st.session_state.webhook_bot = RewaqBotWebhook()
            st.success("✅ Bot initialized successfully!")
        except Exception as e:
            st.error(f"❌ Error initializing bot: {e}")
            return
    
    # Manual message testing section
    st.subheader("🧪 Test Bot Manually")
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        test_message = st.text_input(
            "Enter a message to test:",
            placeholder="/start, /help, /in RA-001, /out RA-001, or any question"
        )
    
    with col2:
        chat_id = st.number_input("Chat ID", value=123456789, step=1)
    
    if st.button("📤 Test Message") and test_message:
        try:
            response = st.session_state.webhook_bot.process_message(test_message, chat_id)
            
            st.markdown("**Bot Response:**")
            st.markdown(f"```\n{response}\n```")
            
            # Optional: Actually send the message
            if st.checkbox("Send to Telegram"):
                success = st.session_state.webhook_bot.send_message(chat_id, response)
                if success:
                    st.success("✅ Message sent to Telegram!")
                else:
                    st.error("❌ Failed to send message to Telegram")
                    
        except Exception as e:
            st.error(f"❌ Error processing message: {e}")
    
    st.markdown("---")
    
    # Statistics section
    st.subheader("📊 Statistics")
    
    try:
        bot = st.session_state.webhook_bot
        
        # Show participants count
        participants_count = len(bot.participants)
        st.metric("Total Participants", participants_count)
        
        # Show recent attendance (today)
        today = bot.today_str()
        attendance_worksheet = bot.attendance_log.get_worksheet(2)
        attendance_records = attendance_worksheet.get_all_records()
        
        today_checkins = [
            record for record in attendance_records 
            if record.get('day') == today
        ]
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Today's Check-ins", len(today_checkins))
        
        with col2:
            checked_out = len([
                record for record in today_checkins 
                if record.get('out_time')
            ])
            st.metric("Today's Check-outs", checked_out)
        
        # Show recent activity
        if today_checkins:
            st.subheader("📋 Today's Activity")
            
            activity_df = pd.DataFrame(today_checkins)
            if not activity_df.empty:
                # Get user names
                activity_df['اسم المستخدم'] = activity_df['user_id'].apply(
                    lambda x: bot.get_user_name(str(x))
                )
                
                st.dataframe(
                    activity_df[['user_id', 'اسم المستخدم', 'in_time', 'out_time']],
                    use_container_width=True
                )
    
    except Exception as e:
        st.error(f"Error loading statistics: {e}")
    
    # Instructions section
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
    - 🧪 Manual message testing interface
    
    **Note:** This version uses webhook-style processing instead of polling to avoid threading issues with Streamlit.
    For production, you would set up actual webhooks to receive messages from Telegram.
    """)

if __name__ == "__main__":
    main()
