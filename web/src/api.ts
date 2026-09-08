export type AgentEvent = {
  type: "message_update" | "tool_start" | "tool_end" | "handoff" |
    "approval_required" | "completed" | "error" | "limit_exceeded";
  run_id: string;
  thread_id: string;
  user_id: string;
  seq: number;
  data: Record<string, unknown>;
};

export function parseSse(text: string): AgentEvent[] {
  return text.split("\n").filter(line => line.startsWith("data: "))
    .map(line => JSON.parse(line.slice(6)) as AgentEvent);
}

const API = import.meta.env.VITE_API_BASE ?? "";

export type Order = {
  id: string;
  status: string;
  items: Array<{ name: string; quantity: number; unit_price_cents: number }>;
};

export async function login(): Promise<string> {
  const response = await fetch(`${API}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: "demo", password: "demo-password" }),
  });
  if (!response.ok) throw new Error("登录失败");
  return (await response.json() as { access_token: string }).access_token;
}

export async function listOrders(token: string): Promise<Order[]> {
  const response = await fetch(`${API}/orders`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) throw new Error("订单查询失败");
  return response.json() as Promise<Order[]>;
}

export async function sendMessage(
  token: string,
  message: string,
  onEvent?: (event: AgentEvent) => void,
): Promise<AgentEvent[]> {
  const response = await fetch(`${API}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({
      thread_id: crypto.randomUUID(), request_id: crypto.randomUUID(), message,
      reason: message,
    }),
  });
  if (!response.ok) throw new Error("请求失败");
  if (!response.body) return parseSse(await response.text());

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const events: AgentEvent[] = [];
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const parsed = parseSse(`${frame}\n\n`);
      for (const event of parsed) {
        events.push(event);
        onEvent?.(event);
      }
    }
    if (done) break;
  }
  if (buffer.trim()) {
    for (const event of parseSse(buffer)) {
      events.push(event);
      onEvent?.(event);
    }
  }
  return events;
}

export async function decide(token: string, approvalId: string, approve: boolean): Promise<unknown> {
  const response = await fetch(`${API}/approvals/${approvalId}/decide`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ approve }),
  });
  if (!response.ok) throw new Error("审批失败");
  return response.json();
}
