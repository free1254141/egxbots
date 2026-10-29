/** @jest-environment jsdom */
import React from 'react';
import { act, cleanup, render } from '@testing-library/react';
import { ChatProvider, useChat } from '../ChatContext';

let mockAuth: { user: { id: string } | null; loading: boolean };
jest.mock('@/contexts/AuthContext', () => ({ useAuth: () => mockAuth }));

let chat: ReturnType<typeof useChat>;
function Probe() {
  chat = useChat();
  return null;
}
const tree = () => (
  <ChatProvider>
    <Probe />
  </ChatProvider>
);

const sessionsResponse = (opts: { isPro?: boolean; autonomous?: boolean; quota?: number } = {}) => ({
  ok: true,
  json: async () => ({
    sessions: [],
    remaining_quota: opts.quota ?? 350,
    quota_limit: 350,
    is_pro: opts.isPro ?? true,
    autonomous_recommendations: opts.autonomous ?? true,
  }),
});

beforeEach(() => {
  localStorage.clear();
  mockAuth = { user: null, loading: false };
  global.fetch = jest.fn();
});

afterEach(cleanup);

test('loads persistent autonomous recommendations from Supabase sessions response for Pro users', async () => {
  mockAuth = { user: { id: 'pro-user-1' }, loading: false };
  (global.fetch as jest.Mock).mockResolvedValueOnce(sessionsResponse({ isPro: true, autonomous: true }));

  await act(async () => {
    render(tree());
  });

  expect(chat.isAccessReady).toBe(true);
  expect(chat.isPro).toBe(true);
  expect(chat.autonomousRecommendations).toBe(true);
  expect(localStorage.getItem('artoro_autonomous_recs_enabled')).toBe('true');
});

test('persists autonomous recommendations to Supabase via /api/ai-chat?action=settings when toggled', async () => {
  mockAuth = { user: { id: 'pro-user-1' }, loading: false };
  (global.fetch as jest.Mock)
    .mockResolvedValueOnce(sessionsResponse({ isPro: true, autonomous: false }))
    .mockResolvedValueOnce({ ok: true, json: async () => ({ ok: true, autonomous_recommendations: true }) });

  await act(async () => {
    render(tree());
  });

  expect(chat.autonomousRecommendations).toBe(false);

  await act(async () => {
    chat.setAutonomousRecommendations(true);
  });

  expect(chat.autonomousRecommendations).toBe(true);
  expect(localStorage.getItem('artoro_autonomous_recs_enabled')).toBe('true');

  expect(global.fetch).toHaveBeenCalledWith(
    '/api/ai-chat?action=settings',
    expect.objectContaining({
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'update_settings', autonomous_recommendations: true }),
    })
  );
});

test('does not enable autonomous mode if the user is not Pro even if setting was true in storage', async () => {
  mockAuth = { user: { id: 'free-user-1' }, loading: false };
  (global.fetch as jest.Mock).mockResolvedValueOnce(sessionsResponse({ isPro: false, autonomous: true }));

  await act(async () => {
    render(tree());
  });

  expect(chat.isAccessReady).toBe(true);
  expect(chat.isPro).toBe(false);
  expect(chat.autonomousRecommendations).toBe(false);
});
