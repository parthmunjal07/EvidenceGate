import {
  createContext,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  getDisplayTimeZone,
  TIME_ZONE_STORAGE_KEY,
  type DisplayTimeZone,
} from "../utils/formatting";

type TimeZoneValue = {
  zone: DisplayTimeZone;
  setZone: (zone: DisplayTimeZone) => void;
};
const TimeZoneContext = createContext<TimeZoneValue | null>(null);

export function TimeZoneProvider({ children }: { children: ReactNode }) {
  const [zone, setZoneState] = useState<DisplayTimeZone>(getDisplayTimeZone);
  const value = useMemo<TimeZoneValue>(
    () => ({
      zone,
      setZone: (next) => {
        localStorage.setItem(TIME_ZONE_STORAGE_KEY, next);
        setZoneState(next);
      },
    }),
    [zone],
  );
  return (
    <TimeZoneContext.Provider value={value}>
      {children}
    </TimeZoneContext.Provider>
  );
}

export function useTimeZone() {
  const value = useContext(TimeZoneContext);
  const [fallbackZone, setFallbackZone] =
    useState<DisplayTimeZone>(getDisplayTimeZone);
  const fallback = useMemo<TimeZoneValue>(
    () => ({
      zone: fallbackZone,
      setZone: (next) => {
        localStorage.setItem(TIME_ZONE_STORAGE_KEY, next);
        setFallbackZone(next);
      },
    }),
    [fallbackZone],
  );
  return value ?? fallback;
}
