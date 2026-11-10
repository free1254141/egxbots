import { NextRequest } from "next/server";
import { GET, POST } from "../route";

describe("VIP Chat Proxy Route (Next.js -> Python Backend)", () => {
    const originalEnv = process.env;
    const originalFetch = global.fetch;

    beforeEach(() => {
        jest.clearAllMocks();
        process.env = {
            ...originalEnv,
            ADMIN_SECRET_KEY: "test_secret_123",
            PYTHON_BACKEND_URL: "http://127.0.0.1:8000",
        };
    });

    afterAll(() => {
        process.env = originalEnv;
        global.fetch = originalFetch;
    });

    test("proxies POST request to Python FastAPI backend with headers and body", async () => {
        const mockResponseData = {
            ok: true,
            reply: "تم الرد من المحرك البايثوني",
            cached: false,
        };

        const mockFetch = jest.fn().mockResolvedValue({
            status: 200,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => mockResponseData,
            arrayBuffer: async () => Buffer.from(JSON.stringify(mockResponseData)),
        });
        global.fetch = mockFetch;

        const req = new NextRequest("http://localhost:3000/api/telegram/vip-chat", {
            method: "POST",
            headers: {
                "content-type": "application/json",
                "x-admin-key": "test_secret_123",
                authorization: "Bearer test_token",
            },
            body: JSON.stringify({
                action: "chat",
                telegram_user_id: 12345678,
                message: "سهم فوري",
            }),
        });

        const res = await POST(req);
        expect(res.status).toBe(200);

        const data = await res.json();
        expect(data.ok).toBe(true);
        expect(data.reply).toBe("تم الرد من المحرك البايثوني");

        expect(mockFetch).toHaveBeenCalledTimes(1);
        const [targetUrl, init] = mockFetch.mock.calls[0];
        expect(targetUrl).toBe("http://127.0.0.1:8000/api/telegram/vip-chat");
        expect(init.method).toBe("POST");
        expect(init.headers.get("x-admin-key")).toBe("test_secret_123");
        expect(init.headers.get("authorization")).toBe("Bearer test_token");
        const bodyParsed = JSON.parse(Buffer.from(init.body).toString("utf-8"));
        expect(bodyParsed).toEqual({
            action: "chat",
            telegram_user_id: 12345678,
            message: "سهم فوري",
        });
    });

    test("proxies GET request with search query parameters to Python backend", async () => {
        const mockResponseData = { ok: true, status: "healthy" };

        const mockFetch = jest.fn().mockResolvedValue({
            status: 200,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => mockResponseData,
            arrayBuffer: async () => Buffer.from(JSON.stringify(mockResponseData)),
        });
        global.fetch = mockFetch;

        const req = new NextRequest("http://localhost:3000/api/telegram/vip-chat?check_quota=true&tg_id=123", {
            method: "GET",
            headers: {
                "x-admin-key": "test_secret_123",
            },
        });

        const res = await GET(req);
        expect(res.status).toBe(200);

        const data = await res.json();
        expect(data.ok).toBe(true);

        expect(mockFetch).toHaveBeenCalledTimes(1);
        const [targetUrl, init] = mockFetch.mock.calls[0];
        expect(targetUrl).toBe("http://127.0.0.1:8000/api/telegram/vip-chat?check_quota=true&tg_id=123");
        expect(init.method).toBe("GET");
    });

    test("passes through HTTP error status codes from Python backend", async () => {
        const mockFetch = jest.fn().mockResolvedValue({
            status: 403,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({ ok: false, error: "Unauthorized" }),
            arrayBuffer: async () => Buffer.from(JSON.stringify({ ok: false, error: "Unauthorized" })),
        });
        global.fetch = mockFetch;

        const req = new NextRequest("http://localhost:3000/api/telegram/vip-chat", {
            method: "POST",
            headers: {
                "content-type": "application/json",
            },
            body: JSON.stringify({ action: "chat" }),
        });

        const res = await POST(req);
        expect(res.status).toBe(403);
        const data = await res.json();
        expect(data.ok).toBe(false);
        expect(data.error).toBe("Unauthorized");
    });
});
