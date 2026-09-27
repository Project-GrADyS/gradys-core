from typing import ClassVar

from gradys_core.event import BaseEvent, EventId
from gradys_core.event.decorator import environment_event


@environment_event
class SimulationInitializationEvent(BaseEvent):
    event_id: ClassVar[EventId] = "SimulationInitializationEvent"


