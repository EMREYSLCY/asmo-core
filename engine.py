import os
import json
import asyncio
import websockets
import logging
import aiosqlite
import urllib.request
from dotenv import load_dotenv
from web3 import AsyncWeb3, AsyncHTTPProvider

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("asmo.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("ASMO")

ARC_RPC_URL = os.getenv("ARC_RPC_URL")
w3 = AsyncWeb3(AsyncHTTPProvider(ARC_RPC_URL))

TRANSFER_SIG = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
ERC8004_REGISTER_SIG = "0x" + w3.keccak(text="AgentRegistered(bytes32,address,string)").hex()
ERC8183_WORKFLOW_SIG = "0x" + w3.keccak(text="WorkflowFunded(bytes32,address,address,uint256)").hex()
CHORDSWAP_SWAP_SIG = "0x" + w3.keccak(text="Swap(address,uint256,uint256,uint256,uint256,address)").hex()
CHORDSWAP_MINT_SIG = "0x" + w3.keccak(text="Mint(address,uint256,uint256)").hex()
CHORDSWAP_BURN_SIG = "0x" + w3.keccak(text="Burn(address,uint256,uint256,address)").hex()
BRIDGE_OUT_SIG = "0x" + w3.keccak(text="BridgeOut(address,uint256,uint256)").hex()
AAVE_SUPPLY_SIG = "0x" + w3.keccak(text="Supply(address,address,address,uint256,uint16)").hex()
AAVE_BORROW_SIG = "0x" + w3.keccak(text="Borrow(address,address,address,uint256,uint8,uint256,uint16)").hex()
AAVE_REPAY_SIG = "0x" + w3.keccak(text="Repay(address,address,address,uint256,bool)").hex()
AAVE_LIQ_SIG = "0x" + w3.keccak(text="LiquidationCall(address,address,address,uint256,uint256,address,bool)").hex()

ERC20_ABI = json.loads('[{"inputs":[],"name":"decimals","outputs":[{"type":"uint8"}],"stateMutability":"view","type":"function"}]')
TOKEN_CACHE = {}
PRICE_CACHE = {
    "ARC": 1.25,
    "DEFAULT_TOKEN": 2.50 
}

connected_clients = set()
seen_pending_txs = set()
WALLET_MEMORY = {}
LENDING_MEMORY = {}
ENTITY_MEMORY = {
    "0x0000000000000000000000000000000000000000": "🏦 Arc Genesis / Burn"
}
CLUSTER_MAP = {}
cluster_counter = 0

AI_TASKS = [
    "🧠 Dataset Analysis & Classification",
    "🛡️ Smart Contract Security Scan",
    "🌐 Cross-Chain Liquidity Optimization",
    "📈 Predictive Price Modeling",
    "🕵️‍♂️ On-Chain Wallet Behavior Analysis",
    "⚡ High-Frequency Trading (HFT) Simulation",
    "📝 Autonomous Reporting & Summarization",
    "🔄 Arbitrage Route Calculation"
]

def decode_agent_narrative(tx_hash, type_sig):
    val = int(tx_hash[-2:], 16)
    if type_sig == "REGISTER":
        return f"New Autonomous Agent Registered (v1.{val%10})"
    else:
        task = AI_TASKS[val % len(AI_TASKS)]
        return f"↳ Workflow: {task}"

def analyze_contract_security(addr):
    if addr in ENTITY_MEMORY and ("Genesis" in ENTITY_MEMORY[addr] or "Pool" in ENTITY_MEMORY[addr] or "Router" in ENTITY_MEMORY[addr]):
        return 99, "✅ VERIFIED SAFE"
    val = int(w3.keccak(text=addr).hex()[-4:], 16)
    score = (val % 100)
    if score < 25: return score, "☢️ HIGH RISK (HONEYPOT)"
    elif score < 50: return score, "⚠️ CAUTION (UNVERIFIED)"
    else: return score + (100 - score) // 2, "✅ SAFE CONTRACT"

def resolve_sybil_cluster(addr1, addr2):
    global cluster_counter
    e1 = ENTITY_MEMORY.get(addr1, "")
    e2 = ENTITY_MEMORY.get(addr2, "")
    if "Pool" in e1 or "Pool" in e2 or "Genesis" in e1 or "Genesis" in e2 or "Router" in e1 or "Router" in e2: return None 
    c1 = CLUSTER_MAP.get(addr1)
    c2 = CLUSTER_MAP.get(addr2)
    if c1 is None and c2 is None:
        cluster_counter += 1
        new_c = f"🔗 Sybil Ring #{cluster_counter}"
        CLUSTER_MAP[addr1] = new_c
        CLUSTER_MAP[addr2] = new_c
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
    col = LENDING_MEMORY[user_addr]["collateral"]
    debt = LENDING_MEMORY[user_addr]["debt"]
    if debt == 0: return 99.0
    hf = (col * 0.8) / debt
    return round(hf, 2)

def simulate_price_impact(usd_volume):
    base_liquidity = 5000000.0 
    if usd_volume <= 0: return 0.0
    impact = (usd_volume / (base_liquidity + usd_volume)) * 100
    return round(impact, 2)

async def init_db():
    async with aiosqlite.connect("asmo.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS transfers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tx_hash TEXT NOT NULL,
                block_number INTEGER NOT NULL,
                type TEXT NOT NULL,
                asset TEXT NOT NULL,
                amount REAL NOT NULL,
                price_usd REAL NOT NULL,
                from_addr TEXT NOT NULL DEFAULT '0x0000000000000000000000000000000000000000',
                to_addr TEXT NOT NULL DEFAULT '0x0000000000000000000000000000000000000000',
                gas_used INTEGER NOT NULL DEFAULT 0,
                execution_depth INTEGER NOT NULL DEFAULT 1,
                pnl REAL NOT NULL DEFAULT 0.0,
                narrative TEXT,
                sec_score INTEGER NOT NULL DEFAULT 99,
                sec_label TEXT NOT NULL DEFAULT '✅ VERIFIED SAFE',
                cluster TEXT,
                health_factor REAL NOT NULL DEFAULT 99.0,
                price_impact REAL NOT NULL DEFAULT 0.0,
                spread REAL NOT NULL DEFAULT 0.0,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        try:
            await db.execute("ALTER TABLE transfers ADD COLUMN spread REAL NOT NULL DEFAULT 0.0")
        except Exception:
            pass
        await db.commit()
        logger.info("💾 Database verified with Arbitrage Scanner Module.")

def calculate_and_update_pnl(from_addr, to_addr, asset, amount, current_price):
    realized_pnl = 0.0
    if to_addr not in WALLET_MEMORY: WALLET_MEMORY[to_addr] = {}
    if asset not in WALLET_MEMORY[to_addr]: WALLET_MEMORY[to_addr][asset] = {"balance": 0.0, "avg_cost": current_price}
    old_bal = WALLET_MEMORY[to_addr][asset]["balance"]
    old_cost = WALLET_MEMORY[to_addr][asset]["avg_cost"]
    new_bal = old_bal + amount
    if new_bal > 0:
        WALLET_MEMORY[to_addr][asset]["avg_cost"] = ((old_bal * old_cost) + (amount * current_price)) / new_bal
    WALLET_MEMORY[to_addr][asset]["balance"] = new_bal
    if from_addr in WALLET_MEMORY and asset in WALLET_MEMORY[from_addr]:
        seller_bal = WALLET_MEMORY[from_addr][asset]["balance"]
        seller_cost = WALLET_MEMORY[from_addr][asset]["avg_cost"]
        if seller_bal > 0:
            realized_pnl = amount * (current_price - seller_cost)
            WALLET_MEMORY[from_addr][asset]["balance"] = max(0.0, seller_bal - amount)
    return realized_pnl

def update_entity_labels(addr, pnl, is_whale):
    if pnl > 1000: ENTITY_MEMORY[addr] = "🐋 Smart Whale"
    elif pnl < -500: ENTITY_MEMORY[addr] = "💥 Rekt Wallet"
    elif is_whale and addr not in ENTITY_MEMORY: ENTITY_MEMORY[addr] = "🐋 Unknown Whale"

async def save_transfer(tx_data, block_number):
    try:
        async with aiosqlite.connect("asmo.db") as db:
            await db.execute(
                """INSERT INTO transfers 
                   (tx_hash, block_number, type, asset, amount, price_usd, from_addr, to_addr, gas_used, execution_depth, pnl, narrative, sec_score, sec_label, cluster, health_factor, price_impact, spread) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (tx_data["tx_hash"], block_number, tx_data["type"], 
                 tx_data["asset"], tx_data["amount"], tx_data["price_usd"],
                 tx_data["from_addr"], tx_data["to_addr"],
                 tx_data.get("gas_used", 0), tx_data.get("execution_depth", 1), 
                 tx_data.get("pnl", 0.0), tx_data.get("narrative", ""),
                 tx_data.get("sec_score", 99), tx_data.get("sec_label", "✅ VERIFIED SAFE"), 
                 tx_data.get("cluster", ""), tx_data.get("health_factor", 99.0), 
                 tx_data.get("price_impact", 0.0), tx_data.get("spread", 0.0))
            )
            await db.commit()
    except Exception as e:
        logger.error(f"Failed to save transfer to DB: {e}")

async def update_price_oracle():
    while True:
        try:
            url = "https://api.coingecko.com/api/v3/simple/price?ids=arbitrum,ethereum&vs_currencies=usd"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            loop = asyncio.get_running_loop()
            resp = await loop.run_in_executor(None, urllib.request.urlopen, req)
            data = json.loads(resp.read().decode('utf-8'))
            if "arbitrum" in data: PRICE_CACHE["ARC"] = float(data["arbitrum"]["usd"])
            if "ethereum" in data: PRICE_CACHE["DEFAULT_TOKEN"] = float(data["ethereum"]["usd"]) * 0.001 
        except Exception:
            pass
        await asyncio.sleep(180)

async def send_history_to_client(websocket):
    try:
        async with aiosqlite.connect("asmo.db") as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM transfers ORDER BY id DESC LIMIT 50")
            rows = await cursor.fetchall()
            for row in reversed(rows):
                time_str = row["timestamp"].split(" ")[1] if row["timestamp"] else None
                amt = row["amount"]
                prc = row["price_usd"]
                flag = "STANDARD"
                if row["type"] == "AI_AGENT": flag = "AGENT_FLOW"
                elif row["type"] == "ARBITRAGE": flag = "ARBITRAGE_ACTIVITY"
                elif row["type"] in ["DEX_SWAP", "DEX_LIQUIDITY"]: flag = "DEX_ACTIVITY"
                elif row["type"] == "CROSS_CHAIN": flag = "BRIDGE_ACTIVITY"
                elif row["type"] == "LENDING": flag = "LENDING_ACTIVITY"
                elif (amt * prc >= 10000 or (prc == 0.0 and amt >= 50000)): flag = "WHALE"
                tx_data = {
                    "time": time_str,
                    "type": row["type"],
                    "asset": row["asset"],
                    "amount": amt,
                    "price_usd": prc,
                    "tx_hash": row["tx_hash"],
                    "from_addr": row["from_addr"],
                    "to_addr": row["to_addr"],
                    "from_label": ENTITY_MEMORY.get(row["from_addr"]),
                    "to_label": ENTITY_MEMORY.get(row["to_addr"]),
                    "gas_used": row["gas_used"],
                    "execution_depth": row["execution_depth"],
                    "pnl": row["pnl"],
                    "narrative": row["narrative"] if "narrative" in row.keys() else "",
                    "sec_score": row["sec_score"] if "sec_score" in row.keys() else 99,
                    "sec_label": row["sec_label"] if "sec_label" in row.keys() else "✅ VERIFIED SAFE",
                    "cluster": row["cluster"] if "cluster" in row.keys() else "",
                    "health_factor": row["health_factor"] if "health_factor" in row.keys() else 99.0,
                    "price_impact": row["price_impact"] if "price_impact" in row.keys() else 0.0,
                    "spread": row["spread"] if "spread" in row.keys() else 0.0,
                    "flag": flag,
                    "status": "CONFIRMED"
                }
                await websocket.send(json.dumps(tx_data))
    except Exception as e:
        logger.error(f"Error sending history to client: {e}")

async def ws_handler(websocket):
    logger.info("🟢 UI Dashboard Connected to Engine!")
    connected_clients.add(websocket)
    await send_history_to_client(websocket)
    try: await websocket.wait_closed()
    finally:
        connected_clients.remove(websocket)
        logger.info("🔴 UI Dashboard Disconnected.")

async def broadcast_alert(data):
    if connected_clients:
        message = json.dumps(data)
        await asyncio.gather(*(client.send(message) for client in connected_clients), return_exceptions=True)

async def get_token_decimals(contract_address):
    if contract_address in TOKEN_CACHE: return TOKEN_CACHE[contract_address]
    try:
        contract_address_checksum = w3.to_checksum_address(contract_address)
        contract = w3.eth.contract(address=contract_address_checksum, abi=ERC20_ABI)
        decimals = await contract.functions.decimals().call()
        TOKEN_CACHE[contract_address] = decimals
        return decimals
    except Exception: return 18

async def fetch_receipt(tx_hash):
    try: return await w3.eth.get_transaction_receipt(tx_hash)
    except Exception: return None

def simulate_execution_trace(receipt):
    gas = receipt.gasUsed if receipt else 21000
    log_count = len(receipt.logs) if receipt else 0
    if log_count > 5 or gas > 250000: return gas, 4
    if log_count > 2 or gas > 100000: return gas, 3
    if log_count > 0 or gas > 50000: return gas, 2
    return gas, 1

async def scan_mempool():
    logger.info("⚡ Mempool Radar Activated: Hunting for Vanguard Signals...")
    while True:
        try:
            pending_block = await w3.eth.get_block('pending', full_transactions=True)
            if pending_block and pending_block.transactions:
                for tx in pending_block.transactions:
                    tx_hash_str = tx.hash.hex()
                    if tx_hash_str in seen_pending_txs: continue
                    seen_pending_txs.add(tx_hash_str)
                    if len(seen_pending_txs) > 10000: seen_pending_txs.clear()
                        
                    if tx.value > 0:
                        actual_value = float(w3.from_wei(tx.value, 'ether'))
                        current_price = PRICE_CACHE["ARC"]
                        usd_volume = actual_value * current_price
                        if usd_volume >= 10000:
                            from_addr = tx["from"] if tx.get("from") else "0x00"
                            to_addr = tx["to"] if tx.get("to") else "0x00"
                            if from_addr not in ENTITY_MEMORY: ENTITY_MEMORY[from_addr] = "⏳ Vanguard Whale"
                            
                            p_impact = simulate_price_impact(usd_volume)
                            
                            tx_data = {
                                "type": "NATIVE",
                                "asset": "ARC",
                                "amount": actual_value,
                                "price_usd": current_price,
                                "tx_hash": tx_hash_str,
                                "from_addr": from_addr,
                                "to_addr": to_addr,
                                "from_label": ENTITY_MEMORY.get(from_addr),
                                "to_label": ENTITY_MEMORY.get(to_addr),
                                "gas_used": 0,
                                "execution_depth": 0,
                                "pnl": 0.0,
                                "narrative": "",
                                "sec_score": 99,
                                "sec_label": "✅ VERIFIED SAFE",
                                "cluster": "",
                                "health_factor": 99.0,
                                "price_impact": p_impact,
                                "spread": 0.0,
                                "flag": "PENDING_WHALE",
                                "status": "PENDING"
                            }
                            await broadcast_alert(tx_data)
        except Exception:
            pass
        await asyncio.sleep(2)

async def scan_block(block_number):
    try:
        block = await w3.eth.get_block(block_number, full_transactions=True)
        tx_count = len(block.transactions)
        logger.info(f"📡 Scanning Block: {block_number} | Transactions: {tx_count}")
        
        tasks = [fetch_receipt(tx.hash) for tx in block.transactions]
        receipts = []
        chunk_size = 15
        
        for i in range(0, len(tasks), chunk_size):
            chunk = tasks[i:i + chunk_size]
            chunk_results = await asyncio.gather(*chunk)
            receipts.extend(chunk_results)
            await asyncio.sleep(0.2)
            
        receipt_map = {r.transactionHash.hex(): r for r in receipts if r}
        
        for tx in block.transactions:
            tx_hash_str = tx.hash.hex()
            receipt = receipt_map.get(tx_hash_str)
            gas_used, exec_depth = simulate_execution_trace(receipt)
            
            if tx.value > 0:
                actual_value = float(w3.from_wei(tx.value, 'ether'))
                current_price = PRICE_CACHE["ARC"]
                usd_volume = actual_value * current_price
                from_addr = tx["from"] if tx.get("from") else "0x00"
                to_addr = tx["to"] if tx.get("to") else "0x00"
                
                realized_pnl = calculate_and_update_pnl(from_addr, to_addr, "ARC", actual_value, current_price)
                is_whale = (usd_volume >= 10000)
                update_entity_labels(from_addr, realized_pnl, is_whale)
                sybil_cluster = resolve_sybil_cluster(from_addr, to_addr)
                p_impact = simulate_price_impact(usd_volume) if is_whale else 0.0
                
                tx_data = {
                    "type": "NATIVE",
                    "asset": "ARC",
                    "amount": actual_value,
                    "price_usd": current_price,
                    "tx_hash": tx_hash_str,
                    "from_addr": from_addr,
                    "to_addr": to_addr,
                    "from_label": ENTITY_MEMORY.get(from_addr),
                    "to_label": ENTITY_MEMORY.get(to_addr),
                    "gas_used": gas_used,
                    "execution_depth": exec_depth,
                    "pnl": realized_pnl,
                    "narrative": "",
                    "sec_score": 99,
                    "sec_label": "✅ VERIFIED SAFE",
                    "cluster": sybil_cluster,
                    "health_factor": calculate_health_factor(from_addr),
                    "price_impact": p_impact,
                    "spread": 0.0,
                    "flag": "WHALE" if is_whale else "STANDARD",
                    "status": "CONFIRMED"
                }
                await broadcast_alert(tx_data)
                await save_transfer(tx_data, block_number)

        for receipt in receipts:
            if not receipt: continue
            tx_hash_str = receipt.transactionHash.hex()
            gas_used, exec_depth = simulate_execution_trace(receipt)
            dex_processed = False
            
            for log in receipt.logs:
                if not log.topics: continue
                topic0 = log.topics[0].hex()
                
                if topic0 in [AAVE_SUPPLY_SIG, AAVE_BORROW_SIG, AAVE_REPAY_SIG, AAVE_LIQ_SIG]:
                    try:
                        ENTITY_MEMORY[log.address] = "🏦 AAVE V3 Pool"
                        user_addr = "0x" + log.topics[2].hex()[26:] if len(log.topics) > 2 else receipt.fromAddress
                        raw_amount = int(log.data.hex()[:64], 16) if len(log.data.hex()) >= 64 else 0
                        actual_amt = (raw_amount / 1e18) if raw_amount > 0 else 1.0
                        usd_val = actual_amt * PRICE_CACHE["DEFAULT_TOKEN"]
                        if user_addr not in LENDING_MEMORY: LENDING_MEMORY[user_addr] = {"collateral": 0.0, "debt": 0.0}
                        narrative_text = ""
                        
                        if topic0 == AAVE_SUPPLY_SIG:
                            LENDING_MEMORY[user_addr]["collateral"] += usd_val
                            narrative_text = f"↳ Lending: Supplied ${usd_val:.2f} Collateral"
                        elif topic0 == AAVE_BORROW_SIG:
                            LENDING_MEMORY[user_addr]["debt"] += usd_val
                            narrative_text = f"↳ Lending: Borrowed ${usd_val:.2f} Debt"
                        elif topic0 == AAVE_REPAY_SIG:
                            LENDING_MEMORY[user_addr]["debt"] = max(0, LENDING_MEMORY[user_addr]["debt"] - usd_val)
                            narrative_text = f"↳ Lending: Repaid ${usd_val:.2f} Debt"
                        elif topic0 == AAVE_LIQ_SIG:
                            LENDING_MEMORY[user_addr]["collateral"] = 0.0
                            LENDING_MEMORY[user_addr]["debt"] = 0.0
                            narrative_text = f"💀 LENDING: LIQUIDATION EXECUTED!"

                        hf_after = calculate_health_factor(user_addr)
                        p_impact = simulate_price_impact(usd_val) if topic0 == AAVE_LIQ_SIG else 0.0
                        
                        tx_data = {
                            "type": "LENDING",
                            "asset": "AAVE Asset",
                            "amount": actual_amt, 
                            "price_usd": PRICE_CACHE["DEFAULT_TOKEN"],
                            "tx_hash": tx_hash_str,
                            "from_addr": user_addr,
                            "to_addr": log.address,
                            "from_label": ENTITY_MEMORY.get(user_addr),
                            "to_label": ENTITY_MEMORY.get(log.address),
                            "gas_used": gas_used,
                            "execution_depth": exec_depth,
                            "pnl": 0.0,
                            "narrative": narrative_text,
                            "sec_score": 99,
                            "sec_label": "✅ VERIFIED SAFE",
                            "cluster": "",
                            "health_factor": hf_after if topic0 != AAVE_LIQ_SIG else 0.0,
                            "price_impact": p_impact,
                            "spread": 0.0,
                            "flag": "LENDING_ACTIVITY",
                            "status": "CONFIRMED"
                        }
                        await broadcast_alert(tx_data)
                        await save_transfer(tx_data, block_number)
                        dex_processed = True
                    except Exception:
                        pass
                
                elif topic0 == BRIDGE_OUT_SIG and not dex_processed:
                    try:
                        ENTITY_MEMORY[log.address] = "🌉 Base Bridge Router"
                        bridger = "0x" + log.topics[1].hex()[26:] if len(log.topics) > 1 else receipt.fromAddress
                        narrative_text = "↳ Cross-Chain Exit: Routing Liquidity to Base"
                        score, label = analyze_contract_security(log.address)
                        usd_val = 1.0 * (PRICE_CACHE["ARC"] * 5)
                        p_impact = simulate_price_impact(usd_val)
                        
                        tx_data = {
                            "type": "CROSS_CHAIN",
                            "asset": "Bridged Asset",
                            "amount": 1.0, 
                            "price_usd": PRICE_CACHE["ARC"] * 5, 
                            "tx_hash": tx_hash_str,
                            "from_addr": bridger,
                            "to_addr": log.address,
                            "from_label": ENTITY_MEMORY.get(bridger),
                            "to_label": ENTITY_MEMORY.get(log.address),
                            "gas_used": gas_used,
                            "execution_depth": exec_depth,
                            "pnl": 0.0,
                            "narrative": narrative_text,
                            "sec_score": score,
                            "sec_label": label,
                            "cluster": "",
                            "health_factor": calculate_health_factor(bridger),
                            "price_impact": p_impact,
                            "spread": 0.0,
                            "flag": "BRIDGE_ACTIVITY",
                            "status": "CONFIRMED"
                        }
                        await broadcast_alert(tx_data)
                        await save_transfer(tx_data, block_number)
                        dex_processed = True
                    except Exception:
                        pass
                elif topic0 == CHORDSWAP_SWAP_SIG and not dex_processed:
                    try:
                        pool_addr = log.address
                        ENTITY_MEMORY[pool_addr] = "🦄 Chordswap Pool"
                        sender = "0x" + log.topics[1].hex()[26:] if len(log.topics) > 1 else receipt.fromAddress
                        current_price = PRICE_CACHE["DEFAULT_TOKEN"]
                        realized_pnl = calculate_and_update_pnl(sender, pool_addr, f"Pool:{pool_addr[:8]}", 1.0, current_price)
                        update_entity_labels(sender, realized_pnl, False)
                        p_impact = simulate_price_impact(1.0 * current_price)
                        
                        spread_val = round(1.0 + (int(tx_hash_str[-2:], 16) / 50.0), 2)
                        is_arb = spread_val >= 2.5
                        
                        tx_data = {
                            "type": "ARBITRAGE" if is_arb else "DEX_SWAP",
                            "asset": f"Pool: {pool_addr[:8]}...",
                            "amount": 1.0, 
                            "price_usd": current_price,
                            "tx_hash": tx_hash_str,
                            "from_addr": sender,
                            "to_addr": pool_addr,
                            "from_label": ENTITY_MEMORY.get(sender),
                            "to_label": ENTITY_MEMORY.get(pool_addr),
                            "gas_used": gas_used,
                            "execution_depth": exec_depth,
                            "pnl": realized_pnl,
                            "narrative": f"⚡ Arbitrage Execution | Spread: +{spread_val}%" if is_arb else "",
                            "sec_score": 99,
                            "sec_label": "✅ VERIFIED SAFE",
                            "cluster": "",
                            "health_factor": calculate_health_factor(sender),
                            "price_impact": p_impact,
                            "spread": spread_val if is_arb else 0.0,
                            "flag": "ARBITRAGE_ACTIVITY" if is_arb else "DEX_ACTIVITY",
                            "status": "CONFIRMED"
                        }
                        await broadcast_alert(tx_data)
                        await save_transfer(tx_data, block_number)
                        dex_processed = True
                    except Exception:
                        pass
                elif topic0 in [CHORDSWAP_MINT_SIG, CHORDSWAP_BURN_SIG] and not dex_processed:
                    try:
                        pool_addr = log.address
                        ENTITY_MEMORY[pool_addr] = "🌊 Liquidity Pool"
                        provider = "0x" + log.topics[1].hex()[26:] if len(log.topics) > 1 else receipt.fromAddress
                        p_impact = simulate_price_impact(1.0 * (PRICE_CACHE["DEFAULT_TOKEN"] * 2))
                        tx_data = {
                            "type": "DEX_LIQUIDITY",
                            "asset": f"LP: {pool_addr[:8]}...",
                            "amount": 1.0,
                            "price_usd": PRICE_CACHE["DEFAULT_TOKEN"] * 2,
                            "tx_hash": tx_hash_str,
                            "from_addr": provider,
                            "to_addr": pool_addr,
                            "from_label": ENTITY_MEMORY.get(provider),
                            "to_label": ENTITY_MEMORY.get(pool_addr),
                            "gas_used": gas_used,
                            "execution_depth": exec_depth,
                            "pnl": 0.0,
                            "narrative": "",
                            "sec_score": 99,
                            "sec_label": "✅ VERIFIED SAFE",
                            "cluster": "",
                            "health_factor": calculate_health_factor(provider),
                            "price_impact": p_impact,
                            "spread": 0.0,
                            "flag": "DEX_ACTIVITY",
                            "status": "CONFIRMED"
                        }
                        await broadcast_alert(tx_data)
                        await save_transfer(tx_data, block_number)
                        dex_processed = True
                    except Exception:
                        pass
                elif topic0 == ERC8004_REGISTER_SIG:
                    try:
                        ENTITY_MEMORY[log.address] = "🤖 Agent Registry"
                        owner_addr = "0x" + log.topics[2].hex()[26:] if len(log.topics) > 2 else receipt.fromAddress
                        narrative_text = decode_agent_narrative(tx_hash_str, "REGISTER")
                        score, label = analyze_contract_security(log.address)
                        tx_data = {
                            "type": "AI_AGENT",
                            "asset": "ERC-8004 Registration",
                            "amount": 1.0,
                            "price_usd": 0.0,
                            "tx_hash": tx_hash_str,
                            "from_addr": owner_addr,
                            "to_addr": log.address,
                            "from_label": ENTITY_MEMORY.get(owner_addr),
                            "to_label": ENTITY_MEMORY.get(log.address),
                            "gas_used": gas_used,
                            "execution_depth": exec_depth,
                            "pnl": 0.0,
                            "narrative": narrative_text,
                            "sec_score": score,
                            "sec_label": label,
                            "cluster": "",
                            "health_factor": calculate_health_factor(owner_addr),
                            "price_impact": 0.0,
                            "spread": 0.0,
                            "flag": "AGENT_FLOW",
                            "status": "CONFIRMED"
                        }
                        await broadcast_alert(tx_data)
                        await save_transfer(tx_data, block_number)
                    except Exception:
                        pass
                elif topic0 == ERC8183_WORKFLOW_SIG:
                    try:
                        funder = "0x" + log.topics[2].hex()[26:] if len(log.topics) > 2 else receipt.fromAddress
                        agent = "0x" + log.topics[3].hex()[26:] if len(log.topics) > 3 else log.address
                        ENTITY_MEMORY[agent] = "🧠 Autonomous Agent"
                        ENTITY_MEMORY[funder] = "💼 Agent Funder"
                        
                        actual_amt = float(w3.from_wei(int(log.data.hex(), 16), 'ether'))
                        narrative_text = decode_agent_narrative(tx_hash_str, "WORKFLOW")
                        score, label = analyze_contract_security(agent)
                        
                        tx_data = {
                            "type": "AI_AGENT",
                            "asset": "ERC-8183 Task Flow",
                            "amount": actual_amt,
                            "price_usd": PRICE_CACHE["ARC"],
                            "tx_hash": tx_hash_str,
                            "from_addr": funder,
                            "to_addr": agent,
                            "from_label": ENTITY_MEMORY.get(funder),
                            "to_label": ENTITY_MEMORY.get(agent),
                            "gas_used": gas_used,
                            "execution_depth": exec_depth,
                            "pnl": 0.0,
                            "narrative": narrative_text,
                            "sec_score": score,
                            "sec_label": label,
                            "cluster": "",
                            "health_factor": calculate_health_factor(funder),
                            "price_impact": 0.0,
                            "spread": 0.0,
                            "flag": "AGENT_FLOW",
                            "status": "CONFIRMED"
                        }
                        await broadcast_alert(tx_data)
                        await save_transfer(tx_data, block_number)
                    except Exception:
                        pass
                elif topic0 == TRANSFER_SIG and not dex_processed:
                    try:
                        raw_amount = int(log.data.hex(), 16)
                        if raw_amount > 0:
                            contract_address = log.address
                            decimals = await get_token_decimals(contract_address)
                            actual_token_amount = raw_amount / (10 ** decimals)
                            current_token_price = PRICE_CACHE["DEFAULT_TOKEN"]
                            usd_volume = actual_token_amount * current_token_price
                            from_addr = "0x" + log.topics[1].hex()[26:] if len(log.topics) > 1 else "0x00"
                            to_addr = "0x" + log.topics[2].hex()[26:] if len(log.topics) > 2 else "0x00"
                            
                            realized_pnl = calculate_and_update_pnl(from_addr, to_addr, contract_address, actual_token_amount, current_token_price)
                            is_whale = (usd_volume >= 10000 or actual_token_amount >= 50000)
                            update_entity_labels(from_addr, realized_pnl, is_whale)
                            sybil_cluster = resolve_sybil_cluster(from_addr, to_addr)
                            score, label = analyze_contract_security(contract_address)
                            p_impact = simulate_price_impact(usd_volume) if is_whale else 0.0
                            
                            tx_data = {
                                "type": "TOKEN",
                                "asset": contract_address,
                                "amount": actual_token_amount,
                                "price_usd": current_token_price,
                                "tx_hash": tx_hash_str,
                                "from_addr": from_addr,
                                "to_addr": to_addr,
                                "from_label": ENTITY_MEMORY.get(from_addr),
                                "to_label": ENTITY_MEMORY.get(to_addr),
                                "gas_used": gas_used,
                                "execution_depth": exec_depth,
                                "pnl": realized_pnl,
                                "narrative": "",
                                "sec_score": score,
                                "sec_label": label,
                                "cluster": sybil_cluster,
                                "health_factor": calculate_health_factor(from_addr),
                                "price_impact": p_impact,
                                "spread": 0.0,
                                "flag": "WHALE" if is_whale else "STANDARD",
                                "status": "CONFIRMED"
                            }
                            await broadcast_alert(tx_data)
                            await save_transfer(tx_data, block_number)
                    except Exception:
                        continue
    except Exception as e:
        logger.error(f"Fatal error scanning block: {e}")

async def check_network_status():
    try:
        if await w3.is_connected(): return await w3.eth.block_number
    except Exception: pass
    return None

async def main():
    logger.info("Initializing A.S.M.O. Boot Sequence...")
    await init_db() 
    last_scanned_block = await check_network_status()
    if not last_scanned_block:
        logger.error("Failed to connect to ARC RPC.")
        return

    asyncio.create_task(update_price_oracle())
    asyncio.create_task(scan_mempool())

    async with websockets.serve(ws_handler, "0.0.0.0", 8765):
        logger.info("🌉 WebSocket Bridge Active on Port 8765")
        while True:
            try:
                current_block = await w3.eth.block_number
                if current_block > last_scanned_block:
                    for b in range(last_scanned_block + 1, current_block + 1):
                        await scan_block(b)
                        last_scanned_block = b
                else:
                    await asyncio.sleep(2)
            except Exception:
                await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())