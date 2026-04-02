import { forwardRef, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { ConfidenceBadge } from '@/components/shared/StatusIndicators';
import { api } from '@/services/api';
import type { PriceCheckResponse } from '@/types/api';
import { Brain, AlertTriangle, ServerCrash, ShieldAlert, Info } from 'lucide-react';
import { RenderState } from '@/components/shared/RenderState';
import { useMouseGlow } from '@/hooks/useMouseGlow';

function isLowTrustEstimate(r: PriceCheckResponse): boolean {
  return r.mlPredicted === false || r.estimateTrust === 'low' || !!r.fallbackReason;
}

const PriceCheckTab = forwardRef<HTMLDivElement, Record<string, never>>(function PriceCheckTab(_props, ref) {
  const [text, setText] = useState('');
  const [result, setResult] = useState<PriceCheckResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const mouseGlow = useMouseGlow();

  const check = async () => {
    if (!text.trim()) {
      setError('Please paste item text first');
      setErrorCode(null);
      return;
    }
    setLoading(true);
    setResult(null);
    setError(null);
    setErrorCode(null);
    try {
      const priceData = await api.priceCheck({ itemText: text });
      setResult(priceData);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Price prediction failed';
      const code = msg.split(':')[0] ?? '';
      setErrorCode(code.trim());
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const lowTrust = result ? isLowTrustEstimate(result) : false;

  return (
    <div ref={ref} className="max-w-4xl mx-auto space-y-6" data-testid="panel-pricecheck-root">
      <PriceCheckInput
        text={text}
        onTextChange={setText}
        onSubmit={check}
        loading={loading}
        error={error}
        errorCode={errorCode}
      />

      {result && (
        <PriceResultCard result={result} lowTrust={lowTrust} onMouseMove={mouseGlow} />
      )}
    </div>
  );
});

/* ─── Sub-components ─── */

function PriceCheckInput({
  text, onTextChange, onSubmit, loading, error, errorCode,
}: {
  text: string;
  onTextChange: (v: string) => void;
  onSubmit: () => void;
  loading: boolean;
  error: string | null;
  errorCode: string | null;
}) {
  return (
    <div className="space-y-3">
      <h2 className="text-lg font-semibold font-sans text-foreground">ML Price Check</h2>
      <p className="text-xs text-muted-foreground">
        Paste PoE clipboard text. The backend runs the trained price model and returns recent market comparables from the synchronized dataset.
      </p>

      <Textarea
        data-testid="pricecheck-input"
        value={text}
        onChange={e => onTextChange(e.target.value)}
        placeholder={`Rarity: Rare\nGrim Bane\nHubris Circlet\n--------\nQuality: +20%\n+2 to Level of Socketed Minion Gems\n+93 to maximum Life\n...`}
        className="min-h-[160px] font-mono text-xs focus:shadow-[0_0_12px_-3px_hsl(38,55%,42%,0.3)] transition-shadow"
      />
      <Button data-testid="pricecheck-submit" onClick={onSubmit} disabled={loading} className="gap-2 w-full sm:w-auto btn-game">
        <Brain className="h-4 w-4" />
        {loading ? 'Checking...' : 'Check Price'}
      </Button>

      {error && errorCode === 'backend_unavailable' && (
        <div className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-3">
          <ServerCrash className="h-4 w-4 text-destructive mt-0.5 shrink-0" />
          <div>
            <p className="text-sm font-medium text-destructive">Model not available</p>
            <p className="text-xs text-muted-foreground mt-0.5">The prediction backend is currently unavailable. Try again later.</p>
          </div>
        </div>
      )}
      {error && errorCode === 'league_not_allowed' && (
        <div className="flex items-start gap-2 rounded-md border border-warning/30 bg-warning/10 p-3">
          <ShieldAlert className="h-4 w-4 text-warning mt-0.5 shrink-0" />
          <div>
            <p className="text-sm font-medium text-warning">League not supported</p>
            <p className="text-xs text-muted-foreground mt-0.5">This league is not currently enabled for price checking.</p>
          </div>
        </div>
      )}
      {error && errorCode !== 'backend_unavailable' && errorCode !== 'league_not_allowed' && (
        <RenderState kind="invalid_input" message={error} />
      )}
    </div>
  );
}

function PriceResultCard({
  result, lowTrust, onMouseMove,
}: {
  result: PriceCheckResponse;
  lowTrust: boolean;
  onMouseMove: React.MouseEventHandler;
}) {
  return (
    <Card className={`card-game animate-scale-fade-in ${lowTrust ? 'border-warning/40' : 'glow-gold'}`} onMouseMove={onMouseMove}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="text-sm font-sans">ML Prediction</CardTitle>
          <div className="flex items-center gap-2 flex-wrap justify-end">
            {result.predictionSource && (
              <Badge variant="outline" className="text-[10px] font-mono px-1.5 py-0 h-5">
                {result.predictionSource}
              </Badge>
            )}
            <ConfidenceBadge value={result.confidence} />
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Low-trust warning banner */}
        {lowTrust && (
          <div className="flex items-start gap-2 rounded-md border border-warning/30 bg-warning/10 p-3">
            <AlertTriangle className="h-4 w-4 text-warning mt-0.5 shrink-0" />
            <div>
              <p className="text-sm font-medium text-warning">Low confidence estimate</p>
              {result.estimateWarning && (
                <p className="text-xs text-muted-foreground mt-0.5">{result.estimateWarning}</p>
              )}
              {result.fallbackReason && (
                <p className="text-xs text-muted-foreground mt-0.5">Reason: {result.fallbackReason}</p>
              )}
            </div>
          </div>
        )}

        {/* Not eligible notice */}
        {result.priceRecommendationEligible === false && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Info className="h-3.5 w-3.5 shrink-0" />
            Not eligible for price recommendation
          </div>
        )}

        {/* Prediction value */}
        <div className="text-center py-4">
          <p className={`text-3xl font-mono font-semibold ${lowTrust ? 'text-muted-foreground' : 'gold-shimmer-text'}`}>
            {result.predictedValue} <span className="text-lg text-muted-foreground">{result.currency}</span>
          </p>
          {result.interval && (
            <p className="text-xs text-muted-foreground mt-1 font-mono">
              p10 {result.interval.p10 ?? 'n/a'} – p90 {result.interval.p90 ?? 'n/a'}
            </p>
          )}
          {typeof result.saleProbabilityPercent === 'number' && (
            <p className="text-xs text-muted-foreground mt-1">
              Sale Probability: {result.saleProbabilityPercent}%
            </p>
          )}

          {/* Secondary metrics: fair value & fast sale */}
          {(result.fairValueP50 != null || result.fastSale24hPrice != null) && (
            <div className="flex items-center justify-center gap-6 mt-2">
              {result.fairValueP50 != null && (
                <span className="text-xs text-muted-foreground">
                  Fair Value: <span className="font-mono text-foreground">{result.fairValueP50} {result.currency}</span>
                </span>
              )}
              {result.fastSale24hPrice != null && (
                <span className="text-xs text-muted-foreground">
                  Fast Sale 24h: <span className="font-mono text-foreground">{result.fastSale24hPrice} {result.currency}</span>
                </span>
              )}
            </div>
          )}
        </div>

        {/* Comparables */}
        <ComparablesTable comparables={result.comparables} />
      </CardContent>
    </Card>
  );
}

function ComparablesTable({ comparables }: { comparables: PriceCheckResponse['comparables'] }) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Recent Comparables</h3>
        <span className="text-xs text-muted-foreground">{comparables.length} rows</span>
      </div>

      {comparables.length > 0 ? (
        <div className="rounded-md border border-border overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="text-xs">Item Name</TableHead>
                <TableHead className="text-xs">Price</TableHead>
                <TableHead className="text-xs">Currency</TableHead>
                <TableHead className="text-xs">League</TableHead>
                <TableHead className="text-xs">Added On</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {comparables.map((row) => (
                <TableRow key={`${row.name}-${row.price}-${row.addedOn ?? 'none'}-${row.currency}`}>
                  <TableCell className="text-xs font-medium text-foreground">{row.name}</TableCell>
                  <TableCell className="text-xs font-mono">{row.price}</TableCell>
                  <TableCell className="text-xs font-mono">{row.currency}</TableCell>
                  <TableCell className="text-xs">{row.league ?? '—'}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{formatComparableDate(row.addedOn)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">
          No recent comparables were found for this parsed base type in the selected league.
        </p>
      )}
    </div>
  );
}

function formatComparableDate(value: string | null | undefined): string {
  if (!value) return '—';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

PriceCheckTab.displayName = 'PriceCheckTab';
export default PriceCheckTab;
