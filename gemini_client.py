import asyncio
import base64
from google import genai
from config import Config

class GeminiClient:
    """Client for interacting with Gemini Live API"""
    
    def __init__(self):
        self.client = genai.Client(api_key=Config.GOOGLE_API_KEY)
        self.session = None
        self.model_id = Config.GEMINI_MODEL
        
    async def start_session(self):
        """Initialize a Gemini Live session"""
        config = {
            "generation_config": {
                "response_modalities": ["AUDIO"],
                "speech_config": {
                    "voice_config": {
                        "prebuilt_voice_config": {
                            "voice_name": "Puck"  # You can change this to other voices
                        }
                    }
                }
            }
        }
        
        # Create async session
        self.session = self.client.aio.live.connect(
            model=self.model_id,
            config=config
        )
        
        print(f"✓ Gemini Live session started with model: {self.model_id}")
        return self.session
    
    async def send_audio(self, pcm_audio: bytes):
        """
        Send PCM audio to Gemini
        
        Args:
            pcm_audio: PCM audio bytes (16-bit, 16kHz)
        """
        if not self.session:
            raise RuntimeError("Session not started. Call start_session() first.")
        
        # Encode PCM to base64 for transmission
        audio_b64 = base64.b64encode(pcm_audio).decode('utf-8')
        
        # Send to Gemini
        await self.session.send(
            {
                "realtime_input": {
                    "media_chunks": [
                        {
                            "mime_type": "audio/pcm",
                            "data": audio_b64
                        }
                    ]
                }
            }
        )
    
    async def send_text(self, text: str):
        """
        Send text message to Gemini
        
        Args:
            text: Text message to send
        """
        if not self.session:
            raise RuntimeError("Session not started. Call start_session() first.")
        
        await self.session.send(text)
    
    async def receive_responses(self, audio_callback):
        """
        Listen for responses from Gemini and handle them
        
        Args:
            audio_callback: Async function to call when audio is received
                           Should accept (audio_bytes, mime_type) as arguments
        """
        if not self.session:
            raise RuntimeError("Session not started. Call start_session() first.")
        
        try:
            async for response in self.session.receive():
                # Handle server content (audio responses)
                if hasattr(response, 'server_content'):
                    server_content = response.server_content
                    
                    if hasattr(server_content, 'model_turn'):
                        model_turn = server_content.model_turn
                        
                        # Extract audio parts
                        for part in model_turn.parts:
                            if hasattr(part, 'inline_data'):
                                inline_data = part.inline_data
                                mime_type = inline_data.mime_type
                                audio_data = inline_data.data
                                
                                # Decode base64 audio
                                audio_bytes = base64.b64decode(audio_data)
                                
                                # Call the callback with audio
                                await audio_callback(audio_bytes, mime_type)
                
                # Handle turn complete events
                if hasattr(response, 'server_content') and \
                   hasattr(response.server_content, 'turn_complete'):
                    print("✓ Gemini turn complete")
                    
        except Exception as e:
            print(f"Error receiving from Gemini: {e}")
            raise
    
    async def close_session(self):
        """Close the Gemini Live session"""
        if self.session:
            try:
                await self.session.close()
                print("✓ Gemini session closed")
            except Exception as e:
                print(f"Error closing Gemini session: {e}")
            finally:
                self.session = None
