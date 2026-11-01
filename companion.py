import json
import os
import tempfile
import base64
import binascii
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from sarvamai import SarvamAI


ROOT = Path(__file__).resolve().parent
LANGUAGES = {
    "en": {"name": "English", "code": "en-IN", "speaker": "ishita"},
    "te": {"name": "Telugu", "code": "te-IN", "speaker": "neha"},
    "hi": {"name": "Hindi", "code": "hi-IN", "speaker": "priya"},
}
MOODS = {"auto", "stressed", "low", "frustrated", "okay", "excited"}
MAX_BODY_BYTES = 2 * 1024 * 1024
MAX_AUDIO_BYTES = 10 * 1024 * 1024
MAX_MESSAGE_CHARS = 3000
MAX_MESSAGES = 24
APP_ENV = os.environ.get("APP_ENV", "local").lower()
APP_USERNAME = os.environ.get("APP_USERNAME", "companion")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")
_sarvam_client = None


def load_api_key():
    if os.environ.get("SARVAM_API_KEY", "").strip():
        return os.environ["SARVAM_API_KEY"].strip()

    env_file = ROOT / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            name, separator, value = line.partition("=")
            if separator and name.strip() == "SARVAM_API_KEY":
                value = value.strip().strip("\"'")
                if value:
                    os.environ["SARVAM_API_KEY"] = value
                    return value
    return None


def get_sarvam_client():
    global _sarvam_client
    if _sarvam_client is None:
        api_key = load_api_key()
        if not api_key:
            raise RuntimeError("SARVAM_API_KEY is not configured.")
        _sarvam_client = SarvamAI(api_subscription_key=api_key)
    return _sarvam_client


class CompanionHandler(BaseHTTPRequestHandler):
    def respond(self, status, payload, content_type="application/json; charset=utf-8", extra_headers=()):
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        for name, value in extra_headers:
            self.send_header(name, value)
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; media-src 'self' data:; connect-src 'self'; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(body)

    def is_allowed_origin(self, require_origin=False):
        host = self.headers.get("Host", "").lower()
        origin = self.headers.get("Origin")
        if require_origin and origin is None:
            return False
        if APP_ENV == "production":
            if not host:
                return False
            scheme = self.headers.get("X-Forwarded-Proto", "https").split(",", 1)[0].strip()
            return origin is None or origin.lower() == f"{scheme}://{host}"
        if host not in ("127.0.0.1:8000", "localhost:8000"):
            return False
        return origin is None or origin.lower() in (f"http://{host}", f"https://{host}")

    def require_auth(self):
        if APP_ENV != "production":
            return True
        if not APP_PASSWORD:
            self.respond(503, {"error": "The app password is not configured on the host."})
            return False
        authorization = self.headers.get("Authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "basic" and token:
            try:
                credentials = base64.b64decode(token, validate=True)
            except (ValueError, binascii.Error):
                credentials = b""
            expected = f"{APP_USERNAME}:{APP_PASSWORD}".encode("utf-8")
            if hmac.compare_digest(credentials, expected):
                return True
        self.respond(
            401,
            {"error": "Sign in to use the conversation companion."},
            extra_headers=[("WWW-Authenticate", 'Basic realm="Conversation Companion", charset="UTF-8"')],
        )
        return False

    def do_GET(self):
        if self.path == "/health":
            self.respond(200, {"status": "ok"})
            return
        if not self.is_allowed_origin():
            self.respond(403, {"error": "Requests must come from this app's address"})
            return
        if not self.require_auth():
            return
        if self.path not in ("/", "/index.html"):
            self.respond(404, {"error": "Not found"})
            return
        self.respond(200, (ROOT / "companion.html").read_bytes(), "text/html; charset=utf-8")

    def do_POST(self):
        if not self.is_allowed_origin(require_origin=True):
            self.respond(403, {"error": "Requests must come from this app's address"})
            return
        if not self.require_auth():
            return
        if self.path not in ("/chat", "/transcribe"):
            self.respond(404, {"error": "Not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.respond(400, {"error": "Invalid request size"})
            return
        max_length = MAX_AUDIO_BYTES if self.path == "/transcribe" else MAX_BODY_BYTES
        if length <= 0 or length > max_length:
            self.respond(413, {"error": "Request is empty or too large"})
            return
        body = self.rfile.read(length)
        if len(body) != length:
            self.respond(400, {"error": "Incomplete request body"})
            return

        try:
            if self.path == "/transcribe":
                content_type = self.headers.get("Content-Type", "").lower()
                if not content_type.startswith("audio/"):
                    self.respond(415, {"error": "Send a recorded audio file"})
                    return
                self.transcribe(body, content_type)
            else:
                if not self.headers.get("Content-Type", "").lower().startswith("application/json"):
                    self.respond(415, {"error": "Send chat details as JSON"})
                    return
                self.chat(json.loads(body))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.respond(400, {"error": "Invalid JSON request"})
        except Exception as error:
            # Avoid logging exception text because SDK errors can include request details.
            print(f"Sarvam request failed ({type(error).__name__}).")
            self.respond(502, {"error": "Sarvam could not complete that request. Check the key, credits, and try again."})

    def transcribe(self, audio_bytes, content_type):
        if not audio_bytes:
            self.respond(400, {"error": "The recording was empty. Try again or type your message."})
            return
        data = json.loads(self.headers.get("X-Companion-Options", "{}"))
        language = data.get("language", "en") if isinstance(data, dict) else "en"
        if language not in LANGUAGES:
            self.respond(400, {"error": "Choose English, Telugu, or Hindi first."})
            return
        suffixes = {
            "audio/webm": ".webm",
            "audio/ogg": ".ogg",
            "audio/mp4": ".m4a",
            "audio/mpeg": ".mp3",
            "audio/wav": ".wav",
            "audio/x-wav": ".wav",
        }
        suffix = suffixes.get(content_type.split(";", 1)[0].strip())
        if not suffix:
            self.respond(415, {"error": "This browser's recording format is not supported. Type your message instead."})
            return
        client = get_sarvam_client()
        with tempfile.NamedTemporaryFile(suffix=suffix) as audio_file:
            audio_file.write(audio_bytes)
            audio_file.flush()
            audio_file.seek(0)
            result = client.speech_to_text.transcribe(
                file=audio_file,
                model="saaras:v4",
                mode="transcribe",
                language_code=LANGUAGES[language]["code"],
            )
        transcript = (result.transcript or "").strip()
        if not transcript:
            self.respond(422, {"error": "I couldn't hear speech clearly. Try again or type your message."})
            return
        self.respond(200, {"transcript": transcript})

    def chat(self, data):
        if not isinstance(data, dict):
            self.respond(400, {"error": "Invalid chat details"})
            return
        language = data.get("language")
        mood = data.get("mood", "auto")
        messages = data.get("messages")
        speak = data.get("speak", True)
        if (
            not isinstance(language, str)
            or language not in LANGUAGES
            or not isinstance(mood, str)
            or mood not in MOODS
            or not isinstance(speak, bool)
        ):
            self.respond(400, {"error": "Choose a supported language and mood."})
            return
        if not isinstance(messages, list) or not messages:
            self.respond(400, {"error": "Write a message first."})
            return

        clean_messages = []
        for item in messages[-MAX_MESSAGES:]:
            if not isinstance(item, dict):
                self.respond(400, {"error": "Invalid conversation history"})
                return
            role, content = item.get("role"), item.get("content")
            if role not in ("user", "assistant") or not isinstance(content, str) or not content.strip():
                self.respond(400, {"error": "Invalid conversation history"})
                return
            if len(content) > MAX_MESSAGE_CHARS:
                self.respond(413, {"error": "Keep each message under 3,000 characters."})
                return
            clean_messages.append({"role": role, "content": content.strip()})
        if clean_messages[-1]["role"] != "user":
            self.respond(400, {"error": "The latest message must be from you."})
            return

        language_name = LANGUAGES[language]["name"]
        mood_guidance = {
            "auto": "Notice the user's emotional tone from what they say. Do not overstate or diagnose it.",
            "stressed": "The user feels stressed. Be calm and grounding; take one thing at a time.",
            "low": (
                "The user feels low. Be especially gentle and reassuring: comfort them first, then offer "
                "one small, optional thing they could do if it feels helpful. Make encouragement specific "
                "and believable, never pressuring or falsely upbeat."
            ),
            "frustrated": "The user feels frustrated. Acknowledge what is frustrating before offering ideas.",
            "okay": "The user feels generally okay. Keep the conversation relaxed and natural.",
            "excited": "The user feels excited. Share their energy while staying natural.",
        }[mood]
        system_prompt = (
            "You are a warm, thoughtful conversation companion who feels like a caring friend. "
            "Talk naturally about anything in the user's life: friends, family, relationships, work, "
            "academics, hobbies, decisions, stress, or an ordinary day. Listen closely and refer to details "
            "they have shared in this conversation. Acknowledge feelings without pretending to know more "
            "than they said. If they want to vent or ask for comfort, stay with them and listen instead of "
            "trying to solve everything. When they seem low, comfort them first, then gently offer one "
            "optional, low-effort next step or activity that fits their situation. It can be rest, a small "
            "change of scene, music, a hobby, reaching out to someone, self-care, or one manageable task; "
            "do not assume productivity is the answer. If they ask for ideas, give a few specific, realistic "
            "choices. Motivate with grounded encouragement tied to what they shared, not empty promises. Ask "
            "at most one gentle follow-up question at a time. Avoid judgment, canned cheerleading, and long "
            "lectures. Be honest that you are an AI if asked; do not claim to be human or remember chats "
            "that are not included here. "
            f"{mood_guidance} "
            f"Reply only in {language_name}. Do not mix languages or switch languages. "
            "For Telugu, write natural Telugu in Telugu script. For Hindi, write natural Hindi in Devanagari. "
            "For English, use natural English. If the user expresses immediate danger or intent to hurt "
            "themselves, respond with care and encourage reaching a trusted person nearby or local emergency help."
        )

        client = get_sarvam_client()
        result = client.chat.completions(
            model="sarvam-105b-conversations",
            messages=[{"role": "system", "content": system_prompt}, *clean_messages],
            max_tokens=500,
        )
        reply = (result.choices[0].message.content or "").strip()
        if not reply:
            self.respond(502, {"error": "I didn't get a reply that time. Please try again."})
            return

        audio = None
        if speak:
            try:
                speech = client.text_to_speech.convert(
                    text=reply[:2400],
                    model="bulbul:v3",
                    language_code=LANGUAGES[language]["code"],
                    speaker=LANGUAGES[language]["speaker"],
                    output_audio_codec="mp3",
                )
                if speech.audios:
                    audio = speech.audios[0]
            except Exception as error:
                print(f"Sarvam speech generation failed ({type(error).__name__}); returning text only.")
        self.respond(200, {"reply": reply, "audio": audio})

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    if not load_api_key():
        raise SystemExit("Add your Sarvam key to .env as SARVAM_API_KEY=... before starting.")
    if APP_ENV == "production" and not APP_PASSWORD:
        raise SystemExit("Set APP_PASSWORD in the host environment before starting in production.")
    port = int(os.environ.get("PORT", "8000"))
    bind_host = "0.0.0.0" if APP_ENV == "production" else "127.0.0.1"
    server = ThreadingHTTPServer((bind_host, port), CompanionHandler)
    server.daemon_threads = True
    display_host = "127.0.0.1" if bind_host == "0.0.0.0" else bind_host
    print(f"Your Conversation Companion: http://{display_host}:{port}")
    print("Chats are kept in this browser. Press Ctrl+C to stop the local server.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nConversation Companion stopped.")
    finally:
        server.server_close()
