import os
import asyncio
from dotenv import load_dotenv
from web3 import AsyncWeb3, AsyncHTTPProvider

load_dotenv()

ARC_RPC_URL = os.getenv("ARC_RPC_URL")
w3 = AsyncWeb3(AsyncHTTPProvider(ARC_RPC_URL))

TRANSFER_SIG = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

async def fetch_receipt(tx_hash):
    try:
        return await w3.eth.get_transaction_receipt(tx_hash)
    except Exception:
        return None

async def scan_block(block_number):
    try:
        block = await w3.eth.get_block(block_number, full_transactions=True)
        tx_count = len(block.transactions)
        print(f"📡 Scanning Block: {block_number} | Transactions: {tx_count}")
        
        for tx in block.transactions:
            if tx.value > 0:
                actual_value = float(w3.from_wei(tx.value, 'ether'))
                print(f"💎 NATIVE COIN TRANSFER! Amount: {actual_value:.4f} | TX: {tx.hash.hex()}")

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
                            print(f"🚨 SMART MONEY (TOKEN) DETECTED! Token: {contract_address} | TX: {tx_hash_str}")
                    except Exception:
                        continue
    except Exception:
        pass

async def check_network_status():
    if await w3.is_connected():
        chain_id = await w3.eth.chain_id
        latest_block = await w3.eth.block_number
        print("🟢 A.S.M.O. Core Engine Online")
        print(f"🔗 Connected to ARC Network | Chain ID: {chain_id}")
        print(f"📦 Synchronized at Block: {latest_block}")
        return latest_block
    else:
        print("🔴 Critical Error: Unable to establish connection to ARC Network.")
        return None

async def main():
    print("Initializing A.S.M.O. Boot Sequence...")
    last_scanned_block = await check_network_status()
    
    if not last_scanned_block:
        return

    print("🔄 Initiating Dual Radar (Native + Tokens)...")
    
    while True:
        try:
            current_block = await w3.eth.block_number
            if current_block > last_scanned_block:
                for block_to_scan in range(last_scanned_block + 1, current_block + 1):
                    await scan_block(block_to_scan)
                    last_scanned_block = block_to_scan
            else:
                await asyncio.sleep(2)
        except Exception:
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())