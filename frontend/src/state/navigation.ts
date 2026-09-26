export type NavigationContext = {
  resultId?: string;
  sourceResultIds?: string[];
  familyViewId?: string;
  linkId?: string;
  family?: string;
};

export function contextFromHash(): NavigationContext {
  const query = location.hash.split("?")[1] ?? "";
  const params = new URLSearchParams(query);
  return {
    ...(params.has("result_id") ? { resultId: params.get("result_id")! } : {}),
    sourceResultIds: params.getAll("source_result_id"),
    ...(params.has("family_view_id") ? { familyViewId: params.get("family_view_id")! } : {}),
    ...(params.has("link_id") ? { linkId: params.get("link_id")! } : {}),
    ...(params.has("family") ? { family: params.get("family")! } : {}),
  };
}
