from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_socketio import SocketIO
import os
import yaml
from kiteconnect import KiteConnect
from datetime import datetime
from pytz import timezone

app = Flask(__name__)
app.secret_key = os.getenv("APP_KEY", "supersecretkey")
socketio = SocketIO(app)

yaml_path = "config.yaml"

def load_config():
    with open(yaml_path, "r") as f:
        return yaml.safe_load(f)

def save_config(config):
    with open(yaml_path, "w") as f:
        yaml.dump(config, f)

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

@app.route("/dashboard")
def dashboard():
    if not session.get("logged_in"):
        return redirect(url_for("login"))
    return render_template("dashboard.html")

@app.route("/add-account", methods=["POST"])
def add_account():
    data = request.json
    config = load_config()
    if any(acc['name'] == data['name'] for acc in config['child_accounts']):
        return jsonify({"status": "error", "message": "Account already exists"}), 400
    config['child_accounts'].append({
        "name": data['name'],
        "api_key": data['api_key'],
        "api_secret": data['api_secret'],
        "access_token": "",
        "totp_key": data.get('totp_key', ''),
        "email": data.get('email', ''),
        "mobile": data.get('mobile', ''),
        "multiplier": 1.0,
        "enabled": True
    })
    save_config(config)
    return jsonify({"status": "success", "message": f"Account {data['name']} added."})

@app.route("/get-accounts-details")
def get_accounts_details():
    config = load_config()
    accounts = []
    for acc in [config["master"]] + config["child_accounts"]:
        try:
            kite = KiteConnect(api_key=acc["api_key"])
            kite.set_access_token(acc["access_token"])
            margin = kite.margins("equity")["net"]
            pnl = 1000  # placeholder for PnL
            accounts.append({
                "name": acc["name"],
                "status": True,
                "balance": margin,
                "pnl": pnl,
                "autologin": acc.get("enabled", False),
                "is_master": acc["name"] == config["master"]["name"]
            })
        except:
            accounts.append({
                "name": acc["name"],
                "status": False,
                "balance": 0,
                "pnl": 0,
                "autologin": acc.get("enabled", False),
                "is_master": acc["name"] == config["master"]["name"]
            })
    return jsonify({"accounts": accounts})

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
