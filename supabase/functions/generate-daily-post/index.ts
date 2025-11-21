// Supabase Edge Function: Generate Daily Knowledge Hub Post
// Runs daily via cron to create AI-generated educational content

import { serve } from "https://deno.land/std@0.168.0/http/server.ts"
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
}

serve(async (req) => {
  // Handle CORS preflight
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders })
  }

  try {
    const supabaseUrl = Deno.env.get('SUPABASE_URL')!
    const supabaseServiceKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!
    const openaiApiKey = Deno.env.get('OPENAI_API_KEY')!

    if (!supabaseUrl || !supabaseServiceKey || !openaiApiKey) {
      throw new Error('Missing required environment variables')
    }

    const supabase = createClient(supabaseUrl, supabaseServiceKey)

    // Topics for 9-year-old Amritha (rotate through these)
    const topics = [
      "Why do stars twinkle? Explain light refraction in a fun way",
      "How do plants talk to each other? Teach about mycorrhizal networks",
      "What makes a rainbow appear? Explore light and water science",
      "Why is the ocean salty? Journey through water cycles",
      "How do birds know where to migrate? Discuss navigation and instinct",
      "What is electricity and how does it power our homes?",
      "Why do seasons change? Explain Earth's tilt and orbit",
      "How do airplanes fly? Introduce aerodynamics simply",
      "What makes volcanoes erupt? Explore plate tectonics",
      "Why do we dream? Simple neuroscience for kids",
      "How does the internet work? Explain data and connections",
      "What are black holes? Make space physics accessible",
      "Why is kindness important? Discuss empathy and community",
      "How can we help the planet? Practical environmental actions",
      "What is creativity and how can we practice it?",
    ]

    // Pick today's topic (based on day of year to ensure variety)
    const dayOfYear = Math.floor((Date.now() - new Date(new Date().getFullYear(), 0, 0).getTime()) / 86400000)
    const topic = topics[dayOfYear % topics.length]

    // Generate content using OpenAI
    const openaiResponse = await fetch('https://api.openai.com/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${openaiApiKey}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        model: 'gpt-4o-mini',
        messages: [
          {
            role: 'system',
            content: `You are a creative educator for The Silent Room app. Create engaging, age-appropriate content for 9-year-old children like Amritha who are curious, creative, and care about the planet. 

Your posts should:
- Be 200-300 words
- Use simple language but don't talk down
- Include a fascinating fact or story
- Ask a thought-provoking question at the end
- Inspire curiosity, kindness, or planet consciousness
- Be warm and encouraging in tone

Format your response as JSON with these fields:
{
  "title": "Catchy title (max 60 chars)",
  "content": "Main educational content (200-300 words)",
  "category": "one of: Science|Nature|Space|Technology|Kindness|Planet|Creativity",
  "emoji": "single relevant emoji",
  "question": "Thought-provoking question to end with"
}`
          },
          {
            role: 'user',
            content: `Create today's Knowledge Hub post about: ${topic}`
          }
        ],
        temperature: 0.8,
        max_tokens: 600,
      }),
    })

    if (!openaiResponse.ok) {
      const error = await openaiResponse.text()
      throw new Error(`OpenAI API error: ${error}`)
    }

    const openaiData = await openaiResponse.json()
    const generatedContent = openaiData.choices[0].message.content

    // Parse the JSON response
    let post
    try {
      post = JSON.parse(generatedContent)
    } catch (e) {
      // If OpenAI didn't return valid JSON, create a fallback
      post = {
        title: "Today's Discovery",
        content: generatedContent,
        category: "Science",
        emoji: "🌟",
        question: "What do you think about this?"
      }
    }

    // Insert into Supabase posts table
    const { data, error } = await supabase
      .from('posts')
      .insert({
        title: post.title,
        content: `${post.emoji} ${post.content}\n\n💭 ${post.question}`,
        category: post.category,
        author: 'The Silent Room Coach',
        published_at: new Date().toISOString(),
        is_featured: true, // Mark daily posts as featured
      })
      .select()

    if (error) {
      throw new Error(`Supabase insert error: ${error.message}`)
    }

    return new Response(
      JSON.stringify({ 
        success: true, 
        post: data[0],
        message: 'Daily post generated successfully',
        topic: topic
      }),
      { 
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        status: 200 
      }
    )

  } catch (error) {
    console.error('Error generating daily post:', error)
    return new Response(
      JSON.stringify({ 
        success: false, 
        error: error.message 
      }),
      { 
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        status: 500 
      }
    )
  }
})
