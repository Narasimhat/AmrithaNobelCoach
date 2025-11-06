import { serve } from "https://deno.land/std@0.208.0/http/server.ts";
import Stripe from "https://esm.sh/stripe@15.11.0?target=deno";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.45.3?target=deno";

const STRIPE_SECRET_KEY = Deno.env.get("STRIPE_SECRET_KEY") ?? "";
const STRIPE_PRICE_ID = Deno.env.get("STRIPE_PRICE_ID") ?? "";
const SUCCESS_URL = Deno.env.get("STRIPE_CHECKOUT_SUCCESS_URL") ?? "";
const CANCEL_URL = Deno.env.get("STRIPE_CHECKOUT_CANCEL_URL") ?? "";
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

  if (!STRIPE_SECRET_KEY || !STRIPE_PRICE_ID || !SUCCESS_URL || !CANCEL_URL) {
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

  const { data: profile, error: profileError } = await supabase
    .from("profiles")
    .select("email, stripe_customer_id")
    .eq("id", supabaseUserId)
    .maybeSingle();

  if (profileError) {
    console.error(profileError);
    return new Response("Unable to load profile", { status: 400 });
  }

  let customerId = profile?.stripe_customer_id ?? null;

  try {
    if (!customerId) {
      const customer = await stripe.customers.create({
        email: profile?.email ?? undefined,
        metadata: { supabase_user_id: supabaseUserId },
      });
      customerId = customer.id;
      await supabase
        .from("profiles")
        .update({ stripe_customer_id: customerId, updated_at: new Date().toISOString() })
        .eq("id", supabaseUserId);
    }

    const session = await stripe.checkout.sessions.create({
      mode: "subscription",
      customer: customerId ?? undefined,
      metadata: { supabase_user_id: supabaseUserId },
      line_items: [
        {
          price: STRIPE_PRICE_ID,
          quantity: 1,
        },
      ],
      allow_promotion_codes: true,
      success_url: SUCCESS_URL,
      cancel_url: CANCEL_URL,
    });

    return new Response(JSON.stringify({ url: session.url }), {
      headers: { "Content-Type": "application/json" },
      status: 200,
    });
  } catch (error) {
    console.error("Stripe checkout error", error);
    return new Response("Failed to create checkout session", { status: 500 });
  }
});
