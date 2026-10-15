/** @jest-environment jsdom */
import React from "react";
import { act, cleanup, render, waitFor } from "@testing-library/react";
import { ChatProvider, useChat } from "../ChatContext";

let mockAuth: { user: { id: string } | null; loading: boolean };
jest.mock("@/contexts/AuthContext", () => ({ useAuth: () => mockAuth }));

let chat: ReturnType<typeof useChat>;
function Probe() {
  chat = useChat();
  return null;
}
const tree = () => <ChatProvider><Probe /></ChatProvider>;
const session = (id: string, updatedAt: string) => ({
  id,
  title: id,
  created_at: updatedAt,
  updated_at: updatedAt,
});
const response = (body: unknown) => ({ ok: true, json: async () => body });
const accessResponse = (sessions: ReturnType<typeof session>[]) => response({ sessions, remaining_quota: 5 });
const historyResponse = (content: string) => response({ history: [{ role: "assistant", content, timestamp: Date.now() }] });
const saveLocalRoom = (id: string, content: string) => {
  localStorage.setItem("egxbots_chat_sessions_v2", JSON.stringify([session(id, "2026-10-15T10:00:00Z")]));
  localStorage.setItem(`egxbots_msgs_${id}`, JSON.stringify([{ role: "assistant", content, timestamp: 1 }]));
};

beforeEach(() => {
  localStorage.clear();
  mockAuth = { user: { id: "user-a" }, loading: false };
  global.fetch = jest.fn();
});
afterEach(cleanup);

test("replaces a remembered room that does not exist on the server with the newest server room", async () => {
  saveLocalRoom("deleted-room", "محادثة قديمة");
  const newest = session("newest-room", "2026-10-15T12:00:00Z");
  (fetch as jest.Mock)
    .mockResolvedValueOnce(accessResponse([session("older-room", "2026-10-15T11:00:00Z"), newest]))
    .mockResolvedValueOnce(historyResponse("محادثة الخادم"));

  await act(async () => { render(tree()); });
  await waitFor(() => expect(chat.messages.map(({ content }) => content)).toEqual(["محادثة الخادم"]));

  expect(chat.activeSessionId).toBe("newest-room");
  expect(chat.sessions.map(({ id }) => id)).toEqual(["newest-room", "older-room"]);
  expect(chat.messages.map(({ content }) => content)).toEqual(["محادثة الخادم"]);
  expect(chat.messages.map(({ content }) => content)).not.toContain("محادثة قديمة");
});

test("clears a remembered room when the signed-in account has no server rooms", async () => {
  saveLocalRoom("another-account-room", "بيانات حساب سابق");
  (fetch as jest.Mock).mockResolvedValueOnce(accessResponse([]));

  await act(async () => { render(tree()); });
  await waitFor(() => expect(chat.isInitializing).toBe(false));

  expect(chat.activeSessionId).toBeNull();
  expect(chat.sessions).toEqual([]);
  expect(chat.messages).toEqual([]);
  expect(localStorage.getItem("egxbots_chat_sessions_v2")).toBe("[]");
});

test("deduplicates same-room history reads and ignores a late response after switching rooms", async () => {
  const roomA = session("room-a", "2026-10-15T12:00:00Z");
  const roomB = session("room-b", "2026-10-15T11:00:00Z");
  saveLocalRoom(roomA.id, "نسخة محلية أ");
  localStorage.setItem(`egxbots_msgs_${roomB.id}`, JSON.stringify([{ role: "assistant", content: "نسخة محلية ب", timestamp: 2 }]));

  let resolveA!: (value: unknown) => void;
  let resolveB!: (value: unknown) => void;
  (fetch as jest.Mock)
    .mockResolvedValueOnce(accessResponse([roomA, roomB]))
    .mockImplementationOnce(() => new Promise(resolve => { resolveA = resolve; }))
    .mockImplementationOnce(() => new Promise(resolve => { resolveB = resolve; }));

  await act(async () => { render(tree()); });
  await waitFor(() => expect(chat.activeSessionId).toBe(roomA.id));
  let firstA!: Promise<void>;
  let secondA!: Promise<void>;
  await act(async () => {
    firstA = chat.switchSession(roomA.id);
    secondA = chat.switchSession(roomA.id);
  });
  expect((fetch as jest.Mock).mock.calls.filter(([url]) => url.includes(`session_id=${roomA.id}`))).toHaveLength(1);

  let pendingB!: Promise<void>;
  await act(async () => { pendingB = chat.switchSession(roomB.id); });
  expect(chat.messages.map(({ content }) => content)).toEqual(["نسخة محلية ب"]);

  await act(async () => {
    resolveA(historyResponse("رد متأخر من أ"));
    await Promise.all([firstA, secondA]);
  });
  expect(chat.activeSessionId).toBe(roomB.id);
  expect(chat.messages.map(({ content }) => content)).toEqual(["نسخة محلية ب"]);

  await act(async () => {
    resolveB(historyResponse("تاريخ ب من الخادم"));
    await pendingB;
  });
  expect(chat.messages.map(({ content }) => content)).toEqual(["تاريخ ب من الخادم"]);
});
