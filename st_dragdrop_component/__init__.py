import os
from streamlit.components.v1 import declare_component

# If a built frontend exists in `frontend/build`, load it. Otherwise, the
# developer can run the frontend dev server at http://localhost:3001 and
# the component will connect to it for development.
_build_dir = os.path.join(os.path.dirname(__file__), "frontend", "build")
if os.path.exists(_build_dir):
    _st_dragdrop = declare_component("st_dragdrop", path=_build_dir)
else:
    # dev server fallback (run `npm start` in frontend to use)
    _st_dragdrop = declare_component("st_dragdrop", url="http://localhost:3001")


def st_dragdrop(assignments, days, hours, rooms=None, classes=None, height=600, key=None):
    """Render the drag-drop board component and return reported moves.

    - `assignments`: list of dicts with keys `id`, `course_code`, `class_name`, `day`, `hour`.
    - `days`: list of day names (columns).
    - `hours`: list of hour ints.

    Returns a list of moves (each a dict with `id`, `day`, `hour`, `room`) or None
    when no report is available yet.
    """
    try:
        value = _st_dragdrop(
            assignments=assignments,
            days=days,
            hours=hours,
            rooms=rooms or [],
            classes=classes or [],
            height=height,
            key=key,
        )
        return value
    except Exception:
        return None
