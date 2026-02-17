import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    """Configuration management for the Twilio-Gemini voice agent"""
    
    # API Keys and Credentials
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
    TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
    TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
    
    # Server Configuration
    PORT = int(os.getenv("PORT", 5000))
    HOST = os.getenv("HOST", "0.0.0.0")
    
    # Audio Configuration
    TWILIO_SAMPLE_RATE = 8000  # Twilio uses 8kHz
    GEMINI_SAMPLE_RATE = 16000  # Gemini expects 16kHz
    AUDIO_ENCODING = "mulaw"  # Twilio uses μ-law encoding
    PCM_SAMPLE_WIDTH = 2  # 16-bit PCM
    
    # Vertex AI Configuration
    VERTEX_PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", os.getenv("GCP_PROJECT_ID"))
    VERTEX_LOCATION = os.getenv("VERTEX_LOCATION", "us-central1")
    VERTEX_LIVE_MODEL = os.getenv(
        "VERTEX_LIVE_MODEL",
        "gemini-live-2.5-flash-native-audio"
    )
    
    @classmethod
    def validate(cls):
        """Validate that all required configuration is present"""
        missing = []
        
        if not cls.GOOGLE_API_KEY:
            missing.append("GOOGLE_API_KEY")
        if not cls.VERTEX_PROJECT_ID:
            missing.append("GOOGLE_CLOUD_PROJECT or GCP_PROJECT_ID")
        if not cls.TWILIO_ACCOUNT_SID:
            missing.append("TWILIO_ACCOUNT_SID")
        if not cls.TWILIO_AUTH_TOKEN:
            missing.append("TWILIO_AUTH_TOKEN")
        
        if missing:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing)}\n"
                f"Please check your .env file"
            )
        
        return True
