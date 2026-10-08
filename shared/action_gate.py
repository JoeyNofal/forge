"""
ACTION GATE — one shared approval gate for every agent that saves data.

WHY THIS EXISTS (Lesson #9, consolidation): atlas_actions.py and
drive_actions.py each carried their own copy of the same safety logic
(find an action by a typed id prefix, claim it atomically, run it once,
record the real outcome, deny, list). Two copies of safety code can
drift apart; one tested copy cannot. STOCK, FLAME and the rest will
reuse this instead of becoming copy number three.

THE RULES (unchanged from ATLAS/DRIVE):
  - propose()            only puts a cleaned action in the shared queue.
                         It never runs anything.
  - approve_and_execute() is the ONLY method that runs a handler. It
                         claims the action atomically first, so two
                         near-simultaneous approvals can never both run.
  - A handler failing is reported and recorded as failed, never dressed
    up as a success (Lesson #12).
  - A handler returns (True, "message") on success or (False, "why not")
    on a clean refusal. Raising an exception is also fine: it is caught
    and recorded as failed.

Each agent builds ONE gate with its own name, its own describe() text
and its own {action_type: handler} table. Everything else lives here.
"""
from shared.pending_actions import (
    create_pending_action, get_pending_action, list_pending_actions,
    claim_action, finalize_action, resolve_action,
)

DEFAULT_MIN_ID_PREFIX = 6


class ActionGate:
    def __init__(self, agent_name, display_name, describe, handlers,
                 min_id_prefix=DEFAULT_MIN_ID_PREFIX):
        """
        agent_name   — lowercase queue name, e.g. "atlas"
        display_name — how messages name the agent, e.g. "ATLAS"
        describe     — function (action_type, details) -> one readable line
        handlers     — dict: action_type -> function(details) -> (ok, message)
        """
        if not isinstance(agent_name, str) or not agent_name.strip():
            raise ValueError("agent_name must be a non-empty string.")
        if not isinstance(display_name, str) or not display_name.strip():
            raise ValueError("display_name must be a non-empty string.")
        if not callable(describe):
            raise TypeError("describe must be a function.")
        if not isinstance(handlers, dict) or not handlers:
            raise TypeError("handlers must be a non-empty dict of action_type -> function.")
        for action_type, fn in handlers.items():
            if not isinstance(action_type, str) or not action_type or not callable(fn):
                raise TypeError("every handler needs a non-empty string type and a function.")
        if isinstance(min_id_prefix, bool) or not isinstance(min_id_prefix, int) or min_id_prefix < 1:
            raise ValueError("min_id_prefix must be a whole number of 1 or more.")

        self.agent_name = agent_name
        self.display_name = display_name
        self.min_id_prefix = min_id_prefix
        self._describe = describe
        self._handlers = dict(handlers)

    # ─────────────────────────────────────────────
    # SUMMARIES
    # ─────────────────────────────────────────────

    def describe(self, action_type, details) -> str:
        """The agent's own summary text, but a bug in it can never crash approve/deny/list."""
        try:
            text = self._describe(action_type, details)
            if isinstance(text, str) and text:
                return text
        except Exception:
            pass
        return f"{action_type}: {details}"

    # ─────────────────────────────────────────────
    # PROPOSING (no effect on any data file)
    # ─────────────────────────────────────────────

    def propose(self, action_type, clean_details) -> str:
        """
        Queues an already-cleaned action and returns its id. An action type
        this gate has no handler for is refused HERE, so a typo can never
        sit in the queue waiting to fail at approval time.
        """
        if action_type not in self._handlers:
            raise ValueError(f"{self.display_name} has no handler for action type '{action_type}'.")
        return create_pending_action(self.agent_name, action_type, clean_details)

    # ─────────────────────────────────────────────
    # FINDING AN ACTION BY (PART OF) ITS ID
    # ─────────────────────────────────────────────

    def find_action(self, action_id):
        """Returns (action, None) or (None, error message). Only this agent's own actions."""
        if not isinstance(action_id, str) or not action_id.strip():
            return None, "No action id given."
        action_id = action_id.strip()
        action = get_pending_action(action_id)
        if action is not None:
            if action["agent"] != self.agent_name:
                return None, f"Action {action_id} doesn't belong to {self.display_name}."
            return action, None
        if len(action_id) >= self.min_id_prefix:
            matches = [a for a in list_pending_actions(self.agent_name) if a["id"].startswith(action_id)]
            if len(matches) == 1:
                return matches[0], None
            if len(matches) > 1:
                return None, f"'{action_id}' matches more than one pending action — type more of the id."
        return None, f"No pending action found with id {action_id}."

    # ─────────────────────────────────────────────
    # APPROVING / DENYING
    # ─────────────────────────────────────────────

    def approve_and_execute(self, action_id) -> str:
        """
        The ONLY method that runs a handler. Claims the action atomically
        first (so it can never run twice), runs the handler, and records
        and reports the real outcome.
        """
        action, err = self.find_action(action_id)
        if action is None:
            return err or "Action not found."
        real_id = action["id"]
        if action["status"] != "pending":
            return f"Action {real_id} was already {action['status']}, not executing again."
        if not claim_action(real_id):
            return f"Action {real_id} was already claimed by another approval, not executing again."

        try:
            handler = self._handlers.get(action["type"])
            if handler is None:
                result = f"Unknown action type: {action['type']}"
                finalize_action(real_id, "failed", result)
                return result

            outcome = handler(action["details"])
            if not (isinstance(outcome, tuple) and len(outcome) == 2
                    and isinstance(outcome[0], bool) and isinstance(outcome[1], str)):
                result = f"Execution failed: the handler for {action['type']} returned an invalid result."
                finalize_action(real_id, "failed", result)
                return result

            ok, result = outcome
            finalize_action(real_id, "executed" if ok else "failed", result)
            return result
        except Exception as e:
            error_result = f"Execution failed: {type(e).__name__}: {e}"
            finalize_action(real_id, "failed", error_result)
            return error_result

    def deny_action(self, action_id) -> str:
        action, err = self.find_action(action_id)
        if action is None:
            return err or "Action not found."
        real_id = action["id"]
        if action["status"] != "pending":
            return f"Action {real_id} was already {action['status']}."
        if not resolve_action(real_id, "denied"):
            return f"Action {real_id} was already resolved by someone else."
        return f"Denied: {self.describe(action['type'], action['details'])}"

    def list_pending(self) -> str:
        """Everything of this agent's still waiting for approval, one per line."""
        actions = list_pending_actions(self.agent_name)
        if not actions:
            return "Nothing waiting for approval."
        return "\n".join(f"{a['id']}  {self.describe(a['type'], a['details'])}" for a in actions)