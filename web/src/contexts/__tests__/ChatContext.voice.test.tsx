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

beforeEach(() => {
  localStorage.clear();
  mockAuth = { user: { id: "ba9c27e8-f62d-452f-8a29-dc77fd092207" }, loading: false };
  global.fetch = jest.fn();
});
afterEach(cleanup);

test("preserves user voice note permanent audio URL and duration when loading history from server", async () => {
  const voiceSession = session("voice-room-1", "2026-11-03T20:00:00Z");
  const testVoiceUrl = "https://gfcmaxbtscmizsakarvc.supabase.co/storage/v1/object/public/chat-audio/user_123/voice_room_1/test_mic.webm";

  (fetch as jest.Mock)
    .mockResolvedValueOnce(response({ sessions: [voiceSession], remaining_quota: 10 }))
    .mockResolvedValueOnce(response({
      history: [
        {
          id: "msg-user-1",
          role: "user",
          content: "فويس نود العميل المسجل بالمايك",
          timestamp: 1730664000000,
          isVoice: true,
          isVoiceNote: true,
          voiceAudioUrl: testVoiceUrl,
          voiceDuration: 18.5,
        },
        {
          id: "msg-asst-1",
          role: "assistant",
          content: "رد أرتورو الصوتي على العميل",
          timestamp: 1730664005000,
          isVoice: true,
          isVoiceNote: false,
          spokenText: "رد أرتورو الصوتي على العميل",
        }
      ]
    }));

  await act(async () => { render(tree()); });
  await waitFor(() => expect(chat.messages).toHaveLength(2));

  const userMsg = chat.messages[0];
  expect(userMsg.role).toBe("user");
  expect(userMsg.isVoiceNote).toBe(true);
  expect(userMsg.voiceAudioUrl).toBe(testVoiceUrl);
  expect(userMsg.voiceDuration).toBe(18.5);

  const localSaved = localStorage.getItem("egxbots_msgs_voice-room-1");
  expect(localSaved).toBeTruthy();
  const parsed = JSON.parse(localSaved!);
  expect(parsed[0].voiceAudioUrl).toBe(testVoiceUrl);
  expect(parsed[0].voiceDuration).toBe(18.5);
});

test("preserves existing local voiceAudioUrl when server returns partial history", async () => {
  const voiceSession = session("voice-room-2", "2026-11-03T21:00:00Z");
  const localVoiceUrl = "https://gfcmaxbtscmizsakarvc.supabase.co/storage/v1/object/public/chat-audio/user_123/voice_room_2/local_mic.webm";

  localStorage.setItem("egxbots_chat_sessions_v2", JSON.stringify([voiceSession]));
  localStorage.setItem("egxbots_msgs_voice-room-2", JSON.stringify([
    {
      role: "user",
      content: "تسجيل صوتي محلي",
      timestamp: 100,
      isVoice: true,
      isVoiceNote: true,
      voiceAudioUrl: localVoiceUrl,
      voiceDuration: 12.0
    }
  ]));

  // Server returns history where voiceAudioUrl is missing for some reason
  (fetch as jest.Mock)
    .mockResolvedValueOnce(response({ sessions: [voiceSession], remaining_quota: 10 }))
    .mockResolvedValueOnce(response({
      history: [
        {
          role: "user",
          content: "تسجيل صوتي محلي",
          timestamp: 100,
        }
      ]
    }));

  await act(async () => { render(tree()); });
  await waitFor(() => expect(chat.messages).toHaveLength(1));

  // localVoiceMap in fetchSessionMessages must safeguard the voiceAudioUrl!
  expect(chat.messages[0].voiceAudioUrl).toBe(localVoiceUrl);
  expect(chat.messages[0].voiceDuration).toBe(12.0);
});
