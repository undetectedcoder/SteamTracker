import logging
import re
import asyncio
import random
from datetime import datetime
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import aiohttp
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)
ua = UserAgent()
Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, unique=True)
    is_premium = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)
    links = relationship("Link", back_populates="user")

class Link(Base):
    __tablename__ = 'links'
    id = Column(Integer, primary_key=True)
    url = Column(String)
    user_id = Column(Integer, ForeignKey('users.id'))
    created_at = Column(DateTime, default=datetime.now)
    user = relationship("User", back_populates="links")
    status = relationship("AccountStatus", uselist=False, back_populates="link")

class AccountStatus(Base):
    __tablename__ = 'account_statuses'
    id = Column(Integer, primary_key=True)
    link_id = Column(Integer, ForeignKey('links.id'))
    in_game = Column(Boolean)
    game_name = Column(String)
    username = Column(String)
    online_status = Column(String)
    session_start = Column(DateTime)
    last_checked = Column(DateTime)
    link = relationship("Link", back_populates="status")

engine = create_engine('sqlite:///bot.db')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
db_session = Session()

async def parse_steam_profile(url: str) -> dict:
    try:
        headers = {
            'User-Agent': ua.random,
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://steamcommunity.com/',
            'DNT': '1'
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{url}?rand={random.randint(10000,99999)}",
                headers=headers,
                timeout=25
            ) as response:
                response.raise_for_status()
                html = await response.text()
        
        soup = BeautifulSoup(html, 'html.parser')
        result = {
            'username': 'Unknown',
            'in_game': False,
            'game_name': None,
            'online_status': 'offline',
            'error': None
        }

        if soup.find('div', class_='profile_private_info'):
            return {'error': 'Private profile'}

        username_tag = soup.find('span', class_='actual_persona_name')
        result['username'] = username_tag.get_text(strip=True) if username_tag else \
            soup.find('div', class_='profile_header_content').find('h1').get_text(strip=True)

        status_div = soup.find('div', class_='profile_in_game_state')
        if status_div:
            result['online_status'] = status_div.get_text(strip=True).lower()

        game_block = soup.find('div', class_='profile_in_game_header')
        game_name_tag = soup.find('div', class_='profile_in_game_name')
        
        if game_block and game_name_tag:
            game_name = game_name_tag.get_text(strip=True)
            result['game_name'] = game_name
            if game_name.lower() not in ['', 'steam', 'steam client']:
                result['in_game'] = True

        return result

    except Exception as e:
        logger.error(f"Parsing error: {str(e)}")
        return {'error': f'Error: {str(e)}'}

async def get_account_status(url: str) -> AccountStatus:
    data = await parse_steam_profile(url)
    if data.get('error'):
        logger.error(f"Error for {url}: {data.get('error')}")
        return None

    return AccountStatus(
        in_game=data['in_game'],
        game_name=data.get('game_name'),
        username=data['username'],
        online_status=data.get('online_status', 'offline'),
        session_start=datetime.now() if data['in_game'] else None,
        last_checked=datetime.now()
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎮 Steam Аккаунт Чекер\n\n"
        "Отправь мне ссылку на профиль стим для отслеживания:\n"
        "• https://steamcommunity.com/id/feel_free\n"
        "• https://steamcommunity.com/profiles/76561199761967394\n\n"
        "Я оповещу тебя о:\n"
        "🕹 Игровых сессиях\n"
        "📛 Изменениях никнеймов\n"
        "🌐 Изменения статуса"
    )

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        chat_id = update.effective_chat.id
        url = update.message.text.strip()

        if not re.match(r'^https://steamcommunity\.com/(id|profiles)/[\w]+/?$', url):
            await update.message.reply_text("❌ Неправильный формат ссылки!")
            return

        user = db_session.query(User).filter_by(chat_id=chat_id).first() or User(chat_id=chat_id)
        db_session.add(user)
        
        if len(user.links) >= (100 if user.is_premium else 5):
            await update.message.reply_text("❌ Достигнут лимит ссылок. \nКомманда /links для управления")
            return

        if any(link.url == url for link in user.links):
            await update.message.reply_text("⚠️ Эта ссылка уже отслеживается")
            return

        link = Link(url=url, user=user)
        db_session.add(link)
        db_session.commit()

        await update.message.reply_text("✅ Ссылка добавлена, провожу первоначальную проверку...")
        await send_status_update(update, link)

    except Exception as e:
        logger.error(f"Link handling error: {e}")
        await update.message.reply_text("⚠️ Ошибка во время запроса \nПовторите попытку позже.")

async def send_status_update(update: Update, link: Link):
    status = await get_account_status(link.url)
    if not status:
        await update.message.reply_text("⚠️ Нет доступа к профилю.\nВозможно он приватный.")
        return

    message = [
        f"🔗 Профиль: {link.url}",
        f"👤 Имя: {status.username}",
        f"🌐 Статус: {status.online_status.capitalize()}",
        "🎮 Активность: " + (f"Играет в: {status.game_name} 🕹" if status.in_game else "Не в игре ❌")
    ]

    if status.in_game and status.session_start:
        duration = datetime.now() - status.session_start
        message.append(f"⏱ Session: {duration.seconds//60} minutes")

    await update.message.reply_text("\n".join(message))

async def manage_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = db_session.query(User).filter_by(chat_id=update.effective_chat.id).first()
        if not user or not user.links:
            await update.message.reply_text("📭 Нет ссылок")
            return

        keyboard = [
            [InlineKeyboardButton(f"🗑 {link.url}", callback_data=f"delete_{link.id}")]
            for link in user.links
        ]
        await update.message.reply_text(
            "🔗 Ваши ссылки:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except Exception as e:
        logger.error(f"Link management error: {e}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("delete_"):
        try:
            link_id = int(query.data.split("_")[1])
            link = db_session.query(Link).get(link_id)
            
            if link:
                db_session.delete(link)
                db_session.commit()
                await query.message.edit_text(f"✅ Удалено: {link.url}")
            else:
                await query.message.edit_text("❌ Ссылка не найдена")

        except Exception as e:
            logger.error(f"Deletion error: {e}")
            await query.message.edit_text("⚠️ Ошибка при удалении ссылки\nПовторите попытку позже.")

async def check_accounts(context: ContextTypes.DEFAULT_TYPE):
    try:
        links = db_session.query(Link).all()
        for link in links:
            try:
                prev_status = link.status
                current_status = await get_account_status(link.url)
                
                if not current_status:
                    continue

                messages = []
                changes = False

                if prev_status:
                    if prev_status.in_game != current_status.in_game:
                        action = "Начал играть 🎮" if current_status.in_game else "Прекратил играть 🚪"
                        messages.append(f"➡️ {action}")
                        changes = True
                        if not current_status.in_game and prev_status.session_start:
                            duration = datetime.now() - prev_status.session_start
                            messages.append(f"⏱ Session lasted: {duration.seconds//60} minutes")
                    if current_status.game_name != prev_status.game_name:
                        if current_status.in_game:
                            messages.append(f"🎮 Новая игра: {current_status.game_name}")
                        changes = True
                    if current_status.username != prev_status.username:
                        messages.append(f"📛 Новый никнейм: {current_status.username}")
                        changes = True
                    if current_status.online_status != prev_status.online_status:
                        messages.append(f"🌐 Статус: {current_status.online_status.capitalize()}")
                        changes = True

                    current_status.session_start = (
                        prev_status.session_start 
                        if current_status.in_game and prev_status.in_game 
                        else (datetime.now() if current_status.in_game else None)
                    )
                else:
                    current_status.session_start = datetime.now() if current_status.in_game else None

                if changes:
                    await context.bot.send_message(
                        chat_id=link.user.chat_id,
                        text=f"🔔 Обновление для: {link.url}:\n" + "\n".join(messages)
                    )

                if prev_status:
                    prev_status.in_game = current_status.in_game
                    prev_status.game_name = current_status.game_name
                    prev_status.username = current_status.username
                    prev_status.online_status = current_status.online_status
                    prev_status.session_start = current_status.session_start
                    prev_status.last_checked = datetime.now()
                else:
                    link.status = current_status

                db_session.commit()

            except Exception as e:
                logger.error(f"Check error for {link.url}: {e}")
                await context.bot.send_message(
                    chat_id=link.user.chat_id,
                    text=f"⚠️ Ошибка проверки ссылки: {link.url}"
                )

    except Exception as e:
        logger.error(f"Checker error: {e}")

def main():
    application = Application.builder().token("ТОКЕН").build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("links", manage_links))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    application.add_handler(CallbackQueryHandler(button_handler))
    job_queue = application.job_queue
    job_queue.run_repeating(check_accounts, interval=300, first=10)  

    application.run_polling()

if __name__ == "__main__":
    main()