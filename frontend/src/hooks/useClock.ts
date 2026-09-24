import { useEffect, useState } from "react";
export function useClock() {
  const [value, setValue] = useState(() =>
    new Date().toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }),
  );
  useEffect(() => {
    const timer = setInterval(
      () =>
        setValue(
          new Date().toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
            hour12: false,
          }),
        ),
      1000,
    );
    return () => clearInterval(timer);
  }, []);
  return value;
}
