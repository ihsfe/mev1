import os
import time
from web3 import Web3
from dotenv import load_dotenv
from flashbots import flashbot
from web3.middleware import geth_poa_middleware

# ===== LOAD ENV VARS =====
load_dotenv()  # Load from .env file

# ===== CONFIGURATION =====
# Wallets
GAS_WALLET_PRIVATE_KEY = os.getenv("GAS_WALLET_PRIVATE_KEY")  # Signs TXs (keep secret!)
PROFIT_WALLET = os.getenv("PROFIT_WALLET")                   # Receives profits (e.g., MetaMask)

# Arbitrage Parameters
ARBITRAGE_PAIRS = ["ETH-USDT", "WBTC-ETH"]
MIN_PROFIT_ETH = float(os.getenv("MIN_PROFIT_ETH", 0.05))    # Min profit threshold
MAX_SLIPPAGE = float(os.getenv("MAX_SLIPPAGE", 0.5))         # Max slippage (0.5%)

# Network
INFURA_URL = os.getenv("INFURA_URL")                         # Mainnet RPC
EIGENPHI_API_KEY = os.getenv("EIGENPHI_API_KEY")             # Arbitrage data

# ===== INIT WEB3 & FLASHBOTS =====
w3 = Web3(Web3.HTTPProvider(INFURA_URL))
w3.middleware_onion.inject(geth_poa_middleware, layer=0)
flashbot(w3, GAS_WALLET_PRIVATE_KEY)  # Enable Flashbots

# ===== CORE FUNCTIONS =====
def fetch_arbitrage_opportunities():
    """Fetch live arbitrage opportunities from EigenPhi."""
    import requests
    url = "https://api.eigenphi.io/v1/arbitrage"
    headers = {"Authorization": f"Bearer {EIGENPHI_API_KEY}"}
    params = {"pairs": ",".join(ARBITRAGE_PAIRS)}
    response = requests.get(url, headers=headers, params=params)
    return response.json().get("opportunities", [])

def execute_arbitrage(opportunity):
    """Execute arbitrage trade and send profits to PROFIT_WALLET."""
    # 1. Take flash loan
    flashloan_amount = w3.toWei(opportunity["optimal_amount"], 'ether')
    
    # 2. Build TX bundle (Flashbots)
    signed_tx = {
        "to": opportunity["contract_address"],
        "value": flashloan_amount,
        "gas": 500000,
        "gasPrice": w3.toWei("50", "gwei"),
        "nonce": w3.eth.get_transaction_count(w3.eth.account.from_key(GAS_WALLET_PRIVATE_KEY)),
        "data": encode_arbitrage_call(opportunity),
    }
    
    # 3. Send TX via Flashbots
    tx_hash = w3.eth.send_transaction(signed_tx)
    
    # 4. Send profits to PROFIT_WALLET
    profit = w3.fromWei(opportunity["profit_eth"], 'ether')
    if profit > 0:
        w3.eth.send_transaction({
            "to": PROFIT_WALLET,
            "value": w3.toWei(profit, 'ether'),
            "gas": 21000,
            "gasPrice": w3.toWei("50", "gwei"),
            "nonce": w3.eth.get_transaction_count(w3.eth.account.from_key(GAS_WALLET_PRIVATE_KEY)) + 1,
        })
    
    return tx_hash

# ===== MAIN LOOP =====
if __name__ == "__main__":
    print(f"🚀 Starting MEV Arbitrage Bot | Gas Wallet: {w3.eth.account.from_key(GAS_WALLET_PRIVATE_KEY).address}")
    print(f"💰 Profit Wallet: {PROFIT_WALLET}")
    
    while True:
        try:
            opportunities = fetch_arbitrage_opportunities()
            for opp in opportunities:
                if opp["profit_eth"] >= MIN_PROFIT_ETH and opp["slippage"] <= MAX_SLIPPAGE:
                    print(f"🔥 Opportunity: {opp['pair']} | Profit: {opp['profit_eth']} ETH")
                    tx_hash = execute_arbitrage(opp)
                    print(f"✅ Success! TX Hash: {tx_hash.hex()}")
                    time.sleep(5)  # Rate limit
        except Exception as e:
            print(f"❌ Error: {e}")
            time.sleep(60)  # Cool down on failure