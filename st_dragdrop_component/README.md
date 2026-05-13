st_dragdrop_component — Streamlit drag-and-drop custom component

This folder contains a minimal Streamlit Custom Component scaffold that
integrates SortableJS to allow dragging assignments between day columns.

Quick start (development):

1. Install Node.js (>=16) and npm.
2. cd st_dragdrop_component/frontend
3. npm install
4. npm run start

This will start a dev server on http://localhost:3001. Keep it running while
you run the Streamlit app. The Python wrapper in `st_dragdrop_component` will
connect to the dev server automatically.

Build for production:

1. cd st_dragdrop_component/frontend
2. npm install
3. npm run build

After a successful build, a `build` directory is created under the frontend
folder. The Python wrapper will load the built files when present and the
component will work without a dev server.

Notes:
- The frontend uses `streamlit-component-lib` to communicate with Streamlit.
- On move, the component reports a list of move objects like `[{"id": 3, "day": "Monday", "hour": 10}]`.
- This scaffold is intentionally minimal; you can extend the UI, add
  hour selection inside columns, show conflict warnings, and batch moves.
