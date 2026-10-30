import logging
from abc import ABC, abstractmethod

from code_review.models.enums import AgentType
from code_review.models.finding import Finding
from code_review.parsers.diff_parser import DiffFile

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    @property
    @abstractmethod
    def agent_type(self) -> AgentType:
        pass

    @property
    def name(self) -> str:
        return self.agent_type.value

    @abstractmethod
    def review(self, diff_files: list[DiffFile]) -> list[Finding]:
        pass

    async def review_async(self, diff_files: list[DiffFile]) -> list[Finding]:
        import asyncio

        return await asyncio.to_thread(self.review, diff_files)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(agent_type={self.agent_type!r})"
