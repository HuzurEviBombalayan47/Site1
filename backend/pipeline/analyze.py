def _resolve_one(
    queries,
    kinds,
    cache,
    diag,
    used_urls,
    used_asset_keys,
):
    for query in queries:
        for kind in kinds:
            results = _cached_search(
                kind,
                query,
                cache,
                diag,
            )

            for candidate in results:
                if not isinstance(candidate, dict):
                    continue

                url = str(
                    candidate.get("url", "") or ""
                ).strip()

                if not url:
                    continue

                normalized_url = _normalize_url(url)

                provider = str(
                    candidate.get("provider", "") or ""
                ).strip().lower()

                provider_id = str(
                    candidate.get("provider_asset_id", "") or ""
                ).strip()

                # Provider'ın gerçek asset ID'si varsa onu kullan.
                # Böylece aynı B-roll farklı CDN URL'siyle gelse bile
                # tekrar kullanılmaz.
                asset_identity = (
                    provider,
                    provider_id or normalized_url,
                )

                if asset_identity in used_asset_keys:
                    continue

                # Aynı URL'nin tekrar kullanılmasını da engelle.
                if normalized_url in used_urls:
                    continue

                if not _validate(url):
                    continue

                used_urls.add(
                    normalized_url
                )

                used_asset_keys.add(
                    asset_identity
                )

                return {
                    **candidate,
                    "query_used": query,
                    "asset_key": "|".join(
                        asset_identity
                    ),
                }

    return None
