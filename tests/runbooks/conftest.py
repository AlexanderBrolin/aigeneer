"""Shared fixtures for runbook tests."""


class MockTool:
    """Mock for LangChain-style MCP tools used by runbooks.

    Runbook tools return dicts with stdout, stderr, exit_code.
    """

    def __init__(self, name: str, response: dict):
        self.name = name
        self._response = response

    async def ainvoke(self, params: dict) -> dict:
        return self._response


class SequentialMockTool:
    """Mock tool that returns responses in order for sequential calls."""

    def __init__(self, name: str, responses: list[dict]):
        self.name = name
        self._responses = list(responses)
        self._call_index = 0

    async def ainvoke(self, params: dict) -> dict:
        resp = self._responses[self._call_index]
        self._call_index += 1
        return resp
