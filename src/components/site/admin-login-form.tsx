"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function AdminLoginForm() {
  const router = useRouter();
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    const response = await fetch("/api/admin/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    });
    setLoading(false);
    if (!response.ok) {
      setError("Token 不正确或服务端未配置 ADMIN_TOKEN");
      return;
    }
    router.push("/admin/news");
    router.refresh();
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <Input value={token} onChange={(event) => setToken(event.target.value)} placeholder="ADMIN_TOKEN" type="password" />
      {error ? <p className="text-sm text-red-600">{error}</p> : null}
      <Button className="w-full" type="submit" disabled={loading}>
        {loading ? "验证中" : "进入后台"}
      </Button>
    </form>
  );
}

