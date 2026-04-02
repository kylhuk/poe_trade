CREATE TABLE public.debug_traffic (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at timestamptz NOT NULL DEFAULT now(),
  method text NOT NULL,
  path text NOT NULL,
  request_headers jsonb,
  request_body text,
  response_status int,
  response_headers jsonb,
  response_body text
);

ALTER TABLE public.debug_traffic ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role only" ON public.debug_traffic
  FOR ALL TO service_role USING (true) WITH CHECK (true);