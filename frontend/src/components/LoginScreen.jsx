// 로그인 화면 — Cognito 연동 전 목 인증 (api/index.js의 authenticate 교체 지점)
import { useState } from "react";
import { Activity, Loader2, Lock, User } from "lucide-react";
import { authenticate } from "../api/index.js";

export default function LoginScreen({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (loading) return;
    setError("");
    setLoading(true);
    try {
      const user = await authenticate(username, password);
      onLogin(user);
    } catch (err) {
      setError(err instanceof Error ? err.message : "로그인에 실패했습니다.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="size-full flex items-center justify-center bg-background"
      style={{ fontFamily: "'Inter', sans-serif" }}
    >
      <div className="w-full max-w-sm px-6">
        <div className="flex flex-col items-center mb-8">
          <div className="w-12 h-12 rounded-xl bg-primary/20 border border-primary/30 flex items-center justify-center mb-3">
            <Activity size={22} className="text-primary" />
          </div>
          <h1 className="text-lg font-semibold text-foreground">예지보전 모니터링 시스템</h1>
          <span className="text-xs text-muted-foreground font-mono mt-1">
            Predictive Maintenance Dashboard
          </span>
        </div>

        <form onSubmit={handleSubmit} className="bg-card border border-border rounded-xl p-6 space-y-4">
          <div>
            <label className="text-xs text-muted-foreground block mb-1.5">아이디</label>
            <div className="relative">
              <User size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                className="w-full bg-white/5 border border-border rounded-lg pl-9 pr-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary/50 transition-colors"
                placeholder="operator 또는 admin"
              />
            </div>
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-1.5">비밀번호</label>
            <div className="relative">
              <Lock size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                className="w-full bg-white/5 border border-border rounded-lg pl-9 pr-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary/50 transition-colors"
                placeholder="••••••••"
              />
            </div>
          </div>

          {error && (
            <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/25 rounded-lg px-3 py-2">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading || !username || !password}
            className={`w-full flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-semibold transition-colors ${
              loading || !username || !password
                ? "bg-primary/10 text-primary/50 cursor-not-allowed"
                : "bg-primary/20 hover:bg-primary/30 text-primary border border-primary/30"
            }`}
          >
            {loading ? (
              <>
                <Loader2 size={14} className="animate-spin" />
                인증 중...
              </>
            ) : (
              "로그인"
            )}
          </button>

          <div className="pt-2 border-t border-border">
            <p className="text-[10px] text-muted-foreground font-mono leading-relaxed">
              데모 계정 — operator / pnu2026! (조회 전용)
              <br />
              admin / pnu2026! (발주 승인 권한)
              <br />
              실제 배포 시 Amazon Cognito User Pool 인증으로 교체
            </p>
          </div>
        </form>
      </div>
    </div>
  );
}
