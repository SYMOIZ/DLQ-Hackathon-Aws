"""P0-T4 scratch: confirm InterventionHandler registration (no AWS calls)."""

from __future__ import annotations

from strands.interventions.actions import BeforeToolCallEvent, Deny, Proceed
from strands.interventions.handler import InterventionHandler


class ProbeGuard(InterventionHandler):
    name = "probe-guard"

    def before_tool_call(self, event: BeforeToolCallEvent, **kwargs):
        tool_name = None
        if event.tool_use:
            tool_name = event.tool_use.get("name")
        # Fields confirmed: selected_tool, tool_use, invocation_state, cancel_tool
        if tool_name == "discard_message":
            return Deny(reason="probe deny")
        return Proceed()


def main() -> None:
    print("InterventionHandler import OK:", InterventionHandler)
    print("Register via Agent(..., interventions=[ProbeGuard()])")
    print("before_tool_call event fields: selected_tool, tool_use, invocation_state, cancel_tool")
    print("Return Deny(...) or Proceed()")


if __name__ == "__main__":
    main()
