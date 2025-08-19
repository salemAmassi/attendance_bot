from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from datetime import datetime as dt
from litellm import completion
from google.oauth2.service_account import Credentials
from telegram.constants import ParseMode
from datetime import timedelta
import datetime
import json
import logging
import os
import gspread
import pandas as pd
from dotenv import load_dotenv
load_dotenv()
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO)
logger = logging.getLogger(__name__)
# Dictionary to store user activity: {user_id: {date: {'in': True, 'out': False}}}
user_log = json.load(open('attendance.json', 'r')) if open(
    'attendance.json', 'r') else {}

SERVICE_ACCOUNT_FILE = 'peerless-aria-466111-h6-b8c14ab44514.json'

# Define the scope (for Google Sheets and Drive)
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

# Authenticate using the service account
credentials = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE,
                                                    scopes=SCOPES)
gc = gspread.authorize(credentials)
client = gspread.authorize(credentials)
spreadsheet = client.open("participants application | Rewaq")
worksheet = spreadsheet.get_worksheet(0)
participants_sheet = worksheet.get_all_records()
participants = pd.DataFrame(participants_sheet[1:],
                            columns=participants_sheet[0])[[
                                'user_id', 'الاسم رباعي'
                            ]]
achivements_sheet = spreadsheet.get_worksheet(1).get_all_records()

def has_checkin(sheet, user_id, today):
    for row in sheet:
        if str(row['user_id']) == str(user_id) and row['day'] == today:
            return True
    return False
    
def today_str():
    return datetime.date.today().isoformat()


async def checkin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    attendance_log = client.open("Attendance Log | Rewaq")
    attendance_worksheet = attendance_log.get_worksheet(2)
    attendance_sheet = attendance_worksheet.get_all_records()
    message = update.message.text.strip()
    parts = message.split()

    if len(parts) != 2 or parts[0] not in ["/in"] or parts[1] == "":
        await update.message.reply_text("❌ استخدم هذا الشكل: \n`/in 1234`",
                                        parse_mode='Markdown')
        return
    action = parts[0]
    user_id = parts[1]
    timestamp = (dt.now() +timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")
    date = timestamp[:10]
    today = today_str()
    if user_id not in participants['user_id'].values:
        await update.message.reply_text("❌ هذا المستخدم غير مسجل في رِواق.")
        return
    first_name = participants.loc[participants['user_id'] == user_id,
                                  'الاسم رباعي'].values[0]
    # if user_id not in user_log:
    #     user_log[user_id] = {}

    # if today not in user_log[user_id]:
        # user_log[user_id][today] = {'in': timestamp, 'out': ''}
    if not has_checkin(attendance_sheet, user_id, today):
        attendance_worksheet.append_row([user_id, timestamp, '', today])
        await update.message.reply_text(
            f"✅ مرحباً {first_name}، نرجو لكِ يوماً سعيداً ومليئاً بالإنجازات 💙",
            parse_mode='Markdown')
            # with open("attendance.json", "w") as f:
            #     json.dump(user_log, f, indent=2)
    else:
        await update.message.reply_text(
            "⚠️ لقد قمتِ بتسجيل الدخول بالفعل اليوم.")


async def checkout_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    attendance_log = client.open("Attendance Log | Rewaq")
    attendance_worksheet = attendance_log.get_worksheet(2)
    attendance_sheet = attendance_worksheet.get_all_records()
    message = update.message.text.strip()
    parts = message.split()
    if len(parts) != 2 or parts[0] not in ["/out"] or parts[1] == "":
        await update.message.reply_text(
            "❌ استخدمي الطريقة الصحيحة رجاءً: /out <user_id>",
            parse_mode='Markdown')
        return
    action = parts[0]
    user_id = parts[1]
    timestamp = (dt.now() +timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")
    date = timestamp[:10]
    today = today_str()
    first_name = participants.loc[participants['user_id'] == user_id,
                                  'الاسم رباعي'].values[0]
    if not has_checkin(attendance_sheet, user_id, today):
        await update.message.reply_text(
            f"⚠️ لم تقومي بتسجيل الدخول اليوم، {first_name} . يرجى تسجيل الدخول أولاً باستخدام /in <user_id>."
        )
        return
    if user_id not in participants['user_id'].values:
        await update.message.reply_text("❌ هذا المستخدم غير مسجل في رِواق.")
        return
        
    if has_checkin(attendance_sheet,user_id,today):
        # Find the row index for the user_id and today
        idx = next((i + 2 for i, row in enumerate(attendance_sheet)
                          if str(row['user_id']) == str(user_id) and row['day'] == today),
                         None) 
        # Update the out_time in column D (index 4)
        attendance_worksheet.update_cell(idx, 3, timestamp) 
        await update.message.reply_text(
            f"✅ تم تسجيل خروجكِ بنجاح، {first_name}. نأمل أن يكون يومكِ مليئاً بالإنجازات. 💙",
            parse_mode='Markdown')
    else:
        await update.message.reply_text(
                f"⚠️ لقد قمتِ بتسجيل الخروج بالفعل اليوم، {first_name}.")
                


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = ("مرحباً بكِ في دليل بوت رِواق: \n"
                 "/in <user_id> -تسجيل الدخول .\n"
                 "/out <user_id> - تسجيل الخروج.\n"
                 "/help - عرض دليل بوت رِواق.\n"
                 "/achieve, <user_id>, <achievement> - تسجيل إنجاز.\n")
    await update.message.reply_text(help_text, parse_mode='Markdown')


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        """  أهلاً وسهلاً بكِ في **رِواق**

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

- [رابط Linktree (يحتوي على موقع مركز الأبحاث والاستشارات القانونية والحماية للمرأة وموقع مساحة رِواق)](https://linktr.ee/rewaq_cwlrcp)
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
- **قناة الإعلانات والتحديثات:**
  [telegram_channel](https://t.me/rewaq_channel)

- ❓ **لأي استفسارات أُخرى**:  
 
**م. سالم العمصي** على تيليجرام: `@salemimad`
""",
        parse_mode = "Markdown"
    )


async def handle_llm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    if "out" in user_message or "in" in user_message:
        await update.message.reply_text("❌ يرجى استخدام الأوامر /in و /out فقط.")
        return
    os.environ[
        'GROQ_API_KEY'] = os.getenv('GROQ_API_KEY')
    response = completion(
        model="groq/meta-llama/llama-4-scout-17b-16e-instruct",
        messages=[{
            "role": "user",
            "content": user_message
        }, {
            "role":
            "system",
            "content":
            """
أنت بوت مساعد رسمي لمكان اسمه 'رِواق'، وهو مساحة آمنة مخصصة للفتيات في قطاع غزة المتأثرات بالحرب. رِواق يوفر خدمات مثل: الإنترنت، الكهرباء، مكان هادئ وآمن للعمل أو الدراسة. دورك هو الرد بلغة عربية بسيطة ومحترمة على استفسارات الفتيات المشاركات أو المهتمات بالانضمام، بطريقة لبقة وواقعية، مع تقديم روابط أو معلومات عند الحاجة.
مكان رِواق: في غزة - الرمال - اللبابيدي - شرق مفترق اللبابيدي مع شارع النصر -  عمارة السعيد - الطابق الرابع.
الروابط المهمة:
رابط linktree يحتوي على موقع مركز الأبحاث والاستشارات القانونية والحماية للمرأة وموقع مساحة رِواق: 
https://linktr.ee/rewaq_cwlrcp
رابط تسجيل العضوية: 
https://forms.gle/viQwbn1GabLm1sLo6
رابط لتقديم الشكاوي:
https://forms.gle/Yuh6dZqv4HQxTb14A
اسم المستخدم للبوت:
 @rewaq_hub_bot
فترات الدوام: 
يومياً من السبت إلى الخميس 9:00 صباحاً - 6:00 مساءً
يتم تقسيم الدوام على المشارِكات إلى 4 فترات: 
السبت، الاثنين، الأربعاء 9:00 صباحاً - 1:30 مساءً
السبت الاثنين، الأربعاء 1:30 مساءً - 6:00 مساءً
لتسجيل الحضور اليومي (الدخول والخروج)، قم بإرشاد الزوار:
لتسجيل الدخول (حينما تدخلين رِواق): قومي بكتابة الأمر: 
/in RA-0000
لتسجيل الخروج (حينما تغادرين رِواق): قومي بكتابة الأمر: 
/out RA-0000


ايميل رِواق الرسمي:
 rewaq.workspace@gmail.com
صفحة انستجرام: 
https://www.instagram.com/rewaq_workspace/
قناة الإعلانات والتحديثات:
https://t.me/rewaq_channel
لأي استفسارات لا تعرف إجابتها بالنسبة لرِواق يرجى توجيه المستخدم للتواصل مع منسق رِواق: م. سالم العمصي على تيليجرام :@salemimad

"""
        }],
    )

    await update.message.reply_text(
        response['choices'][0]['message']['content'])
async def achieve_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    parts = user_message.split(",")
    if len(parts) != 3 :
        await update.message.reply_text(
            "❌ استخدمي هذا الشكل: \n`/achieve, RA-1234 , YOUR ACHIEVEMENT`",
            parse_mode='Markdown')
        return
    user_id = parts[1].strip()
    achievement = parts[2].strip()
    if user_id not in participants['user_id'].values:
        await update.message.reply_text("❌ هذا المستخدم غير مسجل في رِواق.")
        return
    full_name = participants.loc[participants['user_id'] == user_id,
                                  'الاسم رباعي'].values[0]
    achivements_sheet.add_row([user_id, achievement, full_name, dt.now().strftime("%Y-%m-%d")])
    await update.message.reply_text(
        f"✅ تم تسجيل إنجازكِ بنجاح، {full_name}. شكرًا لمشاركتكِ في رِواق!",
        parse_mode='Markdown')
    
    

# Setup the bot
if __name__ == "__main__":
    app = ApplicationBuilder().token(
        os.getenv('BOT_TOKEN')).build()
   
    app.add_handler(CommandHandler("in", checkin_command))
    app.add_handler(CommandHandler("out", checkout_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,
                                   handle_llm))
    app.add_handler(CommandHandler("achieve", achieve_command))

    app.run_polling()






