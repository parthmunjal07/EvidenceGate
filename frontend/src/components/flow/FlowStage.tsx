export function FlowStage({
  name,
  index,
  x,
  y,
  title,
  active,
  presentation = false,
}: {
  name: string;
  index: string;
  x: number;
  y: number;
  title: string[];
  active: boolean;
  presentation?: boolean;
}) {
  const width = presentation
    ? 82
    : name === "analytics"
      ? 150
      : name === "quality"
        ? 145
        : name === "router"
          ? 150
          : name === "results"
            ? 130
            : 134;
  const height = presentation ? 68 : name === "analytics" ? 120 : 80;
  return (
    <g
      className={`flow-stage${presentation ? " presentation-stage" : ""}${active ? (presentation ? " is-presentation" : " is-active") : ""}`}
      data-stage={name}
    >
      <rect x={x} y={y} width={width} height={height} rx="5" />
      <text className="stage-index" x={x + 14} y={y + 20}>
        {index}
      </text>
      {title.map((line, i) => (
        <text
          key={line}
          className={`stage-title${title.length > 2 || presentation ? " small" : ""}`}
          x={x + 14}
          y={
            y +
            (title.length > 2
              ? 40 + i * 17
              : presentation
                ? 38 + i * 16
                : 44 + i * 19)
          }
        >
          {line}
        </text>
      ))}
    </g>
  );
}
