import asyncio
import json
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse
import uvicorn
from config import Config
from audio_converter import AudioConverter
from twilio_voice_service import twilio_voice_service

# Here it Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Twilio-Gemini Voice Agent (Vertex AI)")

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "ok",
        "service": "Twilio-Gemini Voice Agent",
        "backend": "Vertex AI"
    }

@app.post("/twiml")
async def twiml():
    """
    TwiML endpoint for Twilio to connect the call to WebSocket
    This is what you configure in your Twilio phone number settings
    """
    # Get the WebSocket URL (we will need to replace this with our ngrok URL)
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
    Handles bidirectional audio streaming between Twilio and Gemini (Vertex AI)
    """
    await websocket.accept()
    logger.info("✓ WebSocket connection established with Twilio")
    
    stream_sid = None
    live_session = None
    receiver_task = None
    
    try:
        # Main loop: received from Twilio
        while True:
            try:
                # Received message from Twilio
                data = await websocket.receive_text()
                message = json.loads(data)
                
                event = message.get("event")
                
                if event == "start":
                    # Stream started
                    stream_sid = message["start"]["streamSid"]
                    logger.info(f"✓ Stream started: {stream_sid}")
                    
                    # Created Vertex AI session
                    live_session = await twilio_voice_service.get_or_create_session(
                        stream_sid, websocket=websocket
                    )
                    
                    # Started listening for Gemini responses
                    async def stream_responses():
                        try:
                            async for event in live_session.receive():
                                event_type = event.get("type")
                                
                                if event_type == "audio_chunk":
                                    # Converted Gemini's audio to Twilio format
                                    audio_bytes = event["data"]
                                    
                                    # Gemini sends PCM at 24kHz, converted to μ-law 8kHz
                                    base64_audio = AudioConverter.encode_for_twilio(
                                        audio_bytes, 
                                        sample_rate=24000
                                    )
                                    
                                    # Send to Twilio
                                    await websocket.send_json({
                                        "event": "media",
                                        "streamSid": stream_sid,
                                        "media": {
                                            "payload": base64_audio
                                        }
                                    })
                                    logger.debug(f"→ Sent {len(base64_audio)} bytes to Twilio")
                                
                                elif event_type == "turn_complete":
                                    logger.info("✓ Gemini turn complete")
                                
                                elif event_type == "input_transcription":
                                    logger.info(f"📝 User said: {event['text']}")
                                
                                elif event_type == "output_transcription":
                                    logger.info(f"🤖 AI said: {event['text']}")
                                
                                elif event_type == "error":
                                    logger.error(f"❌ Gemini error: {event['error']}")
                        
                        except asyncio.CancelledError:
                            pass
                        except Exception as e:
                            logger.error(f"stream_responses error: {e}")
                    
                    receiver_task = asyncio.create_task(stream_responses())
                
                elif event == "media":
                    # Audio data from caller - streamed directly without buffering
                    if live_session:
                        payload = message["media"]["payload"]
                        
                        # Converted Twilio audio to Gemini format (PCM 16kHz)
                        pcm_audio = AudioConverter.decode_twilio_audio(payload)
                        
                        # Sent directly to Gemini (no chunk buffering)
                        await live_session.send_audio(pcm_audio)
                        logger.debug(f"← Received {len(payload)} bytes from Twilio, sent to Gemini")
                
                elif event == "stop":
                    # Stream stopped
                    logger.info(f"✓ Stream stopped: {stream_sid}")
                    break
            
            except WebSocketDisconnect:
                logger.info("✗ WebSocket disconnected")
                break
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                continue
    
    except Exception as e:
        logger.error(f"Error in WebSocket handler: {e}")
    
    finally:
        # Cleaned up
        logger.info("Cleaning up session...")
        
        # Cancelled receiver task
        if receiver_task:
            receiver_task.cancel()
            try:
                await receiver_task
            except asyncio.CancelledError:
                pass
        
        # Ended Gemini session
        if stream_sid:
            await twilio_voice_service.end_session(stream_sid)
        
        # Closed WebSocket
        try:
            await websocket.close()
        except:
            pass
        
        logger.info("✓ Session cleanup complete")

if __name__ == "__main__":
    # Validated configuration
    try:
        Config.validate()
        logger.info("✓ Configuration validated")
    except ValueError as e:
        logger.error(f"✗ Configuration error: {e}")
        exit(1)
    
    logger.info(f"\n Starting Twilio-Gemini Voice Agent (Vertex AI)")
    logger.info(f" Project: {Config.VERTEX_PROJECT_ID}")
    logger.info(f" Location: {Config.VERTEX_LOCATION}")
    logger.info(f" Model: {Config.VERTEX_LIVE_MODEL}")
    logger.info(f" WebSocket endpoint: ws://localhost:{Config.PORT}/ws")
    logger.info(f" TwiML endpoint: http://localhost:{Config.PORT}/twiml")
    logger.info("\n  Remember to:")
    logger.info("   1. Start ngrok: ngrok http 5000")
    logger.info("   2. Update the ws_url in /twiml endpoint with your ngrok URL")
    logger.info("   3. Configure your Twilio phone number webhook\n")
    
    uvicorn.run(
        app,
        host=Config.HOST,
        port=Config.PORT,
        log_level="info"
    )
