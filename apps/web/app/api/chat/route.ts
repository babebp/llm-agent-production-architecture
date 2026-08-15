// Server-side proxy: the browser never talks to the agent network directly.
const AGENT_URL = process.env.AGENT_URL ?? "http://agent:8000";

export async function POST(req: Request) {
  const body = await req.json();
  try {
    const res = await fetch(`${AGENT_URL}/chat`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    return new Response(res.body, {
      status: res.status,
      headers: { "content-type": "application/json" },
    });
  } catch {
    return Response.json({ error: "agent unavailable" }, { status: 502 });
  }
}
