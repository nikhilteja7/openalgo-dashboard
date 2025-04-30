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

@app.route('/callback/<account>')
def kite_callback(account):
    request_token = request.args.get("request_token")
    if not request_token:
        return "❌ No request_token found"

    creds = load_config()
    selected = creds['master'] if creds['master']['name'] == account else next((c for c in creds['child_accounts'] if c['name'] == account), None)
    if not selected:
        return "❌ Account not found", 404

    kite = KiteConnect(api_key=selected['api_key'])
    try:
        data = kite.generate_session(request_token, api_secret=selected['api_secret'])
        selected['access_token'] = data['access_token']
        if creds['master']['name'] == account:
            creds['master'] = selected
        else:
            creds['child_accounts'] = [c if c['name'] != account else selected for c in creds['child_accounts']]
        save_config(creds)
        return f"✅ Access token saved for {account}"
    except Exception as e:
        return f"❌ Error: {str(e)}"

@app.route('/zerodha-login/<account>')
def zerodha_login(account):
    creds = load_config()
    api_key = creds['master']['api_key'] if account == creds['master']['name'] else next((c['api_key'] for c in creds['child_accounts'] if c['name'] == account), None)
    if not api_key:
        return "❌ Account not found", 404
    kite = KiteConnect(api_key=api_key)
    login_url = kite.login_url().replace("request_token", f"callback/{account}?request_token")
    return redirect(login_url)

@app.route('/chartink-webhook', methods=['POST'])
def chartink_webhook():
    global chartink_status_data
    creds = load_config()
    settings = load_settings()
    data = request.get_json()

    chartink_status_data.update({
        "status": "triggered",
        "time": datetime.datetime.now(timezone('Asia/Kolkata')).strftime("%H:%M:%S"),
        "alert_name": data.get("alert_name", "Unnamed Alert"),
        "stocks": data.get("stocks", "").split(","),
        "prices": data.get("trigger_prices", "").split(",")
    })
    log_trigger_to_file(chartink_status_data["alert_name"], chartink_status_data["stocks"], chartink_status_data["prices"])

    stock = data.get("stock", "UNKNOWN")
    action = data.get("action", "BUY")
    qty = int(data.get("quantity", 1))
    ltp = float(data.get("ltp", 100.0))
    variety = "MIS"

    now = chartink_status_data["time"]
    account_pnl["total_orders"] += 1
    account_pnl["total_pnl"] += qty * ltp * (0.01 if action == "BUY" else -0.01)

    results = []
    if creds['master'].get("enabled", True):
        try:
            kite_master = KiteConnect(api_key=creds['master']['api_key'])
            kite_master.set_access_token(creds['master']['access_token'])
            multiplier = float(creds['master'].get('multiplier', 1.0))
            order_qty = int(qty * multiplier)
            master_order = kite_master.place_order(
                tradingsymbol=stock, exchange="NSE", transaction_type=action,
                quantity=order_qty, order_type="MARKET", product=variety, variety="regular")
            account_pnl["orders"].append({"account": creds['master']['name'], "qty": order_qty, "time": now})
            results.append(f"master ✅ Order {master_order}")
        except Exception as e:
            results.append(f"master ❌ Error: {str(e)}")

    if settings.get('copy_trading', True):
        for child in creds['child_accounts']:
            if not child.get("enabled", True):
                continue
            try:
                kite = KiteConnect(api_key=child['api_key'])
                kite.set_access_token(child['access_token'])
                multiplier = float(child.get('multiplier', 1.0))
                order_qty = int(qty * multiplier)
                order_id = kite.place_order(
                    tradingsymbol=stock, exchange="NSE", transaction_type=action,
                    quantity=order_qty, order_type="MARKET", product=variety, variety="regular")
                account_pnl["orders"].append({"account": child['name'], "qty": order_qty, "time": now})
                results.append(f"{child['name']} ✅ Order {order_id}")
            except Exception as e:
                results.append(f"{child['name']} ❌ Error: {str(e)}")

    socketio.emit('new_order', {"time": now, "stock": stock, "action": action, "qty": qty, "price": ltp, "variety": variety})
    return jsonify({"status": "success", "results": results})

@app.route('/chartink_status')
def get_chartink_status():
    return jsonify(chartink_status_data)

@app.route('/config.yaml')
def get_config():
    return send_file("config.yaml")

@app.route('/settings.yaml')
def get_settings():
    return send_file("settings.yaml")

@app.route('/save-telegram', methods=['POST'])
def save_telegram_route():
    save_telegram(request.json)
    return "✅ Telegram config saved"

@app.route('/make-master/<account>', methods=['POST'])
def make_master(account):
    creds = load_config()
    child = next((c for c in creds['child_accounts'] if c['name'] == account), None)
    if not child:
        return "❌ Child not found", 404
    old_master = creds['master']
    creds['master'] = child
    creds['child_accounts'] = [c for c in creds['child_accounts'] if c['name'] != account] + [old_master]
    save_config(creds)
    return "✅ Master updated"

@app.route('/toggle-copy-trading', methods=['POST'])
def toggle_copy_trading():
    settings = load_settings()
    settings['copy_trading'] = request.json.get("enabled")
    save_settings(settings)
    return jsonify({"status": "success", "copy_trading": settings['copy_trading']})

@app.route('/download-log')
def download_log():
    return send_file(LOG_FILE, as_attachment=True)

@app.route('/live-pnl')
def live_pnl():
    return jsonify(account_pnl)

@socketio.on('manual_order')
def manual_order(data):
    data['ltp'] = 100.0
    data['quantity'] = int(data.get('qty', 1))
    emit('new_order', data, broadcast=True)

@app.route('/health-check')
def health_check():
    return "✅ Server Running", 200

if __name__ == '__main__':
    socketio.run(app, debug=True)
