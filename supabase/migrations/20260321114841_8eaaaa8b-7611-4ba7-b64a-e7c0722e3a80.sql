
-- Create table for persisting POESESSID per user
CREATE TABLE public.user_poe_sessions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL UNIQUE,
  encrypted_session text NOT NULL,
  account_name text,
  updated_at timestamp with time zone NOT NULL DEFAULT now()
);

-- Enable RLS
ALTER TABLE public.user_poe_sessions ENABLE ROW LEVEL SECURITY;

-- Users can only access their own session
CREATE POLICY "Users can read own poe session"
  ON public.user_poe_sessions FOR SELECT
  TO authenticated
  USING (user_id = auth.uid());

CREATE POLICY "Users can insert own poe session"
  ON public.user_poe_sessions FOR INSERT
  TO authenticated
  WITH CHECK (user_id = auth.uid());

CREATE POLICY "Users can update own poe session"
  ON public.user_poe_sessions FOR UPDATE
  TO authenticated
  USING (user_id = auth.uid());

CREATE POLICY "Users can delete own poe session"
  ON public.user_poe_sessions FOR DELETE
  TO authenticated
  USING (user_id = auth.uid());
