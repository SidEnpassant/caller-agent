"""
Twilio Voice Service - Vertex AI Gemini Live

Features:
  - Session resumption: Preserves context across reconnects
  - Context window compression: Prevents early session close
  - Input/output transcription: Real-time speech-to-text
  - Auto-reconnect: Handles disconnections gracefully
"""

import asyncio
import logging
from google import genai
from google.genai import types
from config import Config

logger = logging.getLogger(__name__)

_RECONNECT_DELAY = 1.5

SYSTEM_INSTRUCTION = """You are a helpful voice assistant powered by Twilio and Google Gemini.

Your role:
- Respond naturally to user questions
- Keep responses brief (2-3 sentences)
- Be warm and conversational

Communication style:
- Clear and simple language
- One topic at a time"""


class TwilioVoiceSession:
    """Manages a single Vertex AI Gemini Live session for a Twilio call"""
    
    def __init__(self):
        self._queue = asyncio.Queue()
        self._session = None
        self._closed = False

    async def send_audio(self, audio_data: bytes):
        """Send PCM audio to Gemini (no buffering/chunking)"""
        if self._closed:
            raise RuntimeError("Session is closed")
        if self._session is None:
            logger.debug("send_audio: session not ready, dropping chunk")
            return
        try:
            await self._session.send_realtime_input(
                audio=types.Blob(
                    data=audio_data,
                    mime_type="audio/pcm;rate=16000"
                )
            )
        except Exception as e:
            logger.debug(f"send_audio: session closed mid-send, dropping chunk ({e})")
            self._session = None

    async def receive(self):
        """
        Yields events:
          {"type": "audio_chunk", "data": bytes}
          {"type": "turn_complete"}
          {"type": "input_transcription", "text": str}
          {"type": "output_transcription", "text": str}
          {"type": "error", "error": str}
        """
        while not self._closed:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                yield event
            except asyncio.TimeoutError:
                continue


class TwilioVoiceService:
    """Manages Vertex AI Gemini Live sessions for Twilio calls"""
    
    def __init__(self):
        if not Config.VERTEX_PROJECT_ID:
            raise ValueError(
                "GOOGLE_CLOUD_PROJECT or GCP_PROJECT_ID env variable required"
            )

        self.client = genai.Client(
            vertexai=True,
            project=Config.VERTEX_PROJECT_ID,
            location=Config.VERTEX_LOCATION,
        )

        self.active_sessions: dict[str, TwilioVoiceSession] = {}
        self.ready_events: dict[str, asyncio.Event] = {}
        self._run_tasks: dict[str, asyncio.Task] = {}

        logger.info(
            f"TwilioVoiceService initialized — "
            f"project={Config.VERTEX_PROJECT_ID}, "
            f"location={Config.VERTEX_LOCATION}, "
            f"model={Config.VERTEX_LIVE_MODEL}"
        )

    async def get_or_create_session(
        self,
        stream_sid: str,
        websocket=None
    ) -> TwilioVoiceSession:
        """Get existing session or create new one for this Twilio stream"""
        if stream_sid in self.active_sessions:
            session = self.active_sessions[stream_sid]
            if not session._closed:
                logger.debug(f"Reusing session for {stream_sid}")
                return session
            await self._cleanup(stream_sid)

        logger.info(f"Creating new session for {stream_sid}")

        ready_event = asyncio.Event()
        self.ready_events[stream_sid] = ready_event

        task = asyncio.create_task(self._run(stream_sid, ready_event, websocket))
        self._run_tasks[stream_sid] = task

        try:
            await asyncio.wait_for(ready_event.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            logger.error(f"Session for {stream_sid} timed out")
            await self.end_session(stream_sid)
            raise RuntimeError("Gemini Live session initialization timed out")

        return self.active_sessions[stream_sid]

    async def end_session(self, stream_sid: str):
        """End session for this Twilio stream"""
        logger.info(f"Ending session for {stream_sid}")
        await self._cleanup(stream_sid)

    async def _run(self, stream_sid: str, ready_event: asyncio.Event, websocket):
        """Main session loop with auto-reconnect and session resumption"""
        live_session = TwilioVoiceSession()
        self.active_sessions[stream_sid] = live_session

        resumption_handle = None

        while True:
            try:
                logger.info(
                    f"Connecting to Vertex AI Gemini Live for {stream_sid}"
                    + (" (resuming)" if resumption_handle else " (new)")
                )

                config = types.LiveConnectConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name="Puck"
                            )
                        )
                    ),
                    system_instruction=types.Content(
                        parts=[types.Part.from_text(text=SYSTEM_INSTRUCTION)],
                        role="user"
                    ),
                    context_window_compression=types.ContextWindowCompressionConfig(
                        sliding_window=types.SlidingWindow(),
                    ),
                    session_resumption=types.SessionResumptionConfig(
                        handle=resumption_handle
                    ),
                    input_audio_transcription=types.AudioTranscriptionConfig(),
                    output_audio_transcription=types.AudioTranscriptionConfig(),
                )

                async with self.client.aio.live.connect(
                    model=Config.VERTEX_LIVE_MODEL,
                    config=config,
                ) as session:

                    live_session._session = session

                    if not ready_event.is_set():
                        ready_event.set()
                        logger.info(f"ready_event set for {stream_sid}")

                    if websocket:
                        try:
                            await websocket.send_json({
                                "type": "connected",
                                "backend": "vertex_ai",
                                "model": Config.VERTEX_LIVE_MODEL,
                            })
                        except Exception:
                            pass

                    async for response in session.receive():

                        # Updated resumption handle
                        if response.session_resumption_update:
                            update = response.session_resumption_update
                            if update.resumable and update.new_handle:
                                resumption_handle = update.new_handle
                                logger.debug(f"Resumption handle updated for {stream_sid}")

                        # Logged GoAway signal
                        if response.go_away is not None:
                            logger.warning(
                                f"GoAway received for {stream_sid}, "
                                f"time_left={response.go_away.time_left}"
                            )

                        sc = response.server_content

                        if sc:
                            # Audio chunks from Gemini
                            if sc.model_turn:
                                for part in sc.model_turn.parts:
                                    if part.inline_data and part.inline_data.data:
                                        await live_session._queue.put({
                                            "type": "audio_chunk",
                                            "data": part.inline_data.data,
                                        })

                            # Turn complete
                            if sc.turn_complete:
                                await live_session._queue.put({"type": "turn_complete"})

                            # Input transcription (user speech)
                            if sc.input_transcription and sc.input_transcription.text:
                                await live_session._queue.put({
                                    "type": "input_transcription",
                                    "text": sc.input_transcription.text,
                                })

                            # Output transcription (AI speech)
                            if sc.output_transcription and sc.output_transcription.text:
                                await live_session._queue.put({
                                    "type": "output_transcription",
                                    "text": sc.output_transcription.text,
                                })

                live_session._session = None
                logger.info(f"Gemini session closed cleanly for {stream_sid}, reconnecting...")

            except asyncio.CancelledError:
                logger.info(f"Run task cancelled for {stream_sid}")
                break

            except Exception as e:
                if stream_sid not in self._run_tasks:
                    break
                logger.warning(
                    f"Session error for {stream_sid}: {e} — "
                    f"reconnecting in {_RECONNECT_DELAY}s..."
                )
                live_session._session = None

            await asyncio.sleep(_RECONNECT_DELAY)

        live_session._closed = True
        logger.info(f"Run loop ended for {stream_sid}")

    async def _cleanup(self, stream_sid: str):
        """Clean up session resources"""
        task = self._run_tasks.pop(stream_sid, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        session = self.active_sessions.pop(stream_sid, None)
        if session:
            session._closed = True

        self.ready_events.pop(stream_sid, None)


# Global service instance
twilio_voice_service = TwilioVoiceService()
