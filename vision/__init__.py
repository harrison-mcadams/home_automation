"""Reusable camera and vision helpers with no game knowledge.

Anything that knows about a specific game or use (Spirit Island, couch gestures)
lives in its own folder and imports from here.
"""

from vision.capture import Camera, FramePacket, fetch_still, list_cameras, parse_source

__all__ = ["Camera", "FramePacket", "fetch_still", "list_cameras", "parse_source"]
