import { useEffect, useState } from "react";

/**
 * Like useState, but remembered in this browser (localStorage) across visits.
 * The first render always uses `initial`, so server and browser HTML match;
 * the saved value is applied right after. Storage errors (private mode) are ignored.
 */
export function useStoredState<T>(key: string, initial: T) {
  const [value, setValue] = useState<T>(initial);

  useEffect(() => {
    try {
      const saved = localStorage.getItem(key);
      // Applying a saved preference after mount is the point of this hook.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      if (saved !== null) setValue(JSON.parse(saved) as T);
    } catch {}
  }, [key]);

  const update = (next: T) => {
    setValue(next);
    try {
      localStorage.setItem(key, JSON.stringify(next));
    } catch {}
  };

  return [value, update] as const;
}
