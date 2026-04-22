"""Gemini API integration using google-genai SDK."""

import asyncio
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Callable, ClassVar, Dict, List, Optional

import structlog

from ..config.settings import Settings
from .sdk_integration import ClaudeResponse, StreamUpdate

logger = structlog.get_logger()


class GeminiManager:
    """Executes prompts via Google Gemini API with coding tools."""

    _session_histories: ClassVar[Dict[str, List[Any]]] = {}

    def __init__(self, config: Settings, model: Optional[str] = None) -> None:
        self.config = config
        self.model = model or "gemini-2.5-pro"
        api_key = config.gemini_api_key
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required for projects with cli: gemini")
        from google import genai  # type: ignore[import-untyped]

        self.client = genai.Client(api_key=api_key.get_secret_value())

    async def execute(
        self,
        prompt: str,
        working_directory: Path,
        session_id: Optional[str] = None,
        stream_callback: Optional[Callable[[StreamUpdate], None]] = None,
        interrupt_event: Optional[asyncio.Event] = None,
        images: Optional[List[Dict[str, str]]] = None,
    ) -> ClaudeResponse:
        """Execute a prompt using Gemini with coding tool support."""
        from google.genai import types  # type: ignore[import-untyped]

        start_time = asyncio.get_event_loop().time()
        working_dir = working_directory.resolve()

        # Session management: in-memory history
        if not session_id or session_id not in self._session_histories:
            session_id = str(uuid.uuid4())
            self._session_histories[session_id] = []

        history: List[Any] = self._session_histories[session_id]

        system_prompt = (
            f"You are a coding assistant. "
            f"All file operations must stay within {working_dir}. "
            "Use relative paths for all file operations."
        )

        # Build conversation starting from history + new user turn
        messages: List[Any] = list(history) + [
            types.Content(
                role="user",
                parts=[types.Part(text=prompt)],
            )
        ]

        tool_declarations = self._make_tool_declarations()
        tools_impl = self._make_tools(working_dir)
        all_text: List[str] = []
        all_tools: List[Dict[str, Any]] = []

        # Manual agentic loop (automatic_function_calling disabled for control)
        for _ in range(50):
            if interrupt_event and interrupt_event.is_set():
                break

            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=messages,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    tools=tool_declarations,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(
                        disable=True
                    ),
                ),
            )

            if not response.candidates:
                break

            candidate = response.candidates[0]
            messages.append(candidate.content)

            function_calls = response.function_calls
            if function_calls:
                tool_result_parts: List[Any] = []
                for fc in function_calls:
                    tool_name = fc.name
                    tool_args = dict(fc.args) if fc.args else {}

                    if stream_callback:
                        stream_callback(
                            StreamUpdate(
                                type="assistant",
                                tool_calls=[{"name": tool_name, "input": tool_args}],
                            )
                        )

                    try:
                        result: str = tools_impl[tool_name](**tool_args)
                    except Exception as exc:
                        result = f"Error executing {tool_name}: {exc}"
                        logger.warning(
                            "Gemini tool error",
                            tool=tool_name,
                            error=str(exc),
                        )

                    all_tools.append(
                        {
                            "name": tool_name,
                            "timestamp": time.time(),
                            "input": tool_args,
                        }
                    )
                    tool_result_parts.append(
                        types.Part(
                            function_response=types.FunctionResponse(
                                name=tool_name,
                                response={"result": result},
                            )
                        )
                    )

                messages.append(types.Content(role="user", parts=tool_result_parts))
            else:
                # No more tool calls — final text response
                if response.text:
                    all_text.append(response.text)
                break

        # Persist history (keep last 40 messages to bound memory)
        self._session_histories[session_id] = messages[-40:]

        content = "".join(all_text)
        duration_ms = int((asyncio.get_event_loop().time() - start_time) * 1000)

        logger.info(
            "Gemini command completed",
            session_id=session_id,
            model=self.model,
            duration_ms=duration_ms,
            tools_count=len(all_tools),
        )

        return ClaudeResponse(
            content=content,
            session_id=session_id,
            cost=0.0,
            duration_ms=duration_ms,
            num_turns=1,
            tools_used=all_tools,
        )

    def _make_tools(self, working_dir: Path) -> Dict[str, Callable[..., str]]:
        """Return tool name → callable bound to working_dir."""

        def read_file(path: str) -> str:
            """Read the contents of a file."""
            full = _safe_path(working_dir, path)
            return full.read_text(encoding="utf-8", errors="replace")

        def write_file(path: str, content: str) -> str:
            """Write content to a file, creating parent dirs if needed."""
            full = _safe_path(working_dir, path)
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content, encoding="utf-8")
            return f"Written: {path}"

        def run_bash(command: str) -> str:
            """Run a bash command in the working directory."""
            proc = subprocess.run(
                command,
                shell=True,
                cwd=str(working_dir),
                capture_output=True,
                text=True,
                timeout=60,
            )
            out = proc.stdout
            if proc.returncode != 0:
                out += f"\nSTDERR: {proc.stderr}"
            return out or "(no output)"

        def list_directory(path: str = ".") -> str:
            """List files and directories at path."""
            full = _safe_path(working_dir, path)
            if not full.is_dir():
                return f"Not a directory: {path}"
            items = sorted(full.iterdir(), key=lambda p: (p.is_file(), p.name))
            return "\n".join(f"{'[DIR] ' if p.is_dir() else ''}{p.name}" for p in items)

        return {
            "read_file": read_file,
            "write_file": write_file,
            "run_bash": run_bash,
            "list_directory": list_directory,
        }

    def _make_tool_declarations(self) -> List[Any]:
        """Return google-genai Tool declarations."""
        from google.genai import types  # type: ignore[import-untyped]

        return [
            types.Tool(
                function_declarations=[
                    types.FunctionDeclaration(
                        name="read_file",
                        description=(
                            "Read the contents of a file relative to the working directory."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "path": types.Schema(
                                    type="STRING",
                                    description="Relative file path",
                                )
                            },
                            required=["path"],
                        ),
                    ),
                    types.FunctionDeclaration(
                        name="write_file",
                        description=(
                            "Write content to a file (creates parent directories if needed)."
                        ),
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "path": types.Schema(
                                    type="STRING",
                                    description="Relative file path",
                                ),
                                "content": types.Schema(
                                    type="STRING",
                                    description="Content to write",
                                ),
                            },
                            required=["path", "content"],
                        ),
                    ),
                    types.FunctionDeclaration(
                        name="run_bash",
                        description="Run a bash command in the working directory.",
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "command": types.Schema(
                                    type="STRING",
                                    description="Bash command to execute",
                                )
                            },
                            required=["command"],
                        ),
                    ),
                    types.FunctionDeclaration(
                        name="list_directory",
                        description="List files and directories at the given path.",
                        parameters=types.Schema(
                            type="OBJECT",
                            properties={
                                "path": types.Schema(
                                    type="STRING",
                                    description="Relative directory path (default '.')",
                                )
                            },
                        ),
                    ),
                ]
            )
        ]


def _safe_path(working_dir: Path, path: str) -> Path:
    """Resolve path and verify it stays within working_dir."""
    full = (working_dir / path).resolve()
    try:
        full.relative_to(working_dir)
    except ValueError as exc:
        raise PermissionError(
            f"Access denied: '{path}' is outside the working directory"
        ) from exc
    return full
