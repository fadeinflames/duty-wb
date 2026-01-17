from flask import Flask, render_template
from datetime import datetime, timedelta
import pytz
from calendar import monthrange

app = Flask(__name__)

# Данные сотрудников (в порядке ротации)
EMPLOYEES = [
    {
        'id': 'pavel',
        'name': 'Павел Аминов',
        'telegram': '@username',  # Замените на реальный Telegram
        'bend': '@username'  # Замените на реальный Bend
    },
    {
        'id': 'sergey',
        'name': 'Сергей Петухов',
        'telegram': '@username',  # Замените на реальный Telegram
        'bend': '@username'  # Замените на реальный Bend
    },
    {
        'id': 'maxim',
        'name': 'Максим Огурцов',
        'telegram': '@username',  # Замените на реальный Telegram
        'bend': '@username'  # Замените на реальный Bend
    }
]

# Экстренный контакт (эскалация) - лид команды
EMERGENCY_CONTACT = {
    'name': 'Максим Гусев',
    'telegram': '@username',  # Замените на реальный Telegram
    'bend': '@username'  # Замените на реальный Bend (Mattermost)
}

# Часовой пояс (MSK - Московское время)
TIMEZONE = pytz.timezone('Europe/Moscow')

# Дата начала ротации (можно изменить)
# Начало первой недели ротации
START_DATE = datetime(2024, 1, 1, tzinfo=TIMEZONE)


def get_week_number(date):
    """Вычисляет номер недели с начала ротации"""
    delta = date - START_DATE
    return delta.days // 7


def get_duty_for_week(week_num):
    """
    Определяет Primary и Secondary для недели
    По паттерну из скриншота:
    Неделя 0: P: Павел(0), S: Сергей(1)
    Неделя 1: P: Сергей(1), S: Максим(2)
    Неделя 2: P: Максим(2), S: Павел(0)
    Неделя 3: P: Павел(0), S: Максим(2)
    Неделя 4: P: Сергей(1), S: Павел(0)
    Неделя 5: P: Максим(2), S: Сергей(1)
    """
    # Primary ротация: 0-Павел, 1-Сергей, 2-Максим, 3-Павел...
    primary_idx = week_num % len(EMPLOYEES)
    
    # Secondary ротация по паттерну:
    # Неделя % 6 == 0: Secondary = 1 (Сергей)
    # Неделя % 6 == 1: Secondary = 2 (Максим)
    # Неделя % 6 == 2: Secondary = 0 (Павел)
    # Неделя % 6 == 3: Secondary = 2 (Максим)
    # Неделя % 6 == 4: Secondary = 0 (Павел)
    # Неделя % 6 == 5: Secondary = 1 (Сергей)
    
    pattern = week_num % 6
    if pattern == 0:
        secondary_idx = 1  # Сергей
    elif pattern == 1:
        secondary_idx = 2  # Максим
    elif pattern == 2:
        secondary_idx = 0  # Павел
    elif pattern == 3:
        secondary_idx = 2  # Максим
    elif pattern == 4:
        secondary_idx = 0  # Павел
    else:  # pattern == 5
        secondary_idx = 1  # Сергей
    
    return EMPLOYEES[primary_idx], EMPLOYEES[secondary_idx]


def get_current_duty():
    """Определяет текущих Primary и Secondary дежурных"""
    now = datetime.now(TIMEZONE)
    week_num = get_week_number(now)
    weekday = now.weekday()  # 0 = Monday, 6 = Sunday
    
    primary, secondary = get_duty_for_week(week_num)
    
    # На воскресенье только Secondary
    if weekday == 6:  # Sunday
        return None, secondary
    else:
        return primary, secondary


def get_calendar_data(year, month):
    """Генерирует данные календаря для указанного месяца"""
    last_day_num = monthrange(year, month)[1]
    
    calendar = []
    
    for day in range(1, last_day_num + 1):
        date = datetime(year, month, day, tzinfo=TIMEZONE)
        weekday = date.weekday()
        
        # Определяем неделю для этого дня
        day_week = get_week_number(date)
        
        # Получаем дежурных для этой недели
        primary, secondary = get_duty_for_week(day_week)
        
        # На воскресенье только Secondary
        if weekday == 6:  # Sunday
            primary = None
        
        calendar.append({
            'day': day,
            'weekday': weekday,
            'primary': primary,
            'secondary': secondary
        })
    
    return calendar


@app.route('/')
def index():
    """Главная страница с информацией о текущих дежурных"""
    primary, secondary = get_current_duty()
    
    now = datetime.now(TIMEZONE)
    week_num = get_week_number(now)
    
    # Текущая неделя
    current_primary, current_secondary = get_duty_for_week(week_num)
    
    # Следующая неделя
    next_primary, next_secondary = get_duty_for_week(week_num + 1)
    
    return render_template('index.html',
                         primary=primary if primary else current_primary,
                         secondary=secondary,
                         current_time=now.strftime('%d.%m.%Y %H:%M MSK'),
                         next_primary=next_primary,
                         next_secondary=next_secondary,
                         emergency_contact=EMERGENCY_CONTACT)


@app.route('/calendar')
def calendar():
    """Страница с календарем ротации"""
    now = datetime.now(TIMEZONE)
    year = now.year
    month = now.month
    
    # Получаем данные для текущего месяца
    calendar_data = get_calendar_data(year, month)
    
    # Также для следующего месяца
    if month == 12:
        next_year = year + 1
        next_month = 1
    else:
        next_year = year
        next_month = month + 1
    
    next_calendar_data = get_calendar_data(next_year, next_month)
    
    return render_template('calendar.html',
                         year=year,
                         month=month,
                         next_year=next_year,
                         next_month=next_month,
                         calendar_data=calendar_data,
                         next_calendar_data=next_calendar_data,
                         now=now)


@app.route('/api/current')
def api_current():
    """API endpoint для получения текущих дежурных"""
    primary, secondary = get_current_duty()
    return {
        'primary': primary['name'] if primary else None,
        'secondary': secondary['name'],
        'timestamp': datetime.now(TIMEZONE).isoformat()
    }


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
