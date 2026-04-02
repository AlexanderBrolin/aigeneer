"""Shared fixtures for check tests."""


class MockTool:
    """Mock for LangChain-style MCP tools."""

    def __init__(self, name: str, response: str):
        self.name = name
        self._response = response

    async def ainvoke(self, params: dict | str) -> str:
        return self._response


class DynamicMockTool:
    """Mock tool that returns different responses based on input."""

    def __init__(self, name: str, responses: dict[str, str], default: str = ""):
        self.name = name
        self._responses = responses
        self._default = default

    async def ainvoke(self, params: dict | str) -> str:
        if isinstance(params, dict):
            key = params.get("command", "") or params.get("service", "")
        else:
            key = str(params)
        for pattern, response in self._responses.items():
            if pattern in key:
                return response
        return self._default
