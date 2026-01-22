import { serve } from "https://deno.land/std@0.168.0/http/server.ts"
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2.39.3'

const corsHeaders = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
    'Access-Control-Allow-Methods': 'POST, GET, OPTIONS, PUT, DELETE',
    'Access-Control-Max-Age': '86400',
}

const AUTHORIZED_ADMINS = [
    'saemscodes@gmail.com',
    'saemstunes@gmail.com'
];

serve(async (req: Request) => {
    // Handle CORS Preflight
    if (req.method === 'OPTIONS') {
        return new Response('ok', {
            headers: corsHeaders,
            status: 200
        })
    }

    try {
        const authHeader = req.headers.get('Authorization');
        if (!authHeader) {
            throw new Error('Missing Authorization header');
        }

        const supabaseClient = createClient(
            Deno.env.get('SUPABASE_URL') ?? '',
            Deno.env.get('SUPABASE_ANON_KEY') ?? '',
            { global: { headers: { Authorization: authHeader } } }
        );

        // Get the user from JWT
        const { data: { user }, error: authError } = await supabaseClient.auth.getUser();
        if (authError || !user) {
            throw new Error('Unauthorized session');
        }

        // Check if email is in the manual override list
        if (!AUTHORIZED_ADMINS.includes(user.email ?? '')) {
            throw new Error('Access Denied: Email not in administrative list');
        }

        // Double check database is_admin flag
        const { data: profile, error: dbError } = await supabaseClient
            .from('profiles')
            .select('is_admin')
            .eq('user_id', user.id)
            .single();

        if (dbError || !profile?.is_admin) {
            throw new Error('Access Denied: Administrative privileges not set in profile');
        }

        return new Response(
            JSON.stringify({
                status: 'success',
                message: 'Admin session verified',
                user: {
                    email: user.email,
                    role: 'admin'
                }
            }),
            {
                headers: { ...corsHeaders, "Content-Type": "application/json" },
                status: 200
            }
        )

    } catch (err: any) {
        console.error('Verify Admin Error:', err.message);

        return new Response(
            JSON.stringify({ error: err.message }),
            {
                headers: { ...corsHeaders, "Content-Type": "application/json" },
                status: 403
            }
        )
    }
})
