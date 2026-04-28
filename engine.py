import os
import asyncio
from dotenv import load_dotenv
from web3 import AsyncWeb3, AsyncHTTPProvider

load_dotenv()

ARC_RPC_URL = os.getenv("ARC_RPC_URL")
w3 = AsyncWeb3(AsyncHTTPProvider(ARC_RPC_URL))

async def check_network_status():
    if await w3.is_connected():
        chain_id = await w3.eth.chain_id
        latest_block = await w3.eth.block_number
        print("🟢 A.S.M.O. Core Engine Online")
        print(f"🔗 Connected to ARC Network | Chain ID: {chain_id}")
        print(f"📦 Synchronized at Block: {latest_block}")
        return True
    else:
        print("🔴 Critical Error: Unable to establish connection to ARC Network.")
        return False

async def main():
    print("Initializing A.S.M.O. Boot Sequence...")
    await asyncio.sleep(1)
    
    is_connected = await check_network_status()
    if not is_connected:
        return

if __name__ == "__main__":
    asyncio.run(main())