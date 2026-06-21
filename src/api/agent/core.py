import google.generativeai as genai
import os
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .tools import (
    get_all_cases,
    get_case_detail,
    get_pipeline_logs,
    get_script,
    get_file_tree,
    trigger_pipeline_step,
    read_source_file,
    propose_script_fix,
    get_recent_errors,
    get_all_jobs_tool,
)

PENDING_ACTIONS: dict[str, dict] = {}
NOTIFICATIONS: list[dict] = []

SYSTEM_PROMPT = """You are the pipeline operator agent for IndianCrimes, a Hindi true crime YouTube channel automation system.

Your capabilities:
- See all cases, their status, logs, and files in real time
- Trigger pipeline steps (research, script, TTS, video assembly, etc.)
- Read source code files to diagnose failures
- Propose script fixes
- Warn about stalled or failed cases

Your personality:
- Direct and concise — no fluff
- Action-oriented — when asked to do something, do it, don't just describe what to do
- Technical — use precise language about what's happening
- Proactive — if you notice something broken while answering a question, mention it

When something fails:
1. Call get_pipeline_logs to see the error
2. Call read_source_file to understand the code
3. Diagnose the root cause in one sentence
4. Either fix it (trigger_pipeline_step after fixing) or propose_script_fix

Always use tools to check current state before answering questions about status.
Never say "I don't have access to" — you have tools, use them.
"""


class PipelineAgent:
    def __init__(self):
        api_key = os.environ.get("GOOGLE_API_KEY", "")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(
            "gemini-2.5-flash",
            system_instruction=SYSTEM_PROMPT,
        )

    def _execute_tool(self, name: str, args: dict) -> Any:
        tool_map = {
            "get_all_cases": lambda: get_all_cases(),
            "get_case_detail": lambda: get_case_detail(**args),
            "get_pipeline_logs": lambda: get_pipeline_logs(**args),
            "get_script": lambda: get_script(**args),
            "get_file_tree": lambda: get_file_tree(**args),
            "trigger_pipeline_step": lambda: trigger_pipeline_step(**args),
            "read_source_file": lambda: read_source_file(**args),
            "propose_script_fix": lambda: propose_script_fix(**args),
            "get_recent_errors": lambda: get_recent_errors(),
            "get_all_jobs": lambda: get_all_jobs_tool(),
        }
        fn = tool_map.get(name)
        if not fn:
            return {"error": f"Unknown tool: {name}"}
        try:
            return fn()
        except Exception as e:
            return {"error": f"Tool {name} failed: {e}"}

    def chat(self, message: str, case_slug: str | None, history: list[dict]) -> dict:
        # Build context prefix
        context_parts = []
        if case_slug:
            try:
                case = get_case_detail(case_slug)
                context_parts.append(
                    f"Active case: {case.get('name')} | status: {case.get('status')}"
                )
                files = get_file_tree(case_slug)
                existing = [
                    k for k, v in files.items()
                    if isinstance(v, dict) and v.get("exists")
                ]
                context_parts.append(f"Files present: {', '.join(existing) or 'none'}")
            except Exception:
                pass

        try:
            errors = get_recent_errors()
            if errors:
                context_parts.append(f"⚠ {len(errors)} case(s) with errors")
        except Exception:
            pass

        ctx = "\n".join(f"[{p}]" for p in context_parts)
        full_msg = f"{ctx}\n\n{message}" if ctx else message

        # Build tool declarations
        tools = self._build_tools()

        # Convert chat history (keep last 8 turns)
        gemini_history = []
        for h in history[-8:]:
            role = "user" if h.get("role") == "user" else "model"
            gemini_history.append({"role": role, "parts": [h.get("content", "")]})

        chat_session = self.model.start_chat(history=gemini_history)

        tool_calls_made = []
        action_cards = []

        response = chat_session.send_message(full_msg, tools=tools)

        # Tool loop — max 6 iterations
        for _ in range(6):
            candidate = response.candidates[0]
            parts = candidate.content.parts

            # Find first function_call part
            fc_part = None
            for part in parts:
                if hasattr(part, "function_call") and part.function_call.name:
                    fc_part = part
                    break

            if fc_part is None:
                break

            fn_name = fc_part.function_call.name
            fn_args = dict(fc_part.function_call.args)
            tool_calls_made.append(fn_name)

            result = self._execute_tool(fn_name, fn_args)

            # Handle action cards (requires_approval flow)
            if isinstance(result, dict) and result.get("type") == "action_card":
                action_cards.append(result)
                PENDING_ACTIONS[result["id"]] = result
                result_str = f"Action card created: {result['title']}"
            else:
                result_str = (
                    json.dumps(result) if not isinstance(result, str) else result
                )

            response = chat_session.send_message(
                genai.protos.Content(
                    parts=[
                        genai.protos.Part(
                            function_response=genai.protos.FunctionResponse(
                                name=fn_name,
                                response={"result": result_str},
                            )
                        )
                    ]
                )
            )

        # Extract text reply
        reply = ""
        for part in response.candidates[0].content.parts:
            if hasattr(part, "text") and part.text:
                reply += part.text

        return {
            "reply": reply,
            "tool_calls": tool_calls_made,
            "action_cards": action_cards,
        }

    def monitor(self) -> list[dict]:
        """Poll for new failure notifications. Called periodically by the dashboard."""
        notifications = []
        try:
            cases = get_all_cases()
            for case in cases:
                if case.get("status") == "failed":
                    notifications.append(
                        {
                            "id": f"fail_{case['slug']}",
                            "type": "error",
                            "title": f"❌ {case['name']} failed",
                            "description": case.get("notes") or "Check pipeline logs",
                            "case_slug": case["slug"],
                        }
                    )
        except Exception:
            pass

        existing_ids = {n["id"] for n in NOTIFICATIONS}
        for n in notifications:
            if n["id"] not in existing_ids:
                NOTIFICATIONS.insert(0, n)
        while len(NOTIFICATIONS) > 20:
            NOTIFICATIONS.pop()

        return notifications

    def execute_action(self, action_id: str) -> dict:
        """Execute a previously proposed action card after user approval."""
        action = PENDING_ACTIONS.get(action_id)
        if not action:
            return {"error": "Action not found"}

        action_type = action.get("action_type")
        payload = action.get("payload", {})

        try:
            if action_type == "run_step":
                result = trigger_pipeline_step(payload["slug"], payload["step"])
            elif action_type == "write_script_fix":
                slug = payload["slug"]
                path = Path(f"data/cases/{slug}/script_manual.md")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(payload["content"], encoding="utf-8")
                result = {"message": f"Script fix written to {path}"}
            else:
                result = {"error": f"Unknown action type: {action_type}"}

            del PENDING_ACTIONS[action_id]
            return {"success": True, "result": result}
        except Exception as e:
            return {"error": str(e)}

    def _build_tools(self):
        return [
            genai.protos.Tool(
                function_declarations=[
                    genai.protos.FunctionDeclaration(
                        name="get_all_cases",
                        description="Get all pipeline cases with status, last log line, and notes.",
                    ),
                    genai.protos.FunctionDeclaration(
                        name="get_case_detail",
                        description="Get full detail for a single case including scripts and videos.",
                        parameters=genai.protos.Schema(
                            type=genai.protos.Type.OBJECT,
                            properties={
                                "slug": genai.protos.Schema(
                                    type=genai.protos.Type.STRING,
                                    description="Case slug identifier",
                                )
                            },
                            required=["slug"],
                        ),
                    ),
                    genai.protos.FunctionDeclaration(
                        name="get_pipeline_logs",
                        description="Get the last N lines of a pipeline log for a case.",
                        parameters=genai.protos.Schema(
                            type=genai.protos.Type.OBJECT,
                            properties={
                                "slug": genai.protos.Schema(
                                    type=genai.protos.Type.STRING,
                                    description="Case slug",
                                ),
                                "step": genai.protos.Schema(
                                    type=genai.protos.Type.STRING,
                                    description="Log file name without .log extension (default: pipeline)",
                                ),
                                "lines": genai.protos.Schema(
                                    type=genai.protos.Type.INTEGER,
                                    description="Number of lines to return (default: 100)",
                                ),
                            },
                            required=["slug"],
                        ),
                    ),
                    genai.protos.FunctionDeclaration(
                        name="get_script",
                        description="Get the current script text for a case (manual override preferred).",
                        parameters=genai.protos.Schema(
                            type=genai.protos.Type.OBJECT,
                            properties={
                                "slug": genai.protos.Schema(
                                    type=genai.protos.Type.STRING,
                                    description="Case slug",
                                )
                            },
                            required=["slug"],
                        ),
                    ),
                    genai.protos.FunctionDeclaration(
                        name="get_file_tree",
                        description="Check which output files exist for a case (research, script, audio, video, thumbnail).",
                        parameters=genai.protos.Schema(
                            type=genai.protos.Type.OBJECT,
                            properties={
                                "slug": genai.protos.Schema(
                                    type=genai.protos.Type.STRING,
                                    description="Case slug",
                                )
                            },
                            required=["slug"],
                        ),
                    ),
                    genai.protos.FunctionDeclaration(
                        name="trigger_pipeline_step",
                        description=(
                            "Trigger a pipeline step for a case in a background thread. "
                            "Valid steps: research, script, tts, characters, broll, assemble, thumbnail."
                        ),
                        parameters=genai.protos.Schema(
                            type=genai.protos.Type.OBJECT,
                            properties={
                                "slug": genai.protos.Schema(
                                    type=genai.protos.Type.STRING,
                                    description="Case slug",
                                ),
                                "step": genai.protos.Schema(
                                    type=genai.protos.Type.STRING,
                                    description="Pipeline step name",
                                ),
                            },
                            required=["slug", "step"],
                        ),
                    ),
                    genai.protos.FunctionDeclaration(
                        name="read_source_file",
                        description="Read a source file under src/ for diagnosing failures.",
                        parameters=genai.protos.Schema(
                            type=genai.protos.Type.OBJECT,
                            properties={
                                "relative_path": genai.protos.Schema(
                                    type=genai.protos.Type.STRING,
                                    description="Path relative to project root, must start with src/",
                                )
                            },
                            required=["relative_path"],
                        ),
                    ),
                    genai.protos.FunctionDeclaration(
                        name="propose_script_fix",
                        description="Create an action card proposing a script fix that requires user approval before writing.",
                        parameters=genai.protos.Schema(
                            type=genai.protos.Type.OBJECT,
                            properties={
                                "slug": genai.protos.Schema(
                                    type=genai.protos.Type.STRING,
                                    description="Case slug",
                                ),
                                "issue": genai.protos.Schema(
                                    type=genai.protos.Type.STRING,
                                    description="Brief description of the issue being fixed",
                                ),
                                "fixed_content": genai.protos.Schema(
                                    type=genai.protos.Type.STRING,
                                    description="The corrected script content",
                                ),
                            },
                            required=["slug", "issue", "fixed_content"],
                        ),
                    ),
                    genai.protos.FunctionDeclaration(
                        name="get_recent_errors",
                        description="Get all cases currently in failed status with their recent log output.",
                    ),
                    genai.protos.FunctionDeclaration(
                        name="get_all_jobs",
                        description="Get all running and recently completed background jobs.",
                    ),
                ]
            )
        ]


_agent: PipelineAgent | None = None


def get_agent() -> PipelineAgent:
    global _agent
    if _agent is None:
        _agent = PipelineAgent()
    return _agent
