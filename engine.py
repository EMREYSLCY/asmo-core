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

ERC20_ABI = json.loads('[{"inputs":[],"name":"decimals","outputs":[{"type":"uint8"}],"stateMutability":"view","type":"function"}]')
TOKEN_CACHE = {}
PRICE_CACHE = {
    "ARC": 1.25,
    "DEFAULT_TOKEN": 2.50 
}

connected_clients = set()

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
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        try:
            await db.execute("ALTER TABLE transfers ADD COLUMN from_addr TEXT NOT NULL DEFAULT '0x0000000000000000000000000000000000000000'")
            await db.execute("ALTER TABLE transfers ADD COLUMN to_addr TEXT NOT NULL DEFAULT '0x0000000000000000000000000000000000000000'")
        except Exception:
            pass
        await db.commit()
        logger.info("💾 Database verified with wallet intelligence layer.")

async def save_transfer(tx_data, block_number):
    try:
        async with aiosqlite.connect("asmo.db") as db:
            await db.execute(
                """INSERT INTO transfers 
                   (tx_hash, block_number, type, asset, amount, price_usd, from_addr, to_addr) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (tx_data["tx_hash"], block_number, tx_data["type"], 
                 tx_data["asset"], tx_data["amount"], tx_data["price_usd"],
                 tx_data["from_addr"], tx_data["to_addr"])
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
            
            if "arbitrum" in data:
                PRICE_CACHE["ARC"] = float(data["arbitrum"]["usd"])
            if "ethereum" in data:
                PRICE_CACHE["DEFAULT_TOKEN"] = float(data["ethereum"]["usd"]) * 0.001 
                
            logger.info(f"📈 Oracle Feed Updated | ARC: ${PRICE_CACHE['ARC']} | Tokens Base: ${PRICE_CACHE['DEFAULT_TOKEN']}")
        except Exception as e:
            logger.warning(f"Oracle API sync skipped, using cached prices. Details: {e}")
        
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
                flag = "WHALE" if (amt * prc >= 10000 or (prc == 0.0 and amt >= 50000)) else "STANDARD"
                
                tx_data = {
                    "time": time_str,
                    "type": row["type"],
                    "asset": row["asset"],
                    "amount": amt,
                    "price_usd": prc,
                    "tx_hash": row["tx_hash"],
                    "from_addr": row["from_addr"],
                    "to_addr": row["to_addr"],
                    "flag": flag
                }
                await websocket.send(json.dumps(tx_data))
    except Exception as e:
        logger.error(f"Error sending history to client: {e}")

async def ws_handler(websocket):
    logger.info("🟢 UI Dashboard Connected to Engine!")
    connected_clients.add(websocket)
    await send_history_to_client(websocket)
    try:
        await websocket.wait_closed()
    finally:
        connected_clients.remove(websocket)
        logger.info("🔴 UI Dashboard Disconnected.")

async def broadcast_alert(data):
    if connected_clients:
        message = json.dumps(data)
        await asyncio.gather(*(client.send(message) for client in connected_clients), return_exceptions=True)

async def get_token_decimals(contract_address):
    if contract_address in TOKEN_CACHE:
        return TOKEN_CACHE[contract_address]
    
    try:
        contract_address_checksum = w3.to_checksum_address(contract_address)
        contract = w3.eth.contract(address=contract_address_checksum, abi=ERC20_ABI)
        decimals = await contract.functions.decimals().call()
        TOKEN_CACHE[contract_address] = decimals
        return decimals
    except Exception as e:
        logger.warning(f"Could not fetch decimals for {contract_address}: {e}")
        return 18

async def fetch_receipt(tx_hash):
    try:
        return await w3.eth.get_transaction_receipt(tx_hash)
    except Exception as e:
        logger.error(f"Error fetching receipt for TX {tx_hash.hex()}: {e}")
        return None

async def scan_block(block_number):
    try:
        block = await w3.eth.get_block(block_number, full_transactions=True)
        tx_count = len(block.transactions)
        logger.info(f"📡 Scanning Block: {block_number} | Transactions: {tx_count}")
        
        for tx in block.transactions:
            if tx.value > 0:
                actual_value = float(w3.from_wei(tx.value, 'ether'))
                current_price = PRICE_CACHE["ARC"]
                
                from_addr = tx["from"] if tx.get("from") else "0x0000000000000000000000000000000000000000"
                to_addr = tx["to"] if tx.get("to") else "0x0000000000000000000000000000000000000000"
                
                logger.info(f"💎 NATIVE TRANSFER! Amount: {actual_value:.4f} | From: {from_addr[:8]}... -> To: {to_addr[:8]}...")
                
                flag = "WHALE" if (actual_value * current_price >= 10000) else "STANDARD"
                tx_data = {
                    "type": "NATIVE",
                    "asset": "ARC",
                    "amount": actual_value,
                    "price_usd": current_price,
                    "tx_hash": tx.hash.hex(),
                    "from_addr": from_addr,
                    "to_addr": to_addr,
                    "flag": flag
                }
                await broadcast_alert(tx_data)
                await save_transfer(tx_data, block_number)

        tasks = [fetch_receipt(tx.hash) for tx in block.transactions]
        receipts = []
        chunk_size = 15
        
        for i in range(0, len(tasks), chunk_size):
            chunk = tasks[i:i + chunk_size]
            chunk_results = await asyncio.gather(*chunk)
            receipts.extend(chunk_results)
            await asyncio.sleep(0.2)
            
        for receipt in receipts:
            if not receipt: continue
            for log in receipt.logs:
                if len(log.topics) > 0 and log.topics[0].hex() == TRANSFER_SIG:
                    try:
                        raw_amount = int(log.data.hex(), 16)
                        if raw_amount > 0:
                            tx_hash_str = receipt.transactionHash.hex()
                            contract_address = log.address
                            
                            decimals = await get_token_decimals(contract_address)
                            actual_token_amount = raw_amount / (10 ** decimals)
                            current_token_price = PRICE_CACHE["DEFAULT_TOKEN"]
                            
                            from_addr = "0x" + log.topics[1].hex()[26:] if len(log.topics) > 1 else "0x0000000000000000000000000000000000000000"
                            to_addr = "0x" + log.topics[2].hex()[26:] if len(log.topics) > 2 else "0x0000000000000000000000000000000000000000"
                            
                            logger.info(f"🚨 TOKEN DETECTED! Token: {contract_address} | Amount: {actual_token_amount:.4f} | From: {from_addr[:8]}...")
                            
                            total_usd_value = actual_token_amount * current_token_price
                            flag = "WHALE" if (total_usd_value >= 10000 or actual_token_amount >= 50000) else "STANDARD"
                            
                            tx_data = {
                                "type": "TOKEN",
                                "asset": contract_address,
                                "amount": actual_token_amount,
                                "price_usd": current_token_price,
                                "tx_hash": tx_hash_str,
                                "from_addr": from_addr,
                                "to_addr": to_addr,
                                "flag": flag
                            }
                            await broadcast_alert(tx_data)
                            await save_transfer(tx_data, block_number)
                    except Exception as e:
                        logger.error(f"Error parsing token log for TX {receipt.transactionHash.hex()}: {e}")
                        continue
    except Exception as e:
        logger.error(f"Fatal error scanning block {block_number}: {e}", exc_info=True)

async def check_network_status():
    try:
        if await w3.is_connected():
            return await w3.eth.block_number
    except Exception as e:
        logger.error(f"RPC Connection Error: {e}")
    return None

async def main():
    logger.info("Initializing A.S.M.O. Boot Sequence...")
    await init_db() 
    
    last_scanned_block = await check_network_status()
    if not last_scanned_block:
        logger.error("Failed to connect to ARC RPC. Exiting...")
        return

    asyncio.create_task(update_price_oracle())

    async with websockets.serve(ws_handler, "0.0.0.0", 8765):
        logger.info("🌉 WebSocket Bridge Active on Port 8765")
        logger.info("🔄 Initiating Dual Radar...")
        
        while True:
            try:
                current_block = await w3.eth.block_number
                if current_block > last_scanned_block:
                    for block_to_scan in range(last_scanned_block + 1, current_block + 1):
                        await scan_block(block_to_scan)
                        last_scanned_block = block_to_scan
                else:
                    await asyncio.sleep(2)
            except Exception as e:
                logger.warning(f"Connection lost or RPC rate limit hit. Retrying in 5 seconds... Details: {e}")
                await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())