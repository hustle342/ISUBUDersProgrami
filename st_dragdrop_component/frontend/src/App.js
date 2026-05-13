import React, { useEffect, useMemo, useRef, useState } from "react";
import { Streamlit, withStreamlitConnection } from "streamlit-component-lib";

function App(props) {
  const args = props.args || {};
  const assignments = args.assignments || [];
  const days = args.days || [];
  const hours = args.hours || [];
  const classes = args.classes || [];

  const [layout, setLayout] = useState({});
  const [roomMap, setRoomMap] = useState({});
  const [detail, setDetail] = useState(null);
  const [dragItemId, setDragItemId] = useState(null);
  const [dragRoomCardId, setDragRoomCardId] = useState(null);
  const [dragError, setDragError] = useState("");
  const isHydratedRef = useRef(false);
  const userActionRef = useRef(false);

  const itemMap = useMemo(() => {
    const m = {};
    assignments.forEach((a) => {
      m[String(a.id)] = a;
    });
    return m;
  }, [assignments]);

  const classColorMap = useMemo(() => {
    // Clearly distinguishable background colors — all work well with dark (#222) text
    const basePalette = [
      "#ff8a80", // red
      "#ffb74d", // orange
      "#fff176", // yellow
      "#69f0ae", // green
      "#40c4ff", // light-blue
      "#b388ff", // purple
      "#f48fb1", // pink
      "#80cbc4", // teal
      "#a5d6a7", // mint-green
      "#ce93d8", // lavender
      "#ffcc80", // peach
      "#90caf9", // sky-blue
    ];
    const allClasses = (classes && classes.length > 0 ? classes : assignments.map((a) => a.class_name || "")).filter(Boolean);
    const uniq = Array.from(new Set(allClasses.map((x) => String(x)))).sort();
    const out = {};
    uniq.forEach((cls, idx) => {
      out[cls] = basePalette[idx % basePalette.length];
    });
    return out;
  }, [classes, assignments]);

  const classColor = (name) => classColorMap[String(name || "")] || "#e0e0e0";

  const teacherBase = (value) => String(value || "").split(" || ")[0].trim();

  const buildFromAssignments = () => {
    const next = {};
    const nextRoom = {};
    hours.forEach((h) => {
      days.forEach((d) => {
        next[`${d}__${h}`] = [];
      });
    });
    assignments.forEach((a) => {
      const key = `${a.day}__${a.hour}`;
      if (!next[key]) next[key] = [];
      next[key].push(String(a.id));
      nextRoom[String(a.id)] = a.room || "";
    });
    return { next, nextRoom };
  };

  useEffect(() => {
    const built = buildFromAssignments();
    setLayout(built.next);
    setRoomMap(built.nextRoom);
    setDetail(null);
    setDragError("");
    isHydratedRef.current = true;
    const rowH = 95; // approx px per hour row (card + padding)
    const frameH = Math.max(500, hours.length * rowH + 150);
    Streamlit.setFrameHeight(frameH);
  }, [props.args]);

  useEffect(() => {
    Streamlit.setComponentValue([]);
  }, []);

  const hasConflictInTarget = (draggedId, targetDay, targetHour) => {
    const dragged = itemMap[String(draggedId)];
    if (!dragged) return "";
    const targetKey = `${targetDay}__${targetHour}`;
    const targetIds = layout[targetKey] || [];
    for (const tid of targetIds) {
      if (String(tid) === String(draggedId)) continue;
      const other = itemMap[String(tid)];
      if (!other) continue;
      if (String(other.class_name || "") === String(dragged.class_name || "")) {
        return `Sinif cakismasi: ${dragged.class_name}`;
      }
      if (teacherBase(other.teacher) && teacherBase(other.teacher) === teacherBase(dragged.teacher)) {
        return `Hoca cakismasi: ${teacherBase(dragged.teacher)}`;
      }
    }
    return "";
  };

  const moveCard = (id, targetDay, targetHour) => {
    const conflictText = hasConflictInTarget(id, targetDay, targetHour);
    if (conflictText) {
      setDragError(conflictText);
      return;
    }

    userActionRef.current = true;
    setDragError("");
    setLayout((prev) => {
      const next = {};
      Object.keys(prev).forEach((k) => {
        next[k] = [...prev[k]];
      });
      Object.keys(next).forEach((k) => {
        next[k] = next[k].filter((x) => x !== id);
      });
      const targetKey = `${targetDay}__${targetHour}`;
      if (!next[targetKey]) next[targetKey] = [];
      next[targetKey].push(id);
      return next;
    });
  };

  const swapRooms = (idA, idB) => {
    if (!idA || !idB || idA === idB) return;
    userActionRef.current = true;
    setRoomMap((prev) => {
      const a = prev[idA] || "";
      const b = prev[idB] || "";
      return { ...prev, [idA]: b, [idB]: a };
    });
  };

  const exportMoves = () => {
    const out = [];
    Object.keys(layout).forEach((key) => {
      const [day, hour] = key.split("__");
      (layout[key] || []).forEach((id) => {
        out.push({ id: Number(id), day, hour: Number(hour), room: roomMap[id] || "" });
      });
    });
    Streamlit.setComponentValue(out);
  };

  // Send updates automatically after each drag-drop / room swap.
  useEffect(() => {
    if (!isHydratedRef.current) return;
    if (!userActionRef.current) return;
    userActionRef.current = false;
    exportMoves();
  }, [layout, roomMap]);

  useEffect(() => {
    const rowH = 95;
    const frameH = Math.max(500, hours.length * rowH + 150);
    Streamlit.setFrameHeight(frameH);
  }, [layout, roomMap, dragError]);

  return (
    <div style={{ fontFamily: "Arial, sans-serif" }}>
      {dragError && (
        <div style={{ marginBottom: "8px", padding: "6px 8px", borderRadius: "6px", background: "#ffe3e3", border: "1px solid #ffb5b5", color: "#8f1f1f", fontSize: "12px" }}>
          {dragError}
        </div>
      )}

      <div style={{ overflowX: "auto" }}>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: `90px repeat(${days.length || 1}, minmax(140px, 1fr))`,
          gap: "6px",
          alignItems: "start",
          minWidth: `${90 + (days.length || 1) * 150}px`,
        }}
      >
        <div />
        {days.map((d) => (
          <div key={`head_${d}`} style={{ fontWeight: 700, textAlign: "center", padding: "6px 4px" }}>
            {d}
          </div>
        ))}

        {hours.map((h) => (
          <React.Fragment key={`row_${h}`}>
            <div style={{ fontWeight: 700, paddingTop: "8px" }}>{String(h).padStart(2, "0")}:00</div>
            {days.map((d) => {
              const key = `${d}__${h}`;
              const ids = layout[key] || [];
              return (
                <div
                  key={key}
                  data-cell-key={key}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => {
                    e.preventDefault();
                    const id = e.dataTransfer.getData("text/plain") || dragItemId;
                    if (!id) return;
                    moveCard(String(id), d, h);
                    setDragItemId(null);
                  }}
                  style={{
                    minHeight: "54px",
                    border: "1px solid #ddd",
                    borderRadius: "8px",
                    background: "#fbfbfb",
                    padding: "4px",
                  }}
                >
                  {ids.map((id) => {
                    const a = itemMap[id];
                    if (!a) return null;
                    return (
                      <div
                        key={id}
                        data-item-id={id}
                        onClick={() => setDetail({ ...a, room: roomMap[id] || "" })}
                        draggable
                        onDragStart={(e) => {
                          setDragItemId(String(id));
                          e.dataTransfer.setData("text/plain", String(id));
                        }}
                        onDragEnd={() => setDragItemId(null)}
                        title={`${a.course_code} | ${a.course_name}\n${teacherBase(a.teacher)}\nSınıf: ${a.class_name}`}
                        style={{
                          userSelect: "none",
                          cursor: "grab",
                          borderRadius: "6px",
                          margin: "2px 0",
                          padding: "5px 7px",
                          background: classColor(a.class_name),
                          border: "1px solid rgba(0,0,0,0.25)",
                          color: "#1a1a1a",
                        }}
                      >
                        <div style={{ fontWeight: 800, fontSize: "13px", color: "#111" }}>{a.course_code}</div>
                        <div style={{ fontSize: "11px", fontWeight: 600, color: "#222" }}>
                          {a.class_name} | {teacherBase(a.teacher)}
                        </div>

                        <div style={{ marginTop: "5px", display: "flex", gap: "4px", alignItems: "center" }}>
                          <span style={{ fontSize: "11px", fontWeight: 700 }}>Salon:</span>
                          <div
                            draggable
                            onDragStart={(e) => {
                              e.stopPropagation();
                              setDragRoomCardId(String(id));
                              e.dataTransfer.setData("room-card-id", String(id));
                            }}
                            onDragEnd={(e) => {
                              e.stopPropagation();
                              setDragRoomCardId(null);
                            }}
                            onDragOver={(e) => {
                              e.preventDefault();
                              e.stopPropagation();
                            }}
                            onDrop={(e) => {
                              e.preventDefault();
                              e.stopPropagation();
                              const src = e.dataTransfer.getData("room-card-id") || dragRoomCardId;
                              if (!src) return;
                              swapRooms(String(src), String(id));
                              setDragRoomCardId(null);
                            }}
                            style={{
                              fontSize: "11px",
                              background: "#ffffff",
                              border: "1px dashed #888",
                              borderRadius: "6px",
                              padding: "2px 6px",
                              cursor: "grab",
                              minWidth: "72px",
                              textAlign: "center",
                            }}
                            title="Salon kutucugunu baska karta birakarak salonlari degistirebilirsiniz"
                          >
                            {roomMap[id] || "-"}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              );
            })}
          </React.Fragment>
        ))}
      </div>
      </div>

      <div style={{ marginTop: "10px", display: "flex", gap: "8px" }}>
        <button
          type="button"
          onClick={() => {
            userActionRef.current = true;
            const built = buildFromAssignments();
            setLayout(built.next);
            setRoomMap(built.nextRoom);
            setDetail(null);
            setDragError("");
          }}
          style={{ padding: "6px 10px", cursor: "pointer" }}
        >
          Sifirla
        </button>
      </div>

      {detail && (
        <div style={{ marginTop: "10px", fontSize: "12px", lineHeight: 1.4, color: "#222" }}>
          <strong>Detay:</strong> {detail.course_code} - {detail.course_name} | {teacherBase(detail.teacher)} | {detail.class_name} | Salon: {detail.room || "-"}
        </div>
      )}
    </div>
  );
}

export default withStreamlitConnection(App);
