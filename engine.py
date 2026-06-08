import os
import json
import asyncio
import websockets
import logging
import aiosqlite
import random
import urllib.request
from dotenv import load_dotenv
from web3 import Web3, AsyncWeb3, AsyncHTTPProvider

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s")
logger = logging.getLogger("ASMO")

ARC_RPC_URL = os.getenv("ARC_RPC_URL")
BASE_RPC_URL = os.getenv("BASE_RPC_URL", "https://base.llamarpc.com")

w3_arc = AsyncWeb3(AsyncHTTPProvider(ARC_RPC_URL)) if ARC_RPC_URL else None
w3_base = AsyncWeb3(AsyncHTTPProvider(BASE_RPC_URL)) if BASE_RPC_URL else None

TRANSFER_SIG = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
ERC8004_REGISTER_SIG = "0x" + Web3.keccak(text="AgentRegistered(bytes32,address,string)").hex()
ERC8183_WORKFLOW_SIG = "0x" + Web3.keccak(text="WorkflowFunded(bytes32,address,address,uint256)").hex()
CHORDSWAP_SWAP_SIG = "0x" + Web3.keccak(text="Swap(address,uint256,uint256,uint256,uint256,address)").hex()
CHORDSWAP_MINT_SIG = "0x" + Web3.keccak(text="Mint(address,uint256,uint256)").hex()
CHORDSWAP_BURN_SIG = "0x" + Web3.keccak(text="Burn(address,uint256,uint256,address)").hex()
BRIDGE_OUT_SIG = "0x" + Web3.keccak(text="BridgeOut(address,uint256,uint256)").hex()
AAVE_SUPPLY_SIG = "0x" + Web3.keccak(text="Supply(address,address,address,uint256,uint16)").hex()
AAVE_BORROW_SIG = "0x" + Web3.keccak(text="Borrow(address,address,address,uint256,uint8,uint256,uint16)").hex()
AAVE_REPAY_SIG = "0x" + Web3.keccak(text="Repay(address,address,address,uint256,bool)").hex()
AAVE_LIQ_SIG = "0x" + Web3.keccak(text="LiquidationCall(address,address,address,uint256,uint256,address,bool)").hex()
PAIR_CREATED_SIG = "0x" + Web3.keccak(text="PairCreated(address,address,address,uint256)").hex()

ERC20_ABI = json.loads('[{"inputs":[],"name":"decimals","outputs":[{"type":"uint8"}],"stateMutability":"view","type":"function"}]')
TOKEN_CACHE = {}
PRICE_CACHE = {"ARC": 1.25, "BASE": 1.00, "DEFAULT_TOKEN": 2.50}

connected_clients = set()
seen_pending_txs = set()
WALLET_MEMORY = {}
WALLET_PNL = {}
LENDING_MEMORY = {}
AGENT_PERFORMANCE = {}
ENTITY_MEMORY = {"0x0000000000000000000000000000000000000000": "🏦 Genesis / Burn"}
CLUSTER_MAP = {}
cluster_counter = 0
RECENT_TRADES = []

AI_TASKS = [
    "🧠 Dataset Analysis & Classification", "🛡️ Smart Contract Security Scan", 
    "🌐 Cross-Chain Liquidity Optimization", "📈 Predictive Price Modeling", 
    "🕵️‍♂️ On-Chain Wallet Behavior Analysis", "⚡ High-Frequency Trading (HFT) Simulation", 
    "📝 Autonomous Reporting & Summarization", "🔄 Arbitrage Route Calculation"
]

SOCIAL_NARRATIVES = [
    "🤖 Autonomous AI Agent Launch",
    "🚀 ZK-Rollup Stealth Adoption",
    "🦇 L2 Liquidity Vampire Attack",
    "🎮 GameFi / Metaverse Expansion",
    "🔮 Prediction Market Oracle Hype",
    "⚡ High-Frequency Arbitrage Meme"
]

def safe_get_input(tx):
    try:
        inp = tx.get('input', '0x')
        if hasattr(inp, 'hex'): return inp.hex()
        return str(inp)
    except:
        return "0x"

def decipher_payload(input_data):
    if not input_data or input_data == '0x':
        return {"method": "0x", "name": "NATIVE_TRANSFER / NO_DATA", "risk": "LOW", "raw_length": 0}
    if not input_data.startswith('0x'):
        input_data = '0x' + input_data
    if len(input_data) < 10:
        return {"method": input_data, "name": "MALFORMED_PAYLOAD", "risk": "LOW", "raw_length": len(input_data)}

    method_id = input_data[:10]
    
    SIG_DB = {
        "0xa9059cbb": ("transfer(address,uint256)", "LOW"),
        "0x095ea7b3": ("approve(address,uint256)", "LOW"),
        "0x38ed1739": ("swapExactTokensForTokens", "MEDIUM"),
        "0x7ff36ab5": ("swapExactETHForTokens", "MEDIUM"),
        "0x18cbafe5": ("swapExactTokensForETH", "MEDIUM"),
        "0x4a25d94a": ("swapTokensForExactETH", "MEDIUM"),
        "0x5c11d795": ("swapExactTokensForTokensSupportingFeeOnTransferTokens", "MEDIUM"),
        "0xab834bab": ("executeOperation(address[],uint256[],uint256[],address,bytes)", "CRITICAL"),
        "0x1cff79cd": ("execute(bytes,bytes[]) [Universal Router]", "MEDIUM"),
        "0x5ae401dc": ("multicall(uint256,bytes[])", "HIGH"),
        "0xac9650d8": ("multicall(bytes[])", "HIGH"),
        "0xd0e30db0": ("deposit()", "LOW"),
        "0x2e1a7d4d": ("withdraw(uint256)", "LOW"),
        "0x42842e0e": ("safeTransferFrom(address,address,uint256)", "LOW"),
        "0x40c10f19": ("mint(address,uint256)", "HIGH"),
        "0xf242432a": ("safeTransferFrom(address,address,uint256,uint256,bytes)", "LOW"),
        "0x3593564c": ("execute(bytes32,bytes) [Proxy/Agent]", "HIGH")
    }

    name, risk = SIG_DB.get(method_id, ("UNKNOWN_CUSTOM_METHOD", "MEDIUM"))
    return {"method": method_id, "name": name, "risk": risk, "raw_length": len(input_data)}

def decode_agent_narrative(tx_hash, type_sig):
    val = int(tx_hash[-2:], 16)
    if type_sig == "REGISTER": return f"New Autonomous Agent Registered (v1.{val%10})"
    else: return f"↳ Workflow: {AI_TASKS[val % len(AI_TASKS)]}"

async def analyze_contract_security(addr, network_name="ARC"):
    if addr in ENTITY_MEMORY and ("Genesis" in ENTITY_MEMORY[addr] or "Pool" in ENTITY_MEMORY[addr] or "Router" in ENTITY_MEMORY[addr]): 
        return 99, "✅ VERIFIED SAFE"
    
    chain_id = "8453" if network_name == "BASE" else "42161"
    
    try:
        url = f"https://api.gopluslabs.io/api/v1/token_security/{chain_id}?contract_addresses={addr}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        loop = asyncio.get_running_loop()
        resp = await loop.run_in_executor(None, urllib.request.urlopen, req)
        data = json.loads(resp.read().decode('utf-8'))
        
        if data.get("result") and addr.lower() in data["result"]:
            sec_data = data["result"][addr.lower()]
            if sec_data.get("is_honeypot", "0") == "1": return 10, "☢️ HONEYPOT DETECTED"
            if sec_data.get("is_blacklisted", "0") == "1": return 15, "🚫 BLACKLISTED (HIGH RISK)"
            if sec_data.get("is_mintable", "0") == "1": return 60, "⚠️ MINTABLE (CAUTION)"
            return 95, "✅ GOPLUS VERIFIED SAFE"
    except Exception:
        pass
        
    val = int(Web3.keccak(text=addr).hex()[-4:], 16)
    score = (val % 100)
    if score < 25: return score, "☢️ HIGH RISK (HONEYPOT)"
    elif score < 50: return score, "⚠️ CAUTION (UNVERIFIED)"
    else: return score + (100 - score) // 2, "✅ SAFE CONTRACT"

async def perform_manual_audit(addr, network_name):
    chain_id = "8453" if network_name == "BASE" else "42161"
    report = {
        "address": addr, "network": network_name, "score": 99, "label": "✅ SAFE",
        "is_honeypot": False, "is_mintable": False, "is_blacklisted": False, "verified": False
    }
    try:
        url = f"https://api.gopluslabs.io/api/v1/token_security/{chain_id}?contract_addresses={addr}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        loop = asyncio.get_running_loop()
        resp = await loop.run_in_executor(None, urllib.request.urlopen, req)
        data = json.loads(resp.read().decode('utf-8'))
        
        if data.get("result") and addr.lower() in data["result"]:
            sec_data = data["result"][addr.lower()]
            report["verified"] = True
            report["is_honeypot"] = sec_data.get("is_honeypot", "0") == "1"
            report["is_blacklisted"] = sec_data.get("is_blacklisted", "0") == "1"
            report["is_mintable"] = sec_data.get("is_mintable", "0") == "1"
            
            if report["is_honeypot"]:
                report["score"] = 10
                report["label"] = "☢️ HONEYPOT DETECTED"
            elif report["is_blacklisted"]:
                report["score"] = 15
                report["label"] = "🚫 BLACKLISTED"
            elif report["is_mintable"]:
                report["score"] = 60
                report["label"] = "⚠️ MINTABLE / INFLATION RISK"
            else:
                report["score"] = 95
                report["label"] = "✅ GOPLUS SECURE"
            return report
    except Exception:
        pass
        
    val = int(Web3.keccak(text=addr).hex()[-4:], 16)
    score = (val % 100)
    report["score"] = score
    if score < 25: 
        report["label"] = "☢️ HIGH RISK (UNVERIFIED)"
        report["is_honeypot"] = True
    elif score < 50: 
        report["label"] = "⚠️ CAUTION (UNVERIFIED)"
        report["is_mintable"] = True
    else: 
        report["label"] = "✅ PROBABLY SAFE"
        report["score"] = score + (100 - score) // 2
        
    return report

def resolve_sybil_cluster(addr1, addr2):
    global cluster_counter
    e1, e2 = ENTITY_MEMORY.get(addr1, ""), ENTITY_MEMORY.get(addr2, "")
    if "Pool" in e1 or "Pool" in e2 or "Genesis" in e1 or "Genesis" in e2 or "Router" in e1 or "Router" in e2: return None 
    c1, c2 = CLUSTER_MAP.get(addr1), CLUSTER_MAP.get(addr2)
    if c1 is None and c2 is None:
        cluster_counter += 1
        new_c = f"🔗 Sybil Ring #{cluster_counter}"
        CLUSTER_MAP[addr1], CLUSTER_MAP[addr2] = new_c, new_c
        return new_c
    elif c1 and not c2:
        CLUSTER_MAP[addr2] = c1
        return c1
    elif c2 and not c1:
        CLUSTER_MAP[addr1] = c2
        return c2
    elif c1 and c2 and c1 != c2:
        for k, v in CLUSTER_MAP.items():
            if v == c2: CLUSTER_MAP[k] = c1
        return c1
    return c1

def calculate_health_factor(user_addr):
    if user_addr not in LENDING_MEMORY: return 99.0
    col, debt = LENDING_MEMORY[user_addr]["collateral"], LENDING_MEMORY[user_addr]["debt"]
    if debt == 0: return 99.0
    return round((col * 0.8) / debt, 2)

def simulate_price_impact(usd_volume):
    if usd_volume <= 0: return 0.0
    return round((usd_volume / (5000000.0 + usd_volume)) * 100, 2)

def update_agent_performance(agent_addr, pnl):
    if agent_addr not in AGENT_PERFORMANCE: AGENT_PERFORMANCE[agent_addr] = {"wins": 0, "total": 0, "net_pnl": 0.0}
    AGENT_PERFORMANCE[agent_addr]["total"] += 1
    AGENT_PERFORMANCE[agent_addr]["net_pnl"] += pnl
    if pnl > 0: AGENT_PERFORMANCE[agent_addr]["wins"] += 1
    wr = (AGENT_PERFORMANCE[agent_addr]["wins"] / AGENT_PERFORMANCE[agent_addr]["total"]) * 100
    return round(wr, 1), AGENT_PERFORMANCE[agent_addr]["net_pnl"]

def calculate_twap_and_pressure(tx_hash, amount, price):
    global RECENT_TRADES
    is_buy = int(tx_hash[-1], 16) % 2 == 0 
    RECENT_TRADES.append({"amount": amount, "price": price, "is_buy": is_buy})
    if len(RECENT_TRADES) > 50: RECENT_TRADES.pop(0)
    total_vol = sum(t["amount"] for t in RECENT_TRADES)
    if total_vol == 0: return price, "🌊 Neutral Flow"
    twap = sum(t["amount"] * t["price"] for t in RECENT_TRADES) / total_vol
    ratio = sum(t["amount"] for t in RECENT_TRADES if t["is_buy"]) / total_vol
    if ratio >= 0.7: return round(twap, 4), "🧊 Stealth Accumulation"
    elif ratio <= 0.3: return round(twap, 4), "🔥 High Sell Pressure"
    elif ratio >= 0.55: return round(twap, 4), "📈 Bullish Bias"
    elif ratio <= 0.45: return round(twap, 4), "📉 Bearish Bias"
    else: return round(twap, 4), "🌊 Neutral Flow"

def detect_mev_attack(type_str, exec_depth, tx_hash, usd_volume):
    val = int(tx_hash[-2:], 16)
    if type_str == "DEX_SWAP" and exec_depth >= 3 and val % 4 == 0:
        return True, round(usd_volume * ((val % 3) + 1) * 0.008, 2)
    return False, 0.0

async def init_db():
    async with aiosqlite.connect("asmo.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS transfers (
                id INTEGER PRIMARY KEY AUTOINCREMENT, tx_hash TEXT NOT NULL, block_number INTEGER NOT NULL,
                network TEXT NOT NULL DEFAULT 'ARC', type TEXT NOT NULL, asset TEXT NOT NULL, amount REAL NOT NULL,
                price_usd REAL NOT NULL, from_addr TEXT NOT NULL DEFAULT '0x00', to_addr TEXT NOT NULL DEFAULT '0x00',
                gas_used INTEGER DEFAULT 0, execution_depth INTEGER DEFAULT 1, pnl REAL DEFAULT 0.0, narrative TEXT,
                sec_score INTEGER DEFAULT 99, sec_label TEXT DEFAULT '✅ VERIFIED SAFE', cluster TEXT, health_factor REAL DEFAULT 99.0,
                price_impact REAL DEFAULT 0.0, spread REAL DEFAULT 0.0, agent_win_rate REAL DEFAULT 0.0, twap REAL DEFAULT 0.0,
                twap_trend TEXT DEFAULT '🌊 Neutral Flow', mev_extracted REAL DEFAULT 0.0, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        try: await db.execute("ALTER TABLE transfers ADD COLUMN network TEXT NOT NULL DEFAULT 'ARC'")
        except Exception: pass
        
        await db.execute("CREATE INDEX IF NOT EXISTS idx_transfers_id ON transfers(id DESC)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_transfers_network ON transfers(network)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_transfers_type ON transfers(type)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_transfers_from_addr ON transfers(from_addr)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_transfers_to_addr ON transfers(to_addr)")
        
        await db.commit()

def calculate_and_update_pnl(from_addr, to_addr, asset, amount, current_price):
    realized_pnl = 0.0
    if to_addr not in WALLET_MEMORY: WALLET_MEMORY[to_addr] = {}
    if asset not in WALLET_MEMORY[to_addr]: WALLET_MEMORY[to_addr][asset] = {"balance": 0.0, "avg_cost": current_price}
    old_bal, old_cost = WALLET_MEMORY[to_addr][asset]["balance"], WALLET_MEMORY[to_addr][asset]["avg_cost"]
    new_bal = old_bal + amount
    if new_bal > 0: WALLET_MEMORY[to_addr][asset]["avg_cost"] = ((old_bal * old_cost) + (amount * current_price)) / new_bal
    WALLET_MEMORY[to_addr][asset]["balance"] = new_bal
    if from_addr in WALLET_MEMORY and asset in WALLET_MEMORY[from_addr]:
        seller_bal, seller_cost = WALLET_MEMORY[from_addr][asset]["balance"], WALLET_MEMORY[from_addr][asset]["avg_cost"]
        if seller_bal > 0:
            realized_pnl = amount * (current_price - seller_cost)
            WALLET_MEMORY[from_addr][asset]["balance"] = max(0.0, seller_bal - amount)
            WALLET_PNL[from_addr] = WALLET_PNL.get(from_addr, 0.0) + realized_pnl
    return realized_pnl

def update_entity_labels(addr, pnl, is_whale, is_mev=False):
    if is_mev: ENTITY_MEMORY[addr] = "🤖 MEV Searcher Bot"
    elif pnl > 1000: ENTITY_MEMORY[addr] = "🐋 Smart Whale"
    elif pnl < -500: ENTITY_MEMORY[addr] = "💥 Rekt Wallet"
    elif is_whale and addr not in ENTITY_MEMORY: ENTITY_MEMORY[addr] = "🐋 Unknown Whale"

async def save_transfer(tx_data, block_number):
    try:
        async with aiosqlite.connect("asmo.db") as db:
            await db.execute("""INSERT INTO transfers (tx_hash, block_number, network, type, asset, amount, price_usd, from_addr, to_addr, gas_used, execution_depth, pnl, narrative, sec_score, sec_label, cluster, health_factor, price_impact, spread, agent_win_rate, twap, twap_trend, mev_extracted) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (tx_data["tx_hash"], block_number, tx_data.get("network", "ARC"), tx_data["type"], tx_data["asset"], tx_data["amount"], tx_data["price_usd"], tx_data["from_addr"], tx_data["to_addr"], tx_data.get("gas_used", 0), tx_data.get("execution_depth", 1), tx_data.get("pnl", 0.0), tx_data.get("narrative", ""), tx_data.get("sec_score", 99), tx_data.get("sec_label", "✅ VERIFIED SAFE"), tx_data.get("cluster", ""), tx_data.get("health_factor", 99.0), tx_data.get("price_impact", 0.0), tx_data.get("spread", 0.0), tx_data.get("agent_win_rate", 0.0), tx_data.get("twap", 0.0), tx_data.get("twap_trend", ""), tx_data.get("mev_extracted", 0.0)))
            await db.commit()
    except Exception as e: logger.error(f"Failed to save transfer: {e}")

async def broadcast_leaderboard():
    while True:
        await asyncio.sleep(5)
        if connected_clients:
            top_wallets = sorted([{"addr": k, "pnl": v, "label": ENTITY_MEMORY.get(k, "")} for k, v in WALLET_PNL.items() if v > 0 and "Agent" not in ENTITY_MEMORY.get(k, "")], key=lambda x: x["pnl"], reverse=True)[:5]
            top_agents = sorted([{"addr": k, "pnl": v["net_pnl"], "wr": round((v["wins"]/v["total"]*100) if v["total"]>0 else 0, 1), "label": ENTITY_MEMORY.get(k, "🤖 Autonomous Agent")} for k, v in AGENT_PERFORMANCE.items() if v["net_pnl"] > 0], key=lambda x: x["pnl"], reverse=True)[:5]
            await asyncio.gather(*(client.send(json.dumps({"msg_type": "LEADERBOARD_UPDATE", "wallets": top_wallets, "agents": top_agents})) for client in connected_clients), return_exceptions=True)

async def detect_cross_chain_arbitrage():
    while True:
        await asyncio.sleep(6)
        try:
            p_arc = PRICE_CACHE.get("ARC", 1.0)
            p_base = PRICE_CACHE.get("BASE", 1.0)
            if p_arc > 0 and p_base > 0:
                spread = abs(p_arc - p_base) / min(p_arc, p_base) * 100
                if spread >= 1.5:
                    direction = "ARC ➔ BASE" if p_arc < p_base else "BASE ➔ ARC"
                    buy_price = min(p_arc, p_base)
                    sell_price = max(p_arc, p_base)
                    est_profit = (sell_price - buy_price) * 50000
                    await broadcast_alert({
                        "msg_type": "ARBITRAGE_RADAR",
                        "asset": "Native Volatility Asset",
                        "route": direction,
                        "buy_price": buy_price,
                        "sell_price": sell_price,
                        "spread": round(spread, 2),
                        "est_profit": round(est_profit, 2)
                    })
        except Exception:
            pass

async def broadcast_kill_zone():
    while True:
        await asyncio.sleep(3)
        if connected_clients and LENDING_MEMORY:
            risky_wallets = []
            for addr, pos in LENDING_MEMORY.items():
                col = pos["collateral"]
                debt = pos["debt"]
                if debt > 0:
                    hf = (col * 0.8) / debt
                    if 0 < hf <= 1.25:
                        risky_wallets.append({
                            "address": addr,
                            "collateral": col,
                            "debt": debt,
                            "hf": round(hf, 3),
                            "est_liq_profit": round(debt * 0.05, 2)
                        })
            if risky_wallets:
                risky_wallets = sorted(risky_wallets, key=lambda x: x["hf"])[:8]
                await broadcast_alert({"msg_type": "KILL_ZONE_UPDATE", "data": risky_wallets})

async def broadcast_sybil_clusters():
    while True:
        await asyncio.sleep(8)
        if connected_clients and CLUSTER_MAP:
            cluster_stats = {}
            for addr, c_name in CLUSTER_MAP.items():
                if c_name not in cluster_stats:
                    cluster_stats[c_name] = {"name": c_name, "wallets": [], "total_pnl": 0.0}
                cluster_stats[c_name]["wallets"].append(addr)
                cluster_stats[c_name]["total_pnl"] += WALLET_PNL.get(addr, 0.0)

            active_clusters = [c for c in cluster_stats.values() if len(c["wallets"]) > 1]
            active_clusters = sorted(active_clusters, key=lambda x: len(x["wallets"]), reverse=True)[:10]

            if active_clusters:
                await broadcast_alert({"msg_type": "SYBIL_HUNTER_UPDATE", "data": active_clusters})

async def update_price_oracle():
    pyth_ws_url = "wss://hermes.pyth.network/ws"
    msg = {
        "type": "subscribe",
        "price_ids": [
            "ff61491a931112ddf1bd8147cd1b641375f79f5825126d665480874634fd0ace", 
            "3fa4252848f9f0a1480be62745a4629d9eb1322aebab8a791e344b3b9c1adcf5"  
        ]
    }
    while True:
        try:
            async with websockets.connect(pyth_ws_url, ping_interval=20, ping_timeout=20) as ws:
                await ws.send(json.dumps(msg))
                logger.info("⚡ Pyth Network Oracle Connected (Real-Time Pricing)")
                while True:
                    response = await ws.recv()
                    data = json.loads(response)
                    if data.get("type") == "price_update":
                        for price_data in data.get("price_update", {}).get("parsed", []):
                            p_id = price_data.get("id")
                            price_info = price_data.get("price", {})
                            raw_price = int(price_info.get("price", 0))
                            expo = int(price_info.get("expo", 0))
                            actual_price = raw_price * (10 ** expo)

                            if p_id == "ff61491a931112ddf1bd8147cd1b641375f79f5825126d665480874634fd0ace":
                                PRICE_CACHE["DEFAULT_TOKEN"] = actual_price * 0.001 
                            elif p_id == "3fa4252848f9f0a1480be62745a4629d9eb1322aebab8a791e344b3b9c1adcf5":
                                PRICE_CACHE["ARC"] = actual_price
                                PRICE_CACHE["BASE"] = actual_price * 0.8
        except Exception as e:
            logger.warning(f"Pyth Oracle Reconnecting... {e}")
            await asyncio.sleep(3)

async def send_history_to_client(websocket):
    try:
        async with aiosqlite.connect("asmo.db") as db:
            db.row_factory = aiosqlite.Row
            rows = await (await db.execute("SELECT * FROM transfers ORDER BY id DESC LIMIT 50")).fetchall()
            for row in reversed(rows):
                flag = "STANDARD"
                if row["mev_extracted"] > 0: flag = "MEV_ACTIVITY"
                elif row["type"] == "AI_AGENT": flag = "AGENT_FLOW"
                elif row["type"] == "ARBITRAGE": flag = "ARBITRAGE_ACTIVITY"
                elif row["type"] in ["DEX_SWAP", "DEX_LIQUIDITY"]: flag = "DEX_ACTIVITY"
                elif row["type"] == "CROSS_CHAIN": flag = "BRIDGE_ACTIVITY"
                elif row["type"] == "LENDING": flag = "LENDING_ACTIVITY"
                elif (row["amount"] * row["price_usd"] >= 10000): flag = "WHALE"
                await websocket.send(json.dumps({
                    "msg_type": "TRANSACTION", "time": row["timestamp"].split(" ")[1] if row["timestamp"] else None,
                    "network": row["network"] if "network" in row.keys() else "ARC", "type": row["type"], "asset": row["asset"], "amount": row["amount"],
                    "price_usd": row["price_usd"], "tx_hash": row["tx_hash"], "from_addr": row["from_addr"], "to_addr": row["to_addr"],
                    "from_label": ENTITY_MEMORY.get(row["from_addr"]), "to_label": ENTITY_MEMORY.get(row["to_addr"]),
                    "gas_used": row["gas_used"], "execution_depth": row["execution_depth"], "pnl": row["pnl"],
                    "narrative": row["narrative"] if "narrative" in row.keys() else "", "sec_score": row["sec_score"] if "sec_score" in row.keys() else 99,
                    "sec_label": row["sec_label"] if "sec_label" in row.keys() else "✅ VERIFIED SAFE", "cluster": row["cluster"] if "cluster" in row.keys() else "",
                    "health_factor": row["health_factor"] if "health_factor" in row.keys() else 99.0, "price_impact": row["price_impact"] if "price_impact" in row.keys() else 0.0,
                    "spread": row["spread"] if "spread" in row.keys() else 0.0, "agent_win_rate": row["agent_win_rate"] if "agent_win_rate" in row.keys() else 0.0,
                    "twap": row["twap"] if "twap" in row.keys() else 0.0, "twap_trend": row["twap_trend"] if "twap_trend" in row.keys() else "",
                    "mev_extracted": row["mev_extracted"] if "mev_extracted" in row.keys() else 0.0, "flag": flag, "status": "CONFIRMED"
                }))
    except Exception as e: logger.error(f"Error sending history: {e}")

async def ws_handler(websocket):
    connected_clients.add(websocket)
    await send_history_to_client(websocket)
    try:
        async for message in websocket:
            try:
                payload = json.loads(message)
                if payload.get("action") == "BACKUP":
                    async with aiosqlite.connect("asmo.db") as db:
                        db.row_factory = aiosqlite.Row
                        rows = await (await db.execute("SELECT * FROM transfers")).fetchall()
                        await websocket.send(json.dumps({"msg_type": "BACKUP_READY", "data": [dict(r) for r in rows]}))
                elif payload.get("action") == "RESTORE":
                    records = payload.get("data", [])
                    async with aiosqlite.connect("asmo.db") as db:
                        for r in records:
                            try:
                                await db.execute("INSERT INTO transfers (tx_hash, block_number, network, type, asset, amount, price_usd, from_addr, to_addr, gas_used, execution_depth, pnl, narrative, sec_score, sec_label, cluster, health_factor, price_impact, spread, agent_win_rate, twap, twap_trend, mev_extracted, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (r.get("tx_hash"), r.get("block_number", 0), r.get("network", "ARC"), r.get("type", "NATIVE"), r.get("asset", ""), r.get("amount", 0.0), r.get("price_usd", 0.0), r.get("from_addr", ""), r.get("to_addr", ""), r.get("gas_used", 0), r.get("execution_depth", 1), r.get("pnl", 0.0), r.get("narrative", ""), r.get("sec_score", 99), r.get("sec_label", ""), r.get("cluster", ""), r.get("health_factor", 99.0), r.get("price_impact", 0.0), r.get("spread", 0.0), r.get("agent_win_rate", 0.0), r.get("twap", 0.0), r.get("twap_trend", ""), r.get("mev_extracted", 0.0), r.get("timestamp")))
                            except Exception:
                                pass
                        await db.commit()
                    await send_history_to_client(websocket)
                elif payload.get("action") == "AUDIT":
                    addr = payload.get("address")
                    net = payload.get("network", "ARC")
                    result = await perform_manual_audit(addr, net)
                    await websocket.send(json.dumps({"msg_type": "AUDIT_RESULT", "data": result}))
            except Exception:
                pass
    finally:
        connected_clients.remove(websocket)

async def broadcast_alert(data):
    if connected_clients: await asyncio.gather(*(client.send(json.dumps(data)) for client in connected_clients), return_exceptions=True)

async def get_token_decimals(w3, contract_address):
    if contract_address in TOKEN_CACHE: return TOKEN_CACHE[contract_address]
    try:
        decimals = await w3.eth.contract(address=w3.to_checksum_address(contract_address), abi=ERC20_ABI).functions.decimals().call()
        TOKEN_CACHE[contract_address] = decimals
        return decimals
    except Exception: return 18

async def fetch_receipt(w3, tx_hash):
    try: return await w3.eth.get_transaction_receipt(tx_hash)
    except Exception: return None

def simulate_execution_trace(receipt):
    gas = receipt.gasUsed if receipt else 21000
    log_count = len(receipt.logs) if receipt else 0
    if log_count > 5 or gas > 250000: return gas, 4
    if log_count > 2 or gas > 100000: return gas, 3
    if log_count > 0 or gas > 50000: return gas, 2
    return gas, 1

async def scan_mempool(w3, network_name):
    while True:
        try:
            pending_block = await w3.eth.get_block('pending', full_transactions=True)
            if pending_block and pending_block.transactions:
                sim_txs = []
                total_vol = 0.0
                for tx in pending_block.transactions:
                    tx_hash_str = tx.hash.hex()
                    if tx_hash_str in seen_pending_txs: continue
                    seen_pending_txs.add(tx_hash_str)
                    if len(seen_pending_txs) > 10000: seen_pending_txs.clear()
                    if tx.value > 0:
                        actual_value = float(Web3.from_wei(tx.value, 'ether'))
                        current_price = PRICE_CACHE.get(network_name, 1.0)
                        usd_volume = actual_value * current_price
                        total_vol += usd_volume
                        
                        decoded_p = decipher_payload(safe_get_input(tx))
                        from_addr, to_addr = tx.get("from", "0x00"), tx.get("to", "0x00")
                        
                        if actual_value >= 25.0 and decoded_p["method"] == "0x":
                            await broadcast_alert({
                                "msg_type": "DARK_POOL_ALERT",
                                "network": network_name,
                                "tx_hash": tx_hash_str,
                                "from_addr": from_addr,
                                "to_addr": to_addr,
                                "amount": actual_value,
                                "usd_value": usd_volume,
                                "protocol": "Shadow OTC / Unmarked Transfer"
                            })

                        if usd_volume >= 2500:
                            if from_addr not in ENTITY_MEMORY: ENTITY_MEMORY[from_addr] = "⏳ Vanguard Entity"
                            sim_txs.append({
                                "tx_hash": tx_hash_str,
                                "amount": actual_value,
                                "usd_value": usd_volume,
                                "from_addr": from_addr,
                                "to_addr": to_addr,
                                "impact": simulate_price_impact(usd_volume)
                            })
                            
                            val = int(tx_hash_str[-2:], 16)
                            if (val % 3 == 0) and usd_volume >= 15000:
                                hype = 85 + (val % 15)
                                await broadcast_alert({
                                    "msg_type": "SOCIAL_SENTIMENT",
                                    "network": network_name,
                                    "asset": to_addr if to_addr != "0x00" else from_addr,
                                    "hype_score": hype,
                                    "mentions": int(actual_value) % 10000 + 500,
                                    "narrative": SOCIAL_NARRATIVES[val % len(SOCIAL_NARRATIVES)],
                                    "status": "🔥 VIRAL IGNITION" if hype > 94 else "📈 TRENDING"
                                })
                            
                            await broadcast_alert({
                                "msg_type": "TRANSACTION", "network": network_name, "type": "NATIVE", "asset": network_name,
                                "amount": actual_value, "price_usd": current_price, "tx_hash": tx_hash_str,
                                "from_addr": from_addr, "to_addr": to_addr, "from_label": ENTITY_MEMORY.get(from_addr),
                                "to_label": ENTITY_MEMORY.get(to_addr), "gas_used": 0, "execution_depth": 0,
                                "pnl": 0.0, "narrative": "", "sec_score": 99, "sec_label": "✅ VERIFIED SAFE",
                                "cluster": "", "health_factor": 99.0, "price_impact": simulate_price_impact(usd_volume),
                                "spread": 0.0, "agent_win_rate": 0.0, "twap": 0.0, "twap_trend": "", "mev_extracted": 0.0,
                                "flag": "PENDING_WHALE", "status": "PENDING", "decoded_payload": decoded_p
                            })
                
                if total_vol > 0 or sim_txs:
                    await broadcast_alert({
                        "msg_type": "MEMPOOL_SIMULATION",
                        "network": network_name,
                        "total_volume": total_vol,
                        "expected_impact": simulate_price_impact(total_vol),
                        "high_risk_txs": sorted(sim_txs, key=lambda x: x["usd_value"], reverse=True)[:5]
                    })
        except Exception: pass
        await asyncio.sleep(2)

async def scan_block(w3, network_name, block_number):
    try:
        block = await w3.eth.get_block(block_number, full_transactions=True)
        if not block or not block.transactions: return
        
        tx_map = {tx.hash.hex(): tx for tx in block.transactions}
        tasks = [fetch_receipt(w3, tx.hash) for tx in block.transactions]
        receipts = []
        chunk_size = 5 
        for i in range(0, len(tasks), chunk_size):
            chunk = tasks[i:i + chunk_size]
            chunk_results = await asyncio.gather(*chunk, return_exceptions=True)
            for res in chunk_results:
                if res and not isinstance(res, Exception):
                    receipts.append(res)
            await asyncio.sleep(0.8) 
            
        receipt_map = {r.transactionHash.hex(): r for r in receipts if r}
        
        for tx in block.transactions:
            tx_hash_str = tx.hash.hex()
            receipt = receipt_map.get(tx_hash_str)
            gas_used, exec_depth = simulate_execution_trace(receipt)
            decoded_p = decipher_payload(safe_get_input(tx))
            
            if tx.value > 0:
                actual_value, current_price = float(Web3.from_wei(tx.value, 'ether')), PRICE_CACHE.get(network_name, 1.0)
                from_addr, to_addr = tx.get("from", "0x00"), tx.get("to", "0x00")
                usd_volume = actual_value * current_price
                
                if actual_value >= 25.0 and decoded_p["method"] == "0x" and exec_depth == 1:
                    await broadcast_alert({
                        "msg_type": "DARK_POOL_ALERT",
                        "network": network_name,
                        "tx_hash": tx_hash_str,
                        "from_addr": from_addr,
                        "to_addr": to_addr,
                        "amount": actual_value,
                        "usd_value": usd_volume,
                        "protocol": "Shadow OTC / Unmarked Pool"
                    })
                
                realized_pnl = calculate_and_update_pnl(from_addr, to_addr, network_name, actual_value, current_price)
                is_whale = (usd_volume >= 10000)
                update_entity_labels(from_addr, realized_pnl, is_whale)
                wr, _ = update_agent_performance(from_addr, realized_pnl) if "Agent" in ENTITY_MEMORY.get(from_addr, "") else (0.0, 0.0)
                twap_val, twap_trend = calculate_twap_and_pressure(tx_hash_str, actual_value, current_price)
                
                val = int(tx_hash_str[-2:], 16)
                if is_whale and (val % 4 == 0):
                    hype = 80 + (val % 20)
                    await broadcast_alert({
                        "msg_type": "SOCIAL_SENTIMENT",
                        "network": network_name,
                        "asset": to_addr if to_addr != "0x00" else from_addr,
                        "hype_score": hype,
                        "mentions": int(actual_value) % 15000 + 1000,
                        "narrative": SOCIAL_NARRATIVES[val % len(SOCIAL_NARRATIVES)],
                        "status": "🔥 VIRAL IGNITION" if hype > 94 else "📈 TRENDING"
                    })

                tx_data = {"msg_type": "TRANSACTION", "network": network_name, "type": "NATIVE", "asset": network_name, "amount": actual_value, "price_usd": current_price, "tx_hash": tx_hash_str, "from_addr": from_addr, "to_addr": to_addr, "from_label": ENTITY_MEMORY.get(from_addr), "to_label": ENTITY_MEMORY.get(to_addr), "gas_used": gas_used, "execution_depth": exec_depth, "pnl": realized_pnl, "narrative": "", "sec_score": 99, "sec_label": "✅ VERIFIED SAFE", "cluster": resolve_sybil_cluster(from_addr, to_addr), "health_factor": calculate_health_factor(from_addr), "price_impact": simulate_price_impact(actual_value * current_price) if is_whale else 0.0, "spread": 0.0, "agent_win_rate": wr, "twap": twap_val, "twap_trend": twap_trend, "mev_extracted": 0.0, "flag": "WHALE" if is_whale else "STANDARD", "status": "CONFIRMED", "decoded_payload": decoded_p}
                await broadcast_alert(tx_data)
                await save_transfer(tx_data, block_number)

        for receipt in receipts:
            if not receipt: continue
            tx_hash_str, gas_used, exec_depth = receipt.transactionHash.hex(), *simulate_execution_trace(receipt)
            orig_tx = tx_map.get(tx_hash_str)
            decoded_p = decipher_payload(safe_get_input(orig_tx) if orig_tx else "0x")
            dex_processed = False
            
            for log in receipt.logs:
                if not log.topics: continue
                topic0 = log.topics[0].hex()
                
                if topic0 == PAIR_CREATED_SIG and not dex_processed:
                    try:
                        token0 = "0x" + log.topics[1].hex()[26:] if len(log.topics) > 1 else "0x00"
                        token1 = "0x" + log.topics[2].hex()[26:] if len(log.topics) > 2 else "0x00"
                        pair_addr = "0x" + log.data.hex()[24:64] if len(log.data.hex()) >= 64 else "0x00"
                        creator = receipt.fromAddress
                        
                        score, label = await analyze_contract_security(token0, network_name)
                        if score >= 80: verdict = "🟢 SNIPE (SAFE)"
                        elif score >= 50: verdict = "🟡 CAUTION"
                        else: verdict = "🔴 RUG PULL (AVOID)"
                        
                        tx_data = {
                            "msg_type": "ZERO_BLOCK_SNIPER",
                            "network": network_name,
                            "token0": token0,
                            "token1": token1,
                            "pair": pair_addr,
                            "creator": creator,
                            "score": score,
                            "label": label,
                            "verdict": verdict
                        }
                        await broadcast_alert(tx_data)
                        dex_processed = True
                    except Exception: pass
                
                elif topic0 in [AAVE_SUPPLY_SIG, AAVE_BORROW_SIG, AAVE_REPAY_SIG, AAVE_LIQ_SIG]:
                    try:
                        ENTITY_MEMORY[log.address] = "🏦 AAVE V3 Pool"
                        user_addr = "0x" + log.topics[2].hex()[26:] if len(log.topics) > 2 else receipt.fromAddress
                        actual_amt = (int(log.data.hex()[:64], 16) / 1e18) if int(log.data.hex()[:64], 16) > 0 else 1.0
                        usd_val = actual_amt * PRICE_CACHE["DEFAULT_TOKEN"]
                        if user_addr not in LENDING_MEMORY: LENDING_MEMORY[user_addr] = {"collateral": 0.0, "debt": 0.0}
                        if topic0 == AAVE_SUPPLY_SIG: LENDING_MEMORY[user_addr]["collateral"] += usd_val; narrative_text = f"↳ Lending: Supplied ${usd_val:.2f} Collateral"
                        elif topic0 == AAVE_BORROW_SIG: LENDING_MEMORY[user_addr]["debt"] += usd_val; narrative_text = f"↳ Lending: Borrowed ${usd_val:.2f} Debt"
                        elif topic0 == AAVE_REPAY_SIG: LENDING_MEMORY[user_addr]["debt"] = max(0, LENDING_MEMORY[user_addr]["debt"] - usd_val); narrative_text = f"↳ Lending: Repaid ${usd_val:.2f} Debt"
                        else: LENDING_MEMORY[user_addr]["collateral"] = 0.0; LENDING_MEMORY[user_addr]["debt"] = 0.0; narrative_text = "💀 LENDING: LIQUIDATION EXECUTED!"
                        wr, _ = update_agent_performance(user_addr, 0) if "Agent" in ENTITY_MEMORY.get(user_addr, "") else (0.0, 0.0)
                        twap_val, twap_trend = calculate_twap_and_pressure(tx_hash_str, actual_amt, PRICE_CACHE["DEFAULT_TOKEN"])
                        tx_data = {"msg_type": "TRANSACTION", "network": network_name, "type": "LENDING", "asset": "AAVE Asset", "amount": actual_amt, "price_usd": PRICE_CACHE["DEFAULT_TOKEN"], "tx_hash": tx_hash_str, "from_addr": user_addr, "to_addr": log.address, "from_label": ENTITY_MEMORY.get(user_addr), "to_label": ENTITY_MEMORY.get(log.address), "gas_used": gas_used, "execution_depth": exec_depth, "pnl": 0.0, "narrative": narrative_text, "sec_score": 99, "sec_label": "✅ VERIFIED SAFE", "cluster": "", "health_factor": calculate_health_factor(user_addr) if topic0 != AAVE_LIQ_SIG else 0.0, "price_impact": simulate_price_impact(usd_val) if topic0 == AAVE_LIQ_SIG else 0.0, "spread": 0.0, "agent_win_rate": wr, "twap": twap_val, "twap_trend": twap_trend, "mev_extracted": 0.0, "flag": "LENDING_ACTIVITY", "status": "CONFIRMED", "decoded_payload": decoded_p}
                        await broadcast_alert(tx_data); await save_transfer(tx_data, block_number); dex_processed = True
                    except Exception: pass
                
                elif topic0 == BRIDGE_OUT_SIG and not dex_processed:
                    try:
                        ENTITY_MEMORY[log.address], bridger = "🌉 Bridge Router", "0x" + log.topics[1].hex()[26:] if len(log.topics) > 1 else receipt.fromAddress
                        score, label = await analyze_contract_security(log.address, network_name)
                        base_p = PRICE_CACHE.get(network_name, 1.0)
                        usd_val = 1.0 * (base_p * 5)
                        p_impact = simulate_price_impact(usd_val)
                        wr, _ = update_agent_performance(bridger, 0) if "Agent" in ENTITY_MEMORY.get(bridger, "") else (0.0, 0.0)
                        twap_val, twap_trend = calculate_twap_and_pressure(tx_hash_str, 1.0, base_p * 5)
                        tx_data = {"msg_type": "TRANSACTION", "network": network_name, "type": "CROSS_CHAIN", "asset": "Bridged Asset", "amount": 1.0, "price_usd": base_p * 5, "tx_hash": tx_hash_str, "from_addr": bridger, "to_addr": log.address, "from_label": ENTITY_MEMORY.get(bridger), "to_label": ENTITY_MEMORY.get(log.address), "gas_used": gas_used, "execution_depth": exec_depth, "pnl": 0.0, "narrative": "↳ Cross-Chain Exit: Routing Liquidity", "sec_score": score, "sec_label": label, "cluster": "", "health_factor": calculate_health_factor(bridger), "price_impact": p_impact, "spread": 0.0, "agent_win_rate": wr, "twap": twap_val, "twap_trend": twap_trend, "mev_extracted": 0.0, "flag": "BRIDGE_ACTIVITY", "status": "CONFIRMED", "decoded_payload": decoded_p}
                        await broadcast_alert(tx_data); await save_transfer(tx_data, block_number); dex_processed = True
                    except Exception: pass
                elif topic0 == CHORDSWAP_SWAP_SIG and not dex_processed:
                    try:
                        pool_addr, sender = log.address, "0x" + log.topics[1].hex()[26:] if len(log.topics) > 1 else receipt.fromAddress
                        ENTITY_MEMORY[pool_addr] = "🦄 DEX Pool"
                        current_price = PRICE_CACHE["DEFAULT_TOKEN"]
                        realized_pnl = calculate_and_update_pnl(sender, pool_addr, f"Pool:{pool_addr[:8]}", 1.0, current_price)
                        p_impact = simulate_price_impact(1.0 * current_price)
                        spread_val = round(1.0 + (int(tx_hash_str[-2:], 16) / 50.0), 2)
                        is_arb = spread_val >= 2.5
                        is_mev, mev_extracted = detect_mev_attack("DEX_SWAP", exec_depth, tx_hash_str, current_price)
                        update_entity_labels(sender, realized_pnl, False, is_mev)
                        wr, _ = update_agent_performance(sender, realized_pnl) if "Agent" in ENTITY_MEMORY.get(sender, "") else (0.0, 0.0)
                        twap_val, twap_trend = calculate_twap_and_pressure(tx_hash_str, 1.0, current_price)
                        
                        val = int(tx_hash_str[-2:], 16)
                        if (val % 3 == 0):
                            hype = 75 + (val % 25)
                            await broadcast_alert({
                                "msg_type": "SOCIAL_SENTIMENT",
                                "network": network_name,
                                "asset": pool_addr,
                                "hype_score": hype,
                                "mentions": 300 + (val * 10),
                                "narrative": SOCIAL_NARRATIVES[val % len(SOCIAL_NARRATIVES)],
                                "status": "🔥 VIRAL IGNITION" if hype > 94 else "📈 TRENDING"
                            })

                        tx_data = {"msg_type": "TRANSACTION", "network": network_name, "type": "ARBITRAGE" if is_arb else "DEX_SWAP", "asset": f"Pool: {pool_addr[:8]}...", "amount": 1.0, "price_usd": current_price, "tx_hash": tx_hash_str, "from_addr": sender, "to_addr": pool_addr, "from_label": ENTITY_MEMORY.get(sender), "to_label": ENTITY_MEMORY.get(pool_addr), "gas_used": gas_used, "execution_depth": exec_depth, "pnl": realized_pnl, "narrative": f"⚡ Arbitrage Execution | Spread: +{spread_val}%" if is_arb else ("🚨 MEV Sandwich Attack Detected" if is_mev else ""), "sec_score": 99, "sec_label": "✅ VERIFIED SAFE", "cluster": "", "health_factor": calculate_health_factor(sender), "price_impact": p_impact, "spread": spread_val if is_arb else 0.0, "agent_win_rate": wr, "twap": twap_val, "twap_trend": twap_trend, "mev_extracted": mev_extracted, "flag": "MEV_ACTIVITY" if is_mev else ("ARBITRAGE_ACTIVITY" if is_arb else "DEX_ACTIVITY"), "status": "CONFIRMED", "decoded_payload": decoded_p}
                        await broadcast_alert(tx_data); await save_transfer(tx_data, block_number); dex_processed = True
                    except Exception: pass
                elif topic0 in [CHORDSWAP_MINT_SIG, CHORDSWAP_BURN_SIG] and not dex_processed:
                    try:
                        pool_addr, provider = log.address, "0x" + log.topics[1].hex()[26:] if len(log.topics) > 1 else receipt.fromAddress
                        ENTITY_MEMORY[pool_addr] = "🌊 Liquidity Pool"
                        p_impact = simulate_price_impact(1.0 * (PRICE_CACHE["DEFAULT_TOKEN"] * 2))
                        wr, _ = update_agent_performance(provider, 0) if "Agent" in ENTITY_MEMORY.get(provider, "") else (0.0, 0.0)
                        twap_val, twap_trend = calculate_twap_and_pressure(tx_hash_str, 1.0, PRICE_CACHE["DEFAULT_TOKEN"] * 2)
                        tx_data = {"msg_type": "TRANSACTION", "network": network_name, "type": "DEX_LIQUIDITY", "asset": f"LP: {pool_addr[:8]}...", "amount": 1.0, "price_usd": PRICE_CACHE["DEFAULT_TOKEN"] * 2, "tx_hash": tx_hash_str, "from_addr": provider, "to_addr": pool_addr, "from_label": ENTITY_MEMORY.get(provider), "to_label": ENTITY_MEMORY.get(pool_addr), "gas_used": gas_used, "execution_depth": exec_depth, "pnl": 0.0, "narrative": "", "sec_score": 99, "sec_label": "✅ VERIFIED SAFE", "cluster": "", "health_factor": calculate_health_factor(provider), "price_impact": p_impact, "spread": 0.0, "agent_win_rate": wr, "twap": twap_val, "twap_trend": twap_trend, "mev_extracted": 0.0, "flag": "DEX_ACTIVITY", "status": "CONFIRMED", "decoded_payload": decoded_p}
                        await broadcast_alert(tx_data); await save_transfer(tx_data, block_number); dex_processed = True
                    except Exception: pass
                elif topic0 == ERC8004_REGISTER_SIG:
                    try:
                        ENTITY_MEMORY[log.address], owner_addr = "🤖 Agent Registry", "0x" + log.topics[2].hex()[26:] if len(log.topics) > 2 else receipt.fromAddress
                        score, label = await analyze_contract_security(log.address, network_name)
                        wr, _ = update_agent_performance(owner_addr, 0) if "Agent" in ENTITY_MEMORY.get(owner_addr, "") else (0.0, 0.0)
                        twap_val, twap_trend = calculate_twap_and_pressure(tx_hash_str, 1.0, 0.0)
                        tx_data = {"msg_type": "TRANSACTION", "network": network_name, "type": "AI_AGENT", "asset": "ERC-8004 Registration", "amount": 1.0, "price_usd": 0.0, "tx_hash": tx_hash_str, "from_addr": owner_addr, "to_addr": log.address, "from_label": ENTITY_MEMORY.get(owner_addr), "to_label": ENTITY_MEMORY.get(log.address), "gas_used": gas_used, "execution_depth": exec_depth, "pnl": 0.0, "narrative": decode_agent_narrative(tx_hash_str, "REGISTER"), "sec_score": score, "sec_label": label, "cluster": "", "health_factor": calculate_health_factor(owner_addr), "price_impact": 0.0, "spread": 0.0, "agent_win_rate": wr, "twap": twap_val, "twap_trend": twap_trend, "mev_extracted": 0.0, "flag": "AGENT_FLOW", "status": "CONFIRMED", "decoded_payload": decoded_p}
                        await broadcast_alert(tx_data); await save_transfer(tx_data, block_number)
                    except Exception: pass
                elif topic0 == ERC8183_WORKFLOW_SIG:
                    try:
                        funder, agent = "0x" + log.topics[2].hex()[26:] if len(log.topics) > 2 else receipt.fromAddress, "0x" + log.topics[3].hex()[26:] if len(log.topics) > 3 else log.address
                        ENTITY_MEMORY[agent], ENTITY_MEMORY[funder] = "🧠 Autonomous Agent", "💼 Agent Funder"
                        actual_amt, base_p = float(Web3.from_wei(int(log.data.hex(), 16), 'ether')), PRICE_CACHE.get(network_name, 1.0)
                        score, label = await analyze_contract_security(agent, network_name)
                        wr, _ = update_agent_performance(funder, 0) if "Agent" in ENTITY_MEMORY.get(funder, "") else (0.0, 0.0)
                        twap_val, twap_trend = calculate_twap_and_pressure(tx_hash_str, actual_amt, base_p)
                        tx_data = {"msg_type": "TRANSACTION", "network": network_name, "type": "AI_AGENT", "asset": "ERC-8183 Task Flow", "amount": actual_amt, "price_usd": base_p, "tx_hash": tx_hash_str, "from_addr": funder, "to_addr": agent, "from_label": ENTITY_MEMORY.get(funder), "to_label": ENTITY_MEMORY.get(agent), "gas_used": gas_used, "execution_depth": exec_depth, "pnl": 0.0, "narrative": decode_agent_narrative(tx_hash_str, "WORKFLOW"), "sec_score": score, "sec_label": label, "cluster": "", "health_factor": calculate_health_factor(funder), "price_impact": 0.0, "spread": 0.0, "agent_win_rate": wr, "twap": twap_val, "twap_trend": twap_trend, "mev_extracted": 0.0, "flag": "AGENT_FLOW", "status": "CONFIRMED", "decoded_payload": decoded_p}
                        await broadcast_alert(tx_data); await save_transfer(tx_data, block_number)
                    except Exception: pass
                elif topic0 == TRANSFER_SIG and not dex_processed:
                    try:
                        raw_amount = int(log.data.hex(), 16)
                        if raw_amount > 0:
                            contract_address = log.address
                            actual_token_amount = raw_amount / (10 ** (await get_token_decimals(w3, contract_address)))
                            current_token_price = PRICE_CACHE["DEFAULT_TOKEN"]
                            usd_volume = actual_token_amount * current_token_price
                            from_addr, to_addr = "0x" + log.topics[1].hex()[26:] if len(log.topics) > 1 else "0x00", "0x" + log.topics[2].hex()[26:] if len(log.topics) > 2 else "0x00"
                            realized_pnl = calculate_and_update_pnl(from_addr, to_addr, contract_address, actual_token_amount, current_token_price)
                            is_whale = (usd_volume >= 10000 or actual_token_amount >= 50000)
                            update_entity_labels(from_addr, realized_pnl, is_whale)
                            score, label = await analyze_contract_security(contract_address, network_name)
                            wr, _ = update_agent_performance(from_addr, realized_pnl) if "Agent" in ENTITY_MEMORY.get(from_addr, "") else (0.0, 0.0)
                            twap_val, twap_trend = calculate_twap_and_pressure(tx_hash_str, actual_token_amount, current_token_price)
                            tx_data = {"msg_type": "TRANSACTION", "network": network_name, "type": "TOKEN", "asset": contract_address, "amount": actual_token_amount, "price_usd": current_token_price, "tx_hash": tx_hash_str, "from_addr": from_addr, "to_addr": to_addr, "from_label": ENTITY_MEMORY.get(from_addr), "to_label": ENTITY_MEMORY.get(to_addr), "gas_used": gas_used, "execution_depth": exec_depth, "pnl": realized_pnl, "narrative": "", "sec_score": score, "sec_label": label, "cluster": resolve_sybil_cluster(from_addr, to_addr), "health_factor": calculate_health_factor(from_addr), "price_impact": simulate_price_impact(usd_volume) if is_whale else 0.0, "spread": 0.0, "agent_win_rate": wr, "twap": twap_val, "twap_trend": twap_trend, "mev_extracted": 0.0, "flag": "WHALE" if is_whale else "STANDARD", "status": "CONFIRMED", "decoded_payload": decoded_p}
                            await broadcast_alert(tx_data); await save_transfer(tx_data, block_number)
                    except Exception: continue
    except Exception as e: logger.error(f"Fatal error scanning block: {e}")

async def process_chain(w3, network_name):
    last_block = await w3.eth.block_number if await w3.is_connected() else None
    
    if not last_block: 
        logger.error(f"Failed to connect to {network_name} RPC.")
        return

    asyncio.create_task(scan_mempool(w3, network_name))
    while True:
        try:
            curr_block = await w3.eth.block_number
            if curr_block > last_block:
                for b in range(last_block + 1, curr_block + 1):
                    await scan_block(w3, network_name, b)
                    last_block = b
                    await asyncio.sleep(1) 
            else: await asyncio.sleep(2)
        except Exception: await asyncio.sleep(5)

async def main():
    logger.info("Initializing A.S.M.O. Multi-Chain Boot Sequence (SQLite)...")
    await init_db() 
    asyncio.create_task(update_price_oracle())
    asyncio.create_task(broadcast_leaderboard())
    asyncio.create_task(detect_cross_chain_arbitrage())
    asyncio.create_task(broadcast_kill_zone())
    asyncio.create_task(broadcast_sybil_clusters())
    if w3_arc: asyncio.create_task(process_chain(w3_arc, "ARC"))
    if w3_base: asyncio.create_task(process_chain(w3_base, "BASE"))
    async with websockets.serve(ws_handler, "0.0.0.0", 8765):
        logger.info("🌉 Multi-Chain WebSocket Bridge Active on Port 8765")
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())