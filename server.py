import asyncio
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse
import uvicorn
from config import Config
from audio_converter import AudioConverter
from gemini_client import GeminiClient

app = FastAPI(title="Twilio-Gemini Voice Agent")

# Store active sessions
active_sessions = {}

@app.get("/")
async def root():
    """Health check endpoint"""
    return {"status": "ok", "service": "Twilio-Gemini Voice Agent"}

@app.post("/twiml")
async def twiml():
    """
    TwiML endpoint for Twilio to connect the call to WebSocket
    This is what you configure in your Twilio phone number settings
    """
    # Get the WebSocket URL (you'll need to replace this with your ngrok URL)
    ws_url = "wss://YOUR_NGROK_URL.ngrok.io/ws"
    
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{ws_url}" />
    </Connect>
</Response>"""
    
    return PlainTextResponse(content=twiml, media_type="application/xml")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for Twilio Media Streams
    Handles bidirectional audio streaming between Twilio and Gemini
    """
    await websocket.accept()
    print("✓ WebSocket connection established with Twilio")
    
    # Initialize components
    gemini_client = GeminiClient()
    stream_sid = None
    
    # Audio buffer for accumulating chunks
    audio_buffer = bytearray()
    
    try:
        # Start Gemini session
        await gemini_client.start_session()
        
        # Define callback for Gemini audio responses
        async def handle_gemini_audio(audio_bytes: bytes, mime_type: str):
            """Handle audio received from Gemini and send to Twilio"""
            try:
                # Convert Gemini's audio to Twilio format
                # Gemini typically sends PCM at 24kHz, we need to convert to μ-law 8kHz
                sample_rate = 24000 if "24000" in mime_type else 16000
                
                base64_audio = AudioConverter.encode_for_twilio(audio_bytes, sample_rate)
                
                # Send to Twilio
                if stream_sid:
                    message = {
                        "event": "media",
                        "streamSid": stream_sid,
                        "media": {
                            "payload": base64_audio
                        }
                    }
                    await websocket.send_json(message)
                    print(f"→ Sent {len(base64_audio)} bytes to Twilio")
                    
            except Exception as e:
                print(f"Error handling Gemini audio: {e}")
        
        # Start listening for Gemini responses
        gemini_task = asyncio.create_task(
            gemini_client.receive_responses(handle_gemini_audio)
        )
        
        # Main loop: receive from Twilio
        while True:
            try:
                # Receive message from Twilio
                data = await websocket.receive_text()
                message = json.loads(data)
                
                event = message.get("event")
                
                if event == "start":
                    # Stream started
                    stream_sid = message["start"]["streamSid"]
                    print(f"✓ Stream started: {stream_sid}")
                    
                    # Send initial greeting
                    await gemini_client.send_text(
                        "You are a helpful voice assistant. Greet the caller warmly."
                    )
                
                elif event == "media":
                    # Audio data from caller
                    payload = message["media"]["payload"]
                    stream_sid = message["streamSid"]
                    
                    # Convert Twilio audio to Gemini format
                    pcm_audio = AudioConverter.decode_twilio_audio(payload)
                    
                    # Accumulate audio in buffer
                    audio_buffer.extend(pcm_audio)
                    
                    # Send chunks to Gemini (every ~100ms worth of audio)
                    # At 16kHz, 16-bit mono: 100ms = 3200 bytes
                    chunk_size = 3200
                    if len(audio_buffer) >= chunk_size:
                        chunk = bytes(audio_buffer[:chunk_size])
                        audio_buffer = audio_buffer[chunk_size:]
                        
                        # Send to Gemini
                        await gemini_client.send_audio(chunk)
                        print(f"← Received {len(payload)} bytes from Twilio, sent to Gemini")
                
                elif event == "stop":
                    # Stream stopped
                    print(f"✓ Stream stopped: {stream_sid}")
                    break
                
            except WebSocketDisconnect:
                print("✗ WebSocket disconnected")
                break
            except Exception as e:
                print(f"Error processing message: {e}")
                continue
    
    except Exception as e:
        print(f"Error in WebSocket handler: {e}")
    
    finally:
        # Cleanup
        print("Cleaning up session...")
        
        # Cancel Gemini listener task
        if 'gemini_task' in locals():
            gemini_task.cancel()
            try:
                await gemini_task
            except asyncio.CancelledError:
                pass
        
        # Close Gemini session
        await gemini_client.close_session()
        
        # Close WebSocket
        try:
            await websocket.close()
        except:
            pass
        
        print("✓ Session cleanup complete")

if __name__ == "__main__":
    # Validate configuration
    try:
        Config.validate()
        print("✓ Configuration validated")
    except ValueError as e:
        print(f"✗ Configuration error: {e}")
        exit(1)
    
    print(f"\n🚀 Starting Twilio-Gemini Voice Agent on {Config.HOST}:{Config.PORT}")
    print(f"📞 WebSocket endpoint: ws://localhost:{Config.PORT}/ws")
    print(f"📋 TwiML endpoint: http://localhost:{Config.PORT}/twiml")
    print("\n⚠️  Remember to:")
    print("   1. Start ngrok: ngrok http 5000")
    print("   2. Update the ws_url in /twiml endpoint with your ngrok URL")
    print("   3. Configure your Twilio phone number webhook\n")
    
    uvicorn.run(
        app,
        host=Config.HOST,
        port=Config.PORT,
        log_level="info"
    )
