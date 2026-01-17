from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from datetime import datetime, timedelta
import pytz
import calendar as cal_module
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import and_
import os
from functools import wraps

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///duty_substitutions.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('APP_SECRET_KEY', 'change-me')
db = SQLAlchemy(app)

AUTH_USER = os.environ.get('APP_AUTH_USER', 'admin')
AUTH_PASS = os.environ.get('APP_AUTH_PASS', 'wbadminsre')

# Данные сотрудников (в порядке ротации)
EMPLOYEE_DEFAULTS = [
    {
        'id': 'pavel',
        'name': 'Павел Аминов',
        'telegram': '@nytera',  # Замените на реальный Telegram
        'band': '@aminov.pavel3'  # Замените на реальный Band
    },
    {
        'id': 'sergey',
        'name': 'Сергей Петухов',
        'telegram': '@Fornization',  # Замените на реальный Telegram
        'band': '@petuhov.sergey15'  # Замените на реальный Band
    },
    {
        'id': 'maxim',
        'name': 'Максим Огурцов',
        'telegram': '@username',  # Замените на реальный Telegram
        'band': '@ogurcov.maksim5cal'  # Замените на реальный Band
    }
]

# Экстренный контакт (эскалация) - лид команды
EMERGENCY_CONTACT = {
    'name': 'Максим Гусев',
    'telegram': '@fadeinflames',  # Замените на реальный Telegram
    'band': '@username'  # Замените на реальный Band (Mattermost)
}

# Часовой пояс (MSK - Московское время)
TIMEZONE = pytz.timezone('Europe/Moscow')

# Дата начала ротации
# Неделя 19-25 января должна быть: Павел Primary, Сергей Secondary (неделя 0)
# 19 января 2026 - понедельник
START_DATE = datetime(2026, 1, 19, tzinfo=TIMEZONE)


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

class EmployeeProfile(db.Model):
    id = db.Column(db.String(20), primary_key=True)
    name = db.Column(db.String(100), nullable=True)
    telegram = db.Column(db.String(100), nullable=True)
    band = db.Column(db.String(100), nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'telegram': self.telegram,
            'band': self.band
        }

def get_employees():
    """Возвращает список сотрудников с учетом профилей из БД"""
    profiles = {p.id: p for p in EmployeeProfile.query.all()}
    employees = []
    for emp in EMPLOYEE_DEFAULTS:
        profile = profiles.get(emp['id'])
        if profile:
            employees.append({
                'id': emp['id'],
                'name': profile.name or emp['name'],
                'telegram': profile.telegram or emp['telegram'],
                'band': profile.band or emp['band']
            })
        else:
            employees.append(emp.copy())
    return employees

def get_employee_map():
    """Возвращает словарь сотрудников по id"""
    employees = get_employees()
    return {e['id']: e for e in employees}


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not session.get('auth'):
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Unauthorized'}), 401
            return redirect(url_for('login', next=request.path))
        return func(*args, **kwargs)
    return wrapper

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
    employees = get_employees()
    return employees[primary_idx], employees[secondary_idx]


def get_duty_for_date(date, check_substitutions=True, substitutions_map=None, employees_map=None):
    """
    Определяет дежурных для конкретной даты с учетом замен
    Суббота - Primary = недельный Primary
    Воскресенье - Primary = недельный Secondary (тот кто был Secondary всю неделю)
    В выходные всегда показывается только Primary
    """
    weekday = date.weekday()
    week_num = get_week_number(date)
    
    # Получаем базовых дежурных для недели
    week_primary, week_secondary = get_duty_for_week(week_num)
    if employees_map is None:
        employees_map = get_employee_map()
    
    # Проверяем замены в БД
    if check_substitutions:
        date_only = date.date()
        if substitutions_map is not None:
            day_subs = substitutions_map.get(date_only, {})
            substitutions = list(day_subs.values())
        else:
            substitutions = DutySubstitution.query.filter(
                and_(
                    DutySubstitution.date == date_only,
                    DutySubstitution.duty_type.in_(['primary', 'secondary'])
                )
            ).all()
        
        for substitution in substitutions:
            # На выходных Secondary не отображается, пропускаем такие замены
            if weekday in (5, 6) and substitution.duty_type == 'secondary':
                continue
            # Находим заменяющего
            substitute = employees_map.get(substitution.substitute_employee_id)
            if substitute:
                if substitution.duty_type == 'primary':
                    # Для выходных: замена Primary применяется к тому, кто будет показан как Primary
                    if weekday == 6:  # Воскресенье - Primary = week_secondary
                        week_secondary = substitute
                    else:  # Суббота и будние дни - Primary = week_primary
                        week_primary = substitute
                elif substitution.duty_type == 'secondary':
                    week_secondary = substitute
    
    # Суббота (5) - Primary = недельный Primary
    if weekday == 5:
        return week_primary, None
    
    # Воскресенье (6) - Primary = недельный Secondary (тот кто был Secondary всю неделю)
    if weekday == 6:
        return week_secondary, None
    
    # Остальные дни (понедельник-пятница) - оба дежурных
    return week_primary, week_secondary


def get_current_duty():
    """Определяет текущих Primary и Secondary дежурных"""
    now = datetime.now(TIMEZONE)
    return get_duty_for_date(now)


def get_substitution_map(start_date, end_date):
    """Готовит словарь замен по датам для быстрых вычислений"""
    substitutions = DutySubstitution.query.filter(
        DutySubstitution.date >= start_date,
        DutySubstitution.date <= end_date
    ).all()
    substitutions_map = {}
    for substitution in substitutions:
        substitutions_map.setdefault(substitution.date, {})[substitution.duty_type] = substitution
    return substitutions_map


def build_substitutions_list():
    """Формирует список замен с отметкой диапазона"""
    all_substitutions = DutySubstitution.query.order_by(
        DutySubstitution.date,
        DutySubstitution.duty_type,
        DutySubstitution.original_employee_id,
        DutySubstitution.substitute_employee_id
    ).all()
    substitutions = []
    substitutions_by_key = {}
    for s in all_substitutions:
        key = (
            s.duty_type,
            s.original_employee_id,
            s.substitute_employee_id,
            s.reason or ''
        )
        substitutions_by_key.setdefault(key, []).append(s)

    for s in all_substitutions:
        key = (
            s.duty_type,
            s.original_employee_id,
            s.substitute_employee_id,
            s.reason or ''
        )
        dates = [x.date for x in substitutions_by_key[key]]
        dates_set = set(dates)
        is_range = (s.date - timedelta(days=1)) in dates_set or (s.date + timedelta(days=1)) in dates_set
        s_dict = s.to_dict()
        s_dict['range_type'] = 'range' if is_range else 'single'
        substitutions.append(s_dict)
    return substitutions


def get_substitution_map(start_date, end_date):
    """Готовит словарь замен по датам для быстрых вычислений"""
    substitutions = DutySubstitution.query.filter(
        DutySubstitution.date >= start_date,
        DutySubstitution.date <= end_date
    ).all()
    substitutions_map = {}
    for substitution in substitutions:
        substitutions_map.setdefault(substitution.date, {})[substitution.duty_type] = substitution
    return substitutions_map


def get_calendar_month(year, month, substitutions_map=None, employees_map=None):
    """Генерирует календарь для месяца с данными о дежурных"""
    # Используем встроенный модуль calendar
    cal = cal_module.monthcalendar(year, month)
    
    calendar_data = []
    if employees_map is None:
        employees_map = get_employee_map()
    
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
                primary, secondary = get_duty_for_date(
                    date,
                    substitutions_map=substitutions_map,
                    employees_map=employees_map
                )
                date_only = date.date()
                day_subs = substitutions_map.get(date_only, {}) if substitutions_map else {}
                primary_sub = day_subs.get('primary')
                secondary_sub = day_subs.get('secondary')
                
                week_data.append({
                    'day': day,
                    'weekday': weekday,
                    'primary': primary,
                    'secondary': secondary,
                    'date': date,
                    'primary_sub': primary_sub,
                    'secondary_sub': secondary_sub
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
    
    # Определяем день недели (0 = понедельник, 5 = суббота, 6 = воскресенье)
    weekday = now.weekday()
    is_weekend = weekday >= 5  # Суббота или воскресенье
    
    return render_template('index.html',
                         primary=primary if primary else current_primary,
                         secondary=secondary,
                         current_time=now.strftime('%d.%m.%Y %H:%M MSK'),
                         next_primary=next_primary,
                         next_secondary=next_secondary,
                         next_week_num=next_week_num,
                         emergency_contact=EMERGENCY_CONTACT,
                         employees=get_employees(),
                         substitutions=next_week_substitutions,
                         weekday=weekday,
                         is_weekend=is_weekend)


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Страница входа для защищенных разделов"""
    if request.method == 'POST':
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        if username == AUTH_USER and password == AUTH_PASS:
            session['auth'] = True
            next_url = request.args.get('next') or url_for('index')
            return redirect(next_url)
        return render_template('login.html', error='Неверный логин или пароль')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('auth', None)
    return redirect(url_for('index'))


@app.route('/contacts')
@login_required
def contacts():
    """Страница редактирования контактов сотрудников"""
    return render_template('contacts.html', employees=get_employees())


@app.route('/overrides')
@login_required
def overrides():
    """Страница замен дежурных"""
    substitutions = build_substitutions_list()
    return render_template('overrides.html', employees=get_employees(), substitutions=substitutions)


@app.route('/calendar')
def calendar_view():
    """Страница с календарем ротации на полгода"""
    now = datetime.now(TIMEZONE)
    year = now.year
    month = now.month
    
    # Названия месяцев
    month_names = ['', 'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 
                   'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']
    
    employees_map = get_employee_map()

    # Генерируем данные для 6 месяцев вперед (текущий + 5 следующих)
    months_data = []
    current_year = year
    current_month = month
    
    for i in range(6):
        month_start = datetime(current_year, current_month, 1).date()
        last_day = cal_module.monthrange(current_year, current_month)[1]
        month_end = datetime(current_year, current_month, last_day).date()
        substitutions_map = get_substitution_map(month_start, month_end)
        calendar_data = get_calendar_month(
            current_year,
            current_month,
            substitutions_map=substitutions_map,
            employees_map=employees_map
        )
        for week in calendar_data:
            for day in week:
                if not day:
                    continue
                primary_sub = day.get('primary_sub')
                secondary_sub = day.get('secondary_sub')
                if primary_sub:
                    day['primary_sub'] = {
                        'from': employees_map.get(primary_sub.original_employee_id),
                        'to': employees_map.get(primary_sub.substitute_employee_id)
                    }
                if secondary_sub:
                    day['secondary_sub'] = {
                        'from': employees_map.get(secondary_sub.original_employee_id),
                        'to': employees_map.get(secondary_sub.substitute_employee_id)
                    }
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
                         now=now)


@app.route('/api/employees', methods=['GET'])
@login_required
def get_employees_api():
    """Получить список сотрудников"""
    return jsonify(get_employees())


@app.route('/api/employees/<string:employee_id>', methods=['PUT'])
@login_required
def update_employee(employee_id):
    """Обновить данные сотрудника"""
    data = request.json or {}
    employee_ids = {e['id'] for e in EMPLOYEE_DEFAULTS}
    if employee_id not in employee_ids:
        return jsonify({'error': 'Сотрудник не найден'}), 404

    profile = EmployeeProfile.query.get(employee_id)
    if not profile:
        profile = EmployeeProfile(id=employee_id)
        db.session.add(profile)

    profile.name = data.get('name', profile.name)
    profile.telegram = data.get('telegram', profile.telegram)
    profile.band = data.get('band', profile.band)

    db.session.commit()
    return jsonify(profile.to_dict())


@app.route('/api/substitutions', methods=['GET'])
@login_required
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
@login_required
def create_substitution():
    """Создать замену дежурного (может быть на одну дату или диапазон)"""
    data = request.json
    
    start_date = datetime.fromisoformat(data['start_date']).date()
    end_date = datetime.fromisoformat(data.get('end_date', data['start_date'])).date()
    duty_type = data['duty_type']
    substitute_employee_id = data['substitute_employee_id']
    reason = data.get('reason', '')

    employees_map = get_employee_map()
    if substitute_employee_id not in employees_map:
        return jsonify({'error': 'Неверный сотрудник для замены'}), 400
    
    created_substitutions = []
    skipped_dates = []
    current_date = start_date
    
    while current_date <= end_date:
        # Получаем оригинального дежурного для этой даты
        date_obj = datetime.combine(current_date, datetime.min.time()).replace(tzinfo=TIMEZONE)
        weekday = date_obj.weekday()
        if duty_type == 'secondary' and weekday in (5, 6):
            skipped_dates.append(current_date.isoformat())
            current_date += timedelta(days=1)
            continue
        
        # Для определения оригинального дежурного используем базовую ротацию без замен
        week_num = get_week_number(date_obj)
        week_primary, week_secondary = get_duty_for_week(week_num)
        
        # Определяем, кто будет показан как Primary/Secondary для этой даты
        if weekday == 5:  # Суббота - Primary = week_primary
            primary_for_day = week_primary
            secondary_for_day = None
        elif weekday == 6:  # Воскресенье - Primary = week_secondary
            primary_for_day = week_secondary
            secondary_for_day = None
        else:  # Будние дни
            primary_for_day = week_primary
            secondary_for_day = week_secondary
        
        # Определяем оригинального дежурного в зависимости от типа замены
        if duty_type == 'primary' and primary_for_day:
            original_employee_id = primary_for_day['id']
        elif duty_type == 'secondary' and secondary_for_day:
            original_employee_id = secondary_for_day['id']
        else:
            current_date += timedelta(days=1)
            continue
        
        # Проверяем, нет ли уже замены на эту дату
        # Если есть - обновляем её, если нет - создаем новую
        existing = DutySubstitution.query.filter_by(
            date=current_date,
            duty_type=duty_type
        ).first()
        
        if existing:
            # Обновляем существующую замену
            existing.substitute_employee_id = substitute_employee_id
            existing.original_employee_id = original_employee_id
            existing.reason = reason
            created_substitutions.append(existing)
        else:
            # Создаем новую замену
            substitution = DutySubstitution(
                date=current_date,
                duty_type=duty_type,
                original_employee_id=original_employee_id,
                substitute_employee_id=substitute_employee_id,
                reason=reason
            )
            db.session.add(substitution)
            created_substitutions.append(substitution)
        
        current_date += timedelta(days=1)
    
    db.session.commit()
    
    if not created_substitutions:
        return jsonify({
            'error': 'Нет подходящих дат для замены выбранного типа дежурства',
            'skipped_dates': skipped_dates
        }), 400
    
    return jsonify({
        'created': [s.to_dict() for s in created_substitutions],
        'skipped_dates': skipped_dates
    }), 201


@app.route('/api/substitutions/<int:sub_id>', methods=['DELETE'])
@login_required
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
