from apps.presentation.constants import STAGES
from apps.presentation.scenes import first_scene_for_stage, scenes_for, stage_index
from apps.presentation.story import live_state


def theater_payload(*, story: dict, index: int, snapshot: dict | None = None) -> dict:
    scenes = scenes_for(story)
    if not scenes:
        return {"active": False, "scenes": []}
    index = max(0, min(int(index), len(scenes) - 1))
    current = scenes[index]
    current_stage = stage_index(current["stage"])
    steps = []
    for offset, (key, label) in enumerate(STAGES):
        if offset < current_stage:
            state = "done"
        elif offset == current_stage:
            state = "now"
        else:
            state = "todo"
        steps.append(
            {
                "key": key,
                "label": label,
                "state": state,
                "index": first_scene_for_stage(key),
            }
        )
    live = dict(snapshot or {})
    if story and not live:
        try:
            live = live_state(story) or {}
        except Exception:
            live = {}
    return {
        "active": True,
        "scene": current,
        "index": index,
        "total": len(scenes),
        "has_prev": index > 0,
        "has_next": index < len(scenes) - 1,
        "steps": steps,
        "story": story,
        "snapshot": live,
        "prev_index": max(0, index - 1),
        "next_index": min(len(scenes) - 1, index + 1),
    }
