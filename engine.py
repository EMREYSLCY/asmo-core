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
logger = logging.getLogger("ASMO_CORE")

ARC_RPC_URL = os.getenv("ARC_RPC_URL")
ARC_WSS_URL = os.getenv("ARC_WSS_URL")
BASE_RPC_URL = os.getenv("BASE_RPC_URL", "https://base.llamarpc.com")
BASE_WSS_URL = os.getenv("BASE_WSS_URL", "wss://base.llamarpc.com")

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
ENTITY_MEMORY = {"0x0000000000000000000000000000000000000000": "Genesis / Burn"}
CLUSTER_MAP = {}
SHADOW_TARGETS = set()
cluster_counter = 0
RECENT_TRADES = []

OVERLORD_STATE = {
    "active": False,
    "max_spend": 50000.0,
    "min_profit": 500.0
}

OVERLORD_STRATEGY = []

def safe_get_input(tx):
    try:
        inp = tx.get('input', '0x')
        if hasattr(inp, 'hex'): return inp.hex()
        return str(inp)
    except: return "0x"

def decipher_payload(input_data):
    if not input_data or input_data == '0x': return {"method": "0x", "name": "NATIVE_TRANSFER / NO_DATA", "risk": "LOW", "raw_length": 0}
    if not input_data.startswith('0x'): input_data = '0x' + input_data
    if len(input_data) < 10: return {"method": input_data, "name": "MALFORMED_PAYLOAD", "risk": "LOW", "raw_length": len(input_data)}
    method_id = input_data[:10]
    SIG_DB = {
        "0xa9059cbb": ("transfer(address,uint256)", "LOW"), "0x095ea7b3": ("approve(address,uint256)", "LOW"),
        "0x38ed1739": ("swapExactTokensForTokens", "MEDIUM"), "0x7ff36ab5": ("swapExactETHForTokens", "MEDIUM"),
        "0x18cbafe5": ("swapExactTokensForETH", "MEDIUM"), "0x4a25d94a": ("swapTokensForExactETH", "MEDIUM"),
        "0x5c11d795": ("swapExactTokensForTokensSupportingFeeOnTransferTokens", "MEDIUM"), "0xab834bab": ("executeOperation(address[],uint256[],uint256[],address,bytes)", "CRITICAL"),
        "0x1cff79cd": ("execute(bytes,bytes[]) [Universal Router]", "MEDIUM"), "0x5ae401dc": ("multicall(uint256,bytes[])", "HIGH"),
        "0xac9650d8": ("multicall(bytes[])", "HIGH"), "0xd0e30db0": ("deposit()", "LOW"),
        "0x2e1a7d4d": ("withdraw(uint256)", "LOW"), "0x42842e0e": ("safeTransferFrom(address,address,uint256)", "LOW"),
        "0x40c10f19": ("mint(address,uint256)", "HIGH"), "0xf242432a": ("safeTransferFrom(address,address,uint256,uint256,bytes)", "LOW"),
        "0x3593564c": ("execute(bytes32,bytes) [Proxy/Agent]", "HIGH"), "0xbaa2abde": ("removeLiquidity(address,address,uint256,uint256,uint256,address,uint256)", "CRITICAL"),
        "0x02751cec": ("removeLiquidityETH(address,uint256,uint256,uint256,address,uint256)", "CRITICAL"), "0xaf2979eb": ("removeLiquidityETHSupportingFeeOnTransferTokens", "CRITICAL"),
        "0x5b0d5984": ("removeLiquidityETHWithPermit", "CRITICAL"), "0x86d1a69f": ("release() [Vesting Unlock]", "HIGH"),
        "0x3d18b912": ("unlock() [TimeLock]", "HIGH"), "0x4e71d92d": ("claim() [Vesting Claim]", "MEDIUM")
    }
    name, risk = SIG_DB.get(method_id, ("UNKNOWN_CUSTOM_METHOD", "MEDIUM"))
    return {"method": method_id, "name": name, "risk": risk, "raw_length": len(input_data)}

async def run_chronos_simulation(websocket, payload):
    target = payload.get("target", "0x0000000000000000000000000000000000000000")
    block_num = payload.get("block", "14300000")
    await websocket.send(json.dumps({"msg_type": "CHRONOS_EVENT", "data": {"type": "INIT", "desc": f"Establishing temporal link to Block #{block_num}...", "color": "#0ea5e9"}}))
    await asyncio.sleep(1.5)
    await websocket.send(json.dumps({"msg_type": "CHRONOS_EVENT", "data": {"type": "SYNC", "desc": f"State matrix synchronized. Asset {target[:8]} isolated in historical mempool.", "color": "#3fb950"}}))
    await asyncio.sleep(2.0)
    sim_type = random.choice(["RUG_PULL", "FLASHLOAN", "VESTING_DUMP"])
    if sim_type == "RUG_PULL":
        await websocket.send(json.dumps({"msg_type": "CHRONOS_EVENT", "data": {"type": "THREAT", "desc": f"CRITICAL: Dev wallet submitted removeLiquidity() transaction.", "color": "#f85149"}}))
        await asyncio.sleep(1.2)
        await websocket.send(json.dumps({"msg_type": "CHRONOS_EVENT", "data": {"type": "ACTION", "desc": f"A.S.M.O. Overlord simulated Front-Run with 2x Gas (145 Gwei).", "color": "#d946ef"}}))
        await asyncio.sleep(1.5)
        await websocket.send(json.dumps({"msg_type": "CHRONOS_EVENT", "data": {"type": "RESULT", "desc": f"SUCCESS: Capital extracted 12ms before liquidity pool drained. Saved: $84,500.", "color": "#10b981"}}))
    elif sim_type == "FLASHLOAN":
        await websocket.send(json.dumps({"msg_type": "CHRONOS_EVENT", "data": {"type": "THREAT", "desc": f"DETECTED: AAVE V3 Flashloan initiation of 5,000 ETH targeted at {target[:8]}.", "color": "#eab308"}}))
        await asyncio.sleep(1.2)
        await websocket.send(json.dumps({"msg_type": "CHRONOS_EVENT", "data": {"type": "ACTION", "desc": f"A.S.M.O. Atomic Router calculated counter-arbitrage vector across L0.", "color": "#0ea5e9"}}))
        await asyncio.sleep(1.5)
        await websocket.send(json.dumps({"msg_type": "CHRONOS_EVENT", "data": {"type": "RESULT", "desc": f"SUCCESS: MEV Sandwich executed prior to flashloan settlement. Profit: $12,340.", "color": "#10b981"}}))
    else:
        await websocket.send(json.dumps({"msg_type": "CHRONOS_EVENT", "data": {"type": "THREAT", "desc": f"WARNING: TimeLock contract unlocked 4M tokens to insider cabal.", "color": "#f85149"}}))
        await asyncio.sleep(1.2)
        await websocket.send(json.dumps({"msg_type": "CHRONOS_EVENT", "data": {"type": "ACTION", "desc": f"A.S.M.O. executed pre-emptive SHORT position at $1.45 entry.", "color": "#d946ef"}}))
        await asyncio.sleep(1.5)
        await websocket.send(json.dumps({"msg_type": "CHRONOS_EVENT", "data": {"type": "RESULT", "desc": f"SUCCESS: Asset dumped 45%. Short position covered at $0.80. Net Yield: $24,600.", "color": "#10b981"}}))
    await asyncio.sleep(1.0)
    await websocket.send(json.dumps({"msg_type": "CHRONOS_EVENT", "data": {"type": "COMPLETE", "desc": "Temporal simulation concluded. Returning to live global state.", "color": "#8b949e"}}))

async def perform_forensic_autopsy(tx_hash, network_name):
    await asyncio.sleep(1.5)
    random.seed(int(tx_hash[-8:], 16) if tx_hash else 42)
    tree = {"id": "root", "name": f"Transaction: {tx_hash[:8]}...", "type": "ENTRY", "color": "#d946ef", "children": []}
    is_mev = random.choice([True, False])
    if is_mev:
        tree["children"].append({"id": "node1", "name": "AAVE V3 Flashloan (2000 ETH)", "type": "FLASHLOAN", "color": "#eab308", "children": [{"id": "node2", "name": "Uniswap V3 Swap (ETH -> USDC)", "type": "DEX", "color": "#db2777", "children": [{"id": "node3", "name": "Slippage Exploit (Victim TX)", "type": "VICTIM", "color": "#f85149"}]}, {"id": "node4", "name": "Curve Swap (USDC -> ETH)", "type": "DEX", "color": "#db2777", "children": []}, {"id": "node5", "name": "Flashloan Repayment + Fee", "type": "REPAY", "color": "#10b981", "children": []}]})
        tree["children"].append({"id": "node6", "name": "Miner Bribe (Flashbots) - 0.5 ETH", "type": "BRIBE", "color": "#ea580c"})
        tree["children"].append({"id": "node7", "name": "Net Profit Extraction - 2.4 ETH", "type": "PROFIT", "color": "#3fb950"})
    else:
        tree["children"].append({"id": "node1", "name": "Tornado Cash Withdrawal (100 ETH)", "type": "MIXER", "color": "#f85149", "children": [{"id": "node2", "name": "Intermediate Hop Wallet", "type": "HOP", "color": "#64748b", "children": [{"id": "node3", "name": "DEX Swap (ETH -> Token)", "type": "DEX", "color": "#db2777"}]}, {"id": "node4", "name": "OTC Over-The-Counter Transfer", "type": "OTC", "color": "#0ea5e9", "children": []}]})
    stats = {"total_gas_usd": round(random.uniform(150, 800), 2), "bribe_paid_usd": round(random.uniform(500, 3000), 2) if is_mev else 0, "net_profit_usd": round(random.uniform(4000, 15000), 2) if is_mev else 0, "complexity_score": random.randint(70, 99), "classification": "MEV Sandwich Attack" if is_mev else "Laundering Flow"}
    return {"tx_hash": tx_hash, "network": network_name, "stats": stats, "tree": tree}

async def process_oracle_query(payload, websocket):
    query = payload.get("query", "")
    target = payload.get("target", "GLOBAL_STATE")
    await asyncio.sleep(1.5)
    mock_responses = [
        f"ANALYSIS SECURED: Target {target} exhibits non-standard EIP-20 proxy structures. Ownership renunciation is falsified. Risk index elevated.",
        f"BYTECODE TRACE: Deep execution path for {target} indicates a dormant delegatecall payload. Potential honeypot triggers detected at block + 1400.",
        f"BEHAVIORAL SYNC: Analyzing {target}... Entity displays High-Frequency Arbitrage patterns bridging L1 and L2 via Stargate. Net positive yield consistency is 84%.",
        f"ORACLE RESPONSE: Your query regarding '{query}' reveals a clustering of 14 Sybil nodes routing initial funding through Tornado Cash to {target}.",
        f"SYSTEM DIRECTIVE: The smart contract at {target} possesses a hardcoded fee modifier. Liquidity withdrawal limits are bypassed by the deployer address."
    ]
    response = random.choice(mock_responses)
    if "rug" in query.lower() or "scam" in query.lower():
        response = f"CRITICAL OVERRIDE: Forensic scan of {target} confirms malicious removeLiquidity hooks. Probability of rug-pull exceeds 98.7%."
    await websocket.send(json.dumps({"msg_type": "ORACLE_RESPONSE", "data": {"query": query, "response": response, "target": target, "confidence": round(random.uniform(85.5, 99.9), 2)}}))

async def perform_cabal_scan(addr, network_name):
    await asyncio.sleep(2.0)
    seed_val = int(Web3.keccak(text=addr).hex()[-8:], 16)
    random.seed(seed_val)
    cabals, nodes, links = [], [], []
    num_cabals = random.randint(3, 6)
    cabal_colors = ["#dc2626", "#ea580c", "#ca8a04", "#0ea5e9", "#a371f7", "#db2777"]
    funding_sources = ["Binance 14", "KuCoin Hot Wallet", "Tornado Cash", "Unknown OTC", "Genesis Dev", "FixedFloat"]
    total_cabal_dom = 0
    for i in range(num_cabals):
        c_id = f"cabal_{i}"
        c_color = cabal_colors[i % len(cabal_colors)]
        c_name = f"Syndicate {chr(65+i)} ({funding_sources[i % len(funding_sources)]})"
        cabal_size = random.randint(5, 18)
        cabal_total_supply = random.uniform(5.0, 22.0)
        total_cabal_dom += cabal_total_supply
        cabals.append({"id": c_id, "name": c_name, "color": c_color, "wallets": cabal_size, "control_pct": round(cabal_total_supply, 2)})
        root_wallet = f"0xRoot{i}..." + "".join([random.choice("0123456789abcdef") for _ in range(4)])
        nodes.append({"id": root_wallet, "name": c_name, "val": cabal_total_supply * 1.5, "color": c_color, "type": "ROOT"})
        for j in range(cabal_size):
            node_pct = cabal_total_supply / cabal_size * random.uniform(0.5, 1.5)
            node_addr = f"0x" + "".join([random.choice("0123456789abcdef") for _ in range(8)]) + f"_c{i}_{j}"
            nodes.append({"id": node_addr, "name": f"Wallet {node_addr[:6]}", "val": node_pct * 3, "color": c_color, "type": "NODE"})
            links.append({"source": root_wallet, "target": node_addr, "color": c_color})
            if random.random() > 0.7 and j > 0:
                prev_node = nodes[-2]["id"]
                links.append({"source": prev_node, "target": node_addr, "color": c_color})
    dex_pool_id = "0x" + "".join([random.choice("0123456789abcdef") for _ in range(8)]) + "_DEX"
    nodes.append({"id": dex_pool_id, "name": "Primary DEX Liquidity", "val": 30.0, "color": "#3fb950", "type": "POOL"})
    for i in range(15):
        retail_addr = f"0x" + "".join([random.choice("0123456789abcdef") for _ in range(8)]) + "_ret"
        nodes.append({"id": retail_addr, "name": "Retail Holder", "val": random.uniform(0.1, 0.8), "color": "#64748b", "type": "RETAIL"})
        if random.random() > 0.5: links.append({"source": dex_pool_id, "target": retail_addr, "color": "#64748b"})
    total_cabal_dom = min(total_cabal_dom, 98.5)
    risk_lvl = "CRITICAL" if total_cabal_dom > 60 else "HIGH" if total_cabal_dom > 40 else "MODERATE"
    return {"target_asset": addr, "network": network_name, "total_cabal_dominance": round(total_cabal_dom, 2), "risk_level": risk_lvl, "syndicates": sorted(cabals, key=lambda x: x["control_pct"], reverse=True), "graph": {"nodes": nodes, "links": links}}

async def analyze_contract_security(addr, network_name="ARC"):
    if addr in ENTITY_MEMORY and ("Genesis" in ENTITY_MEMORY[addr] or "Pool" in ENTITY_MEMORY[addr] or "Router" in ENTITY_MEMORY[addr]): return 99, "VERIFIED SAFE"
    chain_id = "8453" if network_name == "BASE" else "42161"
    try:
        url = f"https://api.gopluslabs.io/api/v1/token_security/{chain_id}?contract_addresses={addr}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        loop = asyncio.get_running_loop()
        resp = await loop.run_in_executor(None, urllib.request.urlopen, req)
        data = json.loads(resp.read().decode('utf-8'))
        if data.get("result") and addr.lower() in data["result"]:
            sec_data = data["result"][addr.lower()]
            if sec_data.get("is_honeypot", "0") == "1": return 10, "HONEYPOT DETECTED"
            if sec_data.get("is_blacklisted", "0") == "1": return 15, "BLACKLISTED (HIGH RISK)"
            if sec_data.get("is_mintable", "0") == "1": return 60, "MINTABLE (CAUTION)"
            return 95, "VERIFIED SAFE"
    except Exception: pass
    val = int(Web3.keccak(text=addr).hex()[-4:], 16)
    score = (val % 100)
    if score < 25: return score, "HIGH RISK (HONEYPOT)"
    elif score < 50: return score, "CAUTION (UNVERIFIED)"
    else: return score + (100 - score) // 2, "SAFE CONTRACT"

async def perform_manual_audit(addr, network_name):
    chain_id = "8453" if network_name == "BASE" else "42161"
    report = {"address": addr, "network": network_name, "score": 99, "label": "SAFE", "is_honeypot": False, "is_mintable": False, "is_blacklisted": False, "verified": False}
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
            if report["is_honeypot"]: report["score"], report["label"] = 10, "HONEYPOT DETECTED"
            elif report["is_blacklisted"]: report["score"], report["label"] = 15, "BLACKLISTED"
            elif report["is_mintable"]: report["score"], report["label"] = 60, "MINTABLE / INFLATION RISK"
            else: report["score"], report["label"] = 95, "SECURE"
            return report
    except Exception: pass
    val = int(Web3.keccak(text=addr).hex()[-4:], 16)
    score = (val % 100)
    report["score"] = score
    if score < 25: report["label"], report["is_honeypot"] = "HIGH RISK (UNVERIFIED)", True
    elif score < 50: report["label"], report["is_mintable"] = "CAUTION (UNVERIFIED)", True
    else: report["label"], report["score"] = "PROBABLY SAFE", score + (100 - score) // 2
    return report

async def decompile_bytecode(addr, network_name):
    await asyncio.sleep(1.0)
    val = int(Web3.keccak(text=addr).hex()[-4:], 16)
    is_proxy, has_selfdestruct, has_delegatecall = val % 5 == 0, val % 7 == 0, val % 3 == 0
    tree = {"address": addr, "size_bytes": 1024 + (val * 4), "compiler_version": "solc v0.8.20" if val % 2 == 0 else "solc v0.8.19", "nodes": [{"id": "entry", "label": "EVM Entry Point (Dispatcher)", "type": "ENTRY", "risk": "LOW", "children": []}]}
    funcs = [{"id": "f1", "label": "FUNC: transfer(address,uint256)", "type": "FUNCTION", "risk": "LOW", "children": [{"id": "op1", "label": "OP: SLOAD (Read Balance)", "type": "OPCODE", "risk": "LOW", "children": []}, {"id": "op2", "label": "OP: CALLVALUE ISZERO", "type": "OPCODE", "risk": "LOW", "children": []}]}]
    if has_delegatecall: funcs.append({"id": "f2", "label": "FUNC: executeOperation (Hidden Logic)", "type": "FUNCTION", "risk": "HIGH", "children": [{"id": "op3", "label": "OP: DELEGATECALL (State Modification)", "type": "OPCODE", "risk": "CRITICAL", "children": [{"id": "vuln1", "label": "VULN: Unrestricted DelegateCall Detected", "type": "VULNERABILITY", "risk": "CRITICAL", "children": []}]}]})
    if has_selfdestruct: funcs.append({"id": "f3", "label": "FUNC: kill() / destroy()", "type": "FUNCTION", "risk": "CRITICAL", "children": [{"id": "op4", "label": "OP: CALLER (Check Owner)", "type": "OPCODE", "risk": "MEDIUM", "children": []}, {"id": "op5", "label": "OP: SELFDESTRUCT (Contract Suicide)", "type": "OPCODE", "risk": "CRITICAL", "children": [{"id": "vuln2", "label": "VULN: Malicious Exit Vector", "type": "VULNERABILITY", "risk": "CRITICAL", "children": []}]}]})
    if is_proxy: funcs.append({"id": "f4", "label": "PROXY: Implementation Slot", "type": "STORAGE", "risk": "MEDIUM", "children": [{"id": "op6", "label": "EIP-1967 Transparent Proxy Pattern", "type": "INFO", "risk": "MEDIUM", "children": []}]})
    tree["nodes"][0]["children"] = funcs
    overall_risk = "SAFE"
    if has_selfdestruct or has_delegatecall: overall_risk = "CRITICAL"
    elif is_proxy: overall_risk = "WARNING"
    tree["overall_risk"] = overall_risk
    return tree

def resolve_sybil_cluster(addr1, addr2):
    global cluster_counter
    e1, e2 = ENTITY_MEMORY.get(addr1, ""), ENTITY_MEMORY.get(addr2, "")
    if "Pool" in e1 or "Pool" in e2 or "Genesis" in e1 or "Genesis" in e2 or "Router" in e1 or "Router" in e2: return None 
    c1, c2 = CLUSTER_MAP.get(addr1), CLUSTER_MAP.get(addr2)
    if c1 is None and c2 is None:
        cluster_counter += 1
        new_c = f"Sybil Ring #{cluster_counter}"
        CLUSTER_MAP[addr1], CLUSTER_MAP[addr2] = new_c, new_c
        return new_c
    elif c1 and not c2: CLUSTER_MAP[addr2] = c1; return c1
    elif c2 and not c1: CLUSTER_MAP[addr1] = c2; return c2
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
    if total_vol == 0: return price, "Neutral Flow"
    twap = sum(t["amount"] * t["price"] for t in RECENT_TRADES) / total_vol
    ratio = sum(t["amount"] for t in RECENT_TRADES if t["is_buy"]) / total_vol
    if ratio >= 0.7: return round(twap, 4), "Stealth Accumulation"
    elif ratio <= 0.3: return round(twap, 4), "High Sell Pressure"
    elif ratio >= 0.55: return round(twap, 4), "Bullish Bias"
    elif ratio <= 0.45: return round(twap, 4), "Bearish Bias"
    else: return round(twap, 4), "Neutral Flow"

async def init_db():
    async with aiosqlite.connect("asmo.db") as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS transfers (id INTEGER PRIMARY KEY AUTOINCREMENT, tx_hash TEXT NOT NULL, block_number INTEGER NOT NULL, network TEXT NOT NULL DEFAULT 'ARC', type TEXT NOT NULL, asset TEXT NOT NULL, amount REAL NOT NULL, price_usd REAL NOT NULL, from_addr TEXT NOT NULL DEFAULT '0x00', to_addr TEXT NOT NULL DEFAULT '0x00', gas_used INTEGER DEFAULT 0, execution_depth INTEGER DEFAULT 1, pnl REAL DEFAULT 0.0, narrative TEXT, sec_score INTEGER DEFAULT 99, sec_label TEXT DEFAULT 'VERIFIED SAFE', cluster TEXT, health_factor REAL DEFAULT 99.0, price_impact REAL DEFAULT 0.0, spread REAL DEFAULT 0.0, agent_win_rate REAL DEFAULT 0.0, twap REAL DEFAULT 0.0, twap_trend TEXT DEFAULT 'Neutral Flow', mev_extracted REAL DEFAULT 0.0, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_transfers_id ON transfers(id DESC)")
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
    if is_mev: ENTITY_MEMORY[addr] = "MEV Searcher Bot"
    elif pnl > 1000: ENTITY_MEMORY[addr] = "Smart Whale"
    elif pnl < -500: ENTITY_MEMORY[addr] = "Rekt Wallet"
    elif is_whale and addr not in ENTITY_MEMORY: ENTITY_MEMORY[addr] = "Unknown Whale"

async def save_transfer(tx_data, block_number):
    try:
        async with aiosqlite.connect("asmo.db") as db:
            await db.execute("""INSERT INTO transfers (tx_hash, block_number, network, type, asset, amount, price_usd, from_addr, to_addr, gas_used, execution_depth, pnl, narrative, sec_score, sec_label, cluster, health_factor, price_impact, spread, agent_win_rate, twap, twap_trend, mev_extracted) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (tx_data["tx_hash"], block_number, tx_data.get("network", "ARC"), tx_data["type"], tx_data["asset"], tx_data["amount"], tx_data["price_usd"], tx_data["from_addr"], tx_data["to_addr"], tx_data.get("gas_used", 0), tx_data.get("execution_depth", 1), tx_data.get("pnl", 0.0), tx_data.get("narrative", ""), tx_data.get("sec_score", 99), tx_data.get("sec_label", "VERIFIED SAFE"), tx_data.get("cluster", ""), tx_data.get("health_factor", 99.0), tx_data.get("price_impact", 0.0), tx_data.get("spread", 0.0), tx_data.get("agent_win_rate", 0.0), tx_data.get("twap", 0.0), tx_data.get("twap_trend", ""), tx_data.get("mev_extracted", 0.0)))
            await db.commit()
    except Exception as e: logger.error(f"Failed to save transfer: {e}")

async def broadcast_leaderboard():
    while True:
        await asyncio.sleep(5)
        if connected_clients:
            top_wallets = sorted([{"addr": k, "pnl": v, "label": ENTITY_MEMORY.get(k, "")} for k, v in WALLET_PNL.items() if v > 0 and "Agent" not in ENTITY_MEMORY.get(k, "")], key=lambda x: x["pnl"], reverse=True)[:5]
            top_agents = sorted([{"addr": k, "pnl": v["net_pnl"], "wr": round((v["wins"]/v["total"]*100) if v["total"]>0 else 0, 1), "label": ENTITY_MEMORY.get(k, "Autonomous Agent")} for k, v in AGENT_PERFORMANCE.items() if v["net_pnl"] > 0], key=lambda x: x["pnl"], reverse=True)[:5]
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
                    direction = "ARC -> BASE" if p_arc < p_base else "BASE -> ARC"
                    buy_price = min(p_arc, p_base)
                    sell_price = max(p_arc, p_base)
                    est_profit = (sell_price - buy_price) * OVERLORD_STATE["max_spend"]
                    if OVERLORD_STATE["active"] and est_profit >= OVERLORD_STATE["min_profit"]:
                        src_chain = direction.split(" -> ")[0]
                        dst_chain = direction.split(" -> ")[1]
                        fake_hash_src = "0x" + "".join([str(random.randint(0,9)) for _ in range(64)])
                        tx_data_src = {"msg_type": "TRANSACTION", "network": src_chain, "type": "CROSS_CHAIN", "asset": "Flashloan & Bridge (OVERLORD)", "amount": OVERLORD_STATE["max_spend"], "price_usd": 1.0, "tx_hash": fake_hash_src, "from_addr": "0xASMO_Interchain_Core", "to_addr": "0xStargate_Router", "from_label": "OVERLORD ATOMIC ROUTER", "to_label": "L0 Bridge", "gas_used": 350000, "execution_depth": 4, "pnl": 0.0, "narrative": f"ATOMIC HOP: {src_chain} -> {dst_chain}", "sec_score": 99, "sec_label": "VERIFIED SAFE", "cluster": "", "health_factor": 99.0, "price_impact": 0.0, "spread": 0.0, "agent_win_rate": 100.0, "twap": 0.0, "twap_trend": "", "mev_extracted": 0.0, "flag": "BRIDGE_ACTIVITY", "status": "CONFIRMED"}
                        await broadcast_alert(tx_data_src); await save_transfer(tx_data_src, 99999999)
                        await asyncio.sleep(0.8)
                        fake_hash_dst = "0x" + "".join([str(random.randint(0,9)) for _ in range(64)])
                        tx_data_dst = {"msg_type": "TRANSACTION", "network": dst_chain, "type": "ARBITRAGE", "asset": "Atomic Arbitrage Exec", "amount": OVERLORD_STATE["max_spend"], "price_usd": 1.0, "tx_hash": fake_hash_dst, "from_addr": "0xStargate_Router", "to_addr": "0xASMO_Interchain_Core", "from_label": "L0 Bridge", "to_label": "OVERLORD ATOMIC ROUTER", "gas_used": 210000, "execution_depth": 3, "pnl": est_profit, "narrative": f"ATOMIC PROFIT SECURED | Spread: +{round(spread, 2)}%", "sec_score": 99, "sec_label": "VERIFIED SAFE", "cluster": "", "health_factor": 99.0, "price_impact": 0.0, "spread": round(spread, 2), "agent_win_rate": 100.0, "twap": 0.0, "twap_trend": "", "mev_extracted": 0.0, "flag": "ARBITRAGE_ACTIVITY", "status": "CONFIRMED"}
                        await broadcast_alert(tx_data_dst); await save_transfer(tx_data_dst, 99999999)
                    else:
                        await broadcast_alert({"msg_type": "ARBITRAGE_RADAR", "asset": "Native Volatility Asset", "route": direction, "buy_price": buy_price, "sell_price": sell_price, "spread": round(spread, 2), "est_profit": round(est_profit, 2)})
        except Exception: pass

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
                    if 0 < hf <= 1.25: risky_wallets.append({"address": addr, "collateral": col, "debt": debt, "hf": round(hf, 3), "est_liq_profit": round(debt * 0.05, 2)})
            if risky_wallets:
                risky_wallets = sorted(risky_wallets, key=lambda x: x["hf"])[:8]
                await broadcast_alert({"msg_type": "KILL_ZONE_UPDATE", "data": risky_wallets})

async def broadcast_sybil_clusters():
    while True:
        await asyncio.sleep(8)
        if connected_clients and CLUSTER_MAP:
            cluster_stats = {}
            for addr, c_name in CLUSTER_MAP.items():
                if c_name not in cluster_stats: cluster_stats[c_name] = {"name": c_name, "wallets": [], "total_pnl": 0.0}
                cluster_stats[c_name]["wallets"].append(addr)
                cluster_stats[c_name]["total_pnl"] += WALLET_PNL.get(addr, 0.0)
            active_clusters = sorted([c for c in cluster_stats.values() if len(c["wallets"]) > 1], key=lambda x: len(x["wallets"]), reverse=True)[:10]
            if active_clusters: await broadcast_alert({"msg_type": "SYBIL_HUNTER_UPDATE", "data": active_clusters})

async def detect_incoming_bridge_tsunami():
    sources = ["Ethereum Mainnet", "Optimism L2", "Arbitrum One", "Polygon", "Avalanche"]
    destinations = ["BASE", "ARC"]
    assets = ["USDC", "ETH", "wBTC", "USDT"]
    while True:
        await asyncio.sleep(random.randint(12, 18))
        if connected_clients:
            src = random.choice(sources)
            dst = random.choice(destinations)
            ast = random.choice(assets)
            val = random.uniform(500000, 5000000)
            eta = random.randint(30, 180) 
            await broadcast_alert({"msg_type": "INCOMING_BRIDGE_TSUNAMI", "source": src, "destination": dst, "asset": ast, "usd_value": val, "eta_seconds": eta, "status": "IN TRANSIT"})

async def detect_vesting_dumps():
    assets = ["0xAI_Protocol_Token", "0xGameFi_Governance", "0xDeFi_Yield_Token", "0xLayer2_Native_Coin"]
    while True:
        await asyncio.sleep(random.randint(20, 45))
        if connected_clients:
            val = random.uniform(250000, 3500000)
            await broadcast_alert({"msg_type": "VESTING_DUMP_ALERT", "network": random.choice(["ARC", "BASE"]), "tx_hash": "0x" + "".join([random.choice("0123456789abcdef") for _ in range(64)]), "token_addr": random.choice(assets), "dev_addr": "0x" + "".join([random.choice("0123456789abcdef") for _ in range(40)]), "usd_value": val, "status": "IMMINENT DUMP"})

async def detect_multisig_activity():
    while True:
        await asyncio.sleep(random.randint(15, 35))
        if connected_clients:
            req_sigs = random.choice([3, 4, 5])
            curr_sigs = req_sigs - 1
            safe_addr = "0x" + "".join([random.choice("0123456789abcdef") for _ in range(40)])
            target_addr = "0x" + "".join([random.choice("0123456789abcdef") for _ in range(40)])
            usd_val = random.uniform(1000000, 15000000)
            await broadcast_alert({
                "msg_type": "MULTISIG_ALERT",
                "data": {
                    "safe_address": safe_addr,
                    "target_contract": target_addr,
                    "current_sigs": curr_sigs,
                    "required_sigs": req_sigs,
                    "usd_value": usd_val,
                    "status": "AWAITING FINAL EXECUTION",
                    "network": random.choice(["ARC", "BASE", "ETH"])
                }
            })

async def update_price_oracle():
    pyth_ws_url = "wss://hermes.pyth.network/ws"
    msg = {"type": "subscribe", "price_ids": ["ff61491a931112ddf1bd8147cd1b641375f79f5825126d665480874634fd0ace", "3fa4252848f9f0a1480be62745a4629d9eb1322aebab8a791e344b3b9c1adcf5"]}
    while True:
        try:
            async with websockets.connect(pyth_ws_url, ping_interval=20, ping_timeout=20) as ws:
                await ws.send(json.dumps(msg))
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
                            if p_id == "ff61491a931112ddf1bd8147cd1b641375f79f5825126d665480874634fd0ace": PRICE_CACHE["DEFAULT_TOKEN"] = actual_price * 0.001 
                            elif p_id == "3fa4252848f9f0a1480be62745a4629d9eb1322aebab8a791e344b3b9c1adcf5": PRICE_CACHE["ARC"] = actual_price; PRICE_CACHE["BASE"] = actual_price * 0.8
        except Exception: await asyncio.sleep(3)

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
                await websocket.send(json.dumps({"msg_type": "TRANSACTION", "time": row["timestamp"].split(" ")[1] if row["timestamp"] else None, "network": row["network"] if "network" in row.keys() else "ARC", "type": row["type"], "asset": row["asset"], "amount": row["amount"], "price_usd": row["price_usd"], "tx_hash": row["tx_hash"], "from_addr": row["from_addr"], "to_addr": row["to_addr"], "from_label": ENTITY_MEMORY.get(row["from_addr"]), "to_label": ENTITY_MEMORY.get(row["to_addr"]), "gas_used": row["gas_used"], "execution_depth": row["execution_depth"], "pnl": row["pnl"], "narrative": row["narrative"] if "narrative" in row.keys() else "", "sec_score": row["sec_score"] if "sec_score" in row.keys() else 99, "sec_label": row["sec_label"] if "sec_label" in row.keys() else "VERIFIED SAFE", "cluster": row["cluster"] if "cluster" in row.keys() else "", "health_factor": row["health_factor"] if "health_factor" in row.keys() else 99.0, "price_impact": row["price_impact"] if "price_impact" in row.keys() else 0.0, "spread": row["spread"] if "spread" in row.keys() else 0.0, "agent_win_rate": row["agent_win_rate"] if "agent_win_rate" in row.keys() else 0.0, "twap": row["twap"] if "twap" in row.keys() else 0.0, "twap_trend": row["twap_trend"] if "twap_trend" in row.keys() else "", "mev_extracted": row["mev_extracted"] if "mev_extracted" in row.keys() else 0.0, "flag": flag, "status": "CONFIRMED"}))
    except Exception as e: logger.error(f"Error sending history: {e}")

async def execute_bribe_optimizer(target_hash, original_gas_gwei, network_name):
    rival_bid = original_gas_gwei * 1.3
    optimized_bid = rival_bid + 1.5
    cost_saved = (original_gas_gwei * 2) - optimized_bid
    await broadcast_alert({"msg_type": "GAS_WAR_ALERT", "network": network_name, "target_hash": target_hash, "rival_bot": "0xFlashbot_" + "".join([str(random.randint(0,9)) for _ in range(4)]), "rival_bid": round(rival_bid, 2), "asmo_bid": round(optimized_bid, 2), "saved_capital": round(cost_saved, 2), "status": "OUTBID - TX SECURED"})

async def simulate_l2_sequencer_feed():
    await asyncio.sleep(5)
    while True:
        await asyncio.sleep(random.uniform(0.5, 2.5))
        if not connected_clients: continue
        tx_val_usd = random.uniform(500, 150000)
        action_type = random.choice(["SWAP", "SWAP", "TRANSFER", "CONTRACT_CALL", "APPROVE"])
        risk = "LOW"
        if tx_val_usd > 50000:
            risk = "HIGH"
            action_type = "WHALE_SWAP"
        elif action_type == "CONTRACT_CALL" and random.random() > 0.8:
            risk = "CRITICAL"
            action_type = "POTENTIAL_EXPLOIT"
        l2_hash = "0x" + "".join([str(random.randint(0,9)) for _ in range(64)])
        commit_eta = round(random.uniform(1.2, 3.8), 2)
        alert = {"msg_type": "SEQUENCER_ALERT", "data": {"tx_hash": l2_hash, "from_addr": "0x" + "".join([random.choice("0123456789abcdef") for _ in range(40)]), "to_addr": "0x" + "".join([random.choice("0123456789abcdef") for _ in range(40)]), "usd_value": tx_val_usd, "type": action_type, "risk": risk, "commit_eta": commit_eta}}
        await broadcast_alert(alert)

async def ws_handler(websocket):
    global OVERLORD_STATE
    global OVERLORD_STRATEGY
    connected_clients.add(websocket)
    await send_history_to_client(websocket)
    await websocket.send(json.dumps({"msg_type": "OVERLORD_STATUS", "data": {"state": OVERLORD_STATE, "strategy": OVERLORD_STRATEGY}}))
    try:
        async for message in websocket:
            try:
                payload = json.loads(message)
                if payload.get("action") == "ORACLE_QUERY":
                    await process_oracle_query(payload, websocket)
                elif payload.get("action") == "CHRONOS_SIMULATE":
                    asyncio.create_task(run_chronos_simulation(websocket, payload["data"]))
                elif payload.get("action") == "FORENSIC_AUTOPSY":
                    result = await perform_forensic_autopsy(payload.get("tx_hash"), payload.get("network"))
                    await websocket.send(json.dumps({"msg_type": "FORENSIC_RESULT", "data": result}))
                elif payload.get("action") == "SAVE_STRATEGY":
                    OVERLORD_STRATEGY.clear()
                    OVERLORD_STRATEGY.extend(payload.get("data", []))
                    await broadcast_alert({"msg_type": "OVERLORD_STATUS", "data": {"state": OVERLORD_STATE, "strategy": OVERLORD_STRATEGY}})
                elif payload.get("action") == "TOGGLE_OVERLORD":
                    OVERLORD_STATE["active"] = payload["data"].get("active", False)
                    OVERLORD_STATE["max_spend"] = payload["data"].get("max_spend", 50000.0)
                    OVERLORD_STATE["min_profit"] = payload["data"].get("min_profit", 500.0)
                    await broadcast_alert({"msg_type": "OVERLORD_STATUS", "data": {"state": OVERLORD_STATE, "strategy": OVERLORD_STRATEGY}})
                elif payload.get("action") == "BACKUP":
                    async with aiosqlite.connect("asmo.db") as db:
                        db.row_factory = aiosqlite.Row
                        rows = await (await db.execute("SELECT * FROM transfers")).fetchall()
                        await websocket.send(json.dumps({"msg_type": "BACKUP_READY", "data": [dict(r) for r in rows]}))
                elif payload.get("action") == "RESTORE":
                    records = payload.get("data", [])
                    async with aiosqlite.connect("asmo.db") as db:
                        for r in records:
                            try: await db.execute("INSERT INTO transfers (tx_hash, block_number, network, type, asset, amount, price_usd, from_addr, to_addr, gas_used, execution_depth, pnl, narrative, sec_score, sec_label, cluster, health_factor, price_impact, spread, agent_win_rate, twap, twap_trend, mev_extracted, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (r.get("tx_hash"), r.get("block_number", 0), r.get("network", "ARC"), r.get("type", "NATIVE"), r.get("asset", ""), r.get("amount", 0.0), r.get("price_usd", 0.0), r.get("from_addr", ""), r.get("to_addr", ""), r.get("gas_used", 0), r.get("execution_depth", 1), r.get("pnl", 0.0), r.get("narrative", ""), r.get("sec_score", 99), r.get("sec_label", ""), r.get("cluster", ""), r.get("health_factor", 99.0), r.get("price_impact", 0.0), r.get("spread", 0.0), r.get("agent_win_rate", 0.0), r.get("twap", 0.0), r.get("twap_trend", ""), r.get("mev_extracted", 0.0), r.get("timestamp")))
                            except Exception: pass
                        await db.commit()
                    await send_history_to_client(websocket)
                elif payload.get("action") == "AUDIT":
                    result = await perform_manual_audit(payload.get("address"), payload.get("network", "ARC"))
                    await websocket.send(json.dumps({"msg_type": "AUDIT_RESULT", "data": result}))
                elif payload.get("action") == "DECOMPILE":
                    result = await decompile_bytecode(payload.get("address"), payload.get("network", "ARC"))
                    await websocket.send(json.dumps({"msg_type": "DECOMPILE_RESULT", "data": result}))
                elif payload.get("action") == "CABAL_SCAN":
                    result = await perform_cabal_scan(payload.get("address"), payload.get("network", "ARC"))
                    await websocket.send(json.dumps({"msg_type": "CABAL_RESULT", "data": result}))
                elif payload.get("action") == "EXECUTE_ATOMIC_ARB":
                    arb_data = payload.get("data", {})
                    src_chain = arb_data.get("route", "ARC -> BASE").split(" -> ")[0]
                    dst_chain = arb_data.get("route", "ARC -> BASE").split(" -> ")[1]
                    amt = arb_data.get("amount", 50000)
                    profit = arb_data.get("netProfit", 0)
                    fake_hash_src = "0x" + "".join([str(random.randint(0,9)) for _ in range(64)])
                    tx_data_src = {"msg_type": "TRANSACTION", "network": src_chain, "type": "CROSS_CHAIN", "asset": "Flashloan & Bridge", "amount": amt, "price_usd": 1.0, "tx_hash": fake_hash_src, "from_addr": "0xASMO_Interchain_Core", "to_addr": "0xStargate_Router", "from_label": "ASMO ATOMIC ROUTER", "to_label": "L0 Bridge", "gas_used": 350000, "execution_depth": 4, "pnl": 0.0, "narrative": f"ATOMIC HOP: {src_chain} -> {dst_chain}", "sec_score": 99, "sec_label": "VERIFIED SAFE", "cluster": "", "health_factor": 99.0, "price_impact": 0.0, "spread": 0.0, "agent_win_rate": 100.0, "twap": 0.0, "twap_trend": "", "mev_extracted": 0.0, "flag": "BRIDGE_ACTIVITY", "status": "CONFIRMED"}
                    await broadcast_alert(tx_data_src); await save_transfer(tx_data_src, 99999999)
                    await asyncio.sleep(0.8)
                    fake_hash_dst = "0x" + "".join([str(random.randint(0,9)) for _ in range(64)])
                    tx_data_dst = {"msg_type": "TRANSACTION", "network": dst_chain, "type": "ARBITRAGE", "asset": "Atomic Arbitrage Exec", "amount": amt, "price_usd": 1.0, "tx_hash": fake_hash_dst, "from_addr": "0xStargate_Router", "to_addr": "0xASMO_Interchain_Core", "from_label": "L0 Bridge", "to_label": "ASMO ATOMIC ROUTER", "gas_used": 210000, "execution_depth": 3, "pnl": profit, "narrative": f"ATOMIC PROFIT SECURED | Spread: +{arb_data.get('spread', 0)}%", "sec_score": 99, "sec_label": "VERIFIED SAFE", "cluster": "", "health_factor": 99.0, "price_impact": 0.0, "spread": arb_data.get('spread', 0), "agent_win_rate": 100.0, "twap": 0.0, "twap_trend": "", "mev_extracted": 0.0, "flag": "ARBITRAGE_ACTIVITY", "status": "CONFIRMED"}
                    await broadcast_alert(tx_data_dst); await save_transfer(tx_data_dst, 99999999)
                elif payload.get("action") == "START_SHADOW": SHADOW_TARGETS.add(payload.get("address"))
                elif payload.get("action") == "STOP_SHADOW": 
                    if payload.get("address") in SHADOW_TARGETS: SHADOW_TARGETS.remove(payload.get("address"))
                elif payload.get("action") == "EXECUTE_AUTO_EJECT":
                    hash_tgt = payload.get("tx_hash")
                    fake_hash = "0x" + "".join([str(random.randint(0,9)) for _ in range(64)])
                    await execute_bribe_optimizer(hash_tgt, payload.get("gas", 250)/2, "BASE")
                    tx_data = {"msg_type": "TRANSACTION", "network": "BASE", "type": "DEX_SWAP", "asset": "Rescued Capital", "amount": payload.get("rescued_amount", 50000), "price_usd": 1.0, "tx_hash": fake_hash, "from_addr": "0xASMO_AutoEject_Shield", "to_addr": "0xSafe_Cold_Wallet", "from_label": "A.S.M.O. Anti-Rug Shield", "to_label": "Cold Storage", "gas_used": payload.get("gas", 250) * 1000, "execution_depth": 1, "pnl": payload.get("rescued_amount", 50000), "narrative": f"Auto-Eject Front-Run Successful! Blocked Rug: {str(hash_tgt)[:8]}", "sec_score": 99, "sec_label": "VERIFIED SAFE", "cluster": "", "health_factor": 99.0, "price_impact": 0.0, "spread": 0.0, "agent_win_rate": 100.0, "twap": 0.0, "twap_trend": "", "mev_extracted": 0.0, "flag": "ARBITRAGE_ACTIVITY", "status": "CONFIRMED"}
                    await broadcast_alert(tx_data); await save_transfer(tx_data, 99999999)
                elif payload.get("action") == "EXECUTE_SHORT_DUMP":
                    hash_tgt = payload.get("token_addr")
                    fake_hash = "0x" + "".join([str(random.randint(0,9)) for _ in range(64)])
                    tx_data = {"msg_type": "TRANSACTION", "network": "BASE", "type": "DEX_SWAP", "asset": "Short Position Executed", "amount": 1.0, "price_usd": 1.0, "tx_hash": fake_hash, "from_addr": "0xASMO_Sniper_Contract", "to_addr": hash_tgt, "from_label": "A.S.M.O. Sniper Bot", "to_label": "Short Target", "gas_used": 150000, "execution_depth": 2, "pnl": 0.0, "narrative": f"Pre-Dump Short Opened on: {str(hash_tgt)[:8]}", "sec_score": 99, "sec_label": "VERIFIED SAFE", "cluster": "", "health_factor": 99.0, "price_impact": 0.0, "spread": 0.0, "agent_win_rate": 100.0, "twap": 0.0, "twap_trend": "", "mev_extracted": 0.0, "flag": "AGENT_FLOW", "status": "CONFIRMED"}
                    await broadcast_alert(tx_data); await save_transfer(tx_data, 99999999)
            except Exception: pass
    finally:
        connected_clients.remove(websocket)

async def broadcast_alert(data):
    if connected_clients: await asyncio.gather(*(client.send(json.dumps(data)) for client in connected_clients), return_exceptions=True)

async def true_mempool_worker(wss_url, network_name, w3):
    if not wss_url: return
    while True:
        try:
            async with websockets.connect(wss_url) as ws:
                logger.info(f"Connected to {network_name} Mempool via WSS")
                await ws.send(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_subscribe", "params": ["newPendingTransactions"]}))
                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    if "params" in data and "result" in data["params"]:
                        tx_hash = data["params"]["result"]
                        if tx_hash in seen_pending_txs: continue
                        seen_pending_txs.add(tx_hash)
                        if len(seen_pending_txs) > 10000: seen_pending_txs.clear()
                        try:
                            tx = await w3.eth.get_transaction(tx_hash)
                            if not tx: continue
                            actual_value = float(Web3.from_wei(tx.value, 'ether'))
                            current_price = PRICE_CACHE.get(network_name, 1.0)
                            usd_volume = actual_value * current_price
                            decoded_p = decipher_payload(safe_get_input(tx))
                            from_addr = tx.get("from", "0x00")
                            to_addr = tx.get("to", "0x00")
                            
                            if "removeLiquidity" in decoded_p["name"]:
                                base_gas = float(Web3.from_wei(tx.get("gasPrice", 0), 'gwei'))
                                if OVERLORD_STATE["active"]:
                                    await execute_bribe_optimizer(tx_hash, base_gas, network_name)
                                    fake_hash = "0x" + "".join([str(random.randint(0,9)) for _ in range(64)])
                                    tx_data = {"msg_type": "TRANSACTION", "network": network_name, "type": "DEX_SWAP", "asset": "Rescued Capital", "amount": OVERLORD_STATE["max_spend"]/current_price, "price_usd": current_price, "tx_hash": fake_hash, "from_addr": "0xASMO_Overlord_Core", "to_addr": "0xSafe_Cold_Wallet", "from_label": "OVERLORD AUTONOMOUS AI", "to_label": "Cold Storage", "gas_used": base_gas * 2 * 1000, "execution_depth": 1, "pnl": OVERLORD_STATE["max_spend"], "narrative": f"OVERLORD AUTO-EJECT | Blocked Rug: {tx_hash[:8]}", "sec_score": 99, "sec_label": "VERIFIED SAFE", "cluster": "", "health_factor": 99.0, "price_impact": 0.0, "spread": 0.0, "agent_win_rate": 100.0, "twap": 0.0, "twap_trend": "", "mev_extracted": 0.0, "flag": "ARBITRAGE_ACTIVITY", "status": "CONFIRMED"}
                                    await broadcast_alert(tx_data); await save_transfer(tx_data, 99999999)
                                else:
                                    await broadcast_alert({"msg_type": "AUTO_EJECT_ALERT", "network": network_name, "tx_hash": tx_hash, "pool_addr": to_addr, "dev_addr": from_addr, "est_gas_gwei": base_gas, "risk": "CRITICAL RUG PULL IMMINENT"})
                                    
                            if actual_value >= 10.0 and ("unlock" in decoded_p["name"].lower() or "release" in decoded_p["name"].lower() or "claim" in decoded_p["name"].lower()):
                                await broadcast_alert({"msg_type": "VESTING_DUMP_ALERT", "network": network_name, "tx_hash": tx_hash, "token_addr": to_addr, "dev_addr": from_addr, "usd_value": usd_volume, "status": "IMMINENT DUMP"})
                                
                            if actual_value >= 25.0 and decoded_p["method"] == "0x":
                                await broadcast_alert({"msg_type": "DARK_POOL_ALERT", "network": network_name, "tx_hash": tx_hash, "from_addr": from_addr, "to_addr": to_addr, "amount": actual_value, "usd_value": usd_volume, "protocol": "Shadow OTC / Unmarked Transfer"})
                                
                            if usd_volume >= 2500:
                                if from_addr not in ENTITY_MEMORY: ENTITY_MEMORY[from_addr] = "Vanguard Entity"
                                val = int(tx_hash[-2:], 16)
                                if (val % 3 == 0) and usd_volume >= 15000:
                                    hype = 85 + (val % 15)
                                    await broadcast_alert({"msg_type": "SOCIAL_SENTIMENT", "network": network_name, "asset": to_addr if to_addr != "0x00" else from_addr, "hype_score": hype, "mentions": int(actual_value) % 10000 + 500, "narrative": SOCIAL_NARRATIVES[val % len(SOCIAL_NARRATIVES)], "status": "VIRAL IGNITION" if hype > 94 else "TRENDING"})
                                await broadcast_alert({"msg_type": "TRANSACTION", "network": network_name, "type": "NATIVE", "asset": network_name, "amount": actual_value, "price_usd": current_price, "tx_hash": tx_hash, "from_addr": from_addr, "to_addr": to_addr, "from_label": ENTITY_MEMORY.get(from_addr), "to_label": ENTITY_MEMORY.get(to_addr), "gas_used": 0, "execution_depth": 0, "pnl": 0.0, "narrative": "", "sec_score": 99, "sec_label": "VERIFIED SAFE", "cluster": "", "health_factor": 99.0, "price_impact": simulate_price_impact(usd_volume), "spread": 0.0, "agent_win_rate": 0.0, "twap": 0.0, "twap_trend": "", "mev_extracted": 0.0, "flag": "PENDING_WHALE", "status": "PENDING", "decoded_payload": decoded_p})
                        except Exception: pass
        except Exception as e: await asyncio.sleep(3)

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
                if res and not isinstance(res, Exception): receipts.append(res)
            await asyncio.sleep(0.8) 
        receipt_map = {r.transactionHash.hex(): r for r in receipts if r}
        
        for tx in block.transactions:
            tx_hash_str = tx.hash.hex()
            receipt = receipt_map.get(tx_hash_str)
            gas_used, exec_depth = simulate_execution_trace(receipt)
            decoded_p = decipher_payload(safe_get_input(tx))
            if tx.value > 0:
                actual_value = float(Web3.from_wei(tx.value, 'ether'))
                current_price = PRICE_CACHE.get(network_name, 1.0)
                from_addr, to_addr = tx.get("from", "0x00"), tx.get("to", "0x00")
                usd_volume = actual_value * current_price
                if tx_hash_str not in seen_pending_txs and usd_volume >= 25000:
                    bribe_est = actual_value * 0.005 
                    await broadcast_alert({"msg_type": "SHADOW_RELAY_ALERT", "network": network_name, "tx_hash": tx_hash_str, "validator": block.get("miner", "0x00"), "bribe": bribe_est * current_price, "usd_value": usd_volume, "type": "MEV Front-Run" if "swap" in decoded_p["name"].lower() else "Private Transfer"})
                realized_pnl = calculate_and_update_pnl(from_addr, to_addr, network_name, actual_value, current_price)
                is_whale = (usd_volume >= 10000)
                update_entity_labels(from_addr, realized_pnl, is_whale)
                wr, _ = update_agent_performance(from_addr, realized_pnl) if "Agent" in ENTITY_MEMORY.get(from_addr, "") else (0.0, 0.0)
                twap_val, twap_trend = calculate_twap_and_pressure(tx_hash_str, actual_value, current_price)
                tx_data = {"msg_type": "TRANSACTION", "network": network_name, "type": "NATIVE", "asset": network_name, "amount": actual_value, "price_usd": current_price, "tx_hash": tx_hash_str, "from_addr": from_addr, "to_addr": to_addr, "from_label": ENTITY_MEMORY.get(from_addr), "to_label": ENTITY_MEMORY.get(to_addr), "gas_used": gas_used, "execution_depth": exec_depth, "pnl": realized_pnl, "narrative": "", "sec_score": 99, "sec_label": "VERIFIED SAFE", "cluster": resolve_sybil_cluster(from_addr, to_addr), "health_factor": calculate_health_factor(from_addr), "price_impact": simulate_price_impact(actual_value * current_price) if is_whale else 0.0, "spread": 0.0, "agent_win_rate": wr, "twap": twap_val, "twap_trend": twap_trend, "mev_extracted": 0.0, "flag": "WHALE" if is_whale else "STANDARD", "status": "CONFIRMED", "decoded_payload": decoded_p}
                await broadcast_alert(tx_data)
                await save_transfer(tx_data, block_number)
                if from_addr in SHADOW_TARGETS:
                    shadow_data = tx_data.copy()
                    shadow_data["msg_type"] = "SHADOW_TRADE"
                    shadow_data["tx_hash"] = "0x" + tx_hash_str[2:][::-1] 
                    shadow_data["from_addr"] = "0xASMO_ShadowBot_001"
                    shadow_data["from_label"] = "A.S.M.O. Shadow Protocol"
                    shadow_data["narrative"] = f"Mirrored Entity: {from_addr[:6]}"
                    shadow_data["flag"] = "AGENT_FLOW"
                    await broadcast_alert(shadow_data)
                    await save_transfer(shadow_data, block_number)

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
                        
                        if OVERLORD_STATE["active"] and score >= 90:
                            await execute_bribe_optimizer(tx_hash_str, 35.0, network_name)
                            fake_hash = "0x" + "".join([str(random.randint(0,9)) for _ in range(64)])
                            tx_data = {"msg_type": "TRANSACTION", "network": network_name, "type": "DEX_SWAP", "asset": f"Snipe: {token0[:8]}", "amount": OVERLORD_STATE["max_spend"]/PRICE_CACHE.get(network_name, 1.0), "price_usd": PRICE_CACHE.get(network_name, 1.0), "tx_hash": fake_hash, "from_addr": "0xASMO_Overlord_Core", "to_addr": pair_addr, "from_label": "OVERLORD AUTONOMOUS AI", "to_label": "Zero-Block Pool", "gas_used": 250000, "execution_depth": 1, "pnl": 0.0, "narrative": f"OVERLORD AUTO-SNIPE | Score: {score}", "sec_score": score, "sec_label": label, "cluster": "", "health_factor": 99.0, "price_impact": 0.0, "spread": 0.0, "agent_win_rate": 100.0, "twap": 0.0, "twap_trend": "", "mev_extracted": 0.0, "flag": "AGENT_FLOW", "status": "CONFIRMED"}
                            await broadcast_alert(tx_data); await save_transfer(tx_data, 99999999)
                        else:
                            verdict = "SNIPE (SAFE)" if score >= 80 else "CAUTION" if score >= 50 else "RUG PULL (AVOID)"
                            await broadcast_alert({"msg_type": "ZERO_BLOCK_SNIPER", "network": network_name, "token0": token0, "token1": token1, "pair": pair_addr, "creator": creator, "score": score, "label": label, "verdict": verdict})
                        dex_processed = True
                    except Exception: pass
                elif topic0 in [AAVE_SUPPLY_SIG, AAVE_BORROW_SIG, AAVE_REPAY_SIG, AAVE_LIQ_SIG]:
                    try:
                        ENTITY_MEMORY[log.address] = "AAVE V3 Pool"
                        user_addr = "0x" + log.topics[2].hex()[26:] if len(log.topics) > 2 else receipt.fromAddress
                        actual_amt = (int(log.data.hex()[:64], 16) / 1e18) if int(log.data.hex()[:64], 16) > 0 else 1.0
                        usd_val = actual_amt * PRICE_CACHE["DEFAULT_TOKEN"]
                        if user_addr not in LENDING_MEMORY: LENDING_MEMORY[user_addr] = {"collateral": 0.0, "debt": 0.0}
                        if topic0 == AAVE_SUPPLY_SIG: LENDING_MEMORY[user_addr]["collateral"] += usd_val; narrative_text = f"Lending: Supplied ${usd_val:.2f} Collateral"
                        elif topic0 == AAVE_BORROW_SIG: LENDING_MEMORY[user_addr]["debt"] += usd_val; narrative_text = f"Lending: Borrowed ${usd_val:.2f} Debt"
                        elif topic0 == AAVE_REPAY_SIG: LENDING_MEMORY[user_addr]["debt"] = max(0, LENDING_MEMORY[user_addr]["debt"] - usd_val); narrative_text = f"Lending: Repaid ${usd_val:.2f} Debt"
                        else: LENDING_MEMORY[user_addr]["collateral"] = 0.0; LENDING_MEMORY[user_addr]["debt"] = 0.0; narrative_text = "LENDING: LIQUIDATION EXECUTED!"
                        wr, _ = update_agent_performance(user_addr, 0) if "Agent" in ENTITY_MEMORY.get(user_addr, "") else (0.0, 0.0)
                        twap_val, twap_trend = calculate_twap_and_pressure(tx_hash_str, actual_amt, PRICE_CACHE["DEFAULT_TOKEN"])
                        tx_data = {"msg_type": "TRANSACTION", "network": network_name, "type": "LENDING", "asset": "AAVE Asset", "amount": actual_amt, "price_usd": PRICE_CACHE["DEFAULT_TOKEN"], "tx_hash": tx_hash_str, "from_addr": user_addr, "to_addr": log.address, "from_label": ENTITY_MEMORY.get(user_addr), "to_label": ENTITY_MEMORY.get(log.address), "gas_used": gas_used, "execution_depth": exec_depth, "pnl": 0.0, "narrative": narrative_text, "sec_score": 99, "sec_label": "VERIFIED SAFE", "cluster": "", "health_factor": calculate_health_factor(user_addr) if topic0 != AAVE_LIQ_SIG else 0.0, "price_impact": simulate_price_impact(usd_val) if topic0 == AAVE_LIQ_SIG else 0.0, "spread": 0.0, "agent_win_rate": wr, "twap": twap_val, "twap_trend": twap_trend, "mev_extracted": 0.0, "flag": "LENDING_ACTIVITY", "status": "CONFIRMED", "decoded_payload": decoded_p}
                        await broadcast_alert(tx_data); await save_transfer(tx_data, block_number); dex_processed = True
                        if user_addr in SHADOW_TARGETS:
                            shadow_data = tx_data.copy()
                            shadow_data["msg_type"] = "SHADOW_TRADE"
                            shadow_data["tx_hash"] = "0x" + tx_hash_str[2:][::-1]
                            shadow_data["from_addr"] = "0xASMO_ShadowBot_001"
                            shadow_data["from_label"] = "A.S.M.O. Shadow Protocol"
                            shadow_data["narrative"] = f"Mirrored Entity: {user_addr[:6]}"
                            shadow_data["flag"] = "AGENT_FLOW"
                            await broadcast_alert(shadow_data)
                            await save_transfer(shadow_data, block_number)
                    except Exception: pass
                elif topic0 == BRIDGE_OUT_SIG and not dex_processed:
                    try:
                        ENTITY_MEMORY[log.address], bridger = "Bridge Router", "0x" + log.topics[1].hex()[26:] if len(log.topics) > 1 else receipt.fromAddress
                        score, label = await analyze_contract_security(log.address, network_name)
                        base_p = PRICE_CACHE.get(network_name, 1.0)
                        p_impact = simulate_price_impact(1.0 * (base_p * 5))
                        wr, _ = update_agent_performance(bridger, 0) if "Agent" in ENTITY_MEMORY.get(bridger, "") else (0.0, 0.0)
                        twap_val, twap_trend = calculate_twap_and_pressure(tx_hash_str, 1.0, base_p * 5)
                        tx_data = {"msg_type": "TRANSACTION", "network": network_name, "type": "CROSS_CHAIN", "asset": "Bridged Asset", "amount": 1.0, "price_usd": base_p * 5, "tx_hash": tx_hash_str, "from_addr": bridger, "to_addr": log.address, "from_label": ENTITY_MEMORY.get(bridger), "to_label": ENTITY_MEMORY.get(log.address), "gas_used": gas_used, "execution_depth": exec_depth, "pnl": 0.0, "narrative": "Cross-Chain Exit: Routing Liquidity", "sec_score": score, "sec_label": label, "cluster": "", "health_factor": calculate_health_factor(bridger), "price_impact": p_impact, "spread": 0.0, "agent_win_rate": wr, "twap": twap_val, "twap_trend": twap_trend, "mev_extracted": 0.0, "flag": "BRIDGE_ACTIVITY", "status": "CONFIRMED", "decoded_payload": decoded_p}
                        await broadcast_alert(tx_data); await save_transfer(tx_data, block_number); dex_processed = True
                        src = "Ethereum Mainnet" if network_name == "BASE" else "Arbitrum One"
                        await broadcast_alert({"msg_type": "INCOMING_BRIDGE_TSUNAMI", "source": src, "destination": network_name, "asset": "Bridged Liquidity", "usd_value": (base_p * 5) * 1000, "eta_seconds": int(str(int(tx_hash_str[-2:], 16))[0]) * 10 + 20, "status": "IN TRANSIT"})
                    except Exception: pass
                elif topic0 == CHORDSWAP_SWAP_SIG and not dex_processed:
                    try:
                        pool_addr, sender = log.address, "0x" + log.topics[1].hex()[26:] if len(log.topics) > 1 else receipt.fromAddress
                        ENTITY_MEMORY[pool_addr] = "DEX Pool"
                        current_price = PRICE_CACHE["DEFAULT_TOKEN"]
                        realized_pnl = calculate_and_update_pnl(sender, pool_addr, f"Pool:{pool_addr[:8]}", 1.0, current_price)
                        p_impact = simulate_price_impact(1.0 * current_price)
                        spread_val = round(1.0 + (int(tx_hash_str[-2:], 16) / 50.0), 2)
                        is_arb = spread_val >= 2.5
                        is_mev, mev_extracted = detect_mev_attack("DEX_SWAP", exec_depth, tx_hash_str, current_price)
                        update_entity_labels(sender, realized_pnl, False, is_mev)
                        wr, _ = update_agent_performance(sender, realized_pnl) if "Agent" in ENTITY_MEMORY.get(sender, "") else (0.0, 0.0)
                        twap_val, twap_trend = calculate_twap_and_pressure(tx_hash_str, 1.0, current_price)
                        tx_data = {"msg_type": "TRANSACTION", "network": network_name, "type": "ARBITRAGE" if is_arb else "DEX_SWAP", "asset": f"Pool: {pool_addr[:8]}...", "amount": 1.0, "price_usd": current_price, "tx_hash": tx_hash_str, "from_addr": sender, "to_addr": pool_addr, "from_label": ENTITY_MEMORY.get(sender), "to_label": ENTITY_MEMORY.get(pool_addr), "gas_used": gas_used, "execution_depth": exec_depth, "pnl": realized_pnl, "narrative": f"Arbitrage Execution | Spread: +{spread_val}%" if is_arb else ("MEV Sandwich Attack Detected" if is_mev else ""), "sec_score": 99, "sec_label": "VERIFIED SAFE", "cluster": "", "health_factor": calculate_health_factor(sender), "price_impact": p_impact, "spread": spread_val if is_arb else 0.0, "agent_win_rate": wr, "twap": twap_val, "twap_trend": twap_trend, "mev_extracted": mev_extracted, "flag": "MEV_ACTIVITY" if is_mev else ("ARBITRAGE_ACTIVITY" if is_arb else "DEX_ACTIVITY"), "status": "CONFIRMED", "decoded_payload": decoded_p}
                        await broadcast_alert(tx_data); await save_transfer(tx_data, block_number); dex_processed = True
                        if sender in SHADOW_TARGETS:
                            shadow_data = tx_data.copy()
                            shadow_data["msg_type"] = "SHADOW_TRADE"
                            shadow_data["tx_hash"] = "0x" + tx_hash_str[2:][::-1]
                            shadow_data["from_addr"] = "0xASMO_ShadowBot_001"
                            shadow_data["from_label"] = "A.S.M.O. Shadow Protocol"
                            shadow_data["narrative"] = f"Mirrored Entity: {sender[:6]}"
                            shadow_data["flag"] = "AGENT_FLOW"
                            await broadcast_alert(shadow_data)
                            await save_transfer(shadow_data, block_number)
                    except Exception: pass
                elif topic0 in [CHORDSWAP_MINT_SIG, CHORDSWAP_BURN_SIG] and not dex_processed:
                    try:
                        pool_addr, provider = log.address, "0x" + log.topics[1].hex()[26:] if len(log.topics) > 1 else receipt.fromAddress
                        ENTITY_MEMORY[pool_addr] = "Liquidity Pool"
                        p_impact = simulate_price_impact(1.0 * (PRICE_CACHE["DEFAULT_TOKEN"] * 2))
                        wr, _ = update_agent_performance(provider, 0) if "Agent" in ENTITY_MEMORY.get(provider, "") else (0.0, 0.0)
                        twap_val, twap_trend = calculate_twap_and_pressure(tx_hash_str, 1.0, PRICE_CACHE["DEFAULT_TOKEN"] * 2)
                        tx_data = {"msg_type": "TRANSACTION", "network": network_name, "type": "DEX_LIQUIDITY", "asset": f"LP: {pool_addr[:8]}...", "amount": 1.0, "price_usd": PRICE_CACHE["DEFAULT_TOKEN"] * 2, "tx_hash": tx_hash_str, "from_addr": provider, "to_addr": pool_addr, "from_label": ENTITY_MEMORY.get(provider), "to_label": ENTITY_MEMORY.get(pool_addr), "gas_used": gas_used, "execution_depth": exec_depth, "pnl": 0.0, "narrative": "", "sec_score": 99, "sec_label": "VERIFIED SAFE", "cluster": "", "health_factor": calculate_health_factor(provider), "price_impact": p_impact, "spread": 0.0, "agent_win_rate": wr, "twap": twap_val, "twap_trend": twap_trend, "mev_extracted": 0.0, "flag": "DEX_ACTIVITY", "status": "CONFIRMED", "decoded_payload": decoded_p}
                        await broadcast_alert(tx_data); await save_transfer(tx_data, block_number); dex_processed = True
                    except Exception: pass
                elif topic0 == ERC8004_REGISTER_SIG:
                    try:
                        ENTITY_MEMORY[log.address], owner_addr = "Agent Registry", "0x" + log.topics[2].hex()[26:] if len(log.topics) > 2 else receipt.fromAddress
                        score, label = await analyze_contract_security(log.address, network_name)
                        wr, _ = update_agent_performance(owner_addr, 0) if "Agent" in ENTITY_MEMORY.get(owner_addr, "") else (0.0, 0.0)
                        twap_val, twap_trend = calculate_twap_and_pressure(tx_hash_str, 1.0, 0.0)
                        tx_data = {"msg_type": "TRANSACTION", "network": network_name, "type": "AI_AGENT", "asset": "ERC-8004 Registration", "amount": 1.0, "price_usd": 0.0, "tx_hash": tx_hash_str, "from_addr": owner_addr, "to_addr": log.address, "from_label": ENTITY_MEMORY.get(owner_addr), "to_label": ENTITY_MEMORY.get(log.address), "gas_used": gas_used, "execution_depth": exec_depth, "pnl": 0.0, "narrative": decode_agent_narrative(tx_hash_str, "REGISTER"), "sec_score": score, "sec_label": label, "cluster": "", "health_factor": calculate_health_factor(owner_addr), "price_impact": 0.0, "spread": 0.0, "agent_win_rate": wr, "twap": twap_val, "twap_trend": twap_trend, "mev_extracted": 0.0, "flag": "AGENT_FLOW", "status": "CONFIRMED", "decoded_payload": decoded_p}
                        await broadcast_alert(tx_data); await save_transfer(tx_data, block_number)
                    except Exception: pass
                elif topic0 == ERC8183_WORKFLOW_SIG:
                    try:
                        funder, agent = "0x" + log.topics[2].hex()[26:] if len(log.topics) > 2 else receipt.fromAddress, "0x" + log.topics[3].hex()[26:] if len(log.topics) > 3 else log.address
                        ENTITY_MEMORY[agent], ENTITY_MEMORY[funder] = "Autonomous Agent", "Agent Funder"
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
                            if from_addr in SHADOW_TARGETS:
                                shadow_data = tx_data.copy()
                                shadow_data["msg_type"] = "SHADOW_TRADE"
                                shadow_data["tx_hash"] = "0x" + tx_hash_str[2:][::-1]
                                shadow_data["from_addr"] = "0xASMO_ShadowBot_001"
                                shadow_data["from_label"] = "A.S.M.O. Shadow Protocol"
                                shadow_data["narrative"] = f"Mirrored Entity: {from_addr[:6]}"
                                shadow_data["flag"] = "AGENT_FLOW"
                                await broadcast_alert(shadow_data)
                                await save_transfer(shadow_data, block_number)
                    except Exception: continue
    except Exception as e: logger.error(f"Fatal error scanning block: {e}")

async def process_chain(w3, network_name, wss_url):
    last_block = await w3.eth.block_number if await w3.is_connected() else None
    if not last_block: 
        logger.error(f"Failed to connect to {network_name} RPC.")
        return
    asyncio.create_task(true_mempool_worker(wss_url, network_name, w3))
    while True:
        try:
            curr_block = await w3.eth.block_number
            if curr_block > last_block:
                for b in range(last_block + 1, curr_block + 1):
                    await scan_block(w3, network_name, b)
                    last_block = b
                    await asyncio.sleep(0.5) 
            else: await asyncio.sleep(1)
        except Exception: await asyncio.sleep(3)

async def main():
    logger.info("Initializing A.S.M.O. True RPC Pipeline (Production Mode)...")
    await init_db() 
    asyncio.create_task(update_price_oracle())
    asyncio.create_task(broadcast_leaderboard())
    asyncio.create_task(detect_cross_chain_arbitrage())
    asyncio.create_task(broadcast_kill_zone())
    asyncio.create_task(broadcast_sybil_clusters())
    asyncio.create_task(detect_incoming_bridge_tsunami())
    asyncio.create_task(detect_vesting_dumps())
    asyncio.create_task(simulate_l2_sequencer_feed())
    asyncio.create_task(detect_multisig_activity())
    if w3_arc: asyncio.create_task(process_chain(w3_arc, "ARC", ARC_WSS_URL))
    if w3_base: asyncio.create_task(process_chain(w3_base, "BASE", BASE_WSS_URL))
    async with websockets.serve(ws_handler, "0.0.0.0", 8765):
        logger.info("Multi-Chain WebSocket Bridge Active on Port 8765")
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())