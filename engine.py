import os
import asyncio
from dotenv import load_dotenv
from web3 import AsyncWeb3, AsyncHTTPProvider

load_dotenv()

ARC_RPC_URL = os.getenv("ARC_RPC_URL")
w3 = AsyncWeb3(AsyncHTTPProvider(ARC_RPC_URL))

async def scan_block(block_number):
    try:
        block = await w3.eth.get_block(block_number, full_transactions=False)
        tx_count = len(block.transactions)
        print(f"📡 Scanning Block: {block_number} | Transactions: {tx_count}")
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

    print("🔄 Initiating Continuous Block Scanning...")
    
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