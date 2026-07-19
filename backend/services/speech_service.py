"""
语音识别服务（ASR）
基于 faster-whisper 实现本地离线语音转文字，无需网络。
首次使用会自动下载模型（默认 tiny 模型约 75MB）。
"""
import os
import io
import logging
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)

# 使用 HuggingFace 国内镜像（避免 huggingface.co 被墙无法下载模型）
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "0")

# 配置 ffmpeg 路径（imageio-ffmpeg 自带二进制，避免系统未安装 ffmpeg）
try:
    import imageio_ffmpeg
    _ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    os.environ["FFMPEG_BINARY"] = _ffmpeg_path
    os.environ["IMAGEIO_FFMPEG_EXE"] = _ffmpeg_path
    logger.info(f"[ASR] ffmpeg 路径: {_ffmpeg_path}")
except Exception as e:
    logger.warning(f"[ASR] imageio-ffmpeg 未可用，将依赖系统 ffmpeg: {e}")
    _ffmpeg_path = None

# 模型缓存（进程级别）
_model = None
_model_size = os.getenv("WHISPER_MODEL_SIZE", "tiny")  # tiny / base / small / medium / large-v3
_device = os.getenv("WHISPER_DEVICE", "cpu")            # cpu / cuda
_compute_type = os.getenv("WHISPER_COMPUTE_TYPE", "int8")  # int8 / int8_float16 / float16 / float32


def get_model():
    """懒加载 whisper 模型（首次调用时加载，之后复用）"""
    global _model
    if _model is not None:
        return _model
    try:
        from faster_whisper import WhisperModel
        logger.info(f"[ASR] 加载 whisper 模型: size={_model_size}, device={_device}, compute={_compute_type}")
        _model = WhisperModel(
            _model_size,
            device=_device,
            compute_type=_compute_type,
            download_root=os.path.join(tempfile.gettempdir(), "whisper_models"),
        )
        logger.info("[ASR] 模型加载完成")
        return _model
    except Exception as e:
        logger.error(f"[ASR] 模型加载失败: {e}")
        raise


def transcribe(audio_bytes: bytes, language: str = "zh") -> str:
    """
    语音转文字

    Args:
        audio_bytes: 音频二进制数据（webm/wav/mp3 等格式，faster-whisper 支持 ffmpeg 解码）
        language: 语言代码，如 "zh" / "en"，None 表示自动检测

    Returns:
        识别出的文本
    """
    try:
        model = get_model()
        # 写入临时文件（某些格式 faster-whisper 需要文件路径而非 BytesIO）
        suffix = ".webm"
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        try:
            tmp.write(audio_bytes)
            tmp.flush()
            tmp.close()
            segments, info = model.transcribe(
                tmp.name,
                language=language,
                beam_size=5,
                vad_filter=True,          # 过滤静音段，提升速度
                vad_parameters=dict(
                    min_silence_duration_ms=500,
                    speech_pad_ms=200,
                ),
            )
            # segments 是生成器，迭代获取文本
            text = "".join(seg.text for seg in segments).strip()
        finally:
            try:
                os.unlink(tmp.name)
            except Exception:
                pass
        logger.info(f"[ASR] 识别成功: language={info.language}, duration={info.duration:.1f}s, text='{text[:50]}...'")
        return text
    except Exception as e:
        logger.error(f"[ASR] 识别失败: {e}")
        raise


def is_available() -> bool:
    """检查 ASR 是否可用（尝试加载模型）"""
    try:
        get_model()
        return True
    except Exception:
        return False
