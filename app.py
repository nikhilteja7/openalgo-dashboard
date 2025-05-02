from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
from flask_socketio import SocketIO
import os, yaml, pyotp, csv
from kiteconnect import KiteConnect
from datetime import datetime
from pytz import timezone

app = Flask(__name__)
app.secret_key = os.getenv("APP_KEY", "supersecretkey")
socketio = SocketIO(app, async_mode='eventlet')

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
                if acc.get("opening_balance", 0) == 0:
                    acc["opening_balance"] = kite.margins("equity")["net"]
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
@app.route("/kite/login/<client_id>")
def kite_login(client_id):
    # Generate the login URL with redirect_params to pass client_id
    login_url = kite.login_url()
    # Append client_id as a query parameter
    login_url_with_client = f"{login_url}&redirect_params=client_id={client_id}"
    return redirect(login_url_with_client)
@app.route("/kite/callback")
def kite_callback():
    request_token = request.args.get("request_token")
    client_id = request.args.get("client_id") or "UNKNOWN"

    if not request_token:
        return "❌ Missing request token", 400

    config = load_config()
    kite = KiteConnect(api_key=config["master"]["api_key"])
    try:
        data = kite.generate_session(request_token, api_secret=config["master"]["api_secret"])
        config["master"]["access_token"] = data["access_token"]
        config["master"]["last_login"] = datetime.now(timezone("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S")
        config["master"]["opening_balance"] = kite.margins("equity")["net"]
        save_config(config)
        return f"✅ Login successful for {client_id}. You can close this window."
    except Exception as e:
        return f"❌ Login failed: {str(e)}", 500

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
        "enabled": True,
        "opening_balance": 0.0
    }
    if data.get("role") == "master":
        config["master"] = new_entry
    else:
        if any(acc['name'] == data['name'] for acc in config['child_accounts']):
            return jsonify({"status": "error", "message": "Account already exists"}), 400
        config['child_accounts'].append(new_entry)
    save_config(config)
    return jsonify({"status": "success", "message": f"Account {data['name']} added."})

@app.route("/edit-account", methods=["POST"])
def edit_account():
    data = request.json
    client_id = data["client_id"]
    config = load_config()
    all_accounts = [config["master"]] + config["child_accounts"]

    for acc in all_accounts:
        if acc["name"] == client_id:
            acc.update(data)
            break

    save_config(config)
    return jsonify({"status": "success", "message": f"Account {client_id} updated."})

@app.route("/toggle-autologin", methods=["POST"])
def toggle_autologin():
    data = request.json
    client_id = data["client_id"]
    autologin = data["autologin"]

    config = load_config()
    accounts = [config["master"]] + config["child_accounts"]
    for acc in accounts:
        if acc["name"] == client_id:
            acc["enabled"] = autologin
            break

    save_config(config)
    return jsonify({"status": "success"})

@app.route("/delete-account", methods=["POST"])
def delete_account():
    data = request.json
    client_id = data["client_id"]

    config = load_config()
    if config["master"].get("name") == client_id:
        config["master"] = {}
    else:
        config["child_accounts"] = [a for a in config["child_accounts"] if a["name"] != client_id]

    save_config(config)
    return jsonify({"status": "success", "message": f"Account {client_id} deleted."})

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
            today_pnl = margin - acc.get("opening_balance", 0)
            acc["balance"] = margin
            accounts.append({
                "name": acc["name"],
                "status": True,
                "balance": margin,
                "pnl": today_pnl,
                "opening_balance": acc.get("opening_balance", 0),
                "autologin": acc.get("enabled", False),
                "is_master": acc["name"] == config["master"].get("name")
            })
        except Exception as e:
            accounts.append({
                "name": acc["name"],
                "status": False,
                "balance": 0,
                "pnl": 0,
                "opening_balance": acc.get("opening_balance", 0),
                "autologin": acc.get("enabled", False),
                "is_master": acc["name"] == config["master"].get("name")
            })
    return jsonify({"accounts": accounts})

@app.route("/refresh-session", methods=["POST"])
def refresh_session():
    data = request.json
    client_id = data["client_id"]
    config = load_config()

    accounts = [config["master"]] + config["child_accounts"]
    for acc in accounts:
        if acc["name"] == client_id:
            try:
                kite = KiteConnect(api_key=acc["api_key"])
                if acc.get("totp_key"):
                    totp = pyotp.TOTP(acc["totp_key"]).now()
                    data = kite.generate_session(None, acc["api_secret"], skip_login=True, totp=totp)
                    acc["access_token"] = data["access_token"]
                    acc["opening_balance"] = kite.margins("equity")["net"]
                    save_config(config)
                    return jsonify({"status": "success", "message": f"{client_id} reconnected."})
                else:
                    return jsonify({"status": "error", "message": "TOTP key missing."}), 400
            except Exception as e:
                return jsonify({"status": "error", "message": str(e)}), 500

    return jsonify({"status": "error", "message": "Account not found."}), 404

@app.route("/set-multiplier", methods=["POST"])
def set_multiplier():
    data = request.json
    client_id = data["client_id"]
    multiplier = data["multiplier"]
    config = load_config()

    for acc in config["child_accounts"]:
        if acc["name"] == client_id:
            acc["multiplier"] = multiplier
            save_config(config)
            return jsonify({"status": "success"})

    return jsonify({"status": "error", "message": "Child account not found."}), 404

@app.route("/toggle-copy-trading", methods=["POST"])
def toggle_copy_trading():
    data = request.json
    config = load_config()
    config["features"]["copy_trading"] = data["enabled"]
    save_config(config)
    return jsonify({"status": "success"})

@app.route("/toggle-child-copy", methods=["POST"])
def toggle_child_copy():
    data = request.json
    client_id = data["client_id"]
    enabled = data["enabled"]
    config = load_config()

    for acc in config["child_accounts"]:
        if acc["name"] == client_id:
            acc["enabled"] = enabled
            save_config(config)
            return jsonify({"status": "success"})

    return jsonify({"status": "error", "message": "Child account not found."}), 404

@app.route("/make-master/<client_id>", methods=["POST"])
def make_master(client_id):
    config = load_config()
    all_masters = [config["master"]] + [acc for acc in config["child_accounts"] if acc.get("role") == "master"]

    new_master = next((acc for acc in all_masters if acc["name"] == client_id), None)
    if not new_master:
        return jsonify({"status": "error", "message": "Account not found."}), 404

    config["child_accounts"] = [acc for acc in config["child_accounts"] if acc["name"] != client_id]

    if config.get("master"):
        current_master = config["master"]
        current_master["role"] = "master"
        config["child_accounts"].append(current_master)

    new_master["role"] = "master"
    config["master"] = new_master
    save_config(config)

    return jsonify({"status": "success", "message": f"{client_id} is now the active master"})

@app.route("/get-accounts-summary")
def get_accounts_summary():
    config = load_config()
    summary = []
    for acc in [config["master"]] + config["child_accounts"]:
        orders = acc.get("orders", [])
        wins = sum(1 for o in orders if o.get("pnl", 0) > 0)
        losses = sum(1 for o in orders if o.get("pnl", 0) < 0)
        win_rate = round(100 * wins / max(len(orders), 1), 2)
        summary.append({
            "name": acc["name"],
            "live_balance": acc.get("balance", 0),
            "net_pnl": round(acc.get("balance", 0) - acc.get("opening_balance", 0), 2),
            "total_trades": len(orders),
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "top_symbol": orders[0]["symbol"] if orders else "-"
        })
    return jsonify({"accounts": summary})

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
    config = load_config()
    filename = "trade_summary.csv"
    with open(filename, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Client ID", "Live Balance", "Net P&L", "Total Trades", "Wins", "Losses", "Win Rate %", "Top Symbol"])
        for acc in [config["master"]] + config["child_accounts"]:
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

if __name__ == '__main__':
    socketio.run(app, debug=True)
