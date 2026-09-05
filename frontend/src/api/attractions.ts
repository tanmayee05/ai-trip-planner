import { api } from "@/lib/api";
import type { AttractionsResponse } from "@/types/api";

/** Every well-known place for a destination region (Gemini-curated,
 *  Nominatim-grounded). The user then picks which go into the itinerary. */
export function fetchAttractions(destination: string) {
  return api
    .post<AttractionsResponse>("/attractions", { destination })
    .then((r) => r.data);
}
