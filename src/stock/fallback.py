from urllib.parse import urlencode


class PixabayProvider:
    name = "Pixabay"

    def __init__(self, settings, http, cache):
        self.s, self.http, self.cache = settings, http, cache

    def search(self, query):
        params = {
            "q": query[:100],
            "per_page": 12,
            "lang": "en",
            "video_type": "film",
            "safesearch": "true",
        }
        data = self.cache.get("pixabay", params, 86400)
        if data is None:
            data = self.http.request(
                "GET",
                "https://pixabay.com/api/videos/?"
                + urlencode(dict(params, key=self.s.keys["PIXABAY_API_KEY"])),
            )
            self.cache.put("pixabay", params, data)
        results = []
        for item in data.get("hits", []):
            files = [v for v in item.get("videos", {}).values() if v.get("url")]
            if not files:
                continue
            preview = min(files, key=lambda v: abs(max(v["width"], v["height"]) - 960))
            full = min(files, key=lambda v: abs(min(v["width"], v["height"]) - 1080))
            results.append(
                {
                    "provider": self.name,
                    "id": str(item["id"]),
                    "url": item["pageURL"],
                    "author": item.get("user", ""),
                    "license": "https://pixabay.com/service/license-summary/",
                    "provider_url": "https://pixabay.com",
                    "preview": preview["url"],
                    "download": full["url"],
                    "width": full["width"],
                    "height": full["height"],
                    "duration": item.get("duration", 0),
                }
            )
        return results
