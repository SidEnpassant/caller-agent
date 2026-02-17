"""
Quick test script to verify your setup before running the full server
"""
import sys

def test_imports():
    """Test that all required packages are installed"""
    print("Testing imports...")
    
    try:
        import fastapi
        print("✓ fastapi installed")
    except ImportError:
        print("✗ fastapi not installed")
        return False
    
    try:
        import uvicorn
        print("✓ uvicorn installed")
    except ImportError:
        print("✗ uvicorn not installed")
        return False
    
    try:
        import websockets
        print("✓ websockets installed")
    except ImportError:
        print("✗ websockets not installed")
        return False
    
    try:
        from google import genai
        print("✓ google-genai installed")
    except ImportError:
        print("✗ google-genai not installed")
        return False
    
    try:
        from dotenv import load_dotenv
        print("✓ python-dotenv installed")
    except ImportError:
        print("✗ python-dotenv not installed")
        return False
    
    try:
        try:
            import audioop
            print("✓ audioop available")
        except ImportError:
            import audioop_lts as audioop
            print("✓ audioop-lts available (shimmed)")
    except ImportError:
        print("✗ audioop not available - install 'audioop-lts' for Python 3.13+")
        return False
    
    return True

def test_config():
    """Test configuration loading"""
    print("\nTesting configuration...")
    
    try:
        from config import Config
        print("✓ config.py loaded")
        
        # Check if env vars are set
        if Config.GOOGLE_API_KEY and Config.GOOGLE_API_KEY != "your_google_api_key_here":
            print("✓ GOOGLE_API_KEY is set")
        else:
            print("⚠ GOOGLE_API_KEY not set in .env")
        
        if Config.VERTEX_PROJECT_ID:
            print(f"✓ VERTEX_PROJECT_ID is set ({Config.VERTEX_PROJECT_ID})")
        else:
            print("⚠ VERTEX_PROJECT_ID not set in .env")
        
        if Config.TWILIO_ACCOUNT_SID and Config.TWILIO_ACCOUNT_SID != "your_twilio_account_sid_here":
            print("✓ TWILIO_ACCOUNT_SID is set")
        else:
            print("⚠ TWILIO_ACCOUNT_SID not set in .env")
        
        if Config.TWILIO_AUTH_TOKEN and Config.TWILIO_AUTH_TOKEN != "your_twilio_auth_token_here":
            print("✓ TWILIO_AUTH_TOKEN is set")
        else:
            print("⚠ TWILIO_AUTH_TOKEN not set in .env")
        
        return True
        
    except Exception as e:
        print(f"✗ Error loading config: {e}")
        return False

def test_audio_converter():
    """Test audio conversion utilities"""
    print("\nTesting audio converter...")
    
    try:
        from audio_converter import AudioConverter
        print("✓ audio_converter.py loaded")
        
        # Test basic conversion
        test_data = b'\x00\x01\x02\x03' * 100
        try:
            pcm = AudioConverter.mulaw_to_pcm(test_data)
            print("✓ μ-law to PCM conversion works")
        except Exception as e:
            print(f"✗ Conversion error: {e}")
            return False
        
        return True
        
    except Exception as e:
        print(f"✗ Error loading audio_converter: {e}")
        return False

def test_voice_service():
    """Test Twilio Voice Service loading"""
    print("\nTesting Twilio Voice Service...")
    
    try:
        from twilio_voice_service import TwilioVoiceService
        print("✓ twilio_voice_service.py loaded")
        return True
    except Exception as e:
        print(f"✗ Error loading twilio_voice_service: {e}")
        return False

def test_server():
    """Test server loading"""
    print("\nTesting server...")
    
    try:
        import server
        print("✓ server.py loaded")
        return True
    except Exception as e:
        print(f"✗ Error loading server: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("Twilio-Gemini Voice Agent - Setup Test (Vertex AI)")
    print("=" * 60)
    
    all_passed = True
    
    all_passed &= test_imports()
    all_passed &= test_config()
    all_passed &= test_audio_converter()
    all_passed &= test_voice_service()
    all_passed &= test_server()
    
    print("\n" * 60)
    if all_passed:
        print(" All tests passed! Your setup is ready.")
        print("\nNext steps:")
        print("1. Fill in your .env file with actual credentials")
        print("2. Follow SETUP_GUIDE.md for external service setup")
        print("3. Run: python server.py")
    else:
        print(" Some tests failed. Please check the errors above.")
        sys.exit(1)
    print("=" * 60)
