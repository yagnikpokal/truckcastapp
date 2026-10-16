import { useEffect, useRef, useState } from "react";
import { geocode } from "../api";
import type { Place, PlaceDraft } from "../types";

interface PlaceFieldProps {
  id: string;
  label: string;
  value: PlaceDraft;
  onChange: (value: PlaceDraft) => void;
}

export function PlaceField({ id, label, value, onChange }: PlaceFieldProps) {
  const [results, setResults] = useState<Place[]>([]);
  const [open, setOpen] = useState(false);
  const requestId = useRef(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const text = value.text.trim();
    if (value.place && value.place.label === value.text) {
      setResults([]);
      setOpen(false);
      return;
    }
    if (text.length < 2) {
      setResults([]);
      setOpen(false);
      return;
    }
    const current = ++requestId.current;
    const timer = window.setTimeout(async () => {
      try {
        const found = await geocode(text);
        if (current !== requestId.current) return;
        setResults(found);
        if (document.activeElement === inputRef.current && found.length > 0) setOpen(true);
      } catch {
        if (current === requestId.current) setResults([]);
      }
    }, 280);
    return () => window.clearTimeout(timer);
  }, [value.text, value.place]);

  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input
        ref={inputRef}
        id={id}
        value={value.text}
        autoComplete="off"
        placeholder="City, address, or lat, lon"
        onChange={(event) => onChange({ text: event.target.value, place: null })}
        onFocus={() => results.length > 0 && setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 160)}
      />
      {value.place && (
        <p className="resolved">
          {value.place.lat.toFixed(3)}, {value.place.lon.toFixed(3)}
        </p>
      )}
      {open && results.length > 0 && (
        <ul className="suggestions">
          {results.map((place) => (
            <li key={`${place.lat}-${place.lon}-${place.label}`}>
              <button
                type="button"
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => {
                  onChange({ text: place.label, place });
                  setOpen(false);
                }}
              >
                {place.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
