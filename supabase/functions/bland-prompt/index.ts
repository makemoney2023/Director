import { serve } from 'https://deno.land/std@0.168.0/http/server.ts'

const BLAND_AI_API_KEY = Deno.env.get('BLAND_AI_API_KEY')

interface PromptRequest {
  operation: 'get' | 'create' | 'update'
  data: any
}

serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', {
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
      },
    })
  }

  try {
    const { operation, data } = await req.json() as PromptRequest

    const headers = {
      'Authorization': `Bearer ${BLAND_AI_API_KEY}`,
      'Content-Type': 'application/json',
    }

    let response
    if (operation === 'get') {
      response = await fetch(`https://api.bland.ai/v1/prompts/${data.id}`, {
        method: 'GET',
        headers,
      })
    } else if (operation === 'create') {
      response = await fetch('https://api.bland.ai/v1/prompts', {
        method: 'POST',
        headers,
        body: JSON.stringify(data),
      })
    } else if (operation === 'update') {
      response = await fetch(`https://api.bland.ai/v1/prompts/${data.id}`, {
        method: 'PUT',
        headers,
        body: JSON.stringify(data),
      })
    }

    const result = await response.json()

    return new Response(JSON.stringify(result), {
      headers: { 
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
      },
    })
  } catch (error) {
    return new Response(JSON.stringify({ error: error.message }), {
      status: 500,
      headers: { 
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
      },
    })
  }
}) 