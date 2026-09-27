from gradys_core.event import SimulationInitializationEvent


def _uninitialized_command_message(command_type: str):
    return f"""
    Cannot send command of type '{command_type}' before the protocol is injected into the environment. \n 
    You may be calling the send method too early, sending events is only allowed after the simulation has been 
    initialized. Try calling the send method in a callback to the "{SimulationInitializationEvent.__name__}" event. 
    """
