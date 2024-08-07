import requests
import json
import io
import pygame
import threading
import queue
import time
import random
import openai
import pyaudio
import wave
import numpy as np
import os

# Constants
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
SILENCE_THRESHOLD = 500
SILENCE_DURATION = 1  # seconds
LANG = 'zh'

openai.api_base = 'http://100.65.8.31:8000/v1'
openai.api_key = ''

def clear_lines():
    print("\033[2J")

class AudioRecorder:
    def __init__(self):
        self.audio = pyaudio.PyAudio()
        self.stream = None
        self.frames = []
        self.is_recording = False
        self.silence_start = None

    def start_recording(self):
        self.is_recording = True
        self.frames = []
        self.silence_start = None
        self.stream = self.audio.open(format=FORMAT, channels=CHANNELS,
                                      rate=RATE, input=True,
                                      frames_per_buffer=CHUNK,
                                      stream_callback=self.callback)
        self.stream.start_stream()
        print("Recording started...")

    def stop_recording(self):
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        self.stream = None
        self.is_recording = False
        print("Recording stopped.")
        return self.save_audio()

    def save_audio(self):
        filename = f"recording_{int(time.time())}.wav"
        wf = wave.open(filename, 'wb')
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(self.audio.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b''.join(self.frames))
        wf.close()
        return filename

    def callback(self, in_data, frame_count, time_info, status):
        if self.is_recording:
            self.frames.append(in_data)
            amplitude = np.frombuffer(in_data, dtype=np.int16).max()
            if amplitude < SILENCE_THRESHOLD:
                if self.silence_start is None:
                    self.silence_start = time.time()
                elif time.time() - self.silence_start > SILENCE_DURATION:
                    self.is_recording = False
            else:
                self.silence_start = None
        return (in_data, pyaudio.paContinue)

    def listen(self):
        self.start_recording()
        try:
            while self.is_recording:
                time.sleep(0.1)
        except KeyboardInterrupt:
            pass
        finally:
            return self.stop_recording()

    def __del__(self):
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        self.audio.terminate()

class AudioPlayer:
    def __init__(self):
        self.text_queue = queue.Queue()
        self.audio_data_queue = queue.Queue()
        self.is_playing = False
        pygame.mixer.init()
        threading.Thread(target=self._request_audio_thread, daemon=True).start()
        threading.Thread(target=self._play_audio_thread, daemon=True).start()

    def add_to_queue(self, text):
        self.text_queue.put(text)

    def _request_audio_thread(self):
        while True:
            text = self.text_queue.get()
            response = requests.get("http://100.65.8.31:8001/api/voice/tts", params={"query": text})
            
            if response.status_code == 200:
                audio_data = io.BytesIO(response.content)
                self.audio_data_queue.put(audio_data)
            else:
                print(f"Error: Received status code {response.status_code}")
            
            self.text_queue.task_done()

    def _play_audio_thread(self):
        while True:
            audio_data = self.audio_data_queue.get()
            self._play_audio(audio_data)
            time.sleep(0.8 + 0.1 * abs(random.random()))
            self.audio_data_queue.task_done()

    def _play_audio(self, audio_data):
        self.is_playing = True
        pygame.mixer.music.load(audio_data)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
        self.is_playing = False

def truncate_to_last_sentence(text):
    last_punct = max(text.rfind('！'), text.rfind('。'), text.rfind('？'))
    if last_punct != -1:
        return text[:last_punct + 1]
    return text

def clean_text(text):
    text = text.replace("\n", "")
    text = text.replace("*", "")
    return text

def asr_request(prepared_file):
    url = "http://localhost:50000/api/v1/asr"
    
    with open(prepared_file, 'rb') as f:
        files = [('files', (prepared_file, f, 'audio/wav'))]
        data = {'keys': prepared_file, 'lang': LANG}
        response = requests.post(url, files=files, data=data)
    
    os.remove(prepared_file)
    
    if response.status_code == 200:
        return response.json()
    else:
        print(f"ASR Error: Received status code {response.status_code}")
        return None
    
def stream_chat_response(messages):
    response = openai.ChatCompletion.create(
        model="internlm/internlm2_5-7b-chat",
        messages=messages,
        stream=True
    )

    full_text = ""
    for chunk in response:
        if chunk.choices[0].delta.get("content"):
            new_content = chunk.choices[0].delta.content
            full_text += new_content
            yield new_content, full_text

audio_player = AudioPlayer()
recorder = AudioRecorder()

history = []

while True:
    
    print("Listening... (Speak now)")
    audio_file = recorder.listen()
    print("Processing speech...")
    result = asr_request(audio_file)
    query = result['result'][0]['clean_text']

    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        *[{"role": "user" if i % 2 == 0 else "assistant", "content": msg} for i, msg in enumerate(sum(history, ()))],
        {"role": "user", "content": query}
    ]

    full_text = ""
    audio_chunk = ""

    for new_content, full_text in stream_chat_response(messages):
        clear_lines()
        print("You said:", query)
        print(full_text)

        audio_chunk += new_content

        if ('！' in audio_chunk or '？' in audio_chunk or '。' in audio_chunk) and len(audio_chunk) > 55:
            truncated_chunk = truncate_to_last_sentence(audio_chunk)
            if truncated_chunk:
                cleaned_chunk = clean_text(truncated_chunk)
                audio_player.add_to_queue(cleaned_chunk)
                audio_chunk = audio_chunk[len(truncated_chunk):]

    if audio_chunk:
        truncated_chunk = truncate_to_last_sentence(audio_chunk)
        if truncated_chunk:
            audio_player.add_to_queue(truncated_chunk)
        if len(audio_chunk) > len(truncated_chunk):
            audio_player.add_to_queue(audio_chunk[len(truncated_chunk):])

    history.append((query, full_text))
    history = history[-8:]

    audio_player.text_queue.join()
    audio_player.audio_data_queue.join()