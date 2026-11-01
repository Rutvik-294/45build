import os
from pathlib import Path

from sarvamai import SarvamAI


for line in Path(__file__).with_name(".env").read_text().splitlines():
    name, separator, value = line.partition("=")
    if separator and name.strip() == "SARVAM_API_KEY":
        os.environ.setdefault(name.strip(), value.strip().strip("\"'"))

api_key = os.environ.get("SARVAM_API_KEY")
if not api_key:
    raise SystemExit("Add your Sarvam API key to .env as SARVAM_API_KEY=... and run again.")

client = SarvamAI(api_subscription_key=api_key)
response = client.chat.completions(
    model="sarvam-105b-conversations",
    messages=[{"role": "user", "content": "Say hello in one short sentence."}],
)
print(response.choices[0].message.content)
