import { useEffect, useState, memo } from "react";
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "./ui/card";
import { getCweDistribution, type CweData } from "../lib/api";

const PALETTE = [
  { color: "#38bdf8" },
  { color: "#fb7185" },
  { color: "#34d399" },
  { color: "#fbbf24" },
  { color: "#a78bfa" },
  { color: "#22d3ee" },
];

const TOTAL_LABEL_STYLE: React.CSSProperties = {
  position: "absolute",
  top: "50%",
  left: "50%",
  transform: "translate(-50%, -50%)",
  textAlign: "center",
  pointerEvents: "none",
};

export const CweChart = memo(function CweChart() {
  const [data, setData] = useState<CweData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeIndex, setActiveIndex] = useState<number | null>(null);

  useEffect(() => {
    async function loadData() {
      try {
        setLoading(true);
        const cweData = await getCweDistribution();
        setData(cweData);
        setError(null);
      } catch (err: any) {
        setError(err.message || "Failed to load CWE distribution");
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  const total = data.reduce((sum, d) => sum + d.value, 0);
  const activeItem = activeIndex !== null ? data[activeIndex] : null;
  const activeColor = activeIndex !== null ? PALETTE[activeIndex % PALETTE.length].color : null;

  return (
    <Card className="mb-8">
      <CardHeader className="pb-2">
        <CardTitle className="text-base font-semibold text-slate-100 tracking-tight">
          Vulnerability Distribution
        </CardTitle>
        <CardDescription className="text-slate-400 text-sm">
          Breakdown of active findings by category
        </CardDescription>
      </CardHeader>

      <CardContent>
        {loading ? (
          <div className="h-[280px] flex items-center justify-center">
            <div className="flex flex-col items-center gap-3">
              <div className="w-8 h-8 border-2 border-slate-600 border-t-sky-400 rounded-full animate-spin" />
              <span className="text-slate-500 text-xs">Loading distribution…</span>
            </div>
          </div>
        ) : error ? (
          <div className="h-[280px] flex items-center justify-center">
            <span className="text-rose-400 text-sm font-medium">Error: {error}</span>
          </div>
        ) : data.length === 0 ? (
          <div className="h-[280px] flex items-center justify-center">
            <span className="text-slate-500 text-sm">No scan data yet. Run a scan to see the distribution.</span>
          </div>
        ) : (
          <div className="flex flex-col gap-5 mt-1">
            <div className="relative flex justify-center" style={{ height: 220 }}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={data}
                    cx="50%"
                    cy="50%"
                    innerRadius={72}
                    outerRadius={98}
                    paddingAngle={3}
                    cornerRadius={5}
                    dataKey="value"
                    stroke="none"
                    onMouseEnter={(_, index) => setActiveIndex(index)}
                    onMouseLeave={() => setActiveIndex(null)}
                  >
                    {data.map((_, index) => (
                      <Cell
                        key={`cell-${index}`}
                        fill={PALETTE[index % PALETTE.length].color}
                        opacity={activeIndex === null || activeIndex === index ? 1 : 0.3}
                        style={{ outline: "none", transition: "opacity 0.2s ease" }}
                      />
                    ))}
                  </Pie>
                  <Tooltip
                    cursor={false}
                    content={({ active, payload }) => {
                      if (active && payload && payload.length) {
                        const pct = ((payload[0].value as number / total) * 100).toFixed(1);
                        return (
                          <div
                            className="rounded-lg border border-slate-700/60 shadow-xl px-3 py-2"
                            style={{ background: "#111827" }}
                          >
                            <div className="flex items-center gap-2 mb-0.5">
                              <span
                                className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                                style={{ backgroundColor: payload[0].payload.fill }}
                              />
                              <span className="text-slate-200 font-semibold text-[13px] capitalize">
                                {payload[0].name}
                              </span>
                            </div>
                            <div className="ml-[18px] text-xs text-slate-400 leading-5">
                              <span className="text-white font-medium">{payload[0].value}</span>
                              {" "}findings
                              <span className="ml-2 text-slate-500">({pct}%)</span>
                            </div>
                          </div>
                        );
                      }
                      return null;
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>

              <div style={TOTAL_LABEL_STYLE}>
                {activeItem ? (
                  <>
                    <div
                      className="text-2xl font-bold leading-none"
                      style={{ color: activeColor ?? "#fff" }}
                    >
                      {activeItem.value}
                    </div>
                    <div className="text-[11px] text-slate-400 mt-1 capitalize font-medium tracking-wide">
                      {activeItem.name}
                    </div>
                  </>
                ) : (
                  <>
                    <div className="text-2xl font-bold leading-none text-slate-100">{total}</div>
                    <div className="text-[11px] text-slate-500 mt-1 font-medium tracking-wide uppercase">
                      Total
                    </div>
                  </>
                )}
              </div>
            </div>

            <div className="flex flex-col gap-2 px-1">
              {data.map((entry, index) => {
                const pct = total > 0 ? (entry.value / total) * 100 : 0;
                const color = PALETTE[index % PALETTE.length].color;
                const isDimmed = activeIndex !== null && activeIndex !== index;

                return (
                  <div
                    key={entry.name}
                    className="flex items-center gap-3"
                    style={{ opacity: isDimmed ? 0.35 : 1, transition: "opacity 0.2s ease" }}
                  >
                    <span
                      className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                      style={{ backgroundColor: color }}
                    />
                    <span className="text-[13px] text-slate-300 capitalize flex-1 font-medium leading-none">
                      {entry.name}
                    </span>
                    <div className="flex items-center gap-2 flex-shrink-0" style={{ width: 140 }}>
                      <div className="flex-1 h-1.5 rounded-full bg-slate-800 overflow-hidden">
                        <div
                          className="h-full rounded-full"
                          style={{
                            width: `${pct}%`,
                            backgroundColor: color,
                            opacity: 0.85,
                            transition: "width 0.5s ease",
                          }}
                        />
                      </div>
                      <span
                        className="text-[12px] font-semibold tabular-nums leading-none"
                        style={{ color, minWidth: 24, textAlign: "right" }}
                      >
                        {entry.value}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
});