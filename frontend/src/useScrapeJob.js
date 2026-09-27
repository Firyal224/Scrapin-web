import { useCallback, useEffect, useRef, useState } from "react";
import { createJob, getJob } from "./api.js";

const POLL_MS = 1500;
const MAX_POLL_ERRORS = 5;

export function useScrapeJob({ onDone, onFail }) {
  const [job, setJob] = useState(null);
  const timer = useRef(null);
  const callbacks = useRef({ onDone, onFail });
  callbacks.current = { onDone, onFail };

  const stop = () => clearTimeout(timer.current);
  useEffect(() => stop, []);

  const poll = useCallback((id, errors = 0) => {
    timer.current = setTimeout(async () => {
      try {
        const next = await getJob(id);
        setJob(next);
        if (next.status === "done") callbacks.current.onDone(next);
        else if (next.status === "failed") callbacks.current.onFail(next.error);
        else poll(id);
      } catch (error) {
        if (errors + 1 >= MAX_POLL_ERRORS || error.status === 404) {
          setJob((prev) => prev && { ...prev, status: "failed", error: error.message });
          callbacks.current.onFail(error.message);
        } else {
          poll(id, errors + 1);
        }
      }
    }, POLL_MS);
  }, []);

  const start = useCallback(
    async (params) => {
      stop();
      const created = await createJob(params);
      setJob(created);
      poll(created.id);
      return created;
    },
    [poll]
  );

  const reset = useCallback(() => {
    stop();
    setJob(null);
  }, []);

  return { job, start, reset };
}
