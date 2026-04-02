import { useEffect, useState } from 'react';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Terminal } from 'lucide-react';
import { getApiErrors, clearApiErrors, subscribeApiErrors, type ApiErrorEntry } from '@/services/apiErrorLog';

function useApiErrors() {
  const [errors, setErrors] = useState<ApiErrorEntry[]>(getApiErrors);
  useEffect(() => subscribeApiErrors(() => setErrors(getApiErrors())), []);
  return errors;
}

export default function ApiErrorPanel() {
  const errors = useApiErrors();
  const hasErrors = errors.length > 0;

  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button variant="ghost" size="icon" className="relative h-8 w-8" aria-label="API error log">
          <Terminal className="h-4 w-4 text-muted-foreground" />
          {hasErrors && (
            <span className="absolute top-1 right-1 h-2 w-2 rounded-full bg-destructive error-badge-glow" />
          )}
        </Button>
      </SheetTrigger>
      <SheetContent className="w-[400px] sm:w-[540px]">
        <SheetHeader>
          <div className="flex items-center justify-between">
            <SheetTitle className="text-sm font-semibold">API Error Log ({errors.length})</SheetTitle>
            {hasErrors && (
              <Button variant="outline" size="sm" className="text-xs h-7" onClick={clearApiErrors}>
                Clear
              </Button>
            )}
          </div>
        </SheetHeader>
        <ScrollArea className="h-[calc(100vh-6rem)] mt-4">
          {errors.length === 0 && (
            <p className="text-xs text-muted-foreground py-8 text-center">No errors recorded</p>
          )}
          <div className="space-y-2">
            {errors.map((e) => (
              <div key={e.id} className="rounded border border-border bg-secondary/30 p-3 text-xs space-y-1">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-muted-foreground">
                    {e.timestamp.toLocaleTimeString()}
                  </span>
                  <span className="font-mono px-1.5 py-0.5 rounded bg-destructive/20 text-destructive">
                    {e.statusCode ?? 'NET'}
                  </span>
                </div>
                <p className="font-mono text-foreground break-all">
                  {e.method} {e.path}
                </p>
                <p className="text-muted-foreground">{e.errorCode}: {e.message}</p>
              </div>
            ))}
          </div>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
}
