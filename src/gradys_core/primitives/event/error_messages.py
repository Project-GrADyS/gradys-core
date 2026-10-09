
def invalid_event_base_class(event_class: str, base_class_name: str) -> str:
    return f"The event class {event_class} must inherit from {base_class_name} to be recognized as a valid event."

def invalid_event_type(event_type: str, decorator_name: str) -> str:
    return (f"The event class {event_type} is not a valid environment event. Events should be decorated "
            f"with @{decorator_name} to be recognized as valid environment events.")