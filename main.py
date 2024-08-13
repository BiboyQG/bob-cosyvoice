import os
import logging
from fastapi import (
    FastAPI,
    Request,
    Depends,
    HTTPException,
    status,
    UploadFile,
    File,
    Form,
)
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse

from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from typing import List
import uuid
import requests
import hashlib
from pathlib import Path
import json

from constants import ERROR_MESSAGES
from utils.utils import (
    decode_token,
    get_current_user,
    get_verified_user,
    get_admin_user,
)
from utils.misc import calculate_sha256


from config import (
    SRC_LOG_LEVELS,
    CACHE_DIR,
    UPLOAD_DIR,
    WHISPER_MODEL,
    WHISPER_MODEL_DIR,
    WHISPER_MODEL_AUTO_UPDATE,
    DEVICE_TYPE,
    AUDIO_STT_OPENAI_API_BASE_URL,
    AUDIO_STT_OPENAI_API_KEY,
    AUDIO_TTS_OPENAI_API_BASE_URL,
    AUDIO_TTS_OPENAI_API_KEY,
    AUDIO_TTS_API_KEY,
    AUDIO_STT_ENGINE,
    AUDIO_STT_MODEL,
    AUDIO_TTS_ENGINE,
    AUDIO_TTS_MODEL,
    AUDIO_TTS_VOICE,
    AppConfig,
)

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["AUDIO"])

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.state.config = AppConfig()

app.state.config.STT_OPENAI_API_BASE_URL = AUDIO_STT_OPENAI_API_BASE_URL
app.state.config.STT_OPENAI_API_KEY = AUDIO_STT_OPENAI_API_KEY
app.state.config.STT_ENGINE = AUDIO_STT_ENGINE
app.state.config.STT_MODEL = AUDIO_STT_MODEL

app.state.config.TTS_OPENAI_API_BASE_URL = AUDIO_TTS_OPENAI_API_BASE_URL
app.state.config.TTS_OPENAI_API_KEY = AUDIO_TTS_OPENAI_API_KEY
app.state.config.TTS_ENGINE = AUDIO_TTS_ENGINE
app.state.config.TTS_MODEL = AUDIO_TTS_MODEL
app.state.config.TTS_VOICE = AUDIO_TTS_VOICE
app.state.config.TTS_API_KEY = AUDIO_TTS_API_KEY

# setting device type for whisper model
whisper_device_type = DEVICE_TYPE if DEVICE_TYPE and DEVICE_TYPE == "cuda" else "cpu"
log.info(f"whisper_device_type: {whisper_device_type}")

SPEECH_CACHE_DIR = Path(CACHE_DIR).joinpath("./audio/speech/")
SPEECH_CACHE_DIR.mkdir(parents=True, exist_ok=True)


class TTSConfigForm(BaseModel):
    OPENAI_API_BASE_URL: str
    OPENAI_API_KEY: str
    API_KEY: str
    ENGINE: str
    MODEL: str
    VOICE: str


class STTConfigForm(BaseModel):
    OPENAI_API_BASE_URL: str
    OPENAI_API_KEY: str
    ENGINE: str
    MODEL: str


class AudioConfigUpdateForm(BaseModel):
    tts: TTSConfigForm
    stt: STTConfigForm


from pydub import AudioSegment
from pydub.utils import mediainfo


def is_mp4_audio(file_path):
    """Check if the given file is an MP4 audio file."""
    if not os.path.isfile(file_path):
        print(f"File not found: {file_path}")
        return False

    info = mediainfo(file_path)
    if (
        info.get("codec_name") == "aac"
        and info.get("codec_type") == "audio"
        and info.get("codec_tag_string") == "mp4a"
    ):
        return True
    return False


def convert_mp4_to_wav(file_path, output_path):
    """Convert MP4 audio file to WAV format."""
    audio = AudioSegment.from_file(file_path, format="mp4")
    audio.export(output_path, format="wav")
    print(f"Converted {file_path} to {output_path}")


@app.get("/config")
async def get_audio_config(user=Depends(get_admin_user)):
    return {
        "tts": {
            "OPENAI_API_BASE_URL": app.state.config.TTS_OPENAI_API_BASE_URL,
            "OPENAI_API_KEY": app.state.config.TTS_OPENAI_API_KEY,
            "API_KEY": app.state.config.TTS_API_KEY,
            "ENGINE": app.state.config.TTS_ENGINE,
            "MODEL": app.state.config.TTS_MODEL,
            "VOICE": app.state.config.TTS_VOICE,
        },
        "stt": {
            "OPENAI_API_BASE_URL": app.state.config.STT_OPENAI_API_BASE_URL,
            "OPENAI_API_KEY": app.state.config.STT_OPENAI_API_KEY,
            "ENGINE": app.state.config.STT_ENGINE,
            "MODEL": app.state.config.STT_MODEL,
        },
    }


@app.post("/config/update")
async def update_audio_config(
    form_data: AudioConfigUpdateForm, user=Depends(get_admin_user)
):
    app.state.config.TTS_OPENAI_API_BASE_URL = form_data.tts.OPENAI_API_BASE_URL
    app.state.config.TTS_OPENAI_API_KEY = form_data.tts.OPENAI_API_KEY
    app.state.config.TTS_API_KEY = form_data.tts.API_KEY
    app.state.config.TTS_ENGINE = form_data.tts.ENGINE
    app.state.config.TTS_MODEL = form_data.tts.MODEL
    app.state.config.TTS_VOICE = form_data.tts.VOICE

    app.state.config.STT_OPENAI_API_BASE_URL = form_data.stt.OPENAI_API_BASE_URL
    app.state.config.STT_OPENAI_API_KEY = form_data.stt.OPENAI_API_KEY
    app.state.config.STT_ENGINE = form_data.stt.ENGINE
    app.state.config.STT_MODEL = form_data.stt.MODEL

    return {
        "tts": {
            "OPENAI_API_BASE_URL": app.state.config.TTS_OPENAI_API_BASE_URL,
            "OPENAI_API_KEY": app.state.config.TTS_OPENAI_API_KEY,
            "API_KEY": app.state.config.TTS_API_KEY,
            "ENGINE": app.state.config.TTS_ENGINE,
            "MODEL": app.state.config.TTS_MODEL,
            "VOICE": app.state.config.TTS_VOICE,
        },
        "stt": {
            "OPENAI_API_BASE_URL": app.state.config.STT_OPENAI_API_BASE_URL,
            "OPENAI_API_KEY": app.state.config.STT_OPENAI_API_KEY,
            "ENGINE": app.state.config.STT_ENGINE,
            "MODEL": app.state.config.STT_MODEL,
        },
    }


@app.post("/speech")
async def speech(request: Request, user=Depends(get_verified_user)):
    body = await request.body()
    name = hashlib.sha256(body).hexdigest()

    file_path = SPEECH_CACHE_DIR.joinpath(f"{name}.mp3")
    file_body_path = SPEECH_CACHE_DIR.joinpath(f"{name}.json")

    # Check if the file already exists in the cache
    if file_path.is_file():
        return FileResponse(file_path)

    if app.state.config.TTS_ENGINE == "openai":
        headers = {}
        headers["Authorization"] = f"Bearer {app.state.config.TTS_OPENAI_API_KEY}"
        headers["Content-Type"] = "application/json"

        try:
            body = body.decode("utf-8")
            body = json.loads(body)
            body["model"] = app.state.config.TTS_MODEL
            query = body["input"]
            print(query)
            body = json.dumps(body).encode("utf-8")
        except Exception as e:
            pass

        r = None
        try:
            r = requests.get("http://100.65.8.31:8001/api/voice/tts", params={"query": query})

            # r.raise_for_status()

            # Save the streaming content to a file
            with open(file_path, "wb") as f:
                f.write(r.content)

            with open(file_body_path, "w") as f:
                json.dump(json.loads(body.decode("utf-8")), f)

            # Return the saved file
            return FileResponse(file_path)

        except Exception as e:
            log.exception(e)
            error_detail = "Open WebUI: Server Connection Error"
            if r is not None:
                try:
                    res = r.json()
                    if "error" in res:
                        error_detail = f"External: {res['error']['message']}"
                except:
                    error_detail = f"External: {e}"

            raise HTTPException(
                status_code=r.status_code if r != None else 500,
                detail=error_detail,
            )

    elif app.state.config.TTS_ENGINE == "elevenlabs":
        payload = None
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception as e:
            log.exception(e)
            raise HTTPException(status_code=400, detail="Invalid JSON payload")

        voice_id = payload.get("voice", "")
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": app.state.config.TTS_API_KEY,
        }

        data = {
            "text": payload["input"],
            "model_id": app.state.config.TTS_MODEL,
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.5},
        }

        try:
            r = requests.post(url, json=data, headers=headers)

            r.raise_for_status()

            # Save the streaming content to a file
            with open(file_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

            with open(file_body_path, "w") as f:
                json.dump(json.loads(body.decode("utf-8")), f)

            # Return the saved file
            return FileResponse(file_path)

        except Exception as e:
            log.exception(e)
            error_detail = "Open WebUI: Server Connection Error"
            if r is not None:
                try:
                    res = r.json()
                    if "error" in res:
                        error_detail = f"External: {res['error']['message']}"
                except:
                    error_detail = f"External: {e}"

            raise HTTPException(
                status_code=r.status_code if r != None else 500,
                detail=error_detail,
            )


@app.post("/transcriptions")
def transcribe(
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    log.info(f"file.content_type: {file.content_type}")

    if file.content_type not in ["audio/mpeg", "audio/wav"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.FILE_NOT_SUPPORTED,
        )

    try:
        ext = file.filename.split(".")[-1]

        id = uuid.uuid4()
        filename = f"{id}.{ext}"

        file_dir = f"{CACHE_DIR}/audio/transcriptions"
        os.makedirs(file_dir, exist_ok=True)
        file_path = f"{file_dir}/{filename}"

        print(filename)

        contents = file.file.read()
        with open(file_path, "wb") as f:
            f.write(contents)
            f.close()

        if app.state.config.STT_ENGINE == "":
            from faster_whisper import WhisperModel
            whisper_kwargs = {
                "model_size_or_path": WHISPER_MODEL,
                "device": whisper_device_type,
                "compute_type": "int8",
                "download_root": WHISPER_MODEL_DIR,
                "local_files_only": not WHISPER_MODEL_AUTO_UPDATE,
            }

            log.debug(f"whisper_kwargs: {whisper_kwargs}")

            try:
                model = WhisperModel(**whisper_kwargs)
            except:
                log.warning(
                    "WhisperModel initialization failed, attempting download with local_files_only=False"
                )
                whisper_kwargs["local_files_only"] = False
                model = WhisperModel(**whisper_kwargs)

            segments, info = model.transcribe(file_path, beam_size=5)
            log.info(
                "Detected language '%s' with probability %f"
                % (info.language, info.language_probability)
            )

            # url = "http://localhost:50000/api/v1/asr"

            # print("file_path:", file_path)

            # with open(file_path, 'rb') as f:
            #     files = [('files', (file_path, f, 'audio/wav'))]
            #     data = {'keys': file_path, 'lang': 'zh'}
            #     response = requests.post(url, files=files, data=data)

            # print("response:", response)

            # transcript = result['result'][0]['clean_text']

            transcript = "".join([segment.text for segment in list(segments)])

            data = {"text": transcript.strip()}

            # save the transcript to a json file
            transcript_file = f"{file_dir}/{id}.json"
            with open(transcript_file, "w") as f:
                json.dump(data, f)

            print(data)

            return data

        elif app.state.config.STT_ENGINE == "openai":
            if is_mp4_audio(file_path):
                print("is_mp4_audio")
                os.rename(file_path, file_path.replace(".wav", ".mp4"))
                # Convert MP4 audio file to WAV format
                convert_mp4_to_wav(file_path.replace(".wav", ".mp4"), file_path)

            headers = {"Authorization": f"Bearer {app.state.config.STT_OPENAI_API_KEY}"}

            files = {"file": (filename, open(file_path, "rb"))}
            data = {"model": app.state.config.STT_MODEL}

            print(files, data)

            r = None
            try:
                r = requests.post(
                    url=f"{app.state.config.STT_OPENAI_API_BASE_URL}/audio/transcriptions",
                    headers=headers,
                    files=files,
                    data=data,
                )

                r.raise_for_status()

                data = r.json()

                # save the transcript to a json file
                transcript_file = f"{file_dir}/{id}.json"
                with open(transcript_file, "w") as f:
                    json.dump(data, f)

                print(data)
                return data
            except Exception as e:
                log.exception(e)
                error_detail = "Open WebUI: Server Connection Error"
                if r is not None:
                    try:
                        res = r.json()
                        if "error" in res:
                            error_detail = f"External: {res['error']['message']}"
                    except:
                        error_detail = f"External: {e}"

                raise HTTPException(
                    status_code=r.status_code if r != None else 500,
                    detail=error_detail,
                )

    except Exception as e:
        log.exception(e)

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT(e),
        )


def get_available_models() -> List[dict]:
    if app.state.config.TTS_ENGINE == "openai":
        return [{"id": "tts-1"}, {"id": "tts-1-hd"}]
    elif app.state.config.TTS_ENGINE == "elevenlabs":
        headers = {
            "xi-api-key": app.state.config.TTS_API_KEY,
            "Content-Type": "application/json",
        }

        try:
            response = requests.get(
                "https://api.elevenlabs.io/v1/models", headers=headers
            )
            response.raise_for_status()
            models = response.json()
            return [
                {"name": model["name"], "id": model["model_id"]} for model in models
            ]
        except requests.RequestException as e:
            log.error(f"Error fetching voices: {str(e)}")
    return []


@app.get("/models")
async def get_models(user=Depends(get_verified_user)):
    return {"models": get_available_models()}


def get_available_voices() -> List[dict]:
    if app.state.config.TTS_ENGINE == "openai":
        return [
            {"name": "alloy", "id": "alloy"},
            {"name": "echo", "id": "echo"},
            {"name": "fable", "id": "fable"},
            {"name": "onyx", "id": "onyx"},
            {"name": "nova", "id": "nova"},
            {"name": "shimmer", "id": "shimmer"},
        ]
    elif app.state.config.TTS_ENGINE == "elevenlabs":
        headers = {
            "xi-api-key": app.state.config.TTS_API_KEY,
            "Content-Type": "application/json",
        }

        try:
            response = requests.get(
                "https://api.elevenlabs.io/v1/voices", headers=headers
            )
            response.raise_for_status()
            voices_data = response.json()

            voices = []
            for voice in voices_data.get("voices", []):
                voices.append({"name": voice["name"], "id": voice["voice_id"]})
            return voices
        except requests.RequestException as e:
            log.error(f"Error fetching voices: {str(e)}")

    return []


@app.get("/voices")
async def get_voices(user=Depends(get_verified_user)):
    return {"voices": get_available_voices()}
