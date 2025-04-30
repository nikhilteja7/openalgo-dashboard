from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
from flask_socketio import SocketIO, emit
import os
import yaml
import datetime
from pytz import timezone
from kiteconnect import KiteConnect
import csv, smtplib, requests
from email.message import EmailMessage
from apscheduler.schedulers.background import BackgroundScheduler

yaml_path = "config.yaml"

app = Flask(__name__)
app.secret_key = os.getenv("APP_KEY", "supersecretkey")
socketio = SocketIO(app)

USERNAME = os.getenv("LOGIN_USER", "admin")
PASSWORD = os.getenv("LOGIN_PASS", "secret123")

LOG_FILE = "trigger_log.csv"
chartink_status_data = {"status": "waiting", "time": None, "alert_name": None, "stocks": [], "prices": []}
account_pnl = {"total_orders": 0, "total_pnl": 0.0, "orders": []}


# -------------------- Utilities --------------------
def load_config():
    with open(yaml_path, "r") as f:
        return yaml.safe_load(f)

def save_config(config):
    with open(yaml_path, "w") as f:
        yaml.dump(config, f)

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


# -------------------- Scheduled Email Job --------------------
scheduler = BackgroundScheduler()
scheduler.add_job(send_log_email, 'cron', hour=18, minute=0)
scheduler.start()


# -------------------- Routes --------------------

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


@app.route('/login/<broker>')
def login_broker(broker):
    if not session.get('logged_in'):
        return jsonify({"message": "Unauthorized"}), 401

    account_name = request.args.get("account", "master")
    creds = load_config()

    if broker == "zerodha":
        acc = creds['master'] if account_name == "master" else next((c for c in creds['child_accounts'] if c['name'] == account_name), None)
        if not acc:
            return jsonify({"message": f"Account '{account_name}' not found."}), 404
        kite = KiteConnect(api_key=acc['api_key'])
        return jsonify({"message": "Redirecting to Zerodha login...", "url": kite.login_url()})

    return jsonify({"message": f"Broker '{broker}' not supported"}), 400


@app.route('/login/zerodha/callback')
def zerodha_callback():
    request_token = request.args.get("request_token")
    creds = load_config()
    try:
        matched_account = None
        for acc in [creds['master']] + creds['child_accounts']:
            kite = KiteConnect(api_key=acc['api_key'])
            try:
                data = kite.generate_session(request_token, api_secret=acc['api_secret'])
                acc['access_token'] = data["access_token"]
                matched_account = acc['name']
                save_config(creds)
                break
            except:
                continue
        session['logged_in'] = True
        if matched_account:
            return redirect(url_for('dashboard') + f"?login=success&account={matched_account}")
        else:
            return "Login failed for all accounts"
    except Exception as e:
        return f"❌ Zerodha login failed: {str(e)}"


@app.route('/get-accounts')
def get_accounts():
    creds = load_config()
    return jsonify({"child_accounts": [c['name'] for c in creds['child_accounts']]})


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
    target = creds['master'] if creds['master']['name'] == account else next((c for c in creds['child_accounts'] if c['name'] == account), None)
    if target:
        target['api_key'] = data.get('api_key', '')
        target['api_secret'] = data.get('api_secret', '')
        target['access_token'] = data.get('access_token', '')
        save_config(creds)
        return jsonify({"status": "success", "message": f"{account} credentials updated"})
    return jsonify({"status": "error", "message": "Account not found"}), 404


@app.route('/clear-creds/<account>', methods=['POST'])
def clear_creds(account):
    creds = load_config()
    target = creds['master'] if creds['master']['name'] == account else next((c for c in creds['child_accounts'] if c['name'] == account), None)
    if target:
        target['api_key'] = ''
        target['api_secret'] = ''
        target['access_token'] = ''
        save_config(creds)
        return jsonify({"status": "success", "message": f"{account} credentials cleared"})
    return jsonify({"status": "error", "message": "Account not found"}), 404


@app.route('/get-portfolio-balance')
def get_portfolio_balance():
    creds = load_config()
    try:
        kite = KiteConnect(api_key=creds['master']['api_key'])
        kite.set_access_token(creds['master']['access_token'])
        margin = kite.margins(segment="equity")
        return jsonify({"balance": round(margin['net'], 2)})
    except:
        return jsonify({"balance": "Error"}), 500


@app.route('/get-portfolio-summary')
def get_portfolio_summary():
    account_name = request.args.get("account", "master")
    creds = load_config()
    try:
        acc = creds['master'] if account_name == "master" else next((c for c in creds['child_accounts'] if c['name'] == account_name), None)
        if not acc:
            return jsonify({"balance": 0, "holdings_value": 0, "total_pnl": 0}), 404
        kite = KiteConnect(api_key=acc['api_key'])
        kite.set_access_token(acc['access_token'])
        balance = round(kite.margins(segment="equity")["net"], 2)
        holdings = kite.holdings()
        holdings_value = round(sum(h["last_price"] * h["quantity"] for h in holdings), 2)
        total_pnl = round(sum(h["pnl"] for h in holdings), 2)
        return jsonify({
            "balance": balance,
            "holdings_value": holdings_value,
            "total_pnl": total_pnl
        })
    except:
        return jsonify({"balance": 0, "holdings_value": 0, "total_pnl": 0}), 500


@app.route('/health-check')
def health_check():
    return "✅ OK", 200


# -------------------- Start App --------------------
if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
