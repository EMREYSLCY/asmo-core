import os
import json
import asyncio
import websockets
import logging
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

connected_clients = set()

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
                await broadcast_alert({
                    "type": "NATIVE",
                    "asset": "ARC",
                    "amount": actual_value,
                    "price_usd": ARC_PRICE_USD,
                    "tx_hash": tx.hash.hex()
                })

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
                        amount = int(log.data.hex(), 16)
                        if amount > 0:
                            tx_hash_str = receipt.transactionHash.hex()
                            contract_address = log.address
                            logger.info(f"🚨 TOKEN DETECTED! Token: {contract_address} | TX: {tx_hash_str}")
                            await broadcast_alert({
                                "type": "TOKEN",
                                "asset": contract_address,
                                "amount": "Unknown (Raw)",
                                "price_usd": 0.0,
                                "tx_hash": tx_hash_str
                            })
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