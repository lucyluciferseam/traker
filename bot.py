import time
import requests
import telebot
from threading import Thread, Lock
from datetime import datetime

# Configuration
BOT_TOKEN = "8088857905:AAHKWthrOi-qzq9cGbgy-efsKa24lBJKDKU"
BSCSCAN_API_KEY = "XFZ3MX6XVD7YPQETB9FXABIMHSMBZE78HI"
USDT_CONTRACT = "0x55d398326f99059ff775485246999027b3197955"
POLL_INTERVAL = 15  # Seconds between checks
MAX_TX_CHECK = 5    # Max transactions to check per request

# Initialize bot
bot = telebot.TeleBot(BOT_TOKEN)

# Tracking system
tracked_addresses = {}
tracking_lock = Lock()

class AddressTracker:
    def __init__(self, address, chat_id):
        self.address = address.lower()
        self.chat_id = chat_id
        self.last_tx_hash = None
        self.running = True
        self.start_time = datetime.now()
        
        # Initialize with latest transaction
        initial_txs = get_bsc_transactions(self.address, 1)
        if initial_txs:
            self.last_tx_hash = initial_txs[0]['hash']

    def stop(self):
        self.running = False

def get_bsc_transactions(address, count=5):
    url = f"https://api.bscscan.com/api?module=account&action=tokentx&contractaddress={USDT_CONTRACT}&address={address}&sort=desc&page=1&offset={count}&apikey={BSCSCAN_API_KEY}"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data['status'] == '1':
                return data['result']
        return []
    except Exception as e:
        print(f"API Error: {str(e)}")
        return []

def format_message(tx, direction):
    value = int(tx['value']) / 10**18
    tx_link = f"https://bscscan.com/tx/{tx['hash']}"
    from_link = f"https://bscscan.com/address/{tx['from']}"
    to_link = f"https://bscscan.com/address/{tx['to']}"
    
    return (
        f"🌐 *New USDT Transaction Detected* 🌐\n\n"
        f"▫️ *Direction:* {direction}\n"
        f"▫️ *From:* [{tx['from'][:6]}...{tx['from'][-4:]}]({from_link})\n"
        f"▫️ *To:* [{tx['to'][:6]}...{tx['to'][-4:]}]({to_link})\n"
        f"▫️ *Amount:* `{value:,.2f} USDT`\n"
        f"▫️ *Timestamp:* {datetime.fromtimestamp(int(tx['timeStamp']))}\n"
        f"▫️ [View Transaction]({tx_link})"
    )

def track_address(tracker):
    while tracker.running:
        try:
            # Get latest transactions
            transactions = get_bsc_transactions(tracker.address, MAX_TX_CHECK)
            
            new_txs = []
            for tx in transactions:
                if tx['hash'] == tracker.last_tx_hash:
                    break
                new_txs.append(tx)
            
            # Process new transactions in reverse order (oldest first)
            for tx in reversed(new_txs):
                direction = "🔴 OUTGOING" if tx['from'].lower() == tracker.address else "🟢 INCOMING"
                msg = format_message(tx, direction)
                
                bot.send_message(
                    tracker.chat_id,
                    msg,
                    parse_mode="Markdown",
                    disable_web_page_preview=True
                )
                
                # Update last processed transaction
                tracker.last_tx_hash = tx['hash']
            
            time.sleep(POLL_INTERVAL)
            
        except Exception as e:
            print(f"Tracking error: {str(e)}")
            time.sleep(POLL_INTERVAL)

@bot.message_handler(commands=['track'])
def start_tracking(message):
    try:
        address = message.text.split()[1]
        if not address.startswith('0x') or len(address) != 42:
            raise ValueError
        
        with tracking_lock:
            clean_address = address.lower()
            if clean_address not in tracked_addresses:
                tracker = AddressTracker(clean_address, message.chat.id)
                tracked_addresses[clean_address] = tracker
                Thread(target=track_address, args=(tracker,), daemon=True).start()
                reply = (f"✅ Tracking initiated for:\n"
                        f"`{clean_address}`\n\n"
                        f"[View Wallet](https://bscscan.com/address/{clean_address})")
                bot.reply_to(message, reply, parse_mode="Markdown")
            else:
                bot.reply_to(message, "⚠️ This address is already being tracked!", parse_mode="Markdown")
                
    except (IndexError, ValueError):
        bot.reply_to(message, "❌ Invalid address format! Use:\n`/track 0x...`", parse_mode="Markdown")

@bot.message_handler(commands=['untrack'])
def stop_tracking(message):
    try:
        address = message.text.split()[1].lower()
        with tracking_lock:
            if address in tracked_addresses:
                tracked_addresses[address].stop()
                del tracked_addresses[address]
                reply = (f"❌ Stopped tracking:\n`{address}`\n\n"
                        f"[View Wallet](https://bscscan.com/address/{address})")
                bot.reply_to(message, reply, parse_mode="Markdown")
            else:
                bot.reply_to(message, "⚠️ This address isn't being tracked!", parse_mode="Markdown")
    except:
        bot.reply_to(message, "❌ Invalid format! Use:\n`/untrack 0x...`", parse_mode="Markdown")

@bot.message_handler(commands=['list'])
def list_tracked(message):
    with tracking_lock:
        if not tracked_addresses:
            bot.reply_to(message, "🔍 No addresses being tracked currently")
            return
        
        response = ["📋 Tracked Addresses:"]
        for address, tracker in tracked_addresses.items():
            status = "🟢 Active" if tracker.running else "🔴 Inactive"
            age = (datetime.now() - tracker.start_time).days
            response.append(
                f"• [{address[:6]}...{address[-4:]}](https://bscscan.com/address/{address})\n"
                f"  Status: {status}\n"
                f"  Tracking for: {age} days"
            )
        
        bot.send_message(message.chat.id, "\n\n".join(response), parse_mode="Markdown")

@bot.message_handler(commands=['help', 'start'])
def show_help(message):
    help_text = (
        "🤖 *USDT Tracker Bot Help*\n\n"
        "🔹 Track USDT transactions on Binance Smart Chain\n"
        "🔹 Instant notifications for new transfers\n"
        "🔹 Direct links to BscScan\n\n"
        "*Available Commands:*\n"
        "▫️ /track [address] - Start monitoring wallet\n"
        "▫️ /untrack [address] - Stop monitoring\n"
        "▫️ /list - Show tracked wallets\n"
        "▫️ /help - Show this message\n\n"
        "All messages include clickable links to view transactions on BscScan!"
    )
    bot.reply_to(message, help_text, parse_mode="Markdown")

if __name__ == "__main__":
    print("💎 USDT Tracking Bot Started")
    bot.infinity_polling()