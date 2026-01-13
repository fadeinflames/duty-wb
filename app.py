from flask import Flask, render_template
from datetime import datetime, timedelta
import pytz

app = Flask(__name__)

# Данные сотрудников
EMPLOYEES = {
    'pavel': {
        'name': 'Павел Аминов',
        'phone': '+7 925 020 6969'
    },
    'sergey': {
        'name': 'Сергей Петухов',
        'phone': '+7 915 464 7728'
    },
    'anna': {
        'name': 'Анна',
        'phone': '+7 (999) 000-00-00'  # Замените на реальный телефон
    }
}

# Флаг для включения Анны как постоянного дневного дежурного
# Когда Анна начнет работать, установите ANNA_ENABLED = True
ANNA_ENABLED = False

# Дата начала ротации (можно изменить)
START_DATE = datetime(2024, 1, 1, tzinfo=pytz.UTC)

# Время дня/ночи
DAY_START = 8  # 8:00
DAY_END = 20   # 20:00


def get_week_number(date):
    """Вычисляет номер недели с начала ротации"""
    delta = date - START_DATE
    return delta.days // 7


def is_day_time(hour):
    """Определяет, день сейчас или ночь"""
    return DAY_START <= hour < DAY_END


def get_current_duty():
    """Определяет текущего дежурного"""
    # Получаем текущее время в UTC (можно изменить на нужный часовой пояс)
    now = datetime.now(pytz.UTC)
    week_num = get_week_number(now)
    hour = now.hour
    
    # Определяем, день или ночь
    is_day = is_day_time(hour)
    
    # Если Анна включена - она всегда днем, ночью ротация между Павлом и Сергеем
    if ANNA_ENABLED:
        if is_day:
            return EMPLOYEES['anna'], 'day'
        else:
            # Ночью ротация между Павлом и Сергеем
            if week_num % 2 == 0:
                return EMPLOYEES['sergey'], 'night'
            else:
                return EMPLOYEES['pavel'], 'night'
    else:
        # Старая логика ротации (пока Анна не работает)
        # Если неделя четная - Павел днем, Сергей ночью
        # Если неделя нечетная - Сергей днем, Павел ночью
        if week_num % 2 == 0:
            if is_day:
                return EMPLOYEES['pavel'], 'day'
            else:
                return EMPLOYEES['sergey'], 'night'
        else:
            if is_day:
                return EMPLOYEES['sergey'], 'day'
            else:
                return EMPLOYEES['pavel'], 'night'


@app.route('/')
def index():
    """Главная страница с информацией о текущем дежурном"""
    duty_person, duty_type = get_current_duty()
    
    now = datetime.now(pytz.UTC)
    week_num = get_week_number(now)
    
    # Определяем следующего дежурного для информации
    next_week_num = week_num + 1
    if ANNA_ENABLED:
        # Анна всегда днем
        next_day = EMPLOYEES['anna']
        # Ночью ротация
        if next_week_num % 2 == 0:
            next_night = EMPLOYEES['sergey']
        else:
            next_night = EMPLOYEES['pavel']
    else:
        # Старая логика ротации
        if next_week_num % 2 == 0:
            next_day = EMPLOYEES['pavel']
            next_night = EMPLOYEES['sergey']
        else:
            next_day = EMPLOYEES['sergey']
            next_night = EMPLOYEES['pavel']
    
    return render_template('index.html',
                         duty_person=duty_person,
                         duty_type=duty_type,
                         current_time=now.strftime('%Y-%m-%d %H:%M:%S UTC'),
                         week_number=week_num,
                         next_day=next_day,
                         next_night=next_night)


@app.route('/api/current')
def api_current():
    """API endpoint для получения текущего дежурного"""
    duty_person, duty_type = get_current_duty()
    return {
        'name': duty_person['name'],
        'phone': duty_person['phone'],
        'duty_type': duty_type,
        'timestamp': datetime.now(pytz.UTC).isoformat()
    }


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
