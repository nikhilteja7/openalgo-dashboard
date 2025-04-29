from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_socketio import SocketIO, emit
import datetime
from pytz import timezone
import os
from kiteconnect import KiteConnect
import yaml

# Load config.yaml to get child accounts
with open("config.yaml", "r") as f:
    creds = yaml.safe_load(f)

# === Load and Save Settings ===
def load_settings():
    with open("settings.yaml", "r") as f:
        return yaml.safe_load(f)

def save_settings(settings):
    with open("settings.yaml", "w") as f:
        yaml.dump(settings, f)

app = Flask(__name__)
app.secret_key = os.getenv("APP_KEY", "supersecretkey")
socketio = SocketIO(app)

USERNAME = os.getenv("LOGIN_USER", "admin")
PASSWORD = os.getenv("LOGIN_PASS", "secret123")

live_trades = []
total_orders = 0
total_pnl = 0.0

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
    return render_template('dashboard.html')

@app.route('/chartink-webhook', methods=['POST'])
def chartink_webhook():
    global total_orders, total_pnl
    settings = load_settings()
    data = request.get_json()
    stock = data.get("stock", "UNKNOWN")
    action = data.get("action", "BUY")
    qty = int(data.get("quantity", 1))
    ltp = float(data.get("ltp", 100.0))
    variety = "MIS"

    now = datetime.datetime.now(timezone('Asia/Kolkata')).strftime("%H:%M:%S")
    total_orders += 1
    pnl = qty * (ltp * 0.02 if action.upper() == "BUY" else -ltp * 0.01)
    total_pnl += pnl

    results = []

    # --- Master Order ---
    try:
        master = creds['master']
        kite_master = KiteConnect(api_key=master['api_key'])
        kite_master.set_access_token(master['access_token'])

        master_order = kite_master.place_order(
            tradingsymbol=stock,
            exchange="NSE",
            transaction_type=action.upper(),
            quantity=qty,
            order_type="MARKET",
            product=variety,
            variety="regular"
        )
        results.append(f"master ✅ Order {master_order}")
    except Exception as e:
        results.append(f"master ❌ Error: {str(e)}")

    # --- Copy Trading Section ---
    if settings.get("copy_trading", True):
        for child in creds['child_accounts']:
            try:
                kite = KiteConnect(api_key=child['api_key'])
                kite.set_access_token(child['access_token'])

                order_id = kite.place_order(
                    tradingsymbol=stock,
                    exchange="NSE",
                    transaction_type=action.upper(),
                    quantity=qty,
                    order_type="MARKET",
                    product=variety,
                    variety="regular"
                )
                results.append(f"{child['name']} ✅ Order {order_id}")
            except Exception as e:
                results.append(f"{child['name']} ❌ Error: {str(e)}")

    socketio.emit('new_order', {
        "time": now,
        "stock": stock,
        "action": action,
        "qty": qty,
        "price": ltp,
        "variety": variety
    })

    socketio.emit('update_pnl', {
        "pnl": total_pnl
    })

    return jsonify({"status": "success", "results": results}), 200

@app.route('/toggle-copy-trading', methods=['POST'])
def toggle_copy_trading():
    settings = load_settings()
    status = request.json.get("enabled")
    settings['copy_trading'] = status
    save_settings(settings)
    return jsonify({"status": "success", "copy_trading": status})

@app.route('/make-master/<account>', methods=['POST'])
def make_master(account):
    with open("config.yaml", "r") as f:
        creds = yaml.safe_load(f)

    child_to_promote = None
    for child in creds['child_accounts']:
        if child['name'] == account:
            child_to_promote = child
            break

    if not child_to_promote:
        return "❌ Child not found", 404

    old_master = creds['master']
    creds['master'] = child_to_promote
    creds['child_accounts'] = [c for c in creds['child_accounts'] if c['name'] != account]
    creds['child_accounts'].append(old_master)

    with open("config.yaml", "w") as f:
        yaml.dump(creds, f)

    return "✅ Switched master", 200

@app.route('/get-children')
def get_children():
    return jsonify({
        "child_accounts": creds['child_accounts']
    })

@socketio.on('manual_order')
def manual_order(data):
    data['ltp'] = 100.0  # Dummy price
    data['quantity'] = int(data.get('qty', 1))
    emit('new_order', data, broadcast=True)

if __name__ == '__main__':
    socketio.run(app, debug=True)
