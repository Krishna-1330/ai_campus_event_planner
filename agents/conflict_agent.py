from services.constraint_engine import validate_plan


def run(store, plan, requirements, exclude_event_id=None):
    return validate_plan(store, plan, requirements, exclude_event_id)
