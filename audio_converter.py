import base64
import array
from config import Config

try:
    import audioop
except ImportError:
    try:
        import audioop_lts as audioop
    except ImportError:
        raise ImportError("Could not import audioop. For Python 3.13+, please install 'audioop-lts'")

class AudioConverter:
    """Handle audio format conversions between Twilio (μ-law) and Gemini (PCM)"""
    
    @staticmethod
    def mulaw_to_pcm(mulaw_data: bytes) -> bytes:
        """
        Convert μ-law encoded audio to PCM
        
        Args:
            mulaw_data: μ-law encoded audio bytes (8kHz)
            
        Returns:
            PCM audio bytes (16-bit, 8kHz)
        """
        # Here it Decode μ-law to linear PCM (16-bit)
        pcm_data = audioop.ulaw2lin(mulaw_data, Config.PCM_SAMPLE_WIDTH)
        return pcm_data
    
    @staticmethod
    def pcm_to_mulaw(pcm_data: bytes) -> bytes:
        """
        Convert PCM audio to μ-law encoding
        
        Args:
            pcm_data: PCM audio bytes (16-bit)
            
        Returns:
            μ-law encoded audio bytes
        """
        # Here it Encode linear PCM to μ-law
        mulaw_data = audioop.lin2ulaw(pcm_data, Config.PCM_SAMPLE_WIDTH)
        return mulaw_data
    
    @staticmethod
    def resample_audio(audio_data: bytes, from_rate: int, to_rate: int) -> bytes:
        """
        Resample audio from one sample rate to another
        
        Args:
            audio_data: PCM audio bytes
            from_rate: Source sample rate (Hz)
            to_rate: Target sample rate (Hz)
            
        Returns:
            Resampled PCM audio bytes
        """
        if from_rate == to_rate:
            return audio_data
        
        # Here it Use audioop.ratecv for resampling
        resampled, _ = audioop.ratecv(
            audio_data,
            Config.PCM_SAMPLE_WIDTH,
            1,  # mono
            from_rate,
            to_rate,
            None
        )
        return resampled
    
    @staticmethod
    def decode_twilio_audio(base64_payload: str) -> bytes:
        """
        Decode Twilio's base64-encoded μ-law audio to PCM for Gemini
        
        Args:
            base64_payload: Base64-encoded μ-law audio from Twilio
            
        Returns:
            PCM audio bytes at 16kHz for Gemini
        """
        # Step 1: Here it Decode base64
        mulaw_data = base64.b64decode(base64_payload)
        
        # Step 2: Here it Convert μ-law to PCM (8kHz)
        pcm_8khz = AudioConverter.mulaw_to_pcm(mulaw_data)
        
        # Step 3: Here it Resample from 8kHz to 16kHz for Gemini
        pcm_16khz = AudioConverter.resample_audio(
            pcm_8khz,
            Config.TWILIO_SAMPLE_RATE,
            Config.GEMINI_SAMPLE_RATE
        )
        
        return pcm_16khz
    
    @staticmethod
    def encode_for_twilio(pcm_data: bytes, sample_rate: int = None) -> str:
        """
        Encode PCM audio to base64-encoded μ-law for Twilio
        
        Args:
            pcm_data: PCM audio bytes from Gemini
            sample_rate: Current sample rate of PCM data (default: Gemini's 16kHz)
            
        Returns:
            Base64-encoded μ-law audio string for Twilio
        """
        if sample_rate is None:
            sample_rate = Config.GEMINI_SAMPLE_RATE
        
        # Step 1: Here it Resample from Gemini's rate to Twilio's 8kHz
        pcm_8khz = AudioConverter.resample_audio(
            pcm_data,
            sample_rate,
            Config.TWILIO_SAMPLE_RATE
        )
        
        # Step 2: Here it Convert PCM to μ-law
        mulaw_data = AudioConverter.pcm_to_mulaw(pcm_8khz)
        
        # Step 3: Here it Encode to base64
        base64_payload = base64.b64encode(mulaw_data).decode('utf-8')
        
        return base64_payload
    
    @staticmethod
    def chunk_audio(audio_data: bytes, chunk_size: int = 320) -> list:
        """
        Split audio data into chunks for streaming
        
        Args:
            audio_data: Audio bytes to chunk
            chunk_size: Size of each chunk in bytes (default: 320 = 20ms at 8kHz)
            
        Returns:
            List of audio chunks
        """
        chunks = []
        for i in range(0, len(audio_data), chunk_size):
            chunks.append(audio_data[i:i + chunk_size])
        return chunks
