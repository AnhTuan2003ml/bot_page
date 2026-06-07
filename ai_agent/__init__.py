"""AI model layer.

This package intentionally contains only model client/provider code.
Business rules live in domains/, and orchestration lives in brain/.
"""

from .model_client import call_model

__all__ = ["call_model"]
