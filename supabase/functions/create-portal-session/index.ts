import { serve } from "https://deno.land/std@0.208.0/http/server.ts";
import Stripe from "https://esm.sh/stripe@15.11.0?target=deno";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.45.3?target=deno";

const STRIPE_SECRET_KEY = Deno.env.get("STRIPE_SECRET_KEY") ?? "";
const RETURN_URL = Deno.env.get("STRIPE_PORTAL_RETURN_URL") ?? "";
const SUPABASE_URL = Deno.env.get("SUPABASE_URL") ?? "";
const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";

const stripe = new Stripe(STRIPE_SECRET_KEY, {
  httpClient: Stripe.createFetchHttpClient(),
});

const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);

serve(async (req) => {
  if (req.method !== "POST") {
    return new Response("Method Not Allowed", { status: 405 });
  }

  if (!STRIPE_SECRET_KEY || !RETURN_URL) {
    return new Response("Stripe environment not configured", { status: 500 });
  }

  let body: { supabase_user_id?: string };
  try {
    body = await req.json();
  } catch (_) {
    return new Response("Invalid JSON body", { status: 400 });
  }

  const supabaseUserId = body.supabase_user_id;
  if (!supabaseUserId) {
    return new Response("supabase_user_id is required", { status: 400 });
  }

  const { data: profile, error } = await supabase
    .from("profiles")
    .select("stripe_customer_id")
    .eq("id", supabaseUserId)
    .maybeSingle();

  if (error) {
    console.error(error);
    return new Response("Unable to load profile", { status: 400 });
  }

  if (!profile?.stripe_customer_id) {
    return new Response("No subscription on file", { status: 400 });
  }

  try {
    const session = await stripe.billingPortal.sessions.create({
      customer: profile.stripe_customer_id,
      return_url: RETURN_URL,
    });
    return new Response(JSON.stringify({ url: session.url }), {
      headers: { "Content-Type": "application/json" },
      status: 200,
    });
  } catch (err) {
    console.error("Portal session error", err);
    return new Response("Failed to create portal session", { status: 500 });
  }
});
