import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { RefreshCw, ChevronDown, ChevronRight } from "lucide-react";
import { supabase, SUPABASE_ANON_KEY, SUPABASE_PROJECT_ID } from "@/lib/supabaseClient";

interface TrafficEntry {
  id: string;
  created_at: string;
  method: string;
  path: string;
  request_headers: Record<string, string> | null;
  request_body: string | null;
  response_status: number | null;
  response_headers: Record<string, string> | null;
  response_body: string | null;
}

const statusColor = (status: number | null) => {
  if (!status) return "secondary";
  if (status < 300) return "default";
  if (status < 400) return "secondary";
  if (status < 500) return "outline";
  return "destructive";
};

const ExpandableCell = ({ label, content }: { label: string; content: string | null }) => {
  const [open, setOpen] = useState(false);
  if (!content) return <span className="text-muted-foreground text-xs">—</span>;

  let formatted = content;
  try {
    formatted = JSON.stringify(JSON.parse(content), null, 2);
  } catch {
    // not JSON, keep as-is
  }

  const truncated = content.length > 80;

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger asChild>
        <button type="button" className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors text-left">
          {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          {truncated && !open ? content.slice(0, 80) + "…" : label}
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <pre className="mt-1 text-xs bg-muted/50 p-2 rounded max-h-60 overflow-auto whitespace-pre-wrap break-all font-mono">
          {formatted}
        </pre>
      </CollapsibleContent>
    </Collapsible>
  );
};

const DebugTrafficTab = () => {
  const [entries, setEntries] = useState<TrafficEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [limit, setLimit] = useState(100);

  const fetchEntries = useCallback(async () => {
    setLoading(true);
    try {
      const { data: sessionData } = await supabase.auth.getSession();
      const token = sessionData?.session?.access_token;
      if (!token) return;

      const res = await fetch(
        `https://${SUPABASE_PROJECT_ID}.supabase.co/functions/v1/debug-traffic-reader?limit=${limit}`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
            apikey: SUPABASE_ANON_KEY,
            "Content-Type": "application/json",
          },
        }
      );
      if (res.ok) {
        const data = await res.json();
        setEntries(data);
      }
    } catch (err) {
      console.error("Failed to fetch debug traffic:", err);
    } finally {
      setLoading(false);
    }
  }, [limit]);

  useEffect(() => {
    fetchEntries();
  }, [fetchEntries]);

  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(fetchEntries, 5000);
    return () => clearInterval(interval);
  }, [autoRefresh, fetchEntries]);

  return (
    <Card className="border-border bg-card/80">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-display">API Traffic Log</CardTitle>
          <div className="flex items-center gap-2">
            <select
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
              className="text-xs bg-muted border border-border rounded px-2 py-1"
            >
              <option value={50}>50</option>
              <option value={100}>100</option>
              <option value={250}>250</option>
              <option value={500}>500</option>
              <option value={1000}>1000</option>
            </select>
            <Button
              variant={autoRefresh ? "default" : "outline"}
              size="sm"
              onClick={() => setAutoRefresh(!autoRefresh)}
              className="text-xs gap-1"
            >
              <RefreshCw className={`h-3 w-3 ${autoRefresh ? "animate-spin" : ""}`} />
              Auto
            </Button>
            <Button variant="outline" size="sm" onClick={fetchEntries} disabled={loading} className="text-xs">
              <RefreshCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="max-h-[70vh] overflow-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="text-xs w-[140px]">Time</TableHead>
                <TableHead className="text-xs w-[60px]">Method</TableHead>
                <TableHead className="text-xs">Path</TableHead>
                <TableHead className="text-xs w-[70px]">Status</TableHead>
                <TableHead className="text-xs">Request</TableHead>
                <TableHead className="text-xs">Response</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {entries.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className="text-center text-muted-foreground text-xs py-8">
                    {loading ? "Loading…" : "No traffic captured yet."}
                  </TableCell>
                </TableRow>
              )}
              {entries.map((e) => (
                <TableRow key={e.id}>
                  <TableCell className="text-xs font-mono text-muted-foreground">
                    {new Date(e.created_at).toLocaleTimeString()}
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className="text-xs font-mono">
                      {e.method}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-xs font-mono max-w-[200px] truncate" title={e.path}>
                    {e.path}
                  </TableCell>
                  <TableCell>
                    <Badge variant={statusColor(e.response_status)} className="text-xs font-mono">
                      {e.response_status ?? "—"}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <ExpandableCell label="View body" content={e.request_body} />
                  </TableCell>
                  <TableCell>
                    <ExpandableCell label="View body" content={e.response_body} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
};

export default DebugTrafficTab;
