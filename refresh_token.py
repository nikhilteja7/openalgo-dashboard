# refresh_token.py
import yaml
from kiteconnect import KiteConnect

with open("config.yaml", "r") as f:
    creds = yaml.safe_load(f)

accounts = [creds['master']] + creds['child_accounts']

for acc in accounts:
    kite = KiteConnect(api_key=acc['api_key'])
    print(f"🔐 Login URL for {acc['name']}: {kite.login_url()}")
