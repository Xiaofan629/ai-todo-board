from abc import ABC, abstractmethod
from typing import Callable, Optional


class BotBase(ABC):
    """Abstract base class for bot implementations."""

    def __init__(self):
        self.on_message: Optional[Callable] = None
        self.on_event: Optional[Callable] = None

    @abstractmethod
    async def connect(self) -> None:
        """Connect and start receiving messages. Should run a reconnection loop."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully stop the bot and close connections."""
        ...

    @abstractmethod
    async def send_respond_msg(self, req_id: str, content: str,
                               stream_id: str, finish: bool = False) -> None:
        """Send a response message (streaming or accumulated)."""
        ...

    @abstractmethod
    async def send_welcome(self, req_id: str, text: str) -> None:
        """Send a welcome message."""
        ...

    @abstractmethod
    async def send_text_message(self, chat_id: str, text: str) -> None:
        """Send a plain text message to a chat via REST API."""
        ...
