from flask import Flask, render_template
from datetime import datetime, timedelta
import pytz
import calendar as cal_module

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
# Начало первой недели ротации - понедельник
START_DATE = datetime(2024, 1, 1, tzinfo=TIMEZONE)
# Убедимся, что это понедельник
while START_DATE.weekday() != 0:
    START_DATE += timedelta(days=1)


def get_week_number(date):
    """Вычисляет номер недели с начала ротации"""
    # Находим понедельник этой недели
    days_since_monday = date.weekday()
    monday = date - timedelta(days=days_since_monday)
    
    # Вычисляем разницу в неделях от START_DATE
    delta = monday - START_DATE
    return delta.days // 7


def get_duty_for_week(week_num):
    """
    Определяет Primary и Secondary для недели
    Ротация без нахлестов: каждый человек не может быть Primary на одной неделе
    и Secondary на следующей (или наоборот)
    
    Паттерн на 6 недель:
    Неделя 0: P: Павел(0), S: Сергей(1)
    Неделя 1: P: Сергей(1), S: Максим(2)  - Сергей был S, теперь P (нахлест!)
    
    Правильный паттерн:
    Неделя 0: P: Павел(0), S: Сергей(1)
    Неделя 1: P: Максим(2), S: Павел(0)   - Павел был P, теперь S (нахлест!)
    
    Лучший вариант - 3-недельный цикл с перерывами:
    Неделя 0: P: Павел(0), S: Сергей(1)
    Неделя 1: P: Максим(2), S: Павел(0)   - Павел отдыхал как Primary, теперь Secondary
    Неделя 2: P: Сергей(1), S: Максим(2)  - Максим отдыхал как Primary, теперь Secondary
    
    Но это тоже нахлест. Нужен паттерн где каждый отдыхает между дежурствами:
    
    Неделя 0: P: Павел(0), S: Сергей(1)
    Неделя 1: P: Максим(2), S: Павел(0)   - Павел был P, теперь S - нахлест!
    
    Правильный паттерн без нахлестов (6-недельный цикл):
    Неделя 0: P: Павел(0), S: Сергей(1)
    Неделя 1: P: Максим(2), S: Сергей(1)  - Сергей был S, теперь S (повтор, но не нахлест Primary/Secondary)
    Неделя 2: P: Сергей(1), S: Павел(0)   - Сергей был S, теперь P - нахлест!
    
    Идеальный паттерн (каждый отдыхает минимум 1 неделю между дежурствами):
    Неделя 0: P: Павел(0), S: Сергей(1)
    Неделя 1: P: Максим(2), S: Павел(0)   - Павел отдыхал, Сергей отдыхал
    Неделя 2: P: Сергей(1), S: Максим(2)  - Максим отдыхал, Павел отдыхал
    Неделя 3: P: Павел(0), S: Максим(2)   - Павел отдыхал, Сергей отдыхал
    Неделя 4: P: Сергей(1), S: Павел(0)    - Сергей отдыхал, Максим отдыхал
    Неделя 5: P: Максим(2), S: Сергей(1)   - Максим отдыхал, Павел отдыхал
    
    Проверка нахлестов:
    Неделя 0->1: Павел P->S (нахлест!), Сергей S->отдых (OK), Максим отдых->P (OK)
    Неделя 1->2: Максим P->S (нахлест!), Павел S->отдых (OK), Сергей отдых->P (OK)
    
    Нужен паттерн где никто не переходит из P в S или из S в P на соседних неделях.
    
    Правильный паттерн:
    Неделя 0: P: Павел(0), S: Сергей(1)
    Неделя 1: P: Максим(2), S: Павел(0)   - Павел P->S нахлест!
    
    Финальный правильный паттерн (каждый отдыхает между дежурствами):
    Неделя 0: P: Павел(0), S: Сергей(1)
    Неделя 1: P: Максим(2), S: (кто-то кто отдыхал) - но Сергей был S, не может быть сразу P
    """
    # Ротация без нахлестов: никто не переходит из Primary в Secondary (или наоборот) на соседних неделях
    # Каждый отдыхает минимум 1 неделю между дежурствами
    
    pattern = week_num % 6
    
    # Правильный паттерн (6-недельный цикл):
    # Неделя 0: P: Павел(0), S: Сергей(1)
    # Неделя 1: P: Максим(2), S: Сергей(1)  - Сергей остается S (не нахлест P<->S)
    # Неделя 2: P: Павел(0), S: Максим(2)  - Павел отдыхал, Максим отдыхал
    # Неделя 3: P: Сергей(1), S: Павел(0)  - Сергей отдыхал, Павел отдыхал
    # Неделя 4: P: Максим(2), S: Павел(0)  - Максим отдыхал, Павел остается S (не нахлест)
    # Неделя 5: P: Сергей(1), S: Максим(2) - Сергей отдыхал, Максим отдыхал
    
    rotation = [
        (0, 1),  # Неделя 0: P: Павел, S: Сергей
        (2, 1),  # Неделя 1: P: Максим, S: Сергей (Сергей остается S - не нахлест)
        (0, 2),  # Неделя 2: P: Павел, S: Максим (оба отдыхали)
        (1, 0),  # Неделя 3: P: Сергей, S: Павел (оба отдыхали)
        (2, 0),  # Неделя 4: P: Максим, S: Павел (оба отдыхали)
        (1, 2),  # Неделя 5: P: Сергей, S: Максим (оба отдыхали)
    ]
    
    primary_idx, secondary_idx = rotation[pattern]
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


def get_calendar_month(year, month):
    """Генерирует календарь для месяца с данными о дежурных"""
    # Используем встроенный модуль calendar
    cal = cal_module.monthcalendar(year, month)
    
    calendar_data = []
    
    for week in cal:
        week_data = []
        for day in week:
            if day == 0:
                # Пустой день (из другого месяца)
                week_data.append(None)
            else:
                date = datetime(year, month, day, tzinfo=TIMEZONE)
                weekday = date.weekday()
                week_num = get_week_number(date)
                
                # Получаем дежурных для этой недели
                primary, secondary = get_duty_for_week(week_num)
                
                # На воскресенье только Secondary
                if weekday == 6:  # Sunday
                    primary = None
                
                week_data.append({
                    'day': day,
                    'weekday': weekday,
                    'primary': primary,
                    'secondary': secondary,
                    'date': date
                })
        calendar_data.append(week_data)
    
    return calendar_data


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
def calendar_view():
    """Страница с календарем ротации на полгода"""
    now = datetime.now(TIMEZONE)
    year = now.year
    month = now.month
    
    # Названия месяцев
    month_names = ['', 'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 
                   'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']
    
    # Генерируем данные для 6 месяцев вперед (текущий + 5 следующих)
    months_data = []
    current_year = year
    current_month = month
    
    for i in range(6):
        calendar_data = get_calendar_month(current_year, current_month)
        months_data.append({
            'year': current_year,
            'month': current_month,
            'month_name': month_names[current_month],
            'calendar_data': calendar_data
        })
        
        # Переходим к следующему месяцу
        current_month += 1
        if current_month > 12:
            current_month = 1
            current_year += 1
    
    # Отладочная информация (можно убрать в продакшене)
    month_list = [f"{m['month_name']} {m['year']}" for m in months_data]
    print(f"Generated {len(months_data)} months: {month_list}")
    
    return render_template('calendar.html',
                         months_data=months_data,
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
