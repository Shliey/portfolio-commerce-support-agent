// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("App", () => {
  it("renders order history, streamed approval, and approved result with a fake backend", async () => {
    const approval = {
      type: "approval_required", run_id: "run-1", thread_id: "thread-1", user_id: "user-1",
      seq: 1, data: { id: "approval-1" },
    };
    const completed = {
      type: "completed", run_id: "run-1", thread_id: "thread-1", user_id: "user-1",
      seq: 2, data: { active_agent: "return" },
    };
    const sse = `event: approval_required\ndata: ${JSON.stringify(approval)}\n\n` +
      `event: completed\ndata: ${JSON.stringify(completed)}\n\n`;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/login")) return jsonResponse({ access_token: "token", token_type: "bearer" });
      if (url.endsWith("/orders")) return jsonResponse([{
        id: "order-1001", status: "delivered",
        items: [{ name: "Headphones", quantity: 1, unit_price_cents: 12900 }],
      }]);
      if (url.endsWith("/chat")) return new Response(sse, { status: 200 });
      if (url.includes("/approvals/approval-1/decide")) {
        return jsonResponse({ status: "approved", ticket: { id: "ticket-1" } });
      }
      return jsonResponse({}, 404);
    }));

    render(<App />);
    expect(await screen.findByText("order-1001")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "发送请求" }));
    expect(await screen.findByText("approval_required", { exact: false })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "批准" }));
    expect(await screen.findByText("已批准，工单已创建。", { exact: false })).toBeVisible();
  });

  it("renders a stable login error", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ detail: { code: "invalid_credentials" } }, 401)));
    render(<App />);
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("登录失败"));
    expect(screen.getByRole("button", { name: "发送请求" })).toBeDisabled();
  });

  it("renders the rejected approval result without a ticket", async () => {
    const approval = {
      type: "approval_required", run_id: "run-reject", thread_id: "thread-reject",
      user_id: "user-1", seq: 1, data: { id: "approval-reject" },
    };
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/login")) return jsonResponse({ access_token: "token" });
      if (url.endsWith("/orders")) return jsonResponse([]);
      if (url.endsWith("/chat")) {
        return new Response(`event: approval_required\ndata: ${JSON.stringify(approval)}\n\n`);
      }
      if (url.includes("/approvals/approval-reject/decide")) {
        return jsonResponse({ status: "rejected", ticket: null });
      }
      return jsonResponse({}, 404);
    }));

    render(<App />);
    await waitFor(() => expect(screen.getByRole("button", { name: "发送请求" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "发送请求" }));
    fireEvent.click(await screen.findByRole("button", { name: "拒绝" }));
    expect(await screen.findByText("已拒绝。", { exact: false })).toBeVisible();
    expect(screen.queryByText("工单已创建", { exact: false })).not.toBeInTheDocument();
  });

  it("renders a documented chat error from the fake backend", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/login")) return jsonResponse({ access_token: "token" });
      if (url.endsWith("/orders")) return jsonResponse([]);
      if (url.endsWith("/chat")) {
        return jsonResponse({ detail: { code: "internal_error" } }, 500);
      }
      return jsonResponse({}, 404);
    }));

    render(<App />);
    await waitFor(() => expect(screen.getByRole("button", { name: "发送请求" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "发送请求" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("请求失败"));
  });

  it("renders a documented approval conflict from the fake backend", async () => {
    const approval = {
      type: "approval_required", run_id: "run-conflict", thread_id: "thread-conflict",
      user_id: "user-1", seq: 1, data: { id: "approval-conflict" },
    };
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/login")) return jsonResponse({ access_token: "token" });
      if (url.endsWith("/orders")) return jsonResponse([]);
      if (url.endsWith("/chat")) {
        return new Response(`event: approval_required\ndata: ${JSON.stringify(approval)}\n\n`);
      }
      if (url.includes("/approvals/approval-conflict/decide")) {
        return jsonResponse({ detail: { code: "idempotency_conflict" } }, 409);
      }
      return jsonResponse({}, 404);
    }));

    render(<App />);
    await waitFor(() => expect(screen.getByRole("button", { name: "发送请求" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "发送请求" }));
    fireEvent.click(await screen.findByRole("button", { name: "批准" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("审批失败"));
  });
});
