"""
State Machine Enforcement Service

Validates state transitions for samples, test instances, and bills
to prevent invalid state changes that could corrupt data.

Per PRD Section 16: Timeline Architecture and state machine requirements.
"""
from __future__ import annotations
import logging
from typing import Optional, Set, Tuple
from enum import Enum

logger = logging.getLogger("state_machine")


# ── Valid State Transitions ───────────────────────────────────────────────────

# Sample state transitions (sample_status_t)
SAMPLE_VALID_TRANSITIONS = {
    'draft': {'pending'},
    'pending': {'queued', 'in_transit', 'arrived', 'unassigned', 'rejected', 'cancelled'},
    'queued': {'in_transit', 'arrived'},
    'in_transit': {'arrived'},
    'arrived': {'processing', 'partially_complete', 'completed', 'cancelled', 'rejected', 'delayed'},
    'processing': {'partially_complete', 'completed', 'cancelled', 'rejected', 'delayed'},
    'partially_complete': {'processing', 'completed', 'cancelled', 'rejected'},
    'completed': set(),  # Terminal state
    'cancelled': set(),  # Terminal state
    'rejected': {'pending', 'cancelled'},
    'delayed': {'processing', 'partially_complete', 'completed', 'cancelled', 'rejected'},
    'unassigned': {'pending', 'cancelled'},
    'error': {'pending', 'cancelled'},
}

# Test instance state transitions (test_status_t)
TEST_VALID_TRANSITIONS = {
    'draft': {'pending', 'cancelled'},
    'pending': {'processing', 'result_saved', 'completed', 'cancelled', 'invalidated'},
    'processing': {'result_saved', 'completed', 'cancelled', 'invalidated'},
    'result_saved': {'signed', 'completed', 'cancelled', 'invalidated'},
    'signed': {'submitted', 'completed', 'cancelled'},
    'submitted': {'completed', 'cancelled'},
    'completed': set(),  # Terminal state
    'cancelled': set(),  # Terminal state
    'invalidated': set(),  # Terminal state (for redraw cycles)
}

# Bill state transitions (bill_status_t)
BILL_VALID_TRANSITIONS = {
    'preview': {'active', 'cancelled'},
    'active': {'completed', 'cancelled'},
    'completed': set(),  # Terminal state
    'cancelled': set(),  # Terminal state
}

# Queue state transitions (queue_status_t)
QUEUE_VALID_TRANSITIONS = {
    'scheduled': {'waiting', 'processing', 'cancelled', 'skipped'},
    'waiting': {'processing', 'cancelled', 'skipped'},
    'processing': {'completed', 'cancelled', 'delayed'},
    'completed': set(),  # Terminal state
    'cancelled': set(),  # Terminal state
    'skipped': set(),  # Terminal state
    'delayed': {'processing', 'cancelled'},
}


# ── Validation Functions ───────────────────────────────────────────────────────

def validate_sample_transition(
    current_status: str,
    new_status: str,
    context: Optional[dict] = None
) -> Tuple[bool, Optional[str]]:
    """
    Validate sample state transition.
    
    Args:
        current_status: Current sample status
        new_status: Desired new status
        context: Optional context dict for special cases (e.g., redraw)
    
    Returns:
        (is_valid, error_message)
    """
    # Special case: redraw can transition from any state to pending
    if context and context.get('is_redraw'):
        if new_status == 'pending':
            return True, None
    
    # Special case: unassigned can transition to pending when re-routed
    if current_status == 'unassigned' and new_status == 'pending':
        if context and context.get('is_rerouted'):
            return True, None
    
    valid_next_states = SAMPLE_VALID_TRANSITIONS.get(current_status, set())
    if new_status not in valid_next_states:
        return False, f"Invalid sample transition: {current_status} → {new_status}. Valid: {valid_next_states}"
    
    return True, None


def validate_test_transition(
    current_status: str,
    new_status: str,
    context: Optional[dict] = None
) -> Tuple[bool, Optional[str]]:
    """
    Validate test instance state transition.
    
    Args:
        current_status: Current test instance status
        new_status: Desired new status
        context: Optional context dict for special cases
    
    Returns:
        (is_valid, error_message)
    """
    # Special case: redraw can invalidate current cycle
    if context and context.get('is_redraw'):
        if new_status == 'invalidated':
            return True, None
    
    valid_next_states = TEST_VALID_TRANSITIONS.get(current_status, set())
    if new_status not in valid_next_states:
        return False, f"Invalid test transition: {current_status} → {new_status}. Valid: {valid_next_states}"
    
    return True, None


def validate_bill_transition(
    current_status: str,
    new_status: str,
    context: Optional[dict] = None
) -> Tuple[bool, Optional[str]]:
    """
    Validate bill state transition.
    
    Args:
        current_status: Current bill status
        new_status: Desired new status
        context: Optional context dict for special cases
    
    Returns:
        (is_valid, error_message)
    """
    valid_next_states = BILL_VALID_TRANSITIONS.get(current_status, set())
    if new_status not in valid_next_states:
        return False, f"Invalid bill transition: {current_status} → {new_status}. Valid: {valid_next_states}"
    
    return True, None


def validate_queue_transition(
    current_status: str,
    new_status: str,
    context: Optional[dict] = None
) -> Tuple[bool, Optional[str]]:
    """
    Validate queue entry state transition.
    
    Args:
        current_status: Current queue status
        new_status: Desired new status
        context: Optional context dict for special cases
    
    Returns:
        (is_valid, error_message)
    """
    valid_next_states = QUEUE_VALID_TRANSITIONS.get(current_status, set())
    if new_status not in valid_next_states:
        return False, f"Invalid queue transition: {current_status} → {new_status}. Valid: {valid_next_states}"
    
    return True, None


# ── Helper Functions for Use in Webhook Handlers ───────────────────────────────

def check_and_log_transition(
    entity_type: str,
    entity_id: int,
    current_status: str,
    new_status: str,
    validator_func,
    context: Optional[dict] = None
) -> bool:
    """
    Validate a state transition and log the result.
    
    Args:
        entity_type: Type of entity ('sample', 'test', 'bill', 'queue')
        entity_id: ID of the entity
        current_status: Current status
        new_status: Desired new status
        validator_func: Validation function to use
        context: Optional context dict
    
    Returns:
        True if transition is valid, False otherwise
    """
    is_valid, error_msg = validator_func(current_status, new_status, context)
    
    if not is_valid:
        logger.error(
            "[STATE_MACHINE] Invalid %s transition: id=%d %s → %s. %s",
            entity_type, entity_id, current_status, new_status, error_msg
        )
    else:
        logger.debug(
            "[STATE_MACHINE] Valid %s transition: id=%d %s → %s",
            entity_type, entity_id, current_status, new_status
        )
    
    return is_valid
