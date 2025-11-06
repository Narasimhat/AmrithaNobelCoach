import { serve } from "https://deno.land/std@0.208.0/http/server.ts";
import Stripe from "https://esm.sh/stripe@15.11.0?target=deno";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.45.3?target=deno";

const STRIPE_SECRET_KEY = Deno.env.get("STRIPE_SECRET_KEY") ?? "";
const STRIPE_WEBHOOK_SECRET = Deno.env.get("STRIPE_WEBHOOK_SECRET") ?? "";
const SUPABASE_URL = Deno.env.get("SUPABASE_URL") ?? Deno.env.get("EDGE_SUPABASE_URL") ?? "";
const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? Deno.env.get("EDGE_SUPABASE_SERVICE_ROLE_KEY") ?? "";

const stripe = new Stripe(STRIPE_SECRET_KEY, {
  httpClient: Stripe.createFetchHttpClient(),
});

const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);

interface StripeMetadata {
  supabase_user_id?: string;
  plan_type?: string;
}

function normalizeMetadata(metadata: Stripe.Metadata | null | undefined): Record<string, string> {
  const result: Record<string, string> = {};
  if (!metadata) return result;
  for (const [key, value] of Object.entries(metadata)) {
    if (value !== null && value !== undefined) {
      result[key] = String(value);
    }
  }
  return result;
}

async function upsertProfileFromSubscription(subscription: Stripe.Subscription, fallbackUserId?: string) {
  const metadata = subscription.metadata as StripeMetadata;
  const customerId = typeof subscription.customer === "string" ? subscription.customer : subscription.customer?.id;
  const status = subscription.status;
  const trialEnd = subscription.trial_end ? new Date(subscription.trial_end * 1000).toISOString() : null;

  let supabaseUserId = metadata.supabase_user_id ?? fallbackUserId;
  if (!supabaseUserId && customerId) {
    const { data: profile, error } = await supabase
      .from("profiles")
      .select("id")
      .eq("stripe_customer_id", customerId)
      .maybeSingle();

    if (error) {
      console.error("Error loading profile for customer", customerId, error);
    }
    supabaseUserId = profile?.id ?? supabaseUserId;
  }

  if (!supabaseUserId) {
    console.warn("Missing supabase_user_id metadata on subscription", subscription.id);
    return;
  }

  const { error } = await supabase
    .from("profiles")
    .update({
      stripe_customer_id: customerId,
      subscription_status: status,
      trial_ends_at: trialEnd,
      updated_at: new Date().toISOString(),
    })
    .eq("id", supabaseUserId);

  if (error) {
    console.error("Error updating profile:", error);
  }
}

serve(async (req) => {
  if (req.method === "GET") {
    return new Response("ok", { status: 200 });
  }

  const body = await req.text();
  const signature = req.headers.get("stripe-signature") ?? "";

  let event: Stripe.Event;
  try {
    event = stripe.webhooks.constructEvent(body, signature, STRIPE_WEBHOOK_SECRET);
  } catch (err) {
    console.error("Webhook signature verification failed:", err.message);
    return new Response("Signature verification failed", { status: 400 });
  }

  try {
    switch (event.type) {
      case "customer.subscription.created":
      case "customer.subscription.updated":
      case "customer.subscription.deleted": {
        const subscription = event.data.object as Stripe.Subscription;
        await upsertProfileFromSubscription(subscription);
        break;
      }
      case "checkout.session.completed": {
        const session = event.data.object as Stripe.Checkout.Session;
        const sessionMetadata = session.metadata as StripeMetadata | undefined;
        const sessionUserId = sessionMetadata?.supabase_user_id;
        if (session.subscription) {
          const subscription = await stripe.subscriptions.retrieve(
            typeof session.subscription === "string" ? session.subscription : session.subscription.id,
          );
          if (sessionUserId && !(subscription.metadata as StripeMetadata)?.supabase_user_id) {
            const metadataToPersist = normalizeMetadata(subscription.metadata);
            metadataToPersist.supabase_user_id = sessionUserId;
            if (sessionMetadata?.plan_type) {
              metadataToPersist.plan_type = sessionMetadata.plan_type;
            }
            await stripe.subscriptions.update(subscription.id, { metadata: metadataToPersist });
          }
          await upsertProfileFromSubscription(subscription, sessionUserId);
        }
        break;
      }
      case "invoice.payment_succeeded": {
        const invoice = event.data.object as Stripe.Invoice;
        const subscriptionId = typeof invoice.subscription === "string" ? invoice.subscription : invoice.subscription?.id;
        const customerId =
          typeof invoice.customer === "string" ? invoice.customer : invoice.customer?.id ?? undefined;
        const invoiceMetadata = invoice.metadata as StripeMetadata | undefined;
        const invoiceUserId = invoiceMetadata?.supabase_user_id;
        if (subscriptionId) {
          const subscription = await stripe.subscriptions.retrieve(subscriptionId);
          const currentMetadata = normalizeMetadata(subscription.metadata);
          if (invoiceUserId && !currentMetadata.supabase_user_id) {
            currentMetadata.supabase_user_id = invoiceUserId;
          }
          if (invoiceMetadata?.plan_type && !currentMetadata.plan_type) {
            currentMetadata.plan_type = invoiceMetadata.plan_type;
          }
          if (Object.keys(currentMetadata).length && subscription.metadata !== currentMetadata) {
            await stripe.subscriptions.update(subscription.id, { metadata: currentMetadata });
          }
          await upsertProfileFromSubscription(subscription, invoiceUserId ?? customerId);
        }
        break;
      }
      default:
        console.log("Unhandled event type", event.type);
    }
  } catch (error) {
    console.error("Error processing event:", error);
    return new Response("Webhook handler failure", { status: 500 });
  }

  return new Response("ok", { status: 200 });
});
