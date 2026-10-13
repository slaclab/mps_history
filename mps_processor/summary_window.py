"""
Groups fault and channel history events into fixed time windows, one per fault/channel.
"""
import html
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from mps_processor.HistoryMessageType import HistoryMessageType

WINDOW_TIME = timedelta(seconds=20)
LOCAL_TZ = ZoneInfo("America/Los_Angeles")


@dataclass
class WindowEvent:
    """One decoded event"""
    event_time: datetime  # timezone-aware
    msg_type: HistoryMessageType
    processed_event: dict
    partition: int = 0
    offset: int = 0

    @property
    def info(self) -> dict:
        """The fault or channel part of `processed_event`."""
        return self.processed_event["fault"] if self.msg_type is HistoryMessageType.FaultStateType else self.processed_event["channel"]

    @property
    def name(self) -> str:
        return self.info["name"]


def _local(dt: datetime) -> datetime:
    return dt.astimezone(LOCAL_TZ)


def _time_ms(dt: datetime) -> str:
    return _local(dt).strftime("%H:%M:%S.%f")[:-3]


class SummaryWindow:
    """
    Events of one fault/channel from its first event until WINDOW_TIME later.
    Bypasses are never windowed; the broker wraps each one in a one-event window so all
    entries share the same post/retry/commit path.
    """

    def __init__(self, event: WindowEvent) -> None:
        self.events: list[WindowEvent] = [event]  # sorted by event time
        self.start: datetime = event.event_time

    @property
    def is_summary(self) -> bool:
        return len(self.events) > 1

    @property
    def kind(self) -> str:
        return "Fault" if self.events[0].msg_type is HistoryMessageType.FaultStateType else "Channel"

    def add(self, event: WindowEvent) -> None:
        self.events.append(event)
        # Only reorders if events from different partitions arrive out of order
        self.events.sort(key=lambda e: (e.event_time, e.partition, e.offset))

    def is_expired(self, now: datetime) -> bool:
        return now >= self.start + WINDOW_TIME

    @property
    def final_state(self) -> str:
        return self.events[-1].processed_event.get("new_state") or "Unknown"

    def title(self) -> str:
        return (f"MPS {self.kind} Summary: {self.events[0].name} | {len(self.events)} transitions "
                f"| Final: {self.final_state}")

    def body_html(self) -> str:
        first, final = self.events[0], self.events[-1]
        start, end = first.event_time, final.event_time
        duration = (end - start).total_seconds()
        parts = [
            f"<p><b>{self.kind}</b>: {html.escape(first.name)}<br>",
            f"<b>Transitions</b>: {len(self.events)}, {_local(start):%Y-%m-%d} {_time_ms(start)} – "
            f"{_time_ms(end)} {_local(end):%Z} ({duration:.1f} s)<br>",
            f"<b>Final State</b>: {html.escape(self.final_state)}<br>",
        ]
        # Same format as the individual fault entry, for the final transition (channels have no beams)
        beams = final.info.get("beams")
        if beams:
            parts.append("<b>Affected Beam Destinations</b>:<ol>")
            parts.extend(f"<li>{html.escape(str(b.get('destination', 'Unknown')))} -> "
                         f"{html.escape(str(b.get('class', 'Unknown')))}</li>" for b in beams)
            parts.append("</ol>")
        parts.append("</p>")

        parts.append('<table border="1"><tr><th>Time</th><th>Old State</th><th>New State</th></tr>')
        for e in self.events:
            cells = [_time_ms(e.event_time), e.processed_event.get("old_state"), e.processed_event.get("new_state")]
            parts.append("<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in cells) + "</tr>")
        parts.append("</table>")
        return "".join(parts)
