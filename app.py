from flask import Flask, render_template, request, jsonify, redirect, url_for
from datetime import datetime, timedelta
import pytz
import calendar as cal_module
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import and_

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///duty_substitutions.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Данные сотрудников (в порядке ротации)
EMPLOYEES = [
    {
        'id': 'pavel',
        'name': 'Павел Аминов',
        'telegram': '@nytera',  # Замените на реальный Telegram
        'bend': '@aminov.pavel3'  # Замените на реальный Bend
    },
    {
        'id': 'sergey',
        'name': 'Сергей Петухов',
        'telegram': '@Fornization',  # Замените на реальный Telegram
        'bend': '@petuhov.sergey15'  # Замените на реальный Bend
    },
    {
        'id': 'maxim',
        'name': 'Максим Огурцов',
        'telegram': '@username',  # Замените на реальный Telegram
        'bend': '@ogurcov.maksim5'  # Замените на реальный Bend
    }
]

# Экстренный контакт (эскалация) - лид команды
EMERGENCY_CONTACT = {
    'name': 'Максим Гусев',
    'telegram': '@fadeinflames',  # Замените на реальный Telegram
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


# Модель БД для замен дежурных
class DutySubstitution(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, index=True)
    duty_type = db.Column(db.String(10), nullable=False)  # 'primary' или 'secondary'
    original_employee_id = db.Column(db.String(20), nullable=False)
    substitute_employee_id = db.Column(db.String(20), nullable=False)
    reason = db.Column(db.String(200))  # Причина замены (отпуск и т.д.)
    created_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'date': self.date.isoformat(),
            'duty_type': self.duty_type,
            'original_employee_id': self.original_employee_id,
            'substitute_employee_id': self.substitute_employee_id,
            'reason': self.reason
        }


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
    
    Правильный паттерн (6-недельный цикл):
    Неделя 0: P: Павел(0), S: Сергей(1)
    Неделя 1: P: Максим(2), S: Сергей(1)  - Сергей остается S (не нахлест P<->S)
    Неделя 2: P: Павел(0), S: Максим(2)  - Павел отдыхал, Максим отдыхал
    Неделя 3: P: Сергей(1), S: Павел(0)  - Сергей отдыхал, Павел отдыхал
    Неделя 4: P: Максим(2), S: Павел(0)  - Максим отдыхал, Павел остается S (не нахлест)
    Неделя 5: P: Сергей(1), S: Максим(2) - Сергей отдыхал, Максим отдыхал
    """
    pattern = week_num % 6
    
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


def get_duty_for_date(date, check_substitutions=True):
    """
    Определяет дежурных для конкретной даты с учетом замен
    Суббота - только Primary
    Воскресенье - только Secondary
    """
    weekday = date.weekday()
    week_num = get_week_number(date)
    
    # Получаем базовых дежурных для недели
    primary, secondary = get_duty_for_week(week_num)
    
    # Проверяем замены в БД
    if check_substitutions:
        date_only = date.date()
        substitution = DutySubstitution.query.filter(
            and_(
                DutySubstitution.date == date_only,
                DutySubstitution.duty_type.in_(['primary', 'secondary'])
            )
        ).first()
        
        if substitution:
            if substitution.duty_type == 'primary':
                # Находим заменяющего
                substitute = next((e for e in EMPLOYEES if e['id'] == substitution.substitute_employee_id), None)
                if substitute:
                    primary = substitute
            elif substitution.duty_type == 'secondary':
                # Находим заменяющего
                substitute = next((e for e in EMPLOYEES if e['id'] == substitution.substitute_employee_id), None)
                if substitute:
                    secondary = substitute
    
    # Суббота (5) - только Primary
    if weekday == 5:
        return primary, None
    
    # Воскресенье (6) - только Secondary
    if weekday == 6:
        return None, secondary
    
    # Остальные дни - оба дежурных
    return primary, secondary


def get_current_duty():
    """Определяет текущих Primary и Secondary дежурных"""
    now = datetime.now(TIMEZONE)
    return get_duty_for_date(now)


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
                
                # Получаем дежурных для этой даты
                primary, secondary = get_duty_for_date(date)
                
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
    next_week_num = week_num + 1
    next_primary, next_secondary = get_duty_for_week(next_week_num)
    
    # Получаем замены на следующую неделю
    next_week_start = now + timedelta(days=(7 - now.weekday()))
    next_week_substitutions = []
    for i in range(7):
        check_date = next_week_start + timedelta(days=i)
        sub = DutySubstitution.query.filter_by(date=check_date.date()).first()
        if sub:
            next_week_substitutions.append(sub.to_dict())
    
    return render_template('index.html',
                         primary=primary if primary else current_primary,
                         secondary=secondary,
                         current_time=now.strftime('%d.%m.%Y %H:%M MSK'),
                         next_primary=next_primary,
                         next_secondary=next_secondary,
                         next_week_num=next_week_num,
                         emergency_contact=EMERGENCY_CONTACT,
                         employees=EMPLOYEES,
                         substitutions=next_week_substitutions)


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
    
    return render_template('calendar.html',
                         months_data=months_data,
                         now=now,
                         employees=EMPLOYEES)


@app.route('/api/substitutions', methods=['GET'])
def get_substitutions():
    """Получить все замены"""
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    query = DutySubstitution.query
    
    if start_date:
        query = query.filter(DutySubstitution.date >= datetime.fromisoformat(start_date).date())
    if end_date:
        query = query.filter(DutySubstitution.date <= datetime.fromisoformat(end_date).date())
    
    substitutions = query.order_by(DutySubstitution.date).all()
    return jsonify([s.to_dict() for s in substitutions])


@app.route('/api/substitutions', methods=['POST'])
def create_substitution():
    """Создать замену дежурного"""
    data = request.json
    
    # Проверяем, нет ли уже замены на эту дату
    existing = DutySubstitution.query.filter_by(
        date=datetime.fromisoformat(data['date']).date(),
        duty_type=data['duty_type']
    ).first()
    
    if existing:
        return jsonify({'error': 'Замена на эту дату уже существует'}), 400
    
    substitution = DutySubstitution(
        date=datetime.fromisoformat(data['date']).date(),
        duty_type=data['duty_type'],
        original_employee_id=data['original_employee_id'],
        substitute_employee_id=data['substitute_employee_id'],
        reason=data.get('reason', '')
    )
    
    db.session.add(substitution)
    db.session.commit()
    
    return jsonify(substitution.to_dict()), 201


@app.route('/api/substitutions/<int:sub_id>', methods=['DELETE'])
def delete_substitution(sub_id):
    """Удалить замену"""
    substitution = DutySubstitution.query.get_or_404(sub_id)
    db.session.delete(substitution)
    db.session.commit()
    return jsonify({'message': 'Замена удалена'}), 200


@app.route('/api/current')
def api_current():
    """API endpoint для получения текущих дежурных"""
    date_str = request.args.get('date')
    if date_str:
        date = datetime.fromisoformat(date_str).replace(tzinfo=TIMEZONE)
        primary, secondary = get_duty_for_date(date, check_substitutions=False)
    else:
        primary, secondary = get_current_duty()
    
    return {
        'primary': primary['name'] if primary else None,
        'primary_id': primary['id'] if primary else None,
        'secondary': secondary['name'] if secondary else None,
        'secondary_id': secondary['id'] if secondary else None,
        'timestamp': datetime.now(TIMEZONE).isoformat()
    }


# Инициализация БД
with app.app_context():
    db.create_all()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
