import os
import json
import requests
from dotenv import load_dotenv

load_dotenv('.env')
load_dotenv('web/.env.local', override=True)

bot_token = os.getenv('ARTORO_AI_BOT', '').strip()
raw_target = os.getenv('TELEGRAM_FREE_CHAT_ID', '-1002083067817_153').strip()

if '_' in raw_target:
    chat_id, thread_id_str = raw_target.split('_', 1)
    thread_id = int(thread_id_str)
else:
    chat_id = raw_target
    thread_id = None

banner_path = os.path.join(os.getcwd(), 'egx_bots_facebook_banner.jpg')

caption = (
    "⏳ <b>تنبيه عاجل: باقي 24 ساعة فقط على انتهاء عرض المؤسسين (100 ج.م شهرياً) 👑🇪🇬</b>\n\n"
    "لكل إخوتنا المتداولين في البورصة المصرية.. مهلة تثبيت سعر باقة <b>EGX BOTS PRO</b> بـ <b>100 ج.م فقط شهرياً</b> (بدلاً من 200 ج.م) تنتهي رسمياً خلال 24 ساعة!\n\n"
    "🔒 <b>ميزة تثبيت السعر مدى الحياة:</b>\n"
    "باشتراكك قبل انتهاء العداد، يُثبّت سعر حسابك عند <b>100 ج.م شهرياً مدى الحياة</b> عند كل تجديد، مع <b>مهلة سماح 72 ساعة</b> عند كل تجديد للحفاظ على سعرك المخفض دائماً حتى لو عاد السعر الرسمي لـ 200 ج.م.\n\n"
    "🔥 <b>ماذا تفتح لك باقة PRO فوراً؟</b>\n"
    "• 🎯 <b>الصفقات القصيرة ⚡ PRO:</b> إشارات الزخم السريعة ومتابعة الأرباح ووقف الخسارة الصارم لحظة بلحظة.\n"
    "• 📢 <b>رادار تليجرام الفوري:</b> تنبيهات اختراقات السيولة، تجميع الحيتان (وايكوف)، وتتبع صفقات المطلعين.\n"
    "• 🤖 <b>شات بوت المستشار الذكي 24/7:</b> 350 استشارة شهرياً لتحليل ودعوم ومقاومات أي سهم مصري وتحليل المحفظة من صورة (Vision AI).\n\n"
    "⚡ <b>احجز مقعدك وثبّت سعرك الآن قبل غلق العرض:</b>\n"
    "👉 <a href=\"https://egxbots.com/pricing?plan=pro\">اضغط هنا للاشتراك وتثبيت سعر الـ 100 ج.م 👑</a>\n"
    "💡 <i>التفعيل فوري وآلي بالكامل عبر فودافون كاش / إنستاباي / البطاقات البنكية.</i>"
)

data = {
    'chat_id': chat_id,
    'caption': caption,
    'parse_mode': 'HTML',
}
if thread_id:
    data['message_thread_id'] = thread_id

inline_keyboard = {
    'inline_keyboard': [
        [
            {'text': '⚡ اشترك الآن بـ 100 ج.م وثبّت سعرك', 'url': 'https://egxbots.com/pricing?plan=pro'}
        ],
        [
            {'text': '💬 تجربة المستشار الذكي 3 أيام مجاناً', 'url': 'https://egxbots.com/pricing'}
        ]
    ]
}
data['reply_markup'] = json.dumps(inline_keyboard)

url = f'https://api.telegram.org/bot{bot_token}/sendPhoto'

if os.path.exists(banner_path):
    with open(banner_path, 'rb') as photo:
        files = {'photo': photo}
        res = requests.post(url, data=data, files=files, timeout=25)
else:
    url_msg = f'https://api.telegram.org/bot{bot_token}/sendMessage'
    data['text'] = caption
    res = requests.post(url_msg, data=data, timeout=25)

result = res.json()
print('Telegram post status code:', res.status_code)
print('Telegram post ok:', result.get('ok'))
if not result.get('ok'):
    print('Error description:', result.get('description'))
else:
    print('Message ID:', result.get('result', {}).get('message_id'))
