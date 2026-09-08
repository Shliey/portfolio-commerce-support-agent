import { FormEvent, useEffect, useState } from "react";
import { AgentEvent, decide, login, sendMessage } from "./api";
import "./styles.css";

export default function App() {
  const [token, setToken] = useState("");
  const [message, setMessage] = useState("退货 order-1001，耳机有破损");
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [busy, setBusy] = useState(false);
  useEffect(() => { void login().then(setToken); }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!token) return;
    setBusy(true);
    setEvents([]);
    try {
      await sendMessage(token, message, item => setEvents(current => [...current, item]));
    } finally { setBusy(false); }
  }

  async function review(id: string, approve: boolean) {
    await decide(token, id, approve);
    setEvents(current => [...current, {
      type: "message_update", run_id: "local", thread_id: "local", user_id: "user-1",
      seq: current.length + 1, data: { text: approve ? "已批准，工单已创建。" : "已拒绝。" },
    }]);
  }

  return <main>
    <header><span className="eyebrow">PORTFOLIO · AGENT ENGINEERING</span><h1>可恢复电商售后 Agent</h1>
      <p>确定性权限与资格判断 · 人工审批 · 数据库幂等 · 可观测事件流</p></header>
    <section className="architecture"><span>用户意图</span><b>→</b><span>角色路由</span><b>→</b>
      <span>可信工具</span><b>→</b><span>人工审批</span><b>→</b><span>幂等写入</span></section>
    <form onSubmit={submit}><textarea value={message} onChange={e => setMessage(e.target.value)} />
      <button disabled={!token || busy}>{busy ? "处理中…" : "发送请求"}</button></form>
    <section className="timeline">
      {events.map(item => <article key={`${item.run_id}-${item.seq}`}>
        <small>#{item.seq} · {item.type}</small>
        <pre>{JSON.stringify(item.data, null, 2)}</pre>
        {item.type === "approval_required" && <div className="actions">
          <button onClick={() => void review(String(item.data.id), true)}>批准</button>
          <button className="secondary" onClick={() => void review(String(item.data.id), false)}>拒绝</button>
        </div>}
      </article>)}
    </section>
  </main>;
}
