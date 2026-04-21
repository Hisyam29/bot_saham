import os

RUN_BOT = os.getenv("RUN_BOT")

if RUN_BOT != "ON":
    print("Bot OFF")
    exit()

print("Bot ON - mulai scan saham...")