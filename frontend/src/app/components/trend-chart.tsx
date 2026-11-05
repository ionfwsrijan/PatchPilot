import { useEffect, useState, memo } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
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
import { getTrends, type TrendData } from "../lib/api";

export const TrendChart = memo(function TrendChart() {
  const [data, setData] = useState<TrendData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadData() {
      try {
        setLoading(true);
        const trendData = await getTrends(6);
        setData(trendData);
        setError(null);
      } catch (err: any) {
        setError(err.message || "Failed to load trend data");
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  return (
    <Card className="mb-8">
      <CardHeader>
        <CardTitle>Security Posture Trend</CardTitle>
        <CardDescription>
          Total active findings over the last 6 scans
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="h-72 w-full flex items-center justify-center">
          {loading ? (
            <div className="text-muted-foreground animate-pulse text-sm">
              Loading trend data...
            </div>
          ) : error ? (
            <div className="text-destructive text-sm font-medium">
              Error: {error}
            </div>
          ) : data.length === 0 ? (
            <div className="text-muted-foreground text-sm">
              No scan data available yet. Run a scan to see trends.
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={data}
                margin={{ top: 5, right: 20, left: -20, bottom: 5 }}
              >
                <CartesianGrid
                  strokeDasharray="3 3"
                  vertical={false}
                  stroke="#3f3f46"
                />
                <XAxis
                  dataKey="date"
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: "#a1a1aa", fontSize: 12 }}
                  dy={10}
                />
                <YAxis
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: "#a1a1aa", fontSize: 12 }}
                />
                <Tooltip
                  content={({ active, payload, label }) => {
                    if (active && payload && payload.length) {
                      return (
                        <div className="bg-background border border-border p-3 shadow-sm rounded-md">
                          <p className="font-semibold text-foreground">{label}</p>
                          <p className="font-medium text-destructive">
                            Findings: {payload[0].value}
                          </p>
                        </div>
                      );
                    }
                    return null;
                  }}
                  cursor={{ stroke: "#3f3f46", strokeWidth: 2 }}
                />
                <Line
                  type="monotone"
                  dataKey="findings"
                  stroke="#ef4444"
                  strokeWidth={3}
                  dot={{ r: 4, fill: "#ef4444", strokeWidth: 0 }}
                  activeDot={{
                    r: 6,
                    fill: "#ef4444",
                    stroke: "#18181b",
                    strokeWidth: 4,
                  }}
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      </CardContent>
    </Card>
  );
});