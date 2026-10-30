import pytest

from code_review.agents.base import BaseAgent
from code_review.models.enums import AgentType
from code_review.models.finding import Finding
from code_review.parsers.diff_parser import DiffFile


class StubAgent(BaseAgent):
    @property
    def agent_type(self) -> AgentType:
        return AgentType.AST

    def review(self, diff_files: list[DiffFile]) -> list[Finding]:
        return []


class TestBaseAgentAbstract:
    def test_cannot_instantiate_base_agent(self) -> None:
        with pytest.raises(TypeError, match="abstract method"):
            BaseAgent()  # type: ignore[abstract]

    def test_missing_review_raises_type_error(self) -> None:
        class IncompleteAgent(BaseAgent):
            @property
            def agent_type(self) -> AgentType:
                return AgentType.AST

        with pytest.raises(TypeError, match="abstract method"):
            IncompleteAgent()  # type: ignore[abstract]

    def test_missing_agent_type_raises_type_error(self) -> None:
        class IncompleteAgent(BaseAgent):
            def review(self, diff_files: list[DiffFile]) -> list[Finding]:
                return []

        with pytest.raises(TypeError, match="abstract method"):
            IncompleteAgent()  # type: ignore[abstract]


class TestStubAgent:
    def test_stub_agent_instantiates(self) -> None:
        agent = StubAgent()
        assert agent is not None

    def test_agent_type_property(self) -> None:
        agent = StubAgent()
        assert agent.agent_type == AgentType.AST

    def test_name_property(self) -> None:
        agent = StubAgent()
        assert agent.name == "ast"

    def test_review_returns_empty_list(self) -> None:
        agent = StubAgent()
        result = agent.review([])
        assert result == []
        assert isinstance(result, list)

    def test_repr(self) -> None:
        agent = StubAgent()
        r = repr(agent)
        assert "StubAgent" in r
        assert "ast" in r
