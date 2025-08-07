from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from datetime import datetime as dt
from litellm import completion
from google.oauth2.service_account import Credentials

import datetime
import json
import logging
import os
import gspread
import pandas as pd
import streamlit as st


logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)
# Dictionary to store user activity: {user_id: {date: {'in': True, 'out': False}}}
user_log = json.load(open('attendance.json', 'r')) if open('attendance.json', 'r') else {}

# json_str = config["json_info"]["GOOGLE_SERVICE_ACCOUNT_JSON "]
json_str = st.secrets['json_info']['GOOGLE_SERVICE_ACCOUNT_JSON']
st.write("json_str:", json_str)

# Parse the JSON string
info = json.loads(json_str)

# Define the scope (for Google Sheets and Drive)
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']

# Authenticate using the service account
credentials = Credentials.from_service_account_info(info,scopes=SCOPES)
gc = gspread.authorize(credentials)
client = gspread.authorize(credentials)
spreadsheet = client.open("participants application | Rewaq")
worksheet = spreadsheet.get_worksheet(0)
participants_sheet = worksheet.get_all_records()
participants = pd.DataFrame(participants_sheet[1:], columns=participants_sheet[0])[['user_id', 'الاسم رباعي']]

def today_str():
    return datetime.date.today().isoformat()

async def checkin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message.text.strip()
    parts = message.split()

    if len(parts) != 2 or parts[0] not in ["/in"] or parts[1] == "":
        await update.message.reply_text("❌ Please use the format:\n`/in 1234`", parse_mode='Markdown')
        return
    action = parts[0]
    user_id = parts[1]
    timestamp = dt.now().isoformat()
    date = timestamp[:10]
    today = today_str()
    if user_id not in participants['user_id'].values:
        await update.message.reply_text("❌ هذا المستخدم غير مسجل في رِواق.")
        return
    first_name = participants.loc[participants['user_id'] == user_id, 'الاسم رباعي'].values[0]
    if user_id not in user_log:
        user_log[user_id] = {}
    
    if today not in user_log[user_id]:
        user_log[user_id][today] = {'in': timestamp, 'out': ''}
        await update.message.reply_text(f"✅ مرحباً {first_name}، نرجو لكِ يوماً سعيداً ومليئاً بالإنجازات 💙", parse_mode='Markdown')
        with open("attendance.json", "w") as f:
            json.dump(user_log, f, indent=2)
    else:
        await update.message.reply_text("⚠️ لقد قمتِ بتسجيل الدخول بالفعل اليوم.")

async def checkout_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message.text.strip()
    parts = message.split()
    if len(parts) != 2 or parts[0] not in ["/out"] or parts[1] == "":
        await update.message.reply_text("❌ استخدمي الطريقة الصحيحة رجاءً: /out <user_id>", parse_mode='Markdown')
        return
    action = parts[0]
    user_id = parts[1]
    timestamp = dt.now().isoformat()
    date = timestamp[:10]
    today = today_str()
    first_name = participants.loc[participants['user_id'] == user_id, 'الاسم رباعي'].values[0]
    if user_id not in user_log or today not in user_log[user_id] or not user_log[user_id][today].get('in'):
        await update.message.reply_text(f"⚠️ لم تقومي بتسجيل الدخول اليوم، {first_name} . يرجى تسجيل الدخول أولاً باستخدام /in <user_id>.")
        return
    if user_id not in participants['user_id'].values:
        await update.message.reply_text("❌ هذا المستخدم غير مسجل في رِواق.")
        return
    
    if user_log[user_id][today]['out']:
        await update.message.reply_text(f"⚠️ لقد قمتِ بتسجيل الخروج بالفعل اليوم، {first_name}.")
    else:
        user_log[user_id][today]['out'] = timestamp
        await update.message.reply_text(f"✅ تم تسجيل خروجكِ بنجاح، {first_name}. نأمل أن يكون يومكِ مليئاً بالإنجازات. 💙", parse_mode='Markdown')
        with open("attendance.json", "w") as f:
            json.dump(user_log, f, indent=2)
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "مرحباً بكِ في دليل بوت رِواق: \n"
        "/in <user_id> -تسجيل الدخول .\n"
        "/out <user_id> - تسجيل الخروج.\n"
        "/help - عرض دليل بوت رِواق."
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 مرحباً! أنا بوت رِواق، هنا لمساعدتك في تسجيل الحضور. استخدم /help لمعرفة المزيد.")

async def handle_llm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text



    api_key = st.secrets['json_info']['GOOGLE_SERVICE_ACCOUNT_JSON']




    response = completion(
        api_key = api_key,
        model="groq/meta-llama/llama-4-scout-17b-16e-instruct", 
        messages=[
        {"role": "user", "content": user_message},
        {"role": "system", "content":"""
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
/in ملحَقاً باسم المستخدم الخاص بك على شبكة رِواق
لتسجيل الخروج (حينما تغادرين رِواق): قومي بكتابة الأمر: 
/out
 ملحَقاً باسم المستخدم الخاص بك على شبكة رِواق


ايميل رِواق الرسمي:
 rewaq.workspace@gmail.com
صفحة انستجرام: 
https://www.instagram.com/rewaq_workspace/
لأي استفسارات لا تعرف إجابتها بالنسبة لرِواق يرجى توجيه المستخدم للتواصل مع منسق رِواق: م. سالم العمصي على تيليجرام :@salemimad

"""    }],
    )
    print(response)

    await update.message.reply_text(response['choices'][0]['message']['content'])
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors that occur in the application."""
    logger.error("Exception while handling an update:", exc_info=context.error)
    
    # Send error message to user if possible
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
            "⚠️ An error occurred. Please try again later."
            )
        except Exception:
            pass  
# Setup the bot
if __name__ == "__main__":
    app = ApplicationBuilder().token("8175405891:AAH66-cEzHOo25Irys6Oo6wbR65qYkjAek8").build()
    app.add_handler(CommandHandler("in", checkin_command))
    app.add_handler(CommandHandler("out", checkout_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("start", start_command))
    app.add_error_handler(error_handler)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_llm))

    app.run_polling()








