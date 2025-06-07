from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, send_from_directory
import os
from flask_sqlalchemy import SQLAlchemy
from datetime import date as dt_date, datetime, timedelta, timezone
import csv
import json
from bs4 import BeautifulSoup
import sqlite3
import secrets
import chardet
from flask_login import UserMixin, LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer
from sqlalchemy import text
from flask_migrate import Migrate
import re
from calendar import monthrange
import zipfile
from sqlalchemy import or_, desc
from io import StringIO
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from config import config
from flask_wtf.csrf import CSRFProtect


# Load environment variables from .env file
load_dotenv()



def create_app(config_name=None):
    app = Flask(__name__)
    
    # Load configuration
    config_name = config_name or os.environ.get('FLASK_ENV', 'development')
    app.config.from_object(config[config_name])
    config[config_name].init_app(app)
    
    return app

app = create_app()

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize extensions
db = SQLAlchemy(app)
# csrf = CSRFProtect(app)  # Temporarily disabled until templates are updated

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'

serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

migrate = Migrate(app, db)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

@app.before_request
def require_login():
    # Erlaube Login, Registrierung und statische Dateien ohne Login
    allowed_routes = ['login', 'register', 'static']
    if request.endpoint not in allowed_routes and not current_user.is_authenticated:
        return redirect(url_for('login'))

# Account model
class Account(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    trades = db.relationship('Trade', backref='account', lazy=True)

# Trade model
class Trade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, nullable=True, index=True)  # Zeit (Einstieg) - indexed for sorting
    position = db.Column(db.String(32), nullable=True)            # Position
    symbol = db.Column(db.String(10), nullable=True, index=True)  # Symbol - indexed for filtering
    direction = db.Column(db.String(10), nullable=True)  # Typ (buy, sell, balance)
    position_size = db.Column(db.Float, nullable=True)  # Volumen
    entry_price = db.Column(db.Float, nullable=True)    # Preis (Einstieg)
    sl = db.Column(db.Float, nullable=True)                            # S / L
    tp = db.Column(db.Float, nullable=True)                            # T / P
    exit_date = db.Column(db.DateTime, nullable=True, index=True)      # Zeit (Ausstieg) - indexed for filtering
    exit_price = db.Column(db.Float, nullable=True)                    # Preis (Ausstieg)
    kommission = db.Column(db.Float, nullable=True)                    # Kommission
    swap = db.Column(db.Float, nullable=True)                          # Swap
    pnl = db.Column(db.Float, nullable=True)           # Gewinn
    images = db.Column(db.JSON, nullable=True)                         # Bilder/Screenshots
    account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=True, index=True)  # indexed for joins
    account_type = db.Column(db.String(50), nullable=True, index=True)  # indexed for filtering
    market_phase = db.Column(db.String(10), nullable=True)  # Market Phase (A1, A2, ...)
    analysis = db.Column(db.Text, nullable=True)
    entry_comment = db.Column(db.Text, nullable=True)
    risk_management = db.Column(db.Text, nullable=True)
    psychological_factors = db.Column(db.Text, nullable=True)
    bias_basis = db.Column(db.Text, nullable=True)
    what_went_well_bad = db.Column(db.Text, nullable=True)
    entry_type = db.Column(db.JSON, nullable=True)
    mistakes = db.Column(db.JSON, nullable=True)
    trade_rating = db.Column(db.Float, nullable=True)

# Upload-Historie model
class Upload(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(120), nullable=False)
    upload_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    file_size = db.Column(db.Integer, nullable=True)  # File size in bytes
    status = db.Column(db.String(20), default='success')  # success, failed, error
    trades_imported = db.Column(db.Integer, default=0)  # Number of trades imported
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # Link to user

# User model
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password = db.Column(db.String(200), nullable=False)
    accounts = db.relationship('Account', backref='user', lazy=True)

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/dashboard')
def dashboard():
    accounts = Account.query.filter_by(user_id=current_user.id).all()
    account_type = request.args.get('account_type', 'all')
    date_range = request.args.get('date_range', '')
    
    # FIXED: Standardmäßig alle Trades seit dem ersten Trade anzeigen
    if date_range:
        # Wenn date_range gesetzt ist, verwende den Custom Range
        try:
            start_str, end_str = date_range.split(' - ')
            start = datetime.strptime(start_str, '%Y-%m-%d')
            end = datetime.strptime(end_str, '%Y-%m-%d') + timedelta(days=1, seconds=-1)
        except Exception as e:
            print('Fehler beim Parsen von date_range:', e)
            # Fallback: Alle Trades
            start = datetime(1900, 1, 1)  # Sehr frühes Datum
            end = datetime.now(timezone.utc) + timedelta(days=1)  # Bis morgen
    else:
        # Standardverhalten: Alle Trades seit dem ersten Trade
        start = datetime(1900, 1, 1)  # Sehr frühes Datum um alle Trades zu erfassen
        end = datetime.now(timezone.utc) + timedelta(days=1)  # Bis morgen

    # FIXED: Filtere nach exit_date ODER date (für Trades ohne exit_date)
    if account_type and account_type != 'all':
        trades = Trade.query.join(Account).filter(
            Account.user_id == current_user.id,
            Trade.account_type == account_type,
            ((Trade.exit_date >= start) & (Trade.exit_date <= end)) | 
            ((Trade.exit_date == None) & (Trade.date >= start) & (Trade.date <= end))
        ).order_by(Trade.exit_date.desc().nullslast(), Trade.date.desc()).all()
        selected_account_type = account_type
    else:
        trades = Trade.query.join(Account).filter(
            Account.user_id == current_user.id,
            ((Trade.exit_date >= start) & (Trade.exit_date <= end)) | 
            ((Trade.exit_date == None) & (Trade.date >= start) & (Trade.date <= end))
        ).order_by(Trade.exit_date.desc().nullslast(), Trade.date.desc()).all()
        selected_account_type = None

    def trade_total_pnl(t):
        return (t.pnl or 0) + (t.kommission or 0) + (t.swap or 0)

    net_pnl = sum(trade_total_pnl(t) for t in trades)
    trade_win_percent = round(100 * sum(1 for t in trades if trade_total_pnl(t) > 0) / len(trades), 2) if trades else 0
    try:
        pnl_values = [trade_total_pnl(t) for t in trades]
        profit_factor = round(
            sum(v for v in pnl_values if v > 0) / abs(sum(v for v in pnl_values if v < 0)), 2
        ) if any(v < 0 for v in pnl_values) else 0
    except Exception as e:
        print('Profit Factor Fehler:', e)
        profit_factor = 0
    profit_factor_percent = min(int(profit_factor * 50), 100) if profit_factor else 0
    day_win_percent = trade_win_percent
    avg_win = round(sum(trade_total_pnl(t) for t in trades if trade_total_pnl(t) > 0) / max(1, sum(1 for t in trades if trade_total_pnl(t) > 0)), 2) if trades else 0
    avg_loss = round(sum(trade_total_pnl(t) for t in trades if trade_total_pnl(t) < 0) / max(1, sum(1 for t in trades if trade_total_pnl(t) < 0)), 2) if trades else 0
    avg_win_loss_trade = round(avg_win / abs(avg_loss), 2) if avg_loss != 0 else 0
    recent_trades = trades[:10]
    calendar_month = "June 2024"  # Placeholder
    trade_win_percent_width = f"width: 120px; height: 60px; border-radius: 120px 120px 0 0 / 60px 60px 0 0; background: conic-gradient(#27ae60 0% {trade_win_percent}%, #f4f4f4 {trade_win_percent}% 100%); margin: 0 auto;" if trade_win_percent else "width: 120px; height: 60px; border-radius: 120px 120px 0 0 / 60px 60px 0 0; background: #f4f4f4; margin: 0 auto;"
    profit_factor_gradient = (
        f"margin-top:0.5rem; width:40px; height:40px; border-radius:50%; margin-left:auto; margin-right:auto; background:conic-gradient(#27ae60 0% {profit_factor_percent}%, #f4f4f4 {profit_factor_percent}% 100%);"
        if profit_factor_percent else "margin-top:0.5rem; width:40px; height:40px; border-radius:50%; margin-left:auto; margin-right:auto; background:#f4f4f4;"
    )
    day_win_percent_width = f"width: 120px; height: 60px; border-radius: 120px 120px 0 0 / 60px 60px 0 0; background: conic-gradient(#27ae60 0% {day_win_percent}%, #f4f4f4 {day_win_percent}% 100%); margin: 0 auto;" if day_win_percent else "width: 120px; height: 60px; border-radius: 120px 120px 0 0 / 60px 60px 0 0; background: #f4f4f4; margin: 0 auto;"
    trade_win_wins = sum(1 for t in trades if trade_total_pnl(t) > 0)
    trade_win_draws = sum(1 for t in trades if trade_total_pnl(t) == 0)
    trade_win_losses = sum(1 for t in trades if trade_total_pnl(t) < 0)

    # Entry Type Stacked Chart Data - count wins and losses separately
    entry_type_stats = {}
    for t in trades:
        # Calculate total_pnl for each trade first
        t.total_pnl = (t.pnl or 0) + (t.kommission or 0) + (t.swap or 0)
        
        # Parse entry_type JSON field
        entry_types = []
        if hasattr(t, 'entry_type') and t.entry_type:
            try:
                if isinstance(t.entry_type, str):
                    entry_types = json.loads(t.entry_type)
                elif isinstance(t.entry_type, list):
                    entry_types = t.entry_type
            except (json.JSONDecodeError, TypeError):
                entry_types = []
        
        # Debug: Zeige alle entry_type Werte aus der DB
        print(f"DEBUG DASHBOARD: Trade {t.id} symbol={t.symbol}, entry_type raw='{t.entry_type}', parsed={entry_types}, total_pnl={t.total_pnl}")
        
        # Only skip for entry type chart analysis, not for other stats
        if entry_types:
            print(f"DEBUG DASHBOARD: Trade {t.symbol} has entry_types: {entry_types}, total_pnl: {t.total_pnl}")
            
            # Count wins and losses for each entry type
            for entry_type in entry_types:
                if entry_type not in entry_type_stats:
                    entry_type_stats[entry_type] = {"wins": 0, "losses": 0, "total": 0}
                
                entry_type_stats[entry_type]["total"] += 1
                if t.total_pnl > 0:
                    entry_type_stats[entry_type]["wins"] += 1
                elif t.total_pnl < 0:
                    entry_type_stats[entry_type]["losses"] += 1
        else:
            print(f"DEBUG DASHBOARD: Trade {t.symbol} has no entry_type, will be included in other stats but not entry-type chart")

    print(f"DEBUG DASHBOARD: entry_type_stats = {entry_type_stats}")

    # Prepare chart data - show wins and losses separately for stacked bars
    all_entry_types = ["Fibonacci", "MSS + S", "MSS + D", "FOMO"]
    chart_labels = []
    chart_wins = []
    chart_losses = []
    chart_totals = []
    
    for entry_type in all_entry_types:
        # Always include entry type, even if no trades
        chart_labels.append(entry_type)
        if entry_type in entry_type_stats:
            stats = entry_type_stats[entry_type]
            wins = stats["wins"]
            losses = stats["losses"]
            total = stats["total"]
        else:
            wins = 0
            losses = 0
            total = 0
        
        print(f"DEBUG: {entry_type} -> wins: {wins}, losses: {losses}, total: {total}")
        chart_wins.append(wins)
        chart_losses.append(losses)
        chart_totals.append(total)

    print(f"DEBUG: Final chart data -> labels: {chart_labels}, wins: {chart_wins}, losses: {chart_losses}, totals: {chart_totals}")

    # Hourly Wins/Losses Chart Data
    hourly_stats = {}
    for hour in range(24):
        hourly_stats[hour] = {"wins": 0, "losses": 0, "total": 0}
    
    for t in trades:
        # Use exit_date if available, otherwise use date (same logic as other charts)
        trade_date = t.exit_date if t.exit_date else t.date
        if trade_date:
            hour = trade_date.hour
            total_pnl = trade_total_pnl(t)
            
            hourly_stats[hour]["total"] += 1
            if total_pnl > 0:
                hourly_stats[hour]["wins"] += 1
            elif total_pnl < 0:
                hourly_stats[hour]["losses"] += 1
    
    # Prepare hourly chart data
    hourly_labels = [f"{hour:02d}:00" for hour in range(24)]
    hourly_wins = [hourly_stats[hour]["wins"] for hour in range(24)]
    hourly_losses = [hourly_stats[hour]["losses"] for hour in range(24)]
    hourly_totals = [hourly_stats[hour]["total"] for hour in range(24)]

    print(f"DEBUG: Hourly chart data -> wins: {hourly_wins}, losses: {hourly_losses}, totals: {hourly_totals}")
    
    # Debug: Show detailed trade hour distribution
    print("=== DEBUG: HOURLY TRADE DISTRIBUTION ===")
    for t in trades:
        trade_date = t.exit_date if t.exit_date else t.date
        if trade_date:
            hour = trade_date.hour
            total_pnl = trade_total_pnl(t)
            result = 'WIN' if total_pnl > 0 else 'LOSS' if total_pnl < 0 else 'BE'
            print(f"Trade {t.id}: {t.symbol} at {trade_date.strftime('%H:%M')} (hour {hour}) -> {result} ({total_pnl})")
        else:
            print(f"Trade {t.id}: {t.symbol} -> NO TIME DATA")
    
    # Show summary per hour
    print("\n=== HOURLY SUMMARY ===")
    for hour in range(24):
        stats = hourly_stats[hour]
        if stats["total"] > 0:
            print(f"Hour {hour:02d}:00 -> {stats['wins']} wins, {stats['losses']} losses, {stats['total']} total")
    print("=== END HOURLY DEBUG ===\n")

    # Weekday Wins/Losses Chart Data
    weekday_stats = {}
    weekdays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    for weekday in weekdays:
        weekday_stats[weekday] = {"wins": 0, "losses": 0, "total": 0}
    
    for t in trades:
        # Use exit_date if available, otherwise use date (same logic as other charts)
        trade_date = t.exit_date if t.exit_date else t.date
        if trade_date:
            # Convert Python weekday (0=Monday) to weekday name
            python_weekday = trade_date.weekday()  # 0=Monday, 6=Sunday
            weekday_name = weekdays[python_weekday]
            total_pnl = trade_total_pnl(t)
            
            weekday_stats[weekday_name]["total"] += 1
            if total_pnl > 0:
                weekday_stats[weekday_name]["wins"] += 1
            elif total_pnl < 0:
                weekday_stats[weekday_name]["losses"] += 1
    
    # Prepare weekday chart data
    weekday_labels = weekdays  # Monday through Sunday
    weekday_wins = [weekday_stats[day]["wins"] for day in weekdays]
    weekday_losses = [weekday_stats[day]["losses"] for day in weekdays]
    weekday_totals = [weekday_stats[day]["total"] for day in weekdays]

    print(f"DEBUG: Weekday chart data -> wins: {weekday_wins}, losses: {weekday_losses}, totals: {weekday_totals}")

    # Debug: Show actual trade distribution per weekday for verification
    print("=== DEBUG: TRADE DATA FOR WEEKDAY CHART ===")
    weekday_debug = {'Monday': [], 'Tuesday': [], 'Wednesday': [], 'Thursday': [], 'Friday': [], 'Saturday': [], 'Sunday': []}
    
    for t in trades:
        # Use exit_date if available, otherwise use date (same logic as chart calculation)
        trade_date = t.exit_date if t.exit_date else t.date
        if trade_date:
            # Use the SAME weekday calculation as the chart above
            python_weekday = trade_date.weekday()  # 0=Monday, 6=Sunday
            weekday_name = weekdays[python_weekday]  # Use the same weekdays array
            total_pnl = trade_total_pnl(t)
            weekday_debug[weekday_name].append({
                'id': t.id,
                'symbol': t.symbol,
                'date': trade_date.strftime('%Y-%m-%d %H:%M:%S'),
                'exit_date': t.exit_date.strftime('%Y-%m-%d %H:%M:%S') if t.exit_date else 'None',
                'entry_date': t.date.strftime('%Y-%m-%d %H:%M:%S') if t.date else 'None',
                'pnl': total_pnl,
                'result': 'WIN' if total_pnl > 0 else 'LOSS' if total_pnl < 0 else 'BE'
            })
    
    for day, trades_list in weekday_debug.items():
        wins = len([t for t in trades_list if t['result'] == 'WIN'])
        losses = len([t for t in trades_list if t['result'] == 'LOSS'])
        print(f"{day}: {wins} wins, {losses} losses - {trades_list}")
    print("=== END DEBUG ===")

    return render_template(
        'dashboard.html',
        net_pnl=net_pnl,
        trade_win_percent=trade_win_percent,
        profit_factor=profit_factor,
        profit_factor_percent=profit_factor_percent,
        day_win_percent=day_win_percent,
        avg_win=avg_win,
        avg_loss=avg_loss,
        avg_win_loss_trade=avg_win_loss_trade,
        recent_trades=recent_trades,
        trades=trades,
        calendar_month=calendar_month,
        accounts=accounts,
        selected_account_type=selected_account_type,
        selected_date_range=date_range,  # Füge den date_range Parameter hinzu
        trade_win_percent_width=trade_win_percent_width,
        profit_factor_gradient=profit_factor_gradient,
        day_win_percent_width=day_win_percent_width,
        trade_win_wins=trade_win_wins,
        trade_win_draws=trade_win_draws,
        trade_win_losses=trade_win_losses,
        chart_labels=chart_labels,
        chart_wins=chart_wins,
        chart_losses=chart_losses,
        chart_totals=chart_totals,
        hourly_labels=hourly_labels,
        hourly_wins=hourly_wins,
        hourly_losses=hourly_losses,
        hourly_totals=hourly_totals,
        weekday_labels=weekday_labels,
        weekday_wins=weekday_wins,
        weekday_losses=weekday_losses,
        weekday_totals=weekday_totals,
        current_username=current_user.username
    )

@app.route('/journal-hub', methods=['GET', 'POST'])
@login_required
def journal_hub():
    try:
        # DEBUG: Zeige alle Request-Parameter
        print("=== JOURNAL HUB DEBUG ===")
        print(f"Request method: {request.method}")
        print(f"Request args: {dict(request.args)}")
        print(f"Request form: {dict(request.form)}")
        print("========================")
        
        filter_fields = [
            ('date', 'Einstiegszeit'),
            ('symbol', 'Symbol'),
            ('direction', 'Typ'),
            ('position_size', 'Volumen'),
            ('exit_date', 'Ausstiegszeit'),
            ('kommission', 'Kommission'),
            ('swap', 'Swap'),
            ('pnl', 'Gewinn'),
            ('market_phase', 'Market Phase'),
            ('mistakes', 'Mistake'),
            ('sl', 'SL'),
            ('entry_type', 'Entry Type'),
            ('trade_rating', 'Trade Rating'),
            ('account_type', 'Account Type'),
        ]
        filters = {}
        for field, _ in filter_fields:
            value = request.args.get(field)
            if value and value.strip():  # Validate non-empty values
                filters[field] = value.strip()
                print(f"DEBUG: Filter {field} = '{value.strip()}'")  # Debug output
        
        # Get trades per page limit with validation
        trades_per_page = request.args.get('trades_per_page', '25')
        try:
            trades_limit = max(1, min(1000, int(trades_per_page)))  # Limit between 1-1000
        except (ValueError, TypeError):
            trades_limit = 25
        
        # Datumsfilter (date)
        date_op = request.args.get('date_op')
        date_val = request.args.get('date')
        date_val2 = request.args.get('date2')
        # Datumsfilter (exit_date)
        exit_date_op = request.args.get('exit_date_op')
        exit_date_val = request.args.get('exit_date')
        exit_date_val2 = request.args.get('exit_date2')
        
        # Start with base query filtered by current user's accounts
        accounts = Account.query.filter_by(user_id=current_user.id).all()
        account_ids = [acc.id for acc in accounts]
        
        if not account_ids:
            # User has no accounts, return empty list
            return render_template('journal_hub.html', trades=[], filter_fields=filter_fields, filters=filters, trades_per_page=trades_per_page)
        
        query = Trade.query.filter(Trade.account_id.in_(account_ids))
        
        # Anwenden des Datumsfilters auf das Feld 'date'
        if date_op:
            if date_op == 'is' and date_val:
                query = query.filter(Trade.date.cast(db.Date) == date_val)
            elif date_op == 'is_before' and date_val:
                query = query.filter(Trade.date < date_val)
            elif date_op == 'is_after' and date_val:
                query = query.filter(Trade.date > date_val)
            elif date_op == 'is_on_or_before' and date_val:
                query = query.filter(Trade.date <= date_val)
            elif date_op == 'is_on_or_after' and date_val:
                query = query.filter(Trade.date >= date_val)
            elif date_op == 'is_between' and date_val and date_val2:
                query = query.filter(Trade.date >= date_val, Trade.date <= date_val2)
            elif date_op == 'is_empty':
                query = query.filter(Trade.date == None)
            elif date_op == 'is_not_empty':
                query = query.filter(Trade.date != None)
        
        # Anwenden des Datumsfilters auf das Feld 'exit_date'
        if exit_date_op:
            if exit_date_op == 'is' and exit_date_val:
                query = query.filter(Trade.exit_date.cast(db.Date) == exit_date_val)
            elif exit_date_op == 'is_before' and exit_date_val:
                query = query.filter(Trade.exit_date < exit_date_val)
            elif exit_date_op == 'is_after' and exit_date_val:
                query = query.filter(Trade.exit_date > exit_date_val)
            elif exit_date_op == 'is_on_or_before' and exit_date_val:
                query = query.filter(Trade.exit_date <= exit_date_val)
            elif exit_date_op == 'is_on_or_after' and exit_date_val:
                query = query.filter(Trade.exit_date >= exit_date_val)
            elif exit_date_op == 'is_between' and exit_date_val and exit_date_val2:
                query = query.filter(Trade.exit_date >= exit_date_val, Trade.exit_date <= exit_date_val2)
            elif exit_date_op == 'is_empty':
                query = query.filter(Trade.exit_date == None)
            elif exit_date_op == 'is_not_empty':
                query = query.filter(Trade.exit_date != None)
        
        # Gewinn (pnl) Filter mit Operatoren
        pnl_op = request.args.get('pnl_op')
        pnl_val = request.args.get('pnl')
        pnl_val2 = request.args.get('pnl2')
        
        if pnl_op and pnl_val:
            try:
                pnl_value = float(pnl_val)
                print(f"DEBUG PNL FILTER: op={pnl_op}, val={pnl_value}, val2={pnl_val2}")
                # Filtere NULL-Werte aus und behandle sie als 0
                if pnl_op == 'eq':
                    query = query.filter(Trade.pnl.isnot(None), Trade.pnl == pnl_value)
                elif pnl_op == 'gt':
                    query = query.filter(Trade.pnl.isnot(None), Trade.pnl > pnl_value)
                elif pnl_op == 'lt':
                    query = query.filter(Trade.pnl.isnot(None), Trade.pnl < pnl_value)
                elif pnl_op == 'gte':
                    query = query.filter(Trade.pnl.isnot(None), Trade.pnl >= pnl_value)
                elif pnl_op == 'lte':
                    query = query.filter(Trade.pnl.isnot(None), Trade.pnl <= pnl_value)
                elif pnl_op == 'between' and pnl_val2:
                    try:
                        pnl_value2 = float(pnl_val2)
                        query = query.filter(Trade.pnl.isnot(None), Trade.pnl >= pnl_value, Trade.pnl <= pnl_value2)
                    except ValueError:
                        pass  # Ignore invalid second value
            except ValueError:
                print(f"DEBUG PNL FILTER: Invalid pnl value: {pnl_val}")
                pass  # Ignore invalid pnl value
        
        # Restliche Filter
        for field, _ in filter_fields:
            if field in filters and field not in ['date', 'exit_date', 'pnl']:
                if field in ['position_size', 'kommission', 'swap', 'sl', 'trade_rating']:
                    # Numerische Felder - unterstütze Bereiche mit ':'
                    if ':' in filters[field]:
                        start, end = filters[field].split(':', 1)
                        if start:
                            query = query.filter(getattr(Trade, field) >= float(start))
                        if end:
                            query = query.filter(getattr(Trade, field) <= float(end))
                    else:
                        query = query.filter(getattr(Trade, field) == float(filters[field]))
                elif field == 'market_phase':
                    # Market Phase - exakte Übereinstimmung
                    query = query.filter(Trade.market_phase == filters[field])
                elif field == 'account_type':
                    # Account Type - exakte Übereinstimmung
                    query = query.filter(Trade.account_type == filters[field])
                elif field == 'mistakes':
                    # Mistakes - JSON Array durchsuchen - Raw SQL für Kompatibilität
                    query = query.filter(text("mistakes::jsonb ? :value")).params(value=filters[field])
                elif field == 'entry_type':
                    # Entry Type - JSON Array durchsuchen - Raw SQL für Kompatibilität
                    query = query.filter(text("entry_type::jsonb ? :value")).params(value=filters[field])
                else:
                    # Standard String-Filter mit LIKE
                    query = query.filter(getattr(Trade, field).like(f"%{filters[field]}%"))
        
        # Sort by newest entry date first (descending), then limit
        trades = query.order_by(Trade.date.desc().nullslast()).limit(trades_limit).all()
        
        return render_template('journal_hub.html', trades=trades, filter_fields=filter_fields, filters=filters, trades_per_page=trades_per_page)
        
    except Exception as e:
        print(f"Error handling journal_hub: {e}")
        flash('Ein Fehler ist aufgetreten beim Laden der Trades.', 'error')
        return render_template('journal_hub.html', trades=[], filter_fields=[], filters={}, trades_per_page='25')

@app.route('/daily-journal')
def daily_journal():
    accounts = Account.query.filter_by(user_id=current_user.id).all()
    account_ids = [acc.id for acc in accounts]

    selected_date = request.args.get('date')
    if selected_date:
        try:
            selected_date_dt = datetime.strptime(selected_date, '%Y-%m-%d')
        except ValueError:
            selected_date_dt = datetime.utcnow().date()
            selected_date = selected_date_dt.strftime('%Y-%m-%d')
    else:
        selected_date_dt = datetime.utcnow().date()
        selected_date = selected_date_dt.strftime('%Y-%m-%d')
    start = datetime(selected_date_dt.year, selected_date_dt.month, selected_date_dt.day)
    end = start + timedelta(days=1)
    date_label = start.strftime('%b %d, %Y')

    # Simplified: show all trades for the user (no account filtering)
    trades = Trade.query.filter(
        Trade.account_id.in_(account_ids),
        ((Trade.exit_date >= start) & (Trade.exit_date < end)) | ((Trade.exit_date == None) & (Trade.date >= start) & (Trade.date < end))
    ).order_by(Trade.exit_date.desc().nullslast(), Trade.date.desc()).all()

    print(f"DEBUG DAILY: Zeitraum: {start} bis {end}")
    print(f"DEBUG DAILY: Account IDs: {account_ids}")
    print(f"DEBUG DAILY: Gefundene Trades: {len(trades)}")
    for t in trades:
        print(f"DEBUG DAILY: Trade {t.id}: symbol={t.symbol}, date={t.date}, exit_date={t.exit_date}, account_id={t.account_id}, entry_type='{t.entry_type}'")

    for t in trades:
        t.total_pnl = (t.pnl or 0) + (t.kommission or 0) + (t.swap or 0)

    total_trades = len(trades)
    winners = sum(1 for t in trades if t.total_pnl > 0)
    losers = sum(1 for t in trades if t.total_pnl < 0)
    winrate = (winners / total_trades * 100) if total_trades else 0
    gross_pnl = sum((t.pnl or 0) for t in trades)  # Nur reine P&L ohne Kommissionen/Swap
    commissions = sum((t.kommission or 0) + (t.swap or 0) for t in trades)  # Separate Kommissionen/Swap
    daily_pnl = gross_pnl + commissions  # Gesamte tägliche P&L (gross_pnl + commissions)
    volume = sum((t.position_size if t.position_size is not None else 0) for t in trades)
    profit_factor = (sum(t.total_pnl for t in trades if t.total_pnl > 0) / abs(sum(t.total_pnl for t in trades if t.total_pnl < 0))) if any(t.total_pnl < 0 for t in trades) else 0
    
    # Entry Type Stacked Chart Data - count wins and losses separately
    entry_type_stats = {}
    for t in trades:
        # Calculate total_pnl for each trade first
        t.total_pnl = (t.pnl or 0) + (t.kommission or 0) + (t.swap or 0)
        
        # Parse entry_type JSON field
        entry_types = []
        if hasattr(t, 'entry_type') and t.entry_type:
            try:
                if isinstance(t.entry_type, str):
                    entry_types = json.loads(t.entry_type)
                elif isinstance(t.entry_type, list):
                    entry_types = t.entry_type
            except (json.JSONDecodeError, TypeError):
                entry_types = []
        
        # Only skip for entry type chart analysis, not for other stats
        if entry_types:
            print(f"DEBUG DAILY: Trade {t.symbol} has entry_types: {entry_types}, total_pnl: {t.total_pnl}")
            
            # Count wins and losses for each entry type
            for entry_type in entry_types:
                if entry_type not in entry_type_stats:
                    entry_type_stats[entry_type] = {"wins": 0, "losses": 0, "total": 0}
                
                entry_type_stats[entry_type]["total"] += 1
                if t.total_pnl > 0:
                    entry_type_stats[entry_type]["wins"] += 1
                elif t.total_pnl < 0:
                    entry_type_stats[entry_type]["losses"] += 1
        else:
            print(f"DEBUG DAILY: Trade {t.symbol} has no entry_type, will be included in other stats but not entry-type chart")

    print(f"DEBUG DAILY: entry_type_stats = {entry_type_stats}")
    
    # Prepare chart data - show wins and losses separately for stacked bars
    all_entry_types = ["Fibonacci", "MSS + S", "MSS + D", "FOMO"]
    chart_labels = []
    chart_wins = []
    chart_losses = []
    chart_totals = []
    
    for entry_type in all_entry_types:
        # Always include entry type, even if no trades
        chart_labels.append(entry_type)
        if entry_type in entry_type_stats:
            stats = entry_type_stats[entry_type]
            wins = stats["wins"]
            losses = stats["losses"]
            total = stats["total"]
        else:
            wins = 0
            losses = 0
            total = 0
        
        print(f"DEBUG DAILY: {entry_type} -> wins: {wins}, losses: {losses}, total: {total}")
        chart_wins.append(wins)
        chart_losses.append(losses)
        chart_totals.append(total)

    print(f"DEBUG DAILY: Final chart data -> labels: {chart_labels}, wins: {chart_wins}, losses: {chart_losses}, totals: {chart_totals}")

    # Hourly Wins/Losses Chart Data for Daily Journal
    hourly_stats = {}
    for hour in range(24):
        hourly_stats[hour] = {"wins": 0, "losses": 0, "total": 0}
    
    for t in trades:
        # Use exit_date if available, otherwise use date (same logic as other charts)
        trade_date = t.exit_date if t.exit_date else t.date
        if trade_date:
            hour = trade_date.hour
            total_pnl = (t.pnl or 0) + (t.kommission or 0) + (t.swap or 0)
            
            hourly_stats[hour]["total"] += 1
            if total_pnl > 0:
                hourly_stats[hour]["wins"] += 1
            elif total_pnl < 0:
                hourly_stats[hour]["losses"] += 1
    
    # Prepare hourly chart data
    hourly_labels = [f"{hour:02d}:00" for hour in range(24)]
    hourly_wins = [hourly_stats[hour]["wins"] for hour in range(24)]
    hourly_losses = [hourly_stats[hour]["losses"] for hour in range(24)]
    hourly_totals = [hourly_stats[hour]["total"] for hour in range(24)]

    print(f"DEBUG DAILY: Hourly chart data -> wins: {hourly_wins}, losses: {hourly_losses}, totals: {hourly_totals}")
    
    # Debug: Show detailed trade hour distribution
    print("=== DEBUG: HOURLY TRADE DISTRIBUTION ===")
    for t in trades:
        trade_date = t.exit_date if t.exit_date else t.date
        if trade_date:
            hour = trade_date.hour
            total_pnl = (t.pnl or 0) + (t.kommission or 0) + (t.swap or 0)
            result = 'WIN' if total_pnl > 0 else 'LOSS' if total_pnl < 0 else 'BE'
            print(f"Trade {t.id}: {t.symbol} at {trade_date.strftime('%H:%M')} (hour {hour}) -> {result} ({total_pnl})")
        else:
            print(f"Trade {t.id}: {t.symbol} -> NO TIME DATA")
    
    # Show summary per hour
    print("\n=== HOURLY SUMMARY ===")
    for hour in range(24):
        stats = hourly_stats[hour]
        if stats["total"] > 0:
            print(f"Hour {hour:02d}:00 -> {stats['wins']} wins, {stats['losses']} losses, {stats['total']} total")
    print("=== END HOURLY DEBUG ===\n")

    # Weekday Wins/Losses Chart Data for Daily Journal
    weekday_stats = {}
    weekdays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    for weekday in weekdays:
        weekday_stats[weekday] = {"wins": 0, "losses": 0, "total": 0}
    
    for t in trades:
        # Use exit_date if available, otherwise use date (same logic as other charts)
        trade_date = t.exit_date if t.exit_date else t.date
        if trade_date:
            # Convert Python weekday (0=Monday) to weekday name
            python_weekday = trade_date.weekday()  # 0=Monday, 6=Sunday
            weekday_name = weekdays[python_weekday]
            total_pnl = (t.pnl or 0) + (t.kommission or 0) + (t.swap or 0)
            
            weekday_stats[weekday_name]["total"] += 1
            if total_pnl > 0:
                weekday_stats[weekday_name]["wins"] += 1
            elif total_pnl < 0:
                weekday_stats[weekday_name]["losses"] += 1
    
    # Prepare weekday chart data
    weekday_labels = weekdays  # Monday through Sunday
    weekday_wins = [weekday_stats[day]["wins"] for day in weekdays]
    weekday_losses = [weekday_stats[day]["losses"] for day in weekdays]
    weekday_totals = [weekday_stats[day]["total"] for day in weekdays]

    print(f"DEBUG DAILY: Weekday chart data -> wins: {weekday_wins}, losses: {weekday_losses}, totals: {weekday_totals}")

    return render_template(
        'daily_journal.html',
        trades=trades,
        total_trades=total_trades,
        winners=winners,
        losers=losers,
        winrate=winrate,
        gross_pnl=gross_pnl,
        commissions=commissions,
        daily_pnl=daily_pnl,
        volume=volume,
        profit_factor=profit_factor,
        date_label=date_label,
        chart_labels=chart_labels,
        chart_wins=chart_wins,
        chart_losses=chart_losses,
        chart_totals=chart_totals,
        hourly_labels=hourly_labels,
        hourly_wins=hourly_wins,
        hourly_losses=hourly_losses,
        hourly_totals=hourly_totals,
        weekday_labels=weekday_labels,
        weekday_wins=weekday_wins,
        weekday_losses=weekday_losses,
        weekday_totals=weekday_totals,
        selected_date=selected_date
    )

def allowed_file(filename):
    """Check if uploaded file is allowed"""
    ALLOWED_EXTENSIONS = {'.html', '.htm'}
    return ('.' in filename and 
            os.path.splitext(filename)[1].lower() in ALLOWED_EXTENSIONS)

def validate_file_size(file):
    """Check file size without loading entire file into memory"""
    if hasattr(file, 'content_length') and file.content_length:
        return file.content_length <= app.config['MAX_CONTENT_LENGTH']
    return True

@app.route('/add-trade', methods=['GET', 'POST'])
@login_required
def add_trade():
    if not current_user.is_authenticated:
        return redirect(url_for('login'))
    
    # GET request: Show upload form
    if request.method == 'GET':
        return render_template('add_trade.html')
    
    # POST request: Process file upload
    file = request.files.get('file')
    if not file or file.filename == '':
        flash('No file selected!', 'error')
        return redirect(request.url)
    
    # Validate file type
    if not allowed_file(file.filename):
        flash('Only HTML files (.html, .htm) are allowed!', 'error')
        return redirect(request.url)
    
    # Validate file size
    if not validate_file_size(file):
        flash('File too large! Maximum size is 16MB.', 'error')
        return redirect(request.url)
    
    filename = secure_filename(file.filename)
    if not filename:
        flash('Invalid filename!', 'error')
        return redirect(request.url)
    
    # Save file
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    unique_filename = f"{timestamp}_{filename}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
    
    print(f"Speichere Datei: {filename} als {filepath}")
    
    # Ensure upload directory exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    try:
        file.save(filepath)
        file_size = os.path.getsize(filepath)
        
        print(f"Datei gespeichert, Größe: {file_size} bytes")
        
        # Process the HTML file and import trades
        trades_imported = process_html_file(filepath, current_user.id)
        
        flash(f'Successfully uploaded! Imported {trades_imported} trades.', 'success')
        
    except Exception as e:
        print(f"Upload error: {e}")
        flash(f'Upload failed: {str(e)}', 'error')
        return redirect(request.url)
    
    return redirect(url_for('dashboard'))

def process_html_file(filepath, user_id):
    """Process HTML file and import trades. Returns number of trades imported."""
    import re
    from bs4 import BeautifulSoup
    import chardet
    
    try:
        # Detect encoding first
        with open(filepath, 'rb') as f:
            raw_data = f.read()
            encoding = chardet.detect(raw_data)
            detected_encoding = encoding['encoding'] if encoding['encoding'] else 'utf-8'
        
        # Read the HTML file with correct encoding
        with open(filepath, 'r', encoding=detected_encoding) as f:
            content = f.read()
        
        print(f"Processing HTML file: {filepath} (encoding: {detected_encoding})")
        
        # Parse HTML with BeautifulSoup
        soup = BeautifulSoup(content, 'html.parser')
        
        # Find all tables
        trades_imported = 0
        
        for table in soup.find_all('table'):
            rows = table.find_all('tr')
            
            # Look for rows that contain trade data
            for row in rows:
                cells = row.find_all('td')
                if len(cells) >= 10:
                    cell_texts = [cell.get_text().strip() for cell in cells]
                    
                    # Check if this looks like a trade row
                    # First cell should be a date in format YYYY.MM.DD HH:MM:SS
                    if len(cell_texts) > 2 and re.match(r'\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}:\d{2}', cell_texts[0]):
                        try:
                            entry_time = cell_texts[0]
                            position_id = cell_texts[1]
                            symbol = cell_texts[2]
                            trade_type = cell_texts[3]
                            
                            # Try to extract volume from the typical position after trade_type
                            volume = None
                            if len(cell_texts) > 4:
                                try:
                                    # Volume is typically in the 4th or 5th column
                                    volume_candidate = cell_texts[4]
                                    # Check if it's a number (volume)
                                    volume = float(volume_candidate)
                                except (ValueError, IndexError):
                                    # If 5th column doesn't work, try other positions
                                    for vol_idx in [5, 6]:
                                        if vol_idx < len(cell_texts):
                                            try:
                                                volume = float(cell_texts[vol_idx])
                                                break
                                            except ValueError:
                                                continue
                            
                            # Find exit time and profit
                            exit_time = None
                            profit = None
                            commission = None
                            swap = None
                            
                            for i, cell in enumerate(cell_texts):
                                if i > 4 and re.match(r'\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}:\d{2}', cell):
                                    exit_time = cell
                                    # After finding exit time, look for the financial data
                                    # Typically: Commission (3rd last), Swap (2nd last), Profit (last)
                                    if len(cell_texts) >= 3:
                                        profit = cell_texts[-1]  # Last column - Profit
                                        commission = cell_texts[-3]  # 3rd last column - Commission
                                        swap = cell_texts[-2]  # 2nd last column - Swap
                                    break
                            
                            if exit_time and profit and symbol:
                                print(f"Processing trade: {symbol} | {entry_time} -> {exit_time} | P&L: {profit} | Volume: {volume}")
                                
                                # Parse datetime
                                entry_date = datetime.strptime(entry_time, '%Y.%m.%d %H:%M:%S')
                                exit_date = datetime.strptime(exit_time, '%Y.%m.%d %H:%M:%S')
                                
                                # Parse financial values
                                try:
                                    profit_float = float(profit)
                                except ValueError:
                                    print(f"Could not parse profit: {profit}")
                                    continue
                                
                                # Parse commission
                                commission_float = None
                                if commission and commission != '':
                                    try:
                                        commission_float = float(commission)
                                        if commission_float == 0:
                                            commission_float = None
                                    except ValueError:
                                        print(f"Could not parse commission: {commission}")
                                
                                # Parse swap
                                swap_float = None
                                if swap and swap != '':
                                    try:
                                        swap_float = float(swap)
                                        if swap_float == 0:
                                            swap_float = None
                                    except ValueError:
                                        print(f"Could not parse swap: {swap}")
                                
                                # Debug output
                                if commission_float is not None or swap_float is not None:
                                    print(f"  Commission: {commission_float}, Swap: {swap_float}")
                                
                                # Get user's account
                                account = Account.query.filter_by(user_id=user_id).first()
                                if not account:
                                    print(f"No account found for user {user_id}")
                                    continue
                                
                                # Check if trade already exists (avoid duplicates)
                                existing_trade = Trade.query.filter_by(
                                    symbol=symbol,
                                    date=entry_date,
                                    exit_date=exit_date,
                                    account_id=account.id
                                ).first()
                                
                                if not existing_trade:
                                    # Create new trade
                                    new_trade = Trade(
                                        symbol=symbol,
                                        date=entry_date,
                                        exit_date=exit_date,
                                        pnl=profit_float,
                                        kommission=commission_float,
                                        swap=swap_float,
                                        direction=trade_type,
                                        position_size=volume,  # Add volume to the trade
                                        account_id=account.id
                                    )
                                    
                                    db.session.add(new_trade)
                                    trades_imported += 1
                                    print(f"Added trade: {symbol} {profit_float} (Commission: {commission_float}, Swap: {swap_float}, Volume: {volume})")
                                else:
                                    print(f"Trade already exists: {symbol} {entry_time}")
                                
                        except Exception as e:
                            print(f"Error processing trade row: {e}")
                            continue
        
        # Commit all trades
        if trades_imported > 0:
            db.session.commit()
            print(f"Successfully imported {trades_imported} trades")
        else:
            print("No trades found in HTML file")
        
        return trades_imported
        
    except Exception as e:
        print(f"Error processing HTML file: {e}")
        return 0

@app.route('/trade/<int:trade_id>', methods=['GET', 'POST'])
def trade_detail(trade_id):
    trade = Trade.query.get_or_404(trade_id)
    if request.method == 'POST':
        # Nur Formular-Daten verarbeiten (keine Bilder)
        # Save textarea fields
        trade.analysis = request.form.get('analysis', '')
        trade.entry_comment = request.form.get('entry_comment', '')
        trade.risk_management = request.form.get('risk_management', '')
        trade.psychological_factors = request.form.get('psychological_factors', '')
        trade.bias_basis = request.form.get('bias_basis', '')
        trade.what_went_well_bad = request.form.get('what_went_well_bad', '')
        trade.market_phase = request.form.get('market_phase', '')
        
        # Save account_type field
        trade.account_type = request.form.get('account_type', '')
        
        # Save mistakes and entry_type fields
        mistakes_str = request.form.get('mistakes', '')
        trade.mistakes = mistakes_str.split(',') if mistakes_str else []
        
        entry_type_str = request.form.get('entry_type', '')
        trade.entry_type = entry_type_str.split(',') if entry_type_str else []
        
        # Save SL and trade_rating
        sl_val = request.form.get('sl')
        trade.sl = float(sl_val) if sl_val not in (None, '', 'None') else None
        
        trade_rating_val = request.form.get('trade_rating')
        trade.trade_rating = float(trade_rating_val) if trade_rating_val not in (None, '', 'None') else 0
        
        try:
            db.session.commit()
        except Exception as e:
            app.logger.error(f"Error saving trade: {e}")
            db.session.rollback()
        
        return redirect(url_for('trade_detail', trade_id=trade_id))
    # GET: Seite anzeigen
    # Dummy-Daten ergänzen, falls trade nicht alle Felder hat
    trade_dict = trade.__dict__.copy()
    trade_dict.setdefault('option', '')
    # Berechne NET P&L korrekt
    pnl = getattr(trade, 'pnl', 0) or 0
    kommission = getattr(trade, 'kommission', 0) or 0
    swap = getattr(trade, 'swap', 0) or 0
    trade_dict['net_pl'] = pnl + kommission + swap
    trade_dict.setdefault('options_traded', getattr(trade, 'options_traded', 0))
    trade_dict.setdefault('commissions', getattr(trade, 'commissions', 0.0))
    trade_dict.setdefault('net_roi', getattr(trade, 'net_roi', 0.0))
    trade_dict.setdefault('gross_pl', getattr(trade, 'gross_pl', trade.pnl if hasattr(trade, 'pnl') else 0.0))
    trade_dict.setdefault('adjusted_cost', getattr(trade, 'adjusted_cost', 0.0))
    trade_dict.setdefault('profit_target', getattr(trade, 'profit_target', 0.0))
    trade_dict.setdefault('stop_loss', getattr(trade, 'stop_loss', 0.0))
    trade_dict.setdefault('initial_target', getattr(trade, 'initial_target', 0.0))
    trade_dict.setdefault('trade_risk', getattr(trade, 'trade_risk', 0.0))
    trade_dict.setdefault('planned_r_multiple', getattr(trade, 'planned_r_multiple', 0.0))
    trade_dict.setdefault('realized_r_multiple', getattr(trade, 'realized_r_multiple', 0.0))
    trade_dict.setdefault('setups', getattr(trade, 'setups', []))
    trade_dict.setdefault('mistakes', getattr(trade, 'mistakes', []))
    trade_dict.setdefault('custom_tags', getattr(trade, 'custom_tags', []))
    trade_dict.setdefault('zella_scale', getattr(trade, 'zella_scale', 0.0))
    trade_dict.setdefault('mae_mfe', getattr(trade, 'mae_mfe', 0.0))
    trade_dict.setdefault('trade_rating', getattr(trade, 'trade_rating', 0))
    trade_dict.setdefault('market_phase', getattr(trade, 'market_phase', ''))
    # Neue Felder für Textareas
    trade_dict.setdefault('analysis', getattr(trade, 'analysis', ''))
    trade_dict.setdefault('entry_comment', getattr(trade, 'entry_comment', ''))
    trade_dict.setdefault('risk_management', getattr(trade, 'risk_management', ''))
    trade_dict.setdefault('psychological_factors', getattr(trade, 'psychological_factors', ''))
    trade_dict.setdefault('bias_basis', getattr(trade, 'bias_basis', ''))
    trade_dict.setdefault('what_went_well_bad', getattr(trade, 'what_went_well_bad', ''))
    trade_dict.setdefault('mistakes', getattr(trade, 'mistakes', []))
    trade_dict.setdefault('entry_type', getattr(trade, 'entry_type', []))
    trade_dict.setdefault('trade_rating', getattr(trade, 'trade_rating', 0))
    # Stelle sicher, dass alle Bildpfade in der Liste / statt \ verwenden
    trade_dict['images'] = [img.replace('\\', '/') for img in (trade.images or [])]
    return render_template('trade_detail.html', trade=trade_dict)

def allowed_image_file(filename):
    """Check if uploaded image file is allowed"""
    ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
    return ('.' in filename and 
            os.path.splitext(filename)[1].lower() in ALLOWED_IMAGE_EXTENSIONS)

def validate_image_file(file):
    """Validate image file type by checking file headers"""
    if not file:
        return False
    
    # Read first few bytes to check file signature
    file.seek(0)
    header = file.read(12)
    file.seek(0)
    
    # Check for valid image file signatures
    if header.startswith(b'\xff\xd8\xff'):  # JPEG
        return True
    elif header.startswith(b'\x89PNG\r\n\x1a\n'):  # PNG
        return True
    elif header.startswith(b'GIF87a') or header.startswith(b'GIF89a'):  # GIF
        return True
    elif header.startswith(b'RIFF') and header[8:12] == b'WEBP':  # WebP
        return True
    
    return False

@app.route('/trade/<int:trade_id>/upload-image', methods=['POST'])
@login_required
def upload_image(trade_id):
    trade = Trade.query.get_or_404(trade_id)
    
    # Verify user owns this trade
    if trade.account.user_id != current_user.id:
        flash('Unauthorized access!', 'error')
        return redirect(url_for('trade_detail', trade_id=trade_id))
    
    if 'images' not in request.files:
        flash('No images uploaded!', 'error')
        return redirect(url_for('trade_detail', trade_id=trade_id))
    
    files = request.files.getlist('images')
    
    if not files or files[0].filename == '':
        flash('No files selected!', 'error')
        return redirect(url_for('trade_detail', trade_id=trade_id))
    
    # Initialize images list if None
    if trade.images is None:
        trade.images = []
    
    uploaded_files = []
    max_files = 10  # Limit number of files per upload
    
    if len(files) > max_files:
        flash(f'Too many files! Maximum {max_files} files allowed per upload.', 'error')
        return redirect(url_for('trade_detail', trade_id=trade_id))
    
    for file in files:
        if file and file.filename:
            # Validate file type by extension
            if not allowed_image_file(file.filename):
                flash(f'Invalid file type: {file.filename}. Only JPG, PNG, GIF, WebP allowed.', 'error')
                continue
            
            # Validate file by content
            if not validate_image_file(file):
                flash(f'Invalid image file: {file.filename}', 'error')
                continue
            
            # Validate file size
            if not validate_file_size(file):
                flash(f'File too large: {file.filename}. Maximum size is 16MB.', 'error')
                continue
            
            # Generate secure filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            secure_name = secure_filename(file.filename)
            filename = f"trade_{trade_id}_{timestamp}_{secure_name}"
            filepath = os.path.join('static', 'uploads', filename)
            
            # Ensure upload directory exists
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            
            try:
                # Save the file
                file.save(filepath)
                
                # Verify file was saved and get size
                if os.path.exists(filepath):
                    file_size = os.path.getsize(filepath)
                    if file_size == 0:
                        os.remove(filepath)
                        flash(f'Empty file detected: {file.filename}', 'error')
                        continue
                        
                    # Add to trade images list
                    relative_path = f"uploads/{filename}"
                    trade.images.append(relative_path)
                    uploaded_files.append(relative_path)
                else:
                    flash(f'Failed to save file: {file.filename}', 'error')
                    continue
                    
            except Exception as e:
                flash(f'Error saving file {file.filename}: {str(e)}', 'error')
                continue
    
    # Update database if files were uploaded
    if uploaded_files:
        try:
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(trade, 'images')
            db.session.commit()
            flash(f'Successfully uploaded {len(uploaded_files)} image(s)!', 'success')
        except Exception as e:
            db.session.rollback()
            # Clean up uploaded files on database error
            for file_path in uploaded_files:
                try:
                    os.remove(os.path.join('static', file_path))
                except:
                    pass
            flash(f'Database error: {str(e)}', 'error')
    
    return redirect(url_for('trade_detail', trade_id=trade_id))

@app.route('/trade/<int:trade_id>/delete-image', methods=['POST'])
def delete_image(trade_id):
    trade = Trade.query.get_or_404(trade_id)
    image = request.form.get('image')
    if image and trade.images:
        # Normalisiere den Bildpfad für den Vergleich
        image = image.replace('\\', '/')
        if image in [img.replace('\\', '/') for img in trade.images]:
            # Entferne Bild aus Liste
            trade.images = [img for img in trade.images if img.replace('\\', '/') != image]
            
            # WICHTIG: SQLAlchemy mitteilen, dass sich das JSON-Feld geändert hat
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(trade, 'images')
            
            db.session.commit()
            # Versuche Datei zu löschen
            try:
                file_path = os.path.join('static', image)
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                print(f"Fehler beim Löschen der Bilddatei: {e}")
    return redirect(url_for('trade_detail', trade_id=trade_id))

@app.route('/api/dashboard-stats')
def get_dashboard_stats():
    account = request.args.get('account', 'all')
    
    # Filtere Trades basierend auf Account-Typ
    query = Trade.query
    if account != 'all':
        query = query.filter_by(account_type=account)
    
    trades = query.all()
    
    if not trades:
        return jsonify({
            'winRate': 0,
            'profitLoss': 0,
            'totalTrades': 0,
            'averageRR': 0,
            'chartData': {
                'labels': [],
                'datasets': [{
                    'data': []
                }]
            }
        })
    
    # Berechne Statistiken
    total_trades = len(trades)
    winning_trades = sum(1 for trade in trades if (trade.pnl or 0) > 0)
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
    total_pnl = sum((trade.pnl or 0) for trade in trades)
    
    # Berechne durchschnittliches R:R
    rr_ratios = []
    for trade in trades:
        entry_price = trade.entry_price or 0
        exit_price = trade.exit_price or 0
        
        if entry_price == 0 or exit_price == 0:
            continue
            
        if trade.direction == 'LONG':
            risk = entry_price - min(entry_price, exit_price)
            reward = max(entry_price, exit_price) - entry_price
        else:  # SHORT
            risk = max(entry_price, exit_price) - entry_price
            reward = entry_price - min(entry_price, exit_price)
        
        if risk > 0:
            rr_ratios.append(reward / risk)
    
    avg_rr = sum(rr_ratios) / len(rr_ratios) if rr_ratios else 0
    
    # Bereite Chart-Daten vor
    dates = [trade.date.strftime('%Y-%m-%d') if trade.date else 'Unknown' for trade in trades]
    pnl_values = [(trade.pnl or 0) for trade in trades]
    
    chart_data = {
        'labels': dates,
        'datasets': [{
            'label': 'P&L',
            'data': pnl_values,
            'borderColor': '#10B981',
            'tension': 0.1
        }]
    }
    
    return jsonify({
        'winRate': round(win_rate, 2),
        'profitLoss': round(total_pnl, 2),
        'totalTrades': total_trades,
        'averageRR': round(avg_rr, 2),
        'chartData': chart_data
    })

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'])
        # Prüfe, ob der Benutzername schon existiert
        if User.query.filter_by(username=username).first():
            flash('Benutzername existiert bereits. Bitte wähle einen anderen.', 'error')
            return redirect(url_for('register'))
        user = User(username=username, password=password)
        db.session.add(user)
        db.session.commit()
        # Optional: Account für User anlegen
        acc = Account(name=f"{username}_account", user_id=user.id)
        db.session.add(acc)
        db.session.commit()
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        # Basic input validation
        if not username or not password:
            flash('Username and password are required', 'error')
            return render_template('login.html')
        
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid credentials', 'error')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/test-db-connection')
def test_db_connection():
    try:
        # Versuche, die Anzahl der Trades zu zählen
        trade_count = Trade.query.count()
        # Versuche, die Anzahl der Accounts zu zählen
        account_count = Account.query.count()
        return jsonify({
            'status': 'success',
            'message': 'Datenbankverbindung erfolgreich',
            'trade_count': trade_count,
            'account_count': account_count
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Datenbankfehler: {str(e)}'
        }), 500

@app.route('/add-trade-manual', methods=['GET', 'POST'])
def add_trade_manual():
    if request.method == 'POST':
        # Entferne 'notes' aus den Formulardaten
        trade_data = {
            'date': datetime.strptime(request.form['date'], '%Y-%m-%dT%H:%M'),
            'position': request.form['position'],
            'symbol': request.form['symbol'],
            'direction': request.form['direction'],
            'position_size': float(request.form['position_size']),
            'entry_price': float(request.form['entry_price']),
            'sl': float(request.form['sl']) if request.form['sl'] else None,
            'tp': float(request.form['tp']) if request.form['tp'] else None,
            'exit_date': datetime.strptime(request.form['exit_date'], '%Y-%m-%dT%H:%M') if request.form['exit_date'] else None,
            'exit_price': float(request.form['exit_price']) if request.form['exit_price'] else None,
            'kommission': float(request.form['kommission']) if request.form['kommission'] else None,
            'swap': float(request.form['swap']) if request.form['swap'] else None,
            'pnl': float(request.form['pnl']) if request.form['pnl'] else None,
            'account_id': int(request.form['account_id']),
            'market_phase': request.form.get('market_phase'),
            'analysis': request.form.get('analysis'),
            'entry_comment': request.form.get('entry_comment'),
            'risk_management': request.form.get('risk_management'),
            'psychological_factors': request.form.get('psychological_factors'),
            'bias_basis': request.form.get('bias_basis'),
            'what_went_well_bad': request.form.get('what_went_well_bad'),
        }
        trade = Trade(**trade_data)
        db.session.add(trade)
        db.session.commit()
        return redirect(url_for('trade_detail', trade_id=trade.id))
    return render_template('add_trade_manual.html', accounts=Account.query.all())

@app.route('/edit-trade/<int:trade_id>', methods=['GET', 'POST'])
@login_required
def edit_trade(trade_id):
    trade = Trade.query.get_or_404(trade_id)
    if request.method == 'POST':
        trade.market_phase = request.form.get('market_phase') or ''
        # Zahlenfelder sicher behandeln:
        sl_val = request.form.get('sl')
        trade.sl = float(sl_val) if sl_val not in (None, '', 'None') else None
        entry_price_val = request.form.get('entry_price')
        trade.entry_price = float(entry_price_val) if entry_price_val not in (None, '', 'None') else None
        exit_price_val = request.form.get('exit_price')
        trade.exit_price = float(exit_price_val) if exit_price_val not in (None, '', 'None') else None
        trade.entry_type = request.form.get('entry_type') or ''
        trade.trade_rating = request.form.get('trade_rating') or ''
        # Neue Felder für Textareas
        trade.analysis = request.form.get('analysis', '')
        trade.entry_comment = request.form.get('entry_comment', '')
        trade.risk_management = request.form.get('risk_management', '')
        trade.psychological_factors = request.form.get('psychological_factors', '')
        trade.bias_basis = request.form.get('bias_basis', '')
        trade.what_went_well_bad = request.form.get('what_went_well_bad', '')
        db.session.commit()
        flash('Trade aktualisiert!', 'success')
        return redirect(url_for('trade_detail', trade_id=trade.id))
    return render_template('edit_trade.html', trade=trade)

@app.route('/delete-trade/<int:trade_id>', methods=['POST'])
@login_required
def delete_trade(trade_id):
    trade = Trade.query.get_or_404(trade_id)
    db.session.delete(trade)
    db.session.commit()
    flash('Trade gelöscht!', 'success')
    return redirect(url_for('journal_hub'))

@app.route('/api/calendar-trades')
@login_required
def api_calendar_trades():
    try:
        month = int(request.args.get('month'))  # 1-basiert
        year = int(request.args.get('year'))
        account_type = request.args.get('account_type', 'all')  # Account type filter hinzufügen
        
        from calendar import monthrange
        start = datetime(year, month, 1)
        end = datetime(year, month, monthrange(year, month)[1], 23, 59, 59)
        
        # Debug: Zeige den Zeitraum
        print(f"Kalender-Zeitraum: {start} bis {end}")
        print(f"Kalender account_type filter: {account_type}")
        
        # Filter trades by user's accounts
        accounts = Account.query.filter_by(user_id=current_user.id).all()
        account_ids = [acc.id for acc in accounts]
        
        if not account_ids:
            # No accounts for user, return empty calendar
            day_map = {}
            for d in range(1, monthrange(year, month)[1]+1):
                day_map[d] = {'pnl': 0, 'trades': 0, 'wins': 0, 'losses': 0, 'r_sum': 0, 'winrate': 0}
            
            return jsonify({
                'days': day_map,
                'monthly_pnl': 0,
                'days_traded': 0
            })
        
        # Filter nach exit_date, fallback auf date - only for user's trades
        # Mit account_type Filter hinzufügen
        if account_type and account_type != 'all':
            trades = Trade.query.filter(
                Trade.account_id.in_(account_ids),
                Trade.account_type == account_type,
                ((Trade.exit_date >= start) & (Trade.exit_date <= end)) | 
                ((Trade.exit_date == None) & (Trade.date >= start) & (Trade.date < end))
            ).all()
        else:
            trades = Trade.query.filter(
                Trade.account_id.in_(account_ids),
                ((Trade.exit_date >= start) & (Trade.exit_date <= end)) | 
                ((Trade.exit_date == None) & (Trade.date >= start) & (Trade.date < end))
            ).all()
        
        # Debug: Zeige gefundene Trades mit allen relevanten Werten
        print(f"Gefundene Trades für User {current_user.id}: {[(t.symbol, t.date, t.exit_date, t.pnl, t.kommission, t.swap, t.account_type) for t in trades]}")
        
        day_map = {}
        for d in range(1, monthrange(year, month)[1]+1):
            day_map[d] = {'pnl': 0, 'trades': 0, 'wins': 0, 'losses': 0, 'r_sum': 0}
        
        for t in trades:
            # Für die Tageszuordnung immer exit_date (Ausstiegszeit) verwenden, falls vorhanden
            trade_day = None
            if t.exit_date:
                trade_day = t.exit_date.day
                print(f"Trade {t.symbol}: Verwende exit_date {t.exit_date} -> Tag {trade_day}")
            elif t.date:
                trade_day = t.date.day
                print(f"Trade {t.symbol}: Verwende date {t.date} -> Tag {trade_day}")
            else:
                print(f"Trade {t.symbol}: Kein Datum gefunden, überspringe")
                continue
                
            # PNL immer als Summe aus pnl + kommission + swap berechnen
            total_pnl = (t.pnl or 0) + (t.kommission or 0) + (t.swap or 0)
            print(f"Trade {t.symbol}: PNL={t.pnl}, Kommission={t.kommission}, Swap={t.swap}, Total={total_pnl}")
            
            day_map[trade_day]['pnl'] += total_pnl
            day_map[trade_day]['trades'] += 1
            if total_pnl > 0:
                day_map[trade_day]['wins'] += 1
            elif total_pnl < 0:
                day_map[trade_day]['losses'] += 1
                
            # R-Multiplikator, falls im Modell vorhanden
            r = getattr(t, 'r', None)
            if r is not None:
                try:
                    day_map[trade_day]['r_sum'] += float(r)
                except:
                    pass
        
        # Debug: Zeige Tageszuordnung
        print(f"Tageszuordnung: {day_map}")
        
        for d in day_map:
            total = day_map[d]['trades']
            wins = day_map[d]['wins']
            day_map[d]['winrate'] = round(100 * wins / total, 2) if total else 0
        
        # Monthly stats
        monthly_pnl = sum(day_map[d]['pnl'] for d in day_map)
        days_traded = sum(1 for d in day_map if day_map[d]['trades'] > 0)
        
        return jsonify({
            'days': day_map,
            'monthly_pnl': monthly_pnl,
            'days_traded': days_traded
        })
        
    except Exception as e:
        print(f"Error in calendar API: {e}")
        return jsonify({'error': 'Failed to load calendar data'}), 500

@app.route('/trade/new', methods=['GET', 'POST'])
def trade_new():
    if request.method == 'POST':
        # Trade anlegen und speichern
        def get_form_value(name, cast=None):
            val = request.form.get(name, '').strip()
            if val == '':
                return None
            if cast:
                try:
                    return cast(val)
                except Exception:
                    return None
            return val
        trade_data = {
            'date': datetime.strptime(get_form_value('date'), '%Y-%m-%dT%H:%M') if get_form_value('date') else None,
            'position': get_form_value('position'),
            'symbol': get_form_value('symbol'),
            'direction': get_form_value('direction'),
            'position_size': get_form_value('position_size', float),
            'entry_price': get_form_value('entry_price', float),
            'sl': get_form_value('sl', float),
            'tp': get_form_value('tp', float),
            'exit_date': datetime.strptime(get_form_value('exit_date'), '%Y-%m-%dT%H:%M') if get_form_value('exit_date') else None,
            'exit_price': get_form_value('exit_price', float),
            'kommission': get_form_value('kommission', float),
            'swap': get_form_value('swap', float),
            'pnl': get_form_value('pnl', float),
            'account_id': get_form_value('account_id', int),
            'market_phase': get_form_value('market_phase'),
            'analysis': get_form_value('analysis'),
            'entry_comment': get_form_value('entry_comment'),
            'risk_management': get_form_value('risk_management'),
            'psychological_factors': get_form_value('psychological_factors'),
            'bias_basis': get_form_value('bias_basis'),
            'what_went_well_bad': get_form_value('what_went_well_bad'),
        }
        trade = Trade(**trade_data)
        db.session.add(trade)
        db.session.commit()
        return redirect(url_for('trade_detail', trade_id=trade.id))
    # GET: Leeres Formular anzeigen
    accounts = Account.query.all()
    return render_template('trade_detail.html', trade=None, accounts=accounts, new_trade=True)

@app.route('/settings')
@login_required
def settings():
    return render_template('settings.html', 
                         current_username=current_user.username,
                         current_email=current_user.email)

@app.route('/change_username', methods=['POST'])
@login_required
def change_username():
    new_username = request.form.get('new_username')
    
    if not new_username:
        flash('Username cannot be empty', 'error')
        return redirect(url_for('settings'))
    
    # Check if username already exists
    existing_user = User.query.filter_by(username=new_username).first()
    if existing_user and existing_user.id != current_user.id:
        flash('Username already taken', 'error')
        return redirect(url_for('settings'))
    
    current_user.username = new_username
    db.session.commit()
    flash('Username updated successfully', 'success')
    return redirect(url_for('settings'))

@app.route('/change_email', methods=['POST'])
@login_required
def change_email():
    new_email = request.form.get('new_email')
    
    if not new_email:
        flash('E-Mail-Adresse darf nicht leer sein', 'error')
        return redirect(url_for('settings'))
    
    # Basic email validation
    import re
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_pattern, new_email):
        flash('Ungültige E-Mail-Adresse', 'error')
        return redirect(url_for('settings'))
    
    # Check if email already exists
    existing_user = User.query.filter_by(email=new_email).first()
    if existing_user and existing_user.id != current_user.id:
        flash('Diese E-Mail-Adresse wird bereits verwendet', 'error')
        return redirect(url_for('settings'))
    
    current_user.email = new_email
    db.session.commit()
    flash('E-Mail-Adresse erfolgreich aktualisiert', 'success')
    return redirect(url_for('settings'))

@app.route('/change_password', methods=['POST'])
@login_required
def change_password():
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')
    
    if not current_user.check_password(current_password):
        flash('Current password is incorrect', 'error')
        return redirect(url_for('settings'))
    
    if new_password != confirm_password:
        flash('New passwords do not match', 'error')
        return redirect(url_for('settings'))
    
    if len(new_password) < 6:
        flash('Password must be at least 6 characters long', 'error')
        return redirect(url_for('settings'))
    
    current_user.set_password(new_password)
    db.session.commit()
    flash('Password updated successfully', 'success')
    return redirect(url_for('settings'))

@app.route('/delete_account', methods=['POST'])
@login_required
def delete_account():
    # Delete all user's data
    Trade.query.filter_by(user_id=current_user.id).delete()
    
    # Delete the user
    db.session.delete(current_user)
    db.session.commit()
    
    logout_user()
    flash('Your account has been deleted', 'success')
    return redirect(url_for('login'))

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        username = request.form.get('username')
        user = User.query.filter_by(username=username).first()
        if user:
            token = serializer.dumps(user.id, salt='password-reset-salt')
            reset_url = url_for('reset_password', token=token, _external=True)
            # Hier würdest du normalerweise eine E-Mail senden. Für Demo zeigen wir den Link als Flash.
            flash(f'Passwort-Reset-Link: {reset_url}', 'success')
        else:
            flash('Falls der Benutzer existiert, wurde eine Anweisung zum Zurücksetzen des Passworts gesendet.', 'success')
        return redirect(url_for('login'))
    return render_template('forgot_password.html')

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    try:
        user_id = serializer.loads(token, salt='password-reset-salt', max_age=3600)
    except Exception:
        flash('Der Link ist ungültig oder abgelaufen.', 'error')
        return redirect(url_for('login'))
    user = User.query.get(user_id)
    if not user:
        flash('Benutzer nicht gefunden.', 'error')
        return redirect(url_for('login'))
    if request.method == 'POST':
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        if not new_password or new_password != confirm_password:
            flash('Passwörter stimmen nicht überein.', 'error')
            return redirect(request.url)
        user.set_password(new_password)
        db.session.commit()
        flash('Passwort erfolgreich zurückgesetzt. Du kannst dich jetzt einloggen.', 'success')
        return redirect(url_for('login'))
    return render_template('reset_password.html')

@app.route('/delete-trades', methods=['POST'])
@login_required
def delete_trades():
    data = request.get_json()
    trade_ids = data.get('trade_ids', [])
    if not trade_ids:
        return jsonify({'status': 'error', 'message': 'Keine IDs übergeben!'}), 400
    try:
        Trade.query.filter(Trade.id.in_(trade_ids)).delete(synchronize_session=False)
        db.session.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/entry-type-chart')
@login_required
def api_entry_type_chart():
    """API-Route für Entry Type Chart-Daten"""
    # Hole Parameter
    account_type = request.args.get('account_type', 'all')
    date_param = request.args.get('date')  # Für Daily Journal
    date_range = request.args.get('date_range', '')  # Für Dashboard
    
    # Bestimme den Zeitraum
    if date_param:
        # Daily Journal: Ein spezifischer Tag
        try:
            selected_date_dt = datetime.strptime(date_param, '%Y-%m-%d')
        except ValueError:
            selected_date_dt = datetime.utcnow().date()
        start = datetime(selected_date_dt.year, selected_date_dt.month, selected_date_dt.day)
        end = start + timedelta(days=1)
        print(f"DEBUG API: Daily Journal mode - Date range: {start} to {end}")
    else:
        # Dashboard: Verwende die gleiche Logik wie in der Dashboard Route
        # FIXED: Standardmäßig alle Trades seit dem ersten Trade anzeigen
        if date_range:
            # Wenn date_range gesetzt ist, verwende den Custom Range
            try:
                start_str, end_str = date_range.split(' - ')
                start = datetime.strptime(start_str, '%Y-%m-%d')
                end = datetime.strptime(end_str, '%Y-%m-%d') + timedelta(days=1, seconds=-1)
            except Exception as e:
                print('Fehler beim Parsen von date_range:', e)
                # Fallback: Alle Trades
                start = datetime(1900, 1, 1)  # Sehr frühes Datum
                end = datetime.now(timezone.utc) + timedelta(days=1)  # Bis morgen
        else:
            # Standardverhalten: Alle Trades seit dem ersten Trade
            start = datetime(1900, 1, 1)  # Sehr frühes Datum um alle Trades zu erfassen
            end = datetime.now(timezone.utc) + timedelta(days=1)  # Bis morgen
        
        print(f"DEBUG API: Dashboard mode - Date range: {start} to {end}, account_type: {account_type}")

    # Filtere Trades
    accounts = Account.query.filter_by(user_id=current_user.id).all()
    account_ids = [acc.id for acc in accounts]
    
    if date_param:
        # Daily Journal Filter
        if account_type != 'all':
            trades = Trade.query.filter(
                Trade.account_id.in_(account_ids),
                Trade.account_type == account_type,
                ((Trade.exit_date >= start) & (Trade.exit_date < end)) | 
                ((Trade.exit_date == None) & (Trade.date >= start) & (Trade.date < end))
            ).all()
        else:
            trades = Trade.query.filter(
                Trade.account_id.in_(account_ids),
                ((Trade.exit_date >= start) & (Trade.exit_date < end)) | 
                ((Trade.exit_date == None) & (Trade.date >= start) & (Trade.date < end))
            ).all()
    else:
        # Dashboard Filter
        if account_type != 'all':
            trades = Trade.query.join(Account).filter(
                Account.user_id == current_user.id,
                Trade.account_type == account_type,
                ((Trade.exit_date >= start) & (Trade.exit_date <= end)) | 
                ((Trade.exit_date == None) & (Trade.date >= start) & (Trade.date <= end))
            ).order_by(Trade.exit_date.desc().nullslast(), Trade.date.desc()).all()
        else:
            trades = Trade.query.join(Account).filter(
                Account.user_id == current_user.id,
                ((Trade.exit_date >= start) & (Trade.exit_date <= end)) | 
                ((Trade.exit_date == None) & (Trade.date >= start) & (Trade.date <= end))
            ).order_by(Trade.exit_date.desc().nullslast(), Trade.date.desc()).all()
    
    print(f"DEBUG API: Found {len(trades)} trades for processing")

    # Entry Type Chart Logic (gleich wie in dashboard/daily_journal)
    entry_type_stats = {}
    for t in trades:
        t.total_pnl = (t.pnl or 0) + (t.kommission or 0) + (t.swap or 0)
        
        entry_types = []
        if hasattr(t, 'entry_type') and t.entry_type:
            try:
                if isinstance(t.entry_type, str):
                    entry_types = json.loads(t.entry_type)
                elif isinstance(t.entry_type, list):
                    entry_types = t.entry_type
            except (json.JSONDecodeError, TypeError):
                entry_types = []
        
        # Debug für API Route
        print(f"DEBUG API: Trade {t.id} symbol={t.symbol}, entry_type raw='{t.entry_type}', parsed={entry_types}, total_pnl={t.total_pnl}")
        
        if not entry_types:
            print(f"DEBUG API: Trade {t.symbol} has no entry_type, skipping for entry-type chart")
            continue
            
        for entry_type in entry_types:
            if entry_type not in entry_type_stats:
                entry_type_stats[entry_type] = {"wins": 0, "losses": 0, "total": 0}
            
            entry_type_stats[entry_type]["total"] += 1
            if t.total_pnl > 0:
                entry_type_stats[entry_type]["wins"] += 1
            elif t.total_pnl < 0:
                entry_type_stats[entry_type]["losses"] += 1

    print(f"DEBUG API: entry_type_stats = {entry_type_stats}")

    # Prepare chart data
    all_entry_types = ["Fibonacci", "MSS + S", "MSS + D", "FOMO"]
    chart_labels = []
    chart_wins = []
    chart_losses = []
    chart_totals = []
    
    for entry_type in all_entry_types:
        chart_labels.append(entry_type)
        if entry_type in entry_type_stats:
            stats = entry_type_stats[entry_type]
            wins = stats["wins"]
            losses = stats["losses"]
            total = stats["total"]
        else:
            wins = 0
            losses = 0
            total = 0
        
        chart_wins.append(wins)
        chart_losses.append(losses)
        chart_totals.append(total)

    return jsonify({
        'chart_labels': chart_labels,
        'chart_wins': chart_wins,
        'chart_losses': chart_losses,
        'chart_totals': chart_totals
    })

@app.route('/api/monthly-stats')
@login_required
def api_monthly_stats():
    """API-Route für monatliche Statistiken für das Jahr-Popup"""
    year = int(request.args.get('year', datetime.utcnow().year))
    account_type = request.args.get('account_type', 'all')
    
    # Filtere Trades nach Account und User
    accounts = Account.query.filter_by(user_id=current_user.id).all()
    account_ids = [acc.id for acc in accounts]
    
    # Basis-Query für das Jahr
    year_start = datetime(year, 1, 1)
    year_end = datetime(year, 12, 31, 23, 59, 59)
    
    if account_type != 'all':
        trades = Trade.query.join(Account).filter(
            Account.user_id == current_user.id,
            (Trade.exit_date >= year_start) & (Trade.exit_date <= year_end),
            Trade.account_type == account_type
        ).all()
    else:
        trades = Trade.query.join(Account).filter(
            Account.user_id == current_user.id,
            (Trade.exit_date >= year_start) & (Trade.exit_date <= year_end)
        ).all()
    
    # Gruppiere Trades nach Monaten
    monthly_stats = {}
    for month in range(1, 13):
        monthly_stats[month] = {
            'pnl': 0,
            'trades': 0,
            'wins': 0,
            'losses': 0
        }
    
    for trade in trades:
        if not trade.exit_date:
            continue
            
        month = trade.exit_date.month
        total_pnl = (trade.pnl or 0) + (trade.kommission or 0) + (trade.swap or 0)
        
        monthly_stats[month]['pnl'] += total_pnl
        monthly_stats[month]['trades'] += 1
        
        if total_pnl > 0:
            monthly_stats[month]['wins'] += 1
        elif total_pnl < 0:
            monthly_stats[month]['losses'] += 1
    
    return jsonify({
        'year': year,
        'months': monthly_stats
    })

@app.route('/api/debug-chart-data')
@login_required
def debug_chart_data():
    """Debug endpoint to check chart data"""
    try:
        accounts = Account.query.filter_by(user_id=current_user.id).all()
        account_ids = [acc.id for acc in accounts]
        
        if not account_ids:
            return jsonify({
                'error': 'No accounts found for user',
                'trades': 0
            })
        
        # Get all trades for user
        trades = Trade.query.filter(Trade.account_id.in_(account_ids)).all()
        
        def trade_total_pnl(t):
            return (t.pnl or 0) + (t.kommission or 0) + (t.swap or 0)
        
        # Hourly stats
        hourly_stats = {}
        for hour in range(24):
            hourly_stats[hour] = {"wins": 0, "losses": 0, "total": 0}
        
        trade_details = []
        for t in trades:
            trade_date = t.exit_date if t.exit_date else t.date
            if trade_date:
                hour = trade_date.hour
                total_pnl = trade_total_pnl(t)
                
                hourly_stats[hour]["total"] += 1
                if total_pnl > 0:
                    hourly_stats[hour]["wins"] += 1
                elif total_pnl < 0:
                    hourly_stats[hour]["losses"] += 1
                
                trade_details.append({
                    'id': t.id,
                    'symbol': t.symbol,
                    'date': trade_date.strftime('%Y-%m-%d %H:%M:%S'),
                    'hour': hour,
                    'pnl': total_pnl,
                    'result': 'WIN' if total_pnl > 0 else 'LOSS' if total_pnl < 0 else 'BE'
                })
        
        # Prepare chart arrays
        hourly_wins = [hourly_stats[hour]["wins"] for hour in range(24)]
        hourly_losses = [hourly_stats[hour]["losses"] for hour in range(24)]
        hourly_totals = [hourly_stats[hour]["total"] for hour in range(24)]
        
        return jsonify({
            'total_trades': len(trades),
            'trades_with_time': len(trade_details),
            'hourly_wins': hourly_wins,
            'hourly_losses': hourly_losses,
            'hourly_totals': hourly_totals,
            'trade_details': trade_details[:10],  # Show first 10 trades for debugging
            'hourly_summary': {str(hour): stats for hour, stats in hourly_stats.items() if stats["total"] > 0}
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/chart-test')
@login_required
def chart_test():
    """Test route to verify chart data"""
    accounts = Account.query.filter_by(user_id=current_user.id).all()
    account_ids = [acc.id for acc in accounts]
    
    if not account_ids:
        return "No accounts found"
        
    trades = Trade.query.filter(Trade.account_id.in_(account_ids)).all()
    
    def trade_total_pnl(t):
        return (t.pnl or 0) + (t.kommission or 0) + (t.swap or 0)
    
    # Hourly stats
    hourly_stats = {}
    for hour in range(24):
        hourly_stats[hour] = {"wins": 0, "losses": 0, "total": 0}
    
    for t in trades:
        trade_date = t.exit_date if t.exit_date else t.date
        if trade_date:
            hour = trade_date.hour
            total_pnl = trade_total_pnl(t)
            
            hourly_stats[hour]["total"] += 1
            if total_pnl > 0:
                hourly_stats[hour]["wins"] += 1
            elif total_pnl < 0:
                hourly_stats[hour]["losses"] += 1
    
    # Prepare chart data
    hourly_labels = [f"{hour:02d}:00" for hour in range(24)]
    hourly_wins = [hourly_stats[hour]["wins"] for hour in range(24)]
    hourly_losses = [hourly_stats[hour]["losses"] for hour in range(24)]
    hourly_totals = [hourly_stats[hour]["total"] for hour in range(24)]
    
    return render_template('chart_test.html',
                         hourly_labels=hourly_labels,
                         hourly_wins=hourly_wins,
                         hourly_losses=hourly_losses,
                         hourly_totals=hourly_totals)

@app.route('/dashboard-minimal')
@login_required
def dashboard_minimal():
    """Minimal dashboard for testing charts without external dependencies"""
    accounts = Account.query.filter_by(user_id=current_user.id).all()
    account_ids = [acc.id for acc in accounts]
    
    if not account_ids:
        # No accounts, return empty data
        return render_template('dashboard_minimal.html',
                             weekday_labels=['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'],
                             weekday_wins=[0]*7,
                             weekday_losses=[0]*7,
                             hourly_labels=[f"{hour:02d}:00" for hour in range(24)],
                             hourly_wins=[0]*24,
                             hourly_losses=[0]*24)
    
    trades = Trade.query.filter(Trade.account_id.in_(account_ids)).all()
    
    def trade_total_pnl(t):
        return (t.pnl or 0) + (t.kommission or 0) + (t.swap or 0)
    
    # Weekday data
    weekday_stats = {}
    weekdays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    for weekday in weekdays:
        weekday_stats[weekday] = {"wins": 0, "losses": 0, "total": 0}
    
    # Hourly data
    hourly_stats = {}
    for hour in range(24):
        hourly_stats[hour] = {"wins": 0, "losses": 0, "total": 0}
    
    for t in trades:
        trade_date = t.exit_date if t.exit_date else t.date
        if trade_date:
            # Weekday processing
            python_weekday = trade_date.weekday()
            weekday_name = weekdays[python_weekday]
            total_pnl = trade_total_pnl(t)
            
            weekday_stats[weekday_name]["total"] += 1
            if total_pnl > 0:
                weekday_stats[weekday_name]["wins"] += 1
            elif total_pnl < 0:
                weekday_stats[weekday_name]["losses"] += 1
            
            # Hourly processing
            hour = trade_date.hour
            hourly_stats[hour]["total"] += 1
            if total_pnl > 0:
                hourly_stats[hour]["wins"] += 1
            elif total_pnl < 0:
                hourly_stats[hour]["losses"] += 1
    
    # Prepare data
    weekday_wins = [weekday_stats[day]["wins"] for day in weekdays]
    weekday_losses = [weekday_stats[day]["losses"] for day in weekdays]
    
    hourly_labels = [f"{hour:02d}:00" for hour in range(24)]
    hourly_wins = [hourly_stats[hour]["wins"] for hour in range(24)]
    hourly_losses = [hourly_stats[hour]["losses"] for hour in range(24)]
    
    print(f"MINIMAL DASHBOARD: weekday_wins={weekday_wins}, weekday_losses={weekday_losses}")
    print(f"MINIMAL DASHBOARD: hourly_wins total={sum(hourly_wins)}, hourly_losses total={sum(hourly_losses)}")
    
    return render_template('dashboard_minimal.html',
                         weekday_labels=weekdays,
                         weekday_wins=weekday_wins,
                         weekday_losses=weekday_losses,
                         hourly_labels=hourly_labels,
                         hourly_wins=hourly_wins,
                         hourly_losses=hourly_losses)

@app.route('/chart-debug')
@login_required
def chart_debug():
    """Debug route to test charts with actual data"""
    accounts = Account.query.filter_by(user_id=current_user.id).all()
    account_ids = [acc.id for acc in accounts]
    
    if not account_ids:
        # No accounts, return empty data
        return render_template('chart_debug.html',
                             weekday_labels=['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'],
                             weekday_wins=[0]*7,
                             weekday_losses=[0]*7)
    
    trades = Trade.query.filter(Trade.account_id.in_(account_ids)).all()
    
    def trade_total_pnl(t):
        return (t.pnl or 0) + (t.kommission or 0) + (t.swap or 0)
    
    # Weekday data
    weekday_stats = {}
    weekdays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    for weekday in weekdays:
        weekday_stats[weekday] = {"wins": 0, "losses": 0}
    
    for t in trades:
        trade_date = t.exit_date if t.exit_date else t.date
        if trade_date:
            python_weekday = trade_date.weekday()
            weekday_name = weekdays[python_weekday]
            total_pnl = trade_total_pnl(t)
            
            if total_pnl > 0:
                weekday_stats[weekday_name]["wins"] += 1
            elif total_pnl < 0:
                weekday_stats[weekday_name]["losses"] += 1
    
    weekday_wins = [weekday_stats[day]["wins"] for day in weekdays]
    weekday_losses = [weekday_stats[day]["losses"] for day in weekdays]
    
    return render_template('chart_debug.html',
                         weekday_labels=weekdays,
                         weekday_wins=weekday_wins,
                         weekday_losses=weekday_losses)

@app.route('/test')
def test_page():
    from datetime import datetime
    return render_template('test.html', current_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

def init_db():
    """Initialize database with error handling"""
    try:
        db.create_all()
        app.logger.info("Database tables created/verified successfully")
        return True
    except Exception as e:
        app.logger.error(f"Database setup error: {e}")
        return False

if __name__ == '__main__':
    with app.app_context():
        if not init_db():
            exit(1)
    
    # Get configuration from environment
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_ENV') == 'development'
    
    if debug_mode:
        # Development mode
        app.run(host='127.0.0.1', port=port, debug=True, use_reloader=True)
    else:
        # Production mode - should use WSGI server like Gunicorn
        app.logger.warning("Running in production mode with Flask dev server is not recommended!")
        app.run(host='0.0.0.0', port=port, debug=False) 
