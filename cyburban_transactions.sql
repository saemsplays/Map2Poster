-- CYBURBAN STUDIO: TRANSACTIONS SCHEMA
-- This table tracks all purchase verification requests for the Cyburban Studio High-Res Engine.

-- 0. Ensure profiles table has is_admin
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT false;

-- 1. Create the table
CREATE TABLE IF NOT EXISTS public.cyburban_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    first_name TEXT NOT NULL,
    transaction_code TEXT UNIQUE NOT NULL,
    full_message TEXT NOT NULL,
    city TEXT NOT NULL,
    country TEXT NOT NULL,
    theme TEXT NOT NULL,
    preset TEXT NOT NULL,
    distance INTEGER NOT NULL,
    verse_text TEXT NOT NULL,
    verse_title TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'rejected')) DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 2. Add indexes for performance
CREATE INDEX IF NOT EXISTS idx_cyburban_transactions_user_id ON public.cyburban_transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_cyburban_transactions_status ON public.cyburban_transactions(status);
CREATE INDEX IF NOT EXISTS idx_cyburban_transactions_code ON public.cyburban_transactions(transaction_code);

-- 3. Enable Row Level Security (RLS)
ALTER TABLE public.cyburban_transactions ENABLE ROW LEVEL SECURITY;

-- 4. Policies

-- Policy: Authenticated users can insert their own transactions
CREATE POLICY "Users can insert their own transactions" 
ON public.cyburban_transactions 
FOR INSERT 
TO authenticated 
WITH CHECK (auth.uid() = user_id OR user_id IS NULL); -- Allow null user_id for anonymous-ish flows if needed

-- Policy: Users can view their own transactions
CREATE POLICY "Users can view their own transactions" 
ON public.cyburban_transactions 
FOR SELECT 
TO authenticated 
USING (auth.uid() = user_id OR EXISTS (
    SELECT 1 FROM public.profiles 
    WHERE profiles.id = auth.uid() 
    AND profiles.is_admin = true
));

-- Policy: Admin can do everything
CREATE POLICY "Admin can full manage" 
ON public.cyburban_transactions 
FOR ALL 
TO authenticated 
USING (
    EXISTS (
        SELECT 1 FROM public.profiles
        WHERE profiles.id = auth.uid()
        AND profiles.is_admin = true
    )
);

-- 5. Trigger for updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE OR REPLACE TRIGGER update_cyburban_transactions_updated_at
    BEFORE UPDATE ON public.cyburban_transactions
    FOR EACH ROW
    EXECUTE PROCEDURE update_updated_at_column();

-- 6. Helper to set an admin (Usage: SELECT set_as_admin('YOUR_USER_ID'))
CREATE OR REPLACE FUNCTION set_as_admin(target_user_id UUID)
RETURNS VOID AS $$
BEGIN
    UPDATE public.profiles SET is_admin = true WHERE id = target_user_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

