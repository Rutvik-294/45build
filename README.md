# 45build Conversation Companion

A browser-based space to talk through everyday life. The companion responds in English, Telugu, or Hindi, follows the tone you choose, and can listen to voice messages and speak its replies.

## Features

- Text conversations with a supportive, friend-like assistant.
- English, Telugu, and Hindi language modes, with tone choices for stress, low mood, frustration, casual chat, and excitement.
- Optional voice input using the browser microphone and Sarvam speech recognition.
- Optional spoken replies using Sarvam text-to-speech.
- Daily chat history saved in this browser, separated by language. Choose a day, download its chat, or clear it.
- A password-protected production deployment on Render.

## Run locally

You need Python and a Sarvam API key.

1. Create a `.env` file in the project root with this line, then add your key after `=`:

   ```env
   SARVAM_API_KEY=
   ```

2. Install the pinned dependency:

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. Start the app:

   ```powershell
   python companion.py
   ```

4. Open <http://127.0.0.1:8000>.

Keep `.env` on your machine. It is ignored by Git. You can also provide `SARVAM_API_KEY` through your shell environment instead of `.env`.

To make a single short chat-completion call from the command line, run:

```powershell
python chat.py
```

That command also requires a key in the project's `.env` file. It sends a short prompt to Sarvam and prints the response.

## Deploy on Render

The root [`render.yaml`](render.yaml) defines the web service. In Render, create a Blueprint from this GitHub repository and use the existing `render.yaml`. Set these secret values in Render when prompted:

- `SARVAM_API_KEY`: your Sarvam API key.
- `APP_PASSWORD`: a password you choose for the app's browser sign-in.

The Blueprint sets `APP_ENV=production` and the username `companion`. Use `companion` as the sign-in username and the `APP_PASSWORD` you configured as the password. Never commit either secret. The free Render instance may sleep when idle and take a little time to wake.

## How it works

```text
Browser (companion.html)
  |-- Text and recent conversation -> companion.py -> Sarvam chat completions
  |-- Recorded audio ---------------> companion.py -> Sarvam Saaras speech-to-text
  `-- Reply audio <------------------ companion.py <- Sarvam Bulbul text-to-speech
```

`companion.py` uses Python's standard-library HTTP server. The browser interface is plain HTML, CSS, and JavaScript; the only Python package dependency is the Sarvam SDK pinned in `requirements.txt`.

## Privacy and limits

- Chat archives are stored in this browser's `localStorage`; there is no server-side chat database. Clearing browser data can remove these archives. Use **Download day** to keep a copy.
- The latest conversation turns and each new message are sent to Sarvam to generate replies. Recorded audio is sent for transcription when you use voice input.
- The server checks requests and applies production password protection. Do not expose a deployment without setting `APP_PASSWORD` and `SARVAM_API_KEY`.
- The companion offers supportive conversation, not professional mental-health care. If someone may be in immediate danger, contact a trusted person nearby or local emergency services.

## Project files

| File | Purpose |
| --- | --- |
| `companion.py` | HTTP server, authentication, Sarvam chat, transcription, and speech generation. |
| `companion.html` | Responsive chat interface, voice controls, and browser-side daily archive. |
| `chat.py` | One-call command-line chat example. |
| `requirements.txt` | Pinned Python dependency (`sarvamai`). |
| `render.yaml` | Render Blueprint for the hosted web service. |
| `.python-version` | Python version used by Render. |
| `.gitignore` | Keeps `.env`, virtual environments, and Python cache files out of Git. |

## Credits

- **Sarvam AI** provides the Python SDK and the chat, speech-to-text, and text-to-speech APIs used by this project. The app uses `sarvam-105b-conversations` for chat, `saaras:v4` for speech recognition, and `bulbul:v3` for spoken replies.
- **Render** hosts the web service.
- **Python** and browser APIs (`MediaRecorder` and `localStorage`) provide the server runtime, voice capture, and local chat archive.

This project is independent and is not endorsed by Sarvam AI or Render.

Official references: [Sarvam SDKs](https://docs.sarvam.ai/api/getting-started/sdks) | [Chat completions](https://docs.sarvam.ai/api/token-factory/chat-completions) | [Speech-to-text](https://docs.sarvam.ai/api-reference/speech-to-text/transcribe) | [Text-to-speech](https://docs.sarvam.ai/api-reference/text-to-speech/convert) | [Render Blueprints](https://render.com/docs/infrastructure-as-code) | [Python](https://www.python.org/) | [MediaRecorder](https://developer.mozilla.org/en-US/docs/Web/API/MediaRecorder) | [localStorage](https://developer.mozilla.org/en-US/docs/Web/API/Window/localStorage).
