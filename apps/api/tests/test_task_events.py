import asyncio

from app.services.task_events import publish_task_event, sse_stream, subscribe, unsubscribe


async def _collect_one_event():
    q = await subscribe()
    publish_task_event({"type": "ping", "n": 1})
    try:
        return await asyncio.wait_for(q.get(), timeout=1.0)
    finally:
        await unsubscribe(q)


def test_publish_task_event_delivers_to_subscriber():
    ev = asyncio.run(_collect_one_event())
    assert ev["type"] == "ping"


async def _read_first_sse_line():
    gen = sse_stream(initial={"type": "snapshot", "items": []})
    line = await gen.__anext__()
    return line


def test_sse_stream_emits_initial_snapshot():
    line = asyncio.run(_read_first_sse_line())
    assert line.startswith("data: ")
    assert "snapshot" in line
