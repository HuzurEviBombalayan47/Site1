                asset_key = (
                    candidate.get(
                        "provider",
                        "",
                    ),
                    normalized_url,
                )

                if asset_key in used_asset_keys:
                    continue

                if not _validate(url):
                    continue

                used_urls.add(
                    normalized_url
                )

                used_asset_keys.add(
                    asset_key
                )

                return {
                    **candidate,
                    "query_used": query,
                }
