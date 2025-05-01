from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_socketio import SocketIO
import os, yaml, pyotp
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

def refresh_tokens_from_totp():
    config = load_config()
    updated = False
    all_accounts = [config["master"]] + config["child_accounts"]

    for acc in all_accounts:
        if acc.get("totp_key"):
            kite = KiteConnect(api_key=acc["api_key"])
            try:
                totp = pyotp.TOTP(acc["totp_key"]).now()
                data = kite.generate_session(request_token=None, api_secret=acc["api_secret"], skip_login=True, totp=totp)
                acc["access_token"] = data["access_token"]
                updated = True
            except Exception as e:
                print(f"[ERROR] Login failed for {acc['name']}: {e}")

    if updated:
        save_config(config)
    return {"status": "success" if updated else "error", "message": "Tokens refreshed" if updated else "No updates"}

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
    new_entry = {
        "name": data['name'],
        "api_key": data['api_key'],
        "api_secret": data['api_secret'],
        "access_token": "",
        "totp_key": data.get('totp_key', ''),
        "email": data.get('email', ''),
        "mobile": data.get('mobile', ''),
        "multiplier": 1.0,
        "enabled": True
    }
    if data.get("role") == "master":
        config["master"] = new_entry
    else:
        if any(acc['name'] == data['name'] for acc in config['child_accounts']):
            return jsonify({"status": "error", "message": "Account already exists"}), 400
        config['child_accounts'].append(new_entry)
    save_config(config)
    return jsonify({"status": "success", "message": f"Account {data['name']} added."})

@app.route("/get-accounts-details")
def get_accounts_details():
    config = load_config()
    accounts = []
    all_accounts = [config["master"]] + config["child_accounts"]
    for acc in all_accounts:
        try:
            kite = KiteConnect(api_key=acc["api_key"])
            kite.set_access_token(acc["access_token"])
            margin = kite.margins("equity")["net"]
            pnl = 1000  # Replace with real P&L logic
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

@app.route("/get-accounts-summary")
def get_accounts_summary():
    config = load_config()
    summary = []
    all_accounts = [config["master"]] + config["child_accounts"]
    for acc in all_accounts:
        summary.append({
            "name": acc["name"],
            "opening_balance": 100000,
            "net_pnl": 2000 if acc["name"] == config["master"]["name"] else 1000,
            "total_trades": 10,
            "total_volume": 250,
            "wins": 6,
            "losses": 4,
            "win_rate": 60.0,
            "top_symbol": "INFY"
        })
    return jsonify({"accounts": summary})

@app.route("/get-order-history")
def get_order_history():
    history = [
        {
            "symbol": "INFY",
            "account": "ZCHILD001",
            "timestamp": "2025-05-01 09:30",
            "quantity": 50,
            "avg_price": 1523.50,
            "action": "BUY",
            "order_id": "OID001",
            "status": "COMPLETE",
            "error": "-"
        },
        {
            "symbol": "RELIANCE",
            "account": "ZMASTER123",
            "timestamp": "2025-05-01 10:15",
            "quantity": 100,
            "avg_price": 2740.00,
            "action": "SELL",
            "order_id": "OID002",
            "status": "REJECTED",
            "error": "Margin Error"
        }
    ]
    return jsonify({"orders": history})

@app.route("/refresh-session", methods=["GET", "POST"])
def refresh_session():
    result = refresh_tokens_from_totp()
    return jsonify(result)

# ------------------- ✅ Kite Login Flow -------------------

@app.route("/login-kite/<client_id>")
def login_kite(client_id):
    config = load_config()
    all_accounts = [config["master"]] + config["child_accounts"]
    acc = next((a for a in all_accounts if a["name"] == client_id), None)
    if not acc:
        print(f"[ERROR] Account '{client_id}' not found")
        return "Account not found", 404

    print("🔑 Found account, redirecting to Kite login.")
    kite = KiteConnect(api_key=acc["api_key"])
    login_url = kite.login_url()
    session["client_id"] = client_id
    return redirect(login_url)

@app.route("/kite/callback")
def kite_callback():
    try:
        request_token = request.args.get("request_token")
        client_id = session.get("client_id")

        print("✅ Request token:", request_token)
        print("✅ Client ID from session:", client_id)

        if not request_token or not client_id:
            return "Invalid session or missing request token", 400

        config = load_config()
        all_accounts = [config["master"]] + config["child_accounts"]
        acc = next((a for a in all_accounts if a["name"] == client_id), None)

        if not acc:
            print(f"❌ Account {client_id} not found in config.yaml")
            return "Account not found", 404

        print("🔑 Using API Key:", acc["api_key"])
        kite = KiteConnect(api_key=acc["api_key"])
        data = kite.generate_session(request_token, acc["api_secret"])

        acc["access_token"] = data["access_token"]
        save_config(config)

        print("✅ Access token saved successfully.")
        return redirect("/dashboard")

    except Exception as e:
        print("[🔥 ERROR in /kite/callback]:", str(e))
        return "Internal Server Error during callback", 500

# ------------------- End Kite Login Flow -------------------

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
