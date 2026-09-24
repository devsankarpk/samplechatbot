import json
import datetime
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, RateLimitError

from config import DEEPINFRA_API_KEY, DEEPINFRA_BASE_URL, DEEPINFRA_MODEL
import tools

_client = OpenAI(api_key = DEEPINFRA_API_KEY, base_url = DEEPINFRA_BASE_URL, timeout = 30.0)

SYSTEM_PROMPT_TEMPLATE = """You are a helpful assistant for booking doctor appointments.

Today's date is {today}.

You have tools to look up doctors, check availability, book, list, cancel and reschedule appointments.
Always use these tools for anything involving real doctors, availability, or booking - never invent 
doctor names, id or time solots youself. Appointment times must be iN 'YYYY-MM-DD HH:MM' 24-hours fotmat.

The current patient is {patient_name} (patient id {patient_id}), all booking / cancel / reschedule / list
actions apply to them automatically.

Be concise and friendly. Confirm key details (doctor, date/time) back to the patient after a 
successfull booking, cancellation or reschedule.
"""

class UpstreamError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message

def build_system_prompt(patient_name, patient_id):
    return SYSTEM_PROMPT_TEMPLATE.format(
        today = datetime.date.today().isoformat(),
        patient_name = patient_name,
        patient_id = patient_id
    )

def _call_model(messages):
    try:
        return _client.chat.completions.create(
            model=DEEPINFRA_MODEL,
            messages=messages,
            tools=tools.TOOL_SCHEMAS,
        )
    except (APITimeoutError, APIConnectionError) as exc:
        raise UpstreamError("The LLM provider timed out or was unreachable.") from exc
    except RateLimitError as exc:
        raise UpstreamError("The LLM provider is rate-limiting requests. Try again shortly.") from exc
    except APIStatusError as exc:
        raise UpstreamError(f"The LLM provider returned an error: {exc.message}") from exc
    except Exception as exc:  # noqa: BLE001 - never crash the chat loop on an unexpected error
        raise UpstreamError(f"Unexpected error calling the LLM provider: {exc}") from exc

def call_tools(conn, patient, messages, max_tool_round = 6):
    # Calling tools
    for _ in range(max_tool_round):
        completion = _call_model(messages=messages)
        choice = completion.choices[0]
        message = choice.message

        if not message.tool_calls:
            reply = message.content or ""
            messages.append({"role": "assistant", "content": reply})
            return reply

        messages.append(
            {
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in message.tool_calls
                ],
            }
        )

        for tool_call in message.tool_calls:
            name = tool_call.function.name

            try:
                args = json.loads(tool_call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            func = tools.DISPATCH.get(name)
            if func is None:
                result = {"error": f"Unkown tool '{name}'."}
            else:
                try:
                    result = func(conn, patient["id"], **args)
                except TypeError as exc:
                    result = {"error": f"Invalid arguments for '{name}': '{exc}'"}

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result, default=str),
                }
            )

    fallback = "Sorry, couldn't process right now, Could you rephrase?"
    messages.append({"role": "assistant", "content": fallback})
    return fallback