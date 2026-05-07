import os
import json
import asyncio
import websockets
import logging
import aiosqlite
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
ARC_PRICE_USD = 1.25

ERC20_ABI = json.loads('[{"inputs":[],"name":"decimals","outputs":[{"type":"uint8"}],"stateMutability":"view","type":"function"}]')
TOKEN_CACHE = {}

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
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()
        logger.info("💾 Database initialized successfully.")

async def save_transfer(tx_data, block_number):
    try:
        async with aiosqlite.connect("asmo.db") as db:
            await db.execute(
                """INSERT INTO transfers 
                   (tx_hash, block_number, type, asset, amount, price_usd) 
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (tx_data["tx_hash"], block_number, tx_data["type"], 
                 tx_data["asset"], tx_data["amount"], tx_data["price_usd"])
            )
            await db.commit()
    except Exception as e:
        logger.error(f"Failed to save transfer to DB: {e}")

async def ws_handler(websocket):
    logger.info("🟢 UI Dashboard Connected to Engine!")
    connected_clients.add(websocket)
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
                logger.info(f"💎 NATIVE TRANSFER! Amount: {actual_value:.4f} | TX: {tx.hash.hex()}")
                
                tx_data = {
                    "type": "NATIVE",
                    "asset": "ARC",
                    "amount": actual_value,
                    "price_usd": ARC_PRICE_USD,
                    "tx_hash": tx.hash.hex()
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
                            
                            logger.info(f"🚨 TOKEN DETECTED! Token: {contract_address} | Amount: {actual_token_amount:.4f}")
                            
                            tx_data = {
                                "type": "TOKEN",
                                "asset": contract_address,
                                "amount": actual_token_amount,
                                "price_usd": 0.0,
                                "tx_hash": tx_hash_str
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