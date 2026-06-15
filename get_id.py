import os
import urllib.request
import json
import time
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("TELEGRAM_BOT_TOKEN")

def main():
    if not token or token == "your_bot_token_here":
        print("Error: Please make sure TELEGRAM_BOT_TOKEN is set in your .env file.")
        return
        
    username = "your bot"
    try:
        url = f"https://api.telegram.org/bot{token}/getMe"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode())
            if res_data.get("ok"):
                username = f"@{res_data['result']['username']}"
    except Exception:
        pass

    print(f"Direct API Polling started for bot token: {token[:12]}...")
    print(f"1. Send a direct message to your bot ({username}) on Telegram.")
    print("2. Add your bot to the group/channel as Admin and post a message.")
    print("Press Ctrl+C to stop.")
    
    offset = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{token}/getUpdates?offset={offset}&timeout=5"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())
                if data.get("ok") and data.get("result"):
                    for update in data["result"]:
                        update_id = update["update_id"]
                        offset = update_id + 1
                        
                        # Check different update types
                        msg = update.get("message") or update.get("channel_post") or update.get("edited_channel_post") or update.get("my_chat_member")
                        if msg:
                            chat = msg.get("chat")
                            from_user = msg.get("from")
                            
                            print("\n" + "="*40)
                            if from_user:
                                print(f"USER DETAILS:")
                                print(f"  Name: {from_user.get('first_name', '')} {from_user.get('last_name', '')}")
                                print(f"  User ID: {from_user.get('id')}")
                            if chat:
                                print(f"CHAT/GROUP DETAILS:")
                                print(f"  Title/Name: {chat.get('title') or chat.get('username') or chat.get('first_name')}")
                                print(f"  Chat/Group ID: {chat.get('id')}")
                                print(f"  Type: {chat.get('type')}")
                            print("="*40 + "\n")
        except KeyboardInterrupt:
            print("\nPolling stopped.")
            break
        except Exception as e:
            # Silence transient network/conflict errors to keep output clean
            time.sleep(2)

if __name__ == "__main__":
    main()
