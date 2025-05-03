from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
from flask_socketio import SocketIO
from pymongo import MongoClient
import os, pyotp, csv
from kiteconnect import KiteConnect
from datetime import datetime
from pytz import timezone

app = Flask(__name__)
app.secret_key = os.getenv("APP_KEY", "supersecretkey")
socketio = SocketIO(app, async_mode='eventlet')

mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/openalgo")
client = MongoClient(mongo_uri)

db = client['openalgo']
accounts_col = db['accounts']
settings_col = db['settings']

# Helper functions
def get_all_accounts():
    return list(accounts_col.find())

def get_account(name):
    return accounts_col.find_one({"name": name})

def save_account(account):
    accounts_col.replace_one({"name": account["name"]}, account, upsert=True)

def delete_account(name):
    accounts_col.delete_one({"name": name})

def get_setting(key):
    doc = settings_col.find_one({"_id": key})
    return doc["value"] if doc else None

def set_setting(key, value):
    settings_col.update_one({"_id": key}, {"$set": {"value": value}}, upsert=True)

@app.route("/kite/login/<client_id>")
def kite_login(client_id):
    acc = get_account(client_id)
    if not acc:
        return "❌ Account not found", 404
    kite = KiteConnect(api_key=acc["api_key"])
    redirect_uri = f"https://openalgo-dashboard.onrender.com/kite/callback?client_id={client_id}"
    login_url = kite.login_url().replace("redirect_uri=https://127.0.0.1", f"redirect_uri={redirect_uri}")
    return redirect(login_url)

@app.route("/kite/callback")
def kite_callback():
    request_token = request.args.get("request_token")
    client_id = request.args.get("client_id")
    if not request_token or not client_id:
        return "❌ Missing request token or client ID", 400
    acc = get_account(client_id)
    if not acc:
        return "❌ Account not found", 404
    kite = KiteConnect(api_key=acc["api_key"])
    try:
        data = kite.generate_session(request_token, api_secret=acc["api_secret"])
        acc["access_token"] = data["access_token"]
        acc["last_login"] = datetime.now(timezone("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S")
        acc["opening_balance"] = kite.margins("equity")["net"]
        save_account(acc)
        session['logged_in'] = True
        return redirect(url_for('dashboard') + "?login=success")
    except Exception as e:
        return f"❌ Login failed: {str(e)}", 500

@app.route("/chartink-log")
def chartink_log():
    try:
        with open("trigger_log.csv", "r") as f:
            lines = f.readlines()[1:]
        log = []
        for line in lines[-100:]:
            timestamp, symbol, qty, action = line.strip().split(",")[:4]
            log.append({
                "timestamp": timestamp,
                "symbol": symbol,
                "qty": qty,
                "action": action
            })
        return jsonify({"log": log[::-1]})
    except Exception as e:
        return jsonify({"log": [], "error": str(e)})

@app.route("/download-summary")
def download_summary():
    filename = "trade_summary.csv"
    with open(filename, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Client ID", "Live Balance", "Net P&L", "Total Trades", "Wins", "Losses", "Win Rate %", "Top Symbol"])
        for acc in get_all_accounts():
            orders = acc.get("orders", [])
            wins = sum(1 for o in orders if o.get("pnl", 0) > 0)
            losses = sum(1 for o in orders if o.get("pnl", 0) < 0)
            win_rate = round(100 * wins / max(len(orders), 1), 2)
            writer.writerow([
                acc["name"],
                round(acc.get("balance", 0), 2),
                round(acc.get("balance", 0) - acc.get("opening_balance", 0), 2),
                len(orders),
                wins,
                losses,
                win_rate,
                orders[0]["symbol"] if orders else "-"
            ])
    return send_file(filename, as_attachment=True)

@app.route("/dashboard")
def dashboard():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    return render_template("dashboard.html")

@app.route("/")
def home():
    return redirect(url_for('login'))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form['username'] == os.getenv("LOGIN_USER", "admin") and request.form['password'] == os.getenv("LOGIN_PASS", "secret123"):
            session['logged_in'] = True
            return redirect(url_for("dashboard"))
        return "Invalid credentials", 403
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))
