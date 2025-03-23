# Steam Tracker Bot 🤖🎮

Telegram бот для отслеживания статуса Steam аккаунтов. Мониторит игровые сессии, изменения никнеймов и онлайн-статуса.

## Возможности ✨
- Отслеживание до 5 ссылок
- Уведомления о:
  - Запуске/остановке игр 🕹️
  - Смене никнейма 📛
  - Изменении онлайн-статуса 🌐
- Автоматическая проверка каждые 5 минут
- Управление ссылками через inline-кнопки

## Установка ⚙️

1. Клонировать репозиторий:
```
git clone https://github.com/undetectedcoder/SteamTracker/
cd SteamTracker
```
2. Установить зависимости:
```
python -m venv venv
source venv/bin/activate  # Linux/MacOS
venv\Scripts\activate  # Windows
pip install -r requirements.txt
```
3. Схема БД Sqlite
```
erDiagram
    USER ||--o{ LINK : has
    USER {
        integer id PK
        integer chat_id
        boolean is_premium
        datetime created_at
    }
    
    LINK ||--o| ACCOUNT_STATUS : has
    LINK {
        integer id PK
        string url
        integer user_id FK
        datetime created_at
    }
    
    ACCOUNT_STATUS {
        integer id PK
        integer link_id FK
        boolean in_game
        string game_name
        string username
        string online_status
        datetime session_start
        datetime last_checked
    }
```
4. Зависимости(для установки - pip install -r requirements.txt):
python-telegram-bot>=20.0
beautifulsoup4>=4.9.3
fake-useragent>=1.1.3
aiohttp>=3.8.1
sqlalchemy>=2.0.0
