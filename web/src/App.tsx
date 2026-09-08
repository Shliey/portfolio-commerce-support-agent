import { FormEvent, useEffect, useState } from "react";
import { AgentEvent, Order, decide, listOrders, login, sendMessage } from "./api";
import "./styles.css";

type CitationView = { source: string; title: string; section: string };

function citationsFrom(data: Record<string, unknown>): CitationView[] {
  if (!Array.isArray(data.citations)) return [];
  return data.citations.flatMap(value => {
    if (typeof value !== "object" || value === null) return [];
    const citation = value as Record<string, unknown>;
    if (![citation.source, citation.title, citation.section].every(item => typeof item === "string")) {
      return [];
    }
    return [{
      source: String(citation.source), title: String(citation.title), section: String(citation.section),
    }];
  });
}

function EventDetails({ item }: { item: AgentEvent }) {
  const citations = citationsFrom(item.data);
  return <>
    {item.type === "handoff" && <p>角色切换：{String(item.data.from)} → {String(item.data.to)}</p>}
    {(item.type === "tool_start" || item.type === "tool_end") &&
      <p>工具状态：{String(item.data.tool)} · {item.type === "tool_start" ? "执行中" : "已完成"}</p>}
    {citations.length > 0 && <div aria-label="政策引用"><strong>政策来源</strong><ul>
      {citations.map(citation => <li key={`${citation.source}-${citation.section}`}>
        {citation.title} · {citation.section} <small>{citation.source}</small>
      </li>)}
    </ul></div>}
  </>;
}

export default function App() {
  const [token, setToken] = useState("");
  const [orders, setOrders] = useState<Order[]>([]);
  const [message, setMessage] = useState("退货 order-1001，耳机有破损");
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    void login().then(async accessToken => {
      setToken(accessToken);
      setOrders(await listOrders(accessToken));
    }).catch(reason => setError(reason instanceof Error ? reason.message : "初始化失败"));
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!token) return;
    setBusy(true);
    setError("");
    setEvents([]);
    try {
      await sendMessage(token, message, item => setEvents(current => [...current, item]));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "请求失败");
    } finally { setBusy(false); }
  }

  async function review(id: string, approve: boolean) {
    try {
      await decide(token, id, approve);
      setEvents(current => [...current, {
        type: "message_update", run_id: "local", thread_id: "local", user_id: "user-1",
        seq: current.length + 1, data: { text: approve ? "已批准，工单已创建。" : "已拒绝。" },
      }]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "审批失败");
    }
  }

  return <main>
    <header><span className="eyebrow">PORTFOLIO · AGENT ENGINEERING</span><h1>可恢复电商售后 Agent</h1>
      <p>确定性权限与资格判断 · 人工审批 · 数据库幂等 · 可观测事件流</p></header>
    <section className="architecture"><span>用户意图</span><b>→</b><span>角色路由</span><b>→</b>
      <span>可信工具</span><b>→</b><span>人工审批</span><b>→</b><span>幂等写入</span></section>
    <section aria-label="订单历史" className="orders">
      <h2>我的订单</h2>
      {orders.map(order => <article key={order.id}>
        <strong>{order.id}</strong><span>{order.status}</span>
        <small>{order.items.map(item => `${item.name} × ${item.quantity}`).join("，")}</small>
      </article>)}
    </section>
    {error && <p role="alert">{error}</p>}
    <form onSubmit={submit}><textarea value={message} onChange={e => setMessage(e.target.value)} />
      <button disabled={!token || busy}>{busy ? "处理中…" : "发送请求"}</button></form>
    <section className="timeline">
      {events.map(item => <article key={`${item.run_id}-${item.seq}`}>
        <small>#{item.seq} · {item.type}</small>
        <EventDetails item={item} />
        <pre>{JSON.stringify(item.data, null, 2)}</pre>
        {item.type === "approval_required" && <div className="actions">
          <button onClick={() => void review(String(item.data.id), true)}>批准</button>
          <button className="secondary" onClick={() => void review(String(item.data.id), false)}>拒绝</button>
        </div>}
      </article>)}
    </section>
  </main>;
}
