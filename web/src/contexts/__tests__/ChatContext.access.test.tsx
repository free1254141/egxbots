/** @jest-environment jsdom */
import React, { StrictMode } from 'react';
import { act, cleanup, render } from '@testing-library/react';
import { ChatProvider, useChat } from '../ChatContext';
let mockAuth: {user: {id:string} | null; loading: boolean};
jest.mock('@/contexts/AuthContext',()=>({useAuth:()=>mockAuth}));
let chat: ReturnType<typeof useChat>;
function Probe(){chat=useChat();return null;}
const tree=()=> <ChatProvider><Probe /></ChatProvider>;
const response=(quota=999)=>({ok:true,json:async()=>({sessions:[],remaining_quota:quota})});
beforeEach(()=>{localStorage.clear(); mockAuth={user:null,loading:true};global.fetch=jest.fn();});
afterEach(cleanup);
test('auth and quota loading are shared; same identity refresh does not refetch',async()=>{
 let resolve!: (r:any)=>void;
 (global.fetch as jest.Mock).mockReturnValue(new Promise(r=>{resolve=r;}));
 const view=render(tree());expect(chat.isInitializing).toBe(true);expect(fetch).not.toHaveBeenCalled();
 mockAuth={user:{id:'A'},loading:false};view.rerender(tree());
 expect(chat.isInitializing).toBe(true);expect(fetch).toHaveBeenCalledTimes(1);
 mockAuth={user:{id:'A'},loading:false};view.rerender(tree());expect(fetch).toHaveBeenCalledTimes(1);
 await act(async()=>{resolve(response());});
 expect(chat.isInitializing).toBe(false);expect(chat.remainingQuota).toBe(999);
 mockAuth={user:{id:'A'},loading:false};view.rerender(tree());expect(fetch).toHaveBeenCalledTimes(1);
});
test('StrictMode joins a pending account request instead of duplicating it',async()=>{
 mockAuth={user:{id:'A'},loading:false};let resolve!:(r:any)=>void;
 (fetch as jest.Mock).mockReturnValue(new Promise(r=>{resolve=r;}));
 render(<StrictMode>{tree()}</StrictMode>);expect(fetch).toHaveBeenCalledTimes(1);
 await act(async()=>{resolve(response());});expect(chat.isInitializing).toBe(false);
});
test('access errors stop loading and retry only on request',async()=>{
 mockAuth={user:{id:'A'},loading:false};(fetch as jest.Mock).mockResolvedValueOnce({ok:false}).mockResolvedValueOnce(response(3));
 await act(async()=>{render(tree());});expect(chat.accessError).toBe(true);expect(chat.isInitializing).toBe(false);
 await act(async()=>{chat.retryAccess();chat.retryAccess();});
 expect(fetch).toHaveBeenCalledTimes(2);expect(chat.accessError).toBe(false);expect(chat.remainingQuota).toBe(3);
});
test('an old account response cannot overwrite the current quota',async()=>{
 let resolveA!:(r:any)=>void;let resolveB!:(r:any)=>void;
 (fetch as jest.Mock).mockReturnValueOnce(new Promise(r=>{resolveA=r;})).mockReturnValueOnce(new Promise(r=>{resolveB=r;}));
 mockAuth={user:{id:'A'},loading:false};const view=render(tree());
 mockAuth={user:{id:'B'},loading:false};view.rerender(tree());
 await act(async()=>{resolveA(response(999));});expect(chat.isInitializing).toBe(true);
 await act(async()=>{resolveB(response(0));});expect(chat.remainingQuota).toBe(0);expect(chat.isInitializing).toBe(false);
});
test('confirmed guest requires no access request',()=>{
 mockAuth={user:null,loading:false};render(tree());expect(chat.isInitializing).toBe(false);expect(fetch).not.toHaveBeenCalled();
});

test('payment completion refreshes the shared quota without polling',async()=>{
 mockAuth={user:{id:'A'},loading:false};(fetch as jest.Mock).mockResolvedValueOnce(response(5)).mockResolvedValueOnce(response(999));
 await act(async()=>{render(tree());});expect(chat.remainingQuota).toBe(5);
 await act(async()=>{window.dispatchEvent(new Event('egx:entitlements-updated'));window.dispatchEvent(new Event('egx:entitlements-updated'));});
 expect(fetch).toHaveBeenCalledTimes(2);expect(chat.remainingQuota).toBe(999);
});
