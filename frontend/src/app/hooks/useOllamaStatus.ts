import { useState, useEffect } from "react";
import { getOllamaHealth, type OllamaHealthResponse } from "../lib/api";

export function useOllamaStatus() {
  const [status, setStatus] = useState<OllamaHealthResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;

    async function checkHealth() {
      try {
        const data = await getOllamaHealth();
        if (mounted) {
          setStatus(data);
          setLoading(false);
        }
      } catch (error) {
        if (mounted) {
          setStatus({ available: false, models: [], base_url: "" });
          setLoading(false);
        }
      }
    }

    checkHealth();
    const interval = setInterval(checkHealth, 30000);

    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  return { status, loading };
}