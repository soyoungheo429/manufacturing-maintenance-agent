// API Gateway 연동 계층 — 역할분담서 Step 6/9 스펙
//   GET  /dashboard → dashboard_data Lambda
//   POST /refresh   → refresh Lambda (1분 쿨다운)
//   POST /order     → create_order Lambda
// .env에 VITE_API_GATEWAY_URL 설정 시 라이브 모드, 미설정 시 null 반환(목데이터 유지)

const API_BASE = import.meta.env?.VITE_API_GATEWAY_URL;

async function request(path, options) {
  if (!API_BASE) return null;
  const res = await fetch(`${API_BASE}${path}`, options);
  if (!res.ok) throw new Error(`API Gateway 응답 오류: ${res.status} (${path})`);
  return await res.json();
}

// GET /dashboard — 설비 현황/권고/발주 데이터 조회
export async function getDashboardData() {
  return request("/dashboard");
}

// POST /refresh — sensor_read Lambda 트리거 (서버측 1분 쿨다운)
// 429 응답이면 { cooldown: true, remaining } 반환 — 프론트 쿨다운을 서버 기준으로 동기화
export async function refreshData(userId = "default") {
  if (!API_BASE) return null;
  const res = await fetch(`${API_BASE}/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId }),
  });
  if (res.status === 429) {
    const body = await res.json().catch(() => ({}));
    return { cooldown: true, remaining: body.remaining ?? 60 };
  }
  if (!res.ok) throw new Error(`API Gateway 응답 오류: ${res.status} (/refresh)`);
  return await res.json();
}

// POST /order — 발주서 생성/승인 상태 변경
export async function createOrder(payload) {
  return request("/order", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

// ─── 인증 (Cognito 연동 전 목 구현) ─────────────────────────────
// 실제 연동 시: 이 함수만 Cognito InitiateAuth(SRP) 호출로 교체 (Amplify Auth.signIn 등)
const DEMO_ACCOUNTS = {
  operator: { password: "pnu2026!", role: "operator" },
  admin: { password: "pnu2026!", role: "admin" },
};

export async function authenticate(username, password) {
  await new Promise((r) => setTimeout(r, 600)); // 네트워크 지연 시뮬레이션
  const account = DEMO_ACCOUNTS[username.trim().toLowerCase()];
  if (!account || account.password !== password) {
    throw new Error("아이디 또는 비밀번호가 올바르지 않습니다.");
  }
  return { username: username.trim().toLowerCase(), role: account.role };
}
