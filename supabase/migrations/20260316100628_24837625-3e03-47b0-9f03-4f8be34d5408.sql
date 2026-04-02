
CREATE TABLE public.approved_users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL UNIQUE,
  approved_at timestamptz DEFAULT now()
);

ALTER TABLE public.approved_users ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can check own approval"
  ON public.approved_users FOR SELECT
  TO authenticated
  USING (user_id = auth.uid());
