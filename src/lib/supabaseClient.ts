import { createClient } from '@supabase/supabase-js';

/**
 * External Supabase project client.
 * This replaces the auto-generated Lovable Cloud client.
 */
const SUPABASE_URL = 'https://bzgqnwkxtyhcklwbgfaz.supabase.co';
export const SUPABASE_ANON_KEY = 'sb_publishable_6S7LhKZvY78umfdCHSXGAw_HSiN_Bna';
export const SUPABASE_PROJECT_ID = 'bzgqnwkxtyhcklwbgfaz';

export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
  auth: {
    storage: localStorage,
    persistSession: true,
    autoRefreshToken: true,
  },
});
