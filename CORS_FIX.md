# FIX: notify-admin CORS Error

The "preflight request doesn't pass access control check" error occurs because the Supabase Edge Function is not handling the HTTP `OPTIONS` request.

### Fixed Code for `notify-admin/index.ts`

Replace your current function code with this. It includes the necessary `corsHeaders` and the `OPTIONS` check.

```typescript
import { serve } from "https://deno.land/std@0.168.0/http/server.ts"

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
}

serve(async (req) => {
  // 1. Handle CORS Preflight
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders })
  }

  try {
    const { type, code, name, transaction } = await req.json()

    // ... Your existing logic to send email or log ...
    console.log(`Notification for ${name}: ${code}`);

    return new Response(
      JSON.stringify({ message: "Notification sent successfully" }),
      { 
        headers: { ...corsHeaders, "Content-Type": "application/json" },
        status: 200 
      }
    )

  } catch (error) {
    return new Response(
      JSON.stringify({ error: error.message }),
      { 
        headers: { ...corsHeaders, "Content-Type": "application/json" },
        status: 400 
      }
    )
  }
})
```

### How to Apply:
1. **Via CLI**: Run `supabase functions deploy notify-admin` after saving the file.
2. **Via Dashboard**: Go to **Edge Functions** -> **notify-admin** -> **Edit** and paste the code above.
