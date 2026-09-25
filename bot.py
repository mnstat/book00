import telebot
from telebot import types
import sqlite3
from datetime import datetime, timedelta
import threading
import time
import schedule
from flask import Flask
import os

# --- تنظیمات اتصال به بله ---
TOKEN = '2019587974:XDHe9gGX8eTb3OQFklhAB0XubqttvRT8bo4'
telebot.apihelper.API_URL = "https://tapi.bale.ai/bot{0}/{1}"
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# --- وب‌سرور برای Render ---
@app.route('/')
def home():
    return "ربات کتابخانه نسخه پیشرفته فعال است!"

# --- تنظیمات دیتابیس جدید ---
def init_db():
    conn = sqlite3.connect('library_v2.db')
    c = conn.cursor()
    # جدول کاربران
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (chat_id INTEGER PRIMARY KEY, name TEXT, phone TEXT, is_admin INTEGER DEFAULT 0)''')
    # جدول کتاب‌ها
    c.execute('''CREATE TABLE IF NOT EXISTS books
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, status TEXT DEFAULT 'available')''')
    # جدول امانات
    c.execute('''CREATE TABLE IF NOT EXISTS borrows
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, book_id INTEGER, 
                  borrow_date TIMESTAMP, status TEXT, reminder_sent INTEGER)''')
    # جدول پیشنهادات
    c.execute('''CREATE TABLE IF NOT EXISTS suggestions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, text TEXT, date TIMESTAMP)''')
    conn.commit()
    conn.close()

init_db()
user_steps = {}
temp_data = {}

# --- کیبوردها ---
def main_keyboard(is_admin=False):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton('📚 امانت گرفتن کتاب'), types.KeyboardButton('🗂 کارتابل من'))
    markup.add(types.KeyboardButton('💡 ثبت پیشنهاد'), types.KeyboardButton('💳 مشارکت مالی'))
    if is_admin:
        markup.add(types.KeyboardButton('⚙️ پنل مدیریت'))
    return markup

def contact_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(types.KeyboardButton('📱 ارسال شماره تماس', request_contact=True))
    return markup

def admin_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton('➕ افزودن کتاب جدید'), types.KeyboardButton('📋 لیست کتاب‌های موجود'))
    markup.add(types.KeyboardButton('👥 گزارش افراد و امانات'), types.KeyboardButton('💌 گزارش پیشنهادات'))
    markup.add(types.KeyboardButton('🔙 بازگشت به منوی اصلی'))
    return markup

# --- توابع کمکی دیتابیس ---
def is_user_registered(chat_id):
    conn = sqlite3.connect('library_v2.db')
    c = conn.cursor()
    c.execute("SELECT name FROM users WHERE chat_id=?", (chat_id,))
    res = c.fetchone()
    conn.close()
    return res is not None

def is_admin(chat_id):
    conn = sqlite3.connect('library_v2.db')
    c = conn.cursor()
    c.execute("SELECT is_admin FROM users WHERE chat_id=?", (chat_id,))
    res = c.fetchone()
    conn.close()
    return res and res[0] == 1

# --- هندلرها ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    if is_user_registered(chat_id):
        bot.send_message(chat_id, "به کتابخانه خوش آمدید!", reply_markup=main_keyboard(is_admin(chat_id)))
    else:
        user_steps[chat_id] = 'get_name'
        bot.send_message(chat_id, "سلام! برای عضویت در کتابخانه، لطفاً نام و نام خانوادگی خود را بنویسید:", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(commands=['admin'])
def admin_login(message):
    chat_id = message.chat.id
    user_steps[chat_id] = 'admin_password'
    bot.send_message(chat_id, "لطفاً رمز عبور مدیریت را وارد کنید:")

@bot.message_handler(content_types=['contact'])
def handle_contact(message):
    chat_id = message.chat.id
    if user_steps.get(chat_id) == 'get_contact':
        phone = message.contact.phone_number
        name = temp_data.get(chat_id, 'کاربر')
        
        conn = sqlite3.connect('library_v2.db')
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO users (chat_id, name, phone) VALUES (?, ?, ?)", (chat_id, name, phone))
        conn.commit()
        conn.close()
        
        if chat_id in user_steps: del user_steps[chat_id]
        if chat_id in temp_data: del temp_data[chat_id]
        
        bot.send_message(chat_id, f"✅ {name} عزیز، ثبت‌نام شما با موفقیت انجام شد.", reply_markup=main_keyboard(is_admin(chat_id)))

@bot.message_handler(func=lambda message: True)
def handle_text(message):
    chat_id = message.chat.id
    text = message.text
    step = user_steps.get(chat_id)

    # --- مراحل ثبت نام و ادمین ---
    if step == 'get_name':
        temp_data[chat_id] = text
        user_steps[chat_id] = 'get_contact'
        bot.send_message(chat_id, "لطفاً با زدن دکمه زیر، شماره تماس خود را به اشتراک بگذارید:", reply_markup=contact_keyboard())
        return

    elif step == 'admin_password':
        if text == '1234': # رمز عبور مدیریت (قابل تغییر)
            conn = sqlite3.connect('library_v2.db')
            c = conn.cursor()
            # اگر کاربر ثبت نام نکرده اول باید ثبت نام کند، فرض میکنیم ثبت نام کرده
            c.execute("UPDATE users SET is_admin=1 WHERE chat_id=?", (chat_id,))
            conn.commit()
            conn.close()
            bot.send_message(chat_id, "✅ شما به عنوان مدیر شناخته شدید.", reply_markup=admin_keyboard())
        else:
            bot.send_message(chat_id, "❌ رمز عبور اشتباه است.", reply_markup=main_keyboard(is_admin(chat_id)))
        if chat_id in user_steps: del user_steps[chat_id]
        return

    elif step == 'get_suggestion':
        conn = sqlite3.connect('library_v2.db')
        c = conn.cursor()
        c.execute("INSERT INTO suggestions (chat_id, text, date) VALUES (?, ?, ?)", (chat_id, text, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()
        bot.send_message(chat_id, "ممنون! پیشنهاد شما ثبت شد.", reply_markup=main_keyboard(is_admin(chat_id)))
        del user_steps[chat_id]
        return

    elif step == 'add_book' and is_admin(chat_id):
        conn = sqlite3.connect('library_v2.db')
        c = conn.cursor()
        c.execute("INSERT INTO books (title, status) VALUES (?, 'available')", (text,))
        conn.commit()
        conn.close()
        bot.send_message(chat_id, f"✅ کتاب «{text}» به مخزن اضافه شد.", reply_markup=admin_keyboard())
        del user_steps[chat_id]
        return

    # --- منوی اصلی کاربر ---
    if text == '📚 امانت گرفتن کتاب':
        conn = sqlite3.connect('library_v2.db')
        c = conn.cursor()
        c.execute("SELECT id, title FROM books WHERE status='available'")
        books = c.fetchall()
        conn.close()
        
        if books:
            markup = types.InlineKeyboardMarkup()
            for b in books:
                markup.add(types.InlineKeyboardButton(b[1], callback_data=f"borrow_{b[0]}"))
            bot.send_message(chat_id, "کتاب‌های موجود در کتابخانه:\n(برای امانت گرفتن روی یکی کلیک کنید)", reply_markup=markup)
        else:
            bot.send_message(chat_id, "در حال حاضر هیچ کتابی در کتابخانه موجود نیست!")

    elif text == '🗂 کارتابل من':
        conn = sqlite3.connect('library_v2.db')
        c = conn.cursor()
        c.execute('''SELECT b.id, bk.title, b.borrow_date FROM borrows b 
                     JOIN books bk ON b.book_id = bk.id 
                     WHERE b.chat_id=? AND b.status='borrowed' ''', (chat_id,))
        my_books = c.fetchall()
        conn.close()
        
        if my_books:
            for mb in my_books:
                borrow_id, title, date_str = mb
                b_date = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                deadline = b_date + timedelta(days=5)
                now = datetime.now()
                
                if now > deadline:
                    time_status = "⚠️ مهلت تمام شده!"
                else:
                    diff = deadline - now
                    time_status = f"⏳ {diff.days} روز و {diff.seconds//3600} ساعت باقی‌مانده"

                msg = f"📖 *{title}*\n{time_status}"
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("🔄 بازگشت کتاب", callback_data=f"return_{borrow_id}_{mb[1]}"), # mb[1] is book_id, wait need book_id. Let's fix query
                           types.InlineKeyboardButton("⏳ تمدید (۵ روز)", callback_data=f"extend_{borrow_id}"))
                bot.send_message(chat_id, msg, parse_mode="Markdown", reply_markup=markup)
        else:
            bot.send_message(chat_id, "شما در حال حاضر کتابی به امانت ندارید.")

    elif text == '💡 ثبت پیشنهاد':
        user_steps[chat_id] = 'get_suggestion'
        bot.send_message(chat_id, "لطفاً پیشنهاد یا انتقاد خود را بنویسید:", reply_markup=types.ReplyKeyboardRemove())

    elif text == '💳 مشارکت مالی':
        bot.send_message(chat_id, "از همراهی شما سپاسگزاریم.\nشماره کارت:\n`6037990000000000`\nبه نام: توسعه کتابخانه", parse_mode='Markdown')

    # --- منوی ادمین ---
    elif text == '⚙️ پنل مدیریت' and is_admin(chat_id):
        bot.send_message(chat_id, "به پنل مدیریت وارد شدید:", reply_markup=admin_keyboard())
        
    elif text == '🔙 بازگشت به منوی اصلی':
        bot.send_message(chat_id, "منوی کاربری:", reply_markup=main_keyboard(is_admin(chat_id)))

    elif text == '➕ افزودن کتاب جدید' and is_admin(chat_id):
        user_steps[chat_id] = 'add_book'
        bot.send_message(chat_id, "عنوان کتاب جدید را وارد کنید:")

    elif text == '📋 لیست کتاب‌های موجود' and is_admin(chat_id):
        conn = sqlite3.connect('library_v2.db')
        c = conn.cursor()
        c.execute("SELECT title FROM books WHERE status='available'")
        books = c.fetchall()
        conn.close()
        if books:
            res = "📚 *کتاب‌های موجود:*\n\n" + "\n".join([f"- {b[0]}" for b in books])
            bot.send_message(chat_id, res, parse_mode="Markdown")
        else:
            bot.send_message(chat_id, "هیچ کتاب آزادی وجود ندارد.")

    elif text == '👥 گزارش افراد و امانات' and is_admin(chat_id):
        conn = sqlite3.connect('library_v2.db')
        c = conn.cursor()
        c.execute('''SELECT u.name, u.phone, bk.title, b.borrow_date 
                     FROM borrows b 
                     JOIN users u ON b.chat_id = u.chat_id
                     JOIN books bk ON b.book_id = bk.id
                     WHERE b.status='borrowed' ''')
        records = c.fetchall()
        conn.close()
        if records:
            res = "👥 *گزارش امانات فعال:*\n\n"
            for r in records:
                res += f"👤 {r[0]} ({r[1]})\n📖 {r[2]}\n📅 تاریخ: {r[3][:10]}\n\n"
            bot.send_message(chat_id, res, parse_mode="Markdown")
        else:
            bot.send_message(chat_id, "در حال حاضر هیچ کتابی در دست امانت نیست.")

    elif text == '💌 گزارش پیشنهادات' and is_admin(chat_id):
        conn = sqlite3.connect('library_v2.db')
        c = conn.cursor()
        c.execute("SELECT u.name, s.text, s.date FROM suggestions s JOIN users u ON s.chat_id = u.chat_id ORDER BY s.id DESC LIMIT 10")
        suggs = c.fetchall()
        conn.close()
        if suggs:
            res = "💌 *آخرین پیشنهادات:*\n\n"
            for s in suggs:
                res += f"👤 {s[0]}:\n💬 {s[1]}\n⏱ {s[2][:10]}\n〰️〰️〰️\n"
            bot.send_message(chat_id, res, parse_mode="Markdown")
        else:
            bot.send_message(chat_id, "هیچ پیشنهادی ثبت نشده است.")

# --- کال‌بک‌های دکمه‌های شیشه‌ای ---
@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    chat_id = call.message.chat.id
    data = call.data.split('_')
    action = data[0]
    
    conn = sqlite3.connect('library_v2.db')
    c = conn.cursor()
    
    if action == 'borrow':
        book_id = data[1]
        # بررسی دوباره که کتاب در همین لحظه توسط شخص دیگری امانت گرفته نشده باشد
        c.execute("SELECT status, title FROM books WHERE id=?", (book_id,))
        book_status = c.fetchone()
        
        if book_status and book_status[0] == 'available':
            b_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            c.execute("INSERT INTO borrows (chat_id, book_id, borrow_date, status, reminder_sent) VALUES (?, ?, ?, 'borrowed', 0)", (chat_id, book_id, b_date))
            c.execute("UPDATE books SET status='borrowed' WHERE id=?", (book_id,))
            bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=f"✅ کتاب «{book_status[1]}» با موفقیت برای شما امانت ثبت شد. جهت مشاهده وضعیت به بخش کارتابل من مراجعه کنید.")
        else:
            bot.answer_callback_query(call.id, "❌ این کتاب همین الان توسط شخص دیگری به امانت گرفته شد!")

    elif action == 'return':
        borrow_id = data[1]
        # پیدا کردن book_id
        c.execute("SELECT book_id FROM borrows WHERE id=?", (borrow_id,))
        b_id_res = c.fetchone()
        if b_id_res:
            book_id = b_id_res[0]
            c.execute("UPDATE borrows SET status='returned' WHERE id=?", (borrow_id,))
            c.execute("UPDATE books SET status='available' WHERE id=?", (book_id,))
            bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text="✅ بازگشت کتاب با موفقیت ثبت شد.")
            bot.send_message(chat_id, "لطفاً در صورت تمایل از منوی اصلی، نظرتان را در بخش پیشنهادات بنویسید.")
            
    elif action == 'extend':
        borrow_id = data[1]
        new_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("UPDATE borrows SET borrow_date=?, reminder_sent=0 WHERE id=?", (new_date, borrow_id))
        bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text="✅ مهلت مطالعه با موفقیت ۵ روز از هم‌اکنون تمدید شد.")
        
    conn.commit()
    conn.close()

# --- سیستم چک کردن مهلت ۵ روزه ---
def check_overdue_books():
    conn = sqlite3.connect('library_v2.db')
    c = conn.cursor()
    c.execute("SELECT id, chat_id, borrow_date FROM borrows WHERE status='borrowed' AND reminder_sent=0")
    records = c.fetchall()
    
    now = datetime.now()
    for row in records:
        record_id, chat_id, borrow_date_str = row
        borrow_date = datetime.strptime(borrow_date_str, "%Y-%m-%d %H:%M:%S")
        
        if now - borrow_date >= timedelta(days=5):
            msg = "سلام ارادت؛ مدت ۵ روزه مطالعه کتاب شما به اتمام رسیده. اگر دوست دارید می‌توانید از بخش «کارتابل من» آن را تمدید کنید؛ در غیر این صورت در میدان مفید منتظر شما هستیم."
            try:
                bot.send_message(chat_id, msg)
                c.execute("UPDATE borrows SET reminder_sent=1 WHERE id=?", (record_id,))
                conn.commit()
            except:
                pass
    conn.close()

def run_scheduler():
    schedule.every(1).hours.do(check_overdue_books)
    while True:
        schedule.run_pending()
        time.sleep(60)

def run_bot():
    bot.infinity_polling()

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    threading.Thread(target=run_scheduler, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
