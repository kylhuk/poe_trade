import React, { useMemo } from 'react';

export interface SparklinePoint {
  timestamp: string;
  value: number;
}

interface Props {
  points: SparklinePoint[] | null | undefined;
  width?: number;
  height?: number;
  loading?: boolean;
}

export default function PriceSparkline({ points, width = 80, height = 24, loading }: Props) {
  const { path, fill, trending } = useMemo(() => {
    if (!points || points.length < 2) return { path: '', fill: '', trending: 0 };

    const sorted = [...points].sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
    const vals = sorted.map(p => p.value);
    const min = Math.min(...vals);
    const max = Math.max(...vals);
    const range = max - min || 1;
    const pad = 2;
    const w = width - pad * 2;
    const h = height - pad * 2;

    const pts = vals.map((v, i) => ({
      x: pad + (i / (vals.length - 1)) * w,
      y: pad + h - ((v - min) / range) * h,
    }));

    const line = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
    const fillPath = `${line} L${pts[pts.length - 1].x.toFixed(1)},${height} L${pts[0].x.toFixed(1)},${height} Z`;
    const trend = vals[vals.length - 1] - vals[0];

    return { path: line, fill: fillPath, trending: trend };
  }, [points, width, height]);

  if (loading) {
    return (
      <div className="flex items-center justify-center" style={{ width, height }}>
        <div className="w-3 h-3 rounded-full border border-muted-foreground/30 border-t-primary animate-spin" />
      </div>
    );
  }

  if (!points || points.length < 2) {
    return <span className="text-muted-foreground text-[10px]">—</span>;
  }

  const color = trending >= 0 ? 'hsl(var(--success))' : 'hsl(var(--destructive))';
  const fillColor = trending >= 0 ? 'hsl(var(--success) / 0.15)' : 'hsl(var(--destructive) / 0.15)';

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="inline-block">
      <path d={fill} fill={fillColor} />
      <path d={path} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
