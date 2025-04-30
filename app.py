# Add these routes in your `app.py`

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
from flask_socketio import SocketIO, emit
import os
import yaml
import datetime
from pytz import timezone
from kiteconnect import KiteConnect
import csv, smtplib
from email.message import EmailMessage
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
app.secret_key = os.getenv("APP_KEY", "supersecretkey")
socketio = SocketIO(app)

USERNAME = os.getenv("LOGIN_USER", "admin")
PASSWORD = os.getenv("LOGIN_PASS", "secret123")

LOG_FILE = "trigger_log.csv"
chartink_status_data = {"status": "waiting", "time": None, "alert_name": None, "stocks": [], "prices": []}
account_pnl = {"total_orders": 0, "total_pnl": 0.0, "orders": []}

# --- Loaders ---
def load_config():
    with open("config.yaml", "r") as f:
        return yaml.safe_load(f)

def load_settings():
    with open("settings.yaml", "r") as f:
        return yaml.safe_load(f)

def save_settings(settings):
    with open("settings.yaml", "w") as f:
        yaml.dump(settings, f)

def save_config(config):
    with open("config.yaml", "w") as f:
        yaml.dump(config, f)

def save_telegram(data):
    with open("telegram.yaml", "w") as f:
        yaml.dump(data, f)

def log_trigger_to_file(alert_name, stocks, prices):
    with open(LOG_FILE, mode='a', newline='') as file:
        writer = csv.writer(file)
        timestamp = datetime.datetime.now(timezone('Asia/Kolkata')).strftime("%Y-%m-%d %H:%M:%S")
        for s, p in zip(stocks, prices):
            writer.writerow([timestamp, alert_name, s.strip(), p.strip()])

def send_log_email():
    msg = EmailMessage()
    msg['Subject'] = 'Chartink Trigger Log'
    msg['From'] = 'youremail@gmail.com'
    msg['To'] = 'recipient@example.com'
    msg.set_content("Attached is the latest Chartink trigger log.")
    with open(LOG_FILE, 'rb') as f:
        msg.add_attachment(f.read(), maintype='text', subtype='csv', filename='trigger_log.csv')
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
        smtp.login('youremail@gmail.com', 'your-app-password')
        smtp.send_message(msg)

scheduler = BackgroundScheduler()
scheduler.add_job(send_log_email, 'cron', hour=18, minute=0)
scheduler.start()

@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['username'] == USERNAME and request.form['password'] == PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('dashboard'))
        return "Invalid Credentials", 401
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    creds = load_config()
    return render_template('dashboard.html', master_name=creds['master']['name'], child_accounts=creds['child_accounts'])

@app.route('/toggle-account/<account>', methods=['POST'])
def toggle_account(account):
    creds = load_config()
    status = request.json.get("enabled", True)
    if creds['master']['name'] == account:
        creds['master']['enabled'] = status
    else:
        for child in creds['child_accounts']:
            if child['name'] == account:
                child['enabled'] = status
                break
    save_config(creds)
    return jsonify({"status": "success", "account": account, "enabled": status})

@app.route('/set-multiplier/<account>', methods=['POST'])
def set_multiplier(account):
    creds = load_config()
    multiplier = request.json.get("multiplier", 1.0)
    if creds['master']['name'] == account:
        creds['master']['multiplier'] = multiplier
    else:
        for child in creds['child_accounts']:
            if child['name'] == account:
                child['multiplier'] = multiplier
                break
    save_config(creds)
    return jsonify({"status": "success", "account": account, "multiplier": multiplier})

@app.route('/update-creds/<account>', methods=['POST'])
def update_creds(account):
    creds = load_config()
    data = request.json
    updated = False
    if creds['master']['name'] == account:
        creds['master']['api_key'] = data.get('api_key', '')
        creds['master']['api_secret'] = data.get('api_secret', '')
        creds['master']['access_token'] = data.get('access_token', '')
        updated = True
    else:
        for c in creds['child_accounts']:
            if c['name'] == account:
                c['api_key'] = data.get('api_key', '')
                c['api_secret'] = data.get('api_secret', '')
                c['access_token'] = data.get('access_token', '')
                updated = True
                break
    if updated:
        save_config(creds)
        return jsonify({"status": "success", "message": f"{account} credentials updated"})
    else:
        return jsonify({"status": "error", "message": "Account not found"}), 404

@app.route('/clear-creds/<account>', methods=['POST'])
def clear_creds(account):
    creds = load_config()
    cleared = False
    if creds['master']['name'] == account:
        creds['master']['api_key'] = ''
        creds['master']['api_secret'] = ''
        creds['master']['access_token'] = ''
        cleared = True
    else:
        for c in creds['child_accounts']:
            if c['name'] == account:
                c['api_key'] = ''
                c['api_secret'] = ''
                c['access_token'] = ''
                cleared = True
                break
    if cleared:
        save_config(creds)
        return jsonify({"status": "success", "message": f"{account} credentials cleared"})
    else:
        return jsonify({"status": "error", "message": "Account not found"}), 404
