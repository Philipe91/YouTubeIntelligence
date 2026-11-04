"""YouTube falso para testes de integração: usa IDs fictícios e não acessa a rede."""
from __future__ import annotations

import json
from datetime import timedelta

import httpx


class FakeYouTube:
    def __init__(self, now, video_count=12):
        self.now = now
        self.calls: list[httpx.Request] = []
        self.fail_next: list[httpx.Response | Exception] = []
        self.views_multiplier = 1.0
        self.missing: set[str] = set()
        self.channel = {
            "id": "UCfake1",
            "snippet": {"title": "Canal Falso", "customUrl": "@falso", "country": "BR", "thumbnails": {"default": {"url": "http://t/c.jpg"}}},
            "statistics": {"subscriberCount": "50000", "viewCount": "1000000", "videoCount": str(video_count), "hiddenSubscriberCount": False},
            "contentDetails": {"relatedPlaylists": {"uploads": "UUfake1"}},
        }
        self.videos = {}
        for index in range(video_count):
            is_short = index % 2 == 0
            vid = f"vid{index:02d}"
            self.videos[vid] = {
                "id": vid,
                "snippet": {
                    "channelId": "UCfake1", "title": f"Roma antiga parte {index}", "description": "desc",
                    "publishedAt": (now - timedelta(days=30 + index)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "liveBroadcastContent": "none", "defaultAudioLanguage": "pt",
                    "thumbnails": {"medium": {"url": f"http://t/{vid}.jpg"}},
                },
                "contentDetails": {"duration": "PT45S" if is_short else "PT12M"},
                "player": {"embedWidth": "405", "embedHeight": "720"} if is_short else {"embedWidth": "1280", "embedHeight": "720"},
                "statistics": {"viewCount": str(1000 + index * 100), "likeCount": "10", "commentCount": "2"},
            }
        self.videos["vid00"]["statistics"]["viewCount"] = "50000"

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        if self.fail_next:
            failure = self.fail_next.pop(0)
            if isinstance(failure, Exception):
                raise failure
            return failure
        path = request.url.path
        params = request.url.params
        if path.endswith("/channels"):
            return self._json({"items": [self.channel]})
        if path.endswith("/playlistItems"):
            return self._json({"items": [{"contentDetails": {"videoId": v}} for v in self.videos]})
        if path.endswith("/search"):
            if params.get("type") == "channel":
                return self._json({"kind": "youtube#searchListResponse", "pageInfo": {"totalResults": 1, "resultsPerPage": 25},
                                   "items": [{"kind": "youtube#searchResult", "id": {"kind": "youtube#channel", "channelId": self.channel["id"]},
                                              "snippet": {"channelId": self.channel["id"], "publishedAt": "2020-01-01T00:00:00Z", "title": self.channel["snippet"]["title"]}}]})
            return self._json({"kind": "youtube#searchListResponse", "pageInfo": {"totalResults": 12345, "resultsPerPage": 50},
                               "items": [{"kind": "youtube#searchResult", "id": {"kind": "youtube#video", "videoId": v},
                                          "snippet": {"channelId": "UCfake1", "publishedAt": self.videos[v]["snippet"]["publishedAt"], "title": self.videos[v]["snippet"]["title"]}}
                                         for v in self.videos]})
        if path.endswith("/videos"):
            # Igual à documentação oficial: maxResults não combina com id.
            if "maxResults" in params and "id" in params:
                return error_response(400, "badRequest")
            ids = params["id"].split(",")
            items = []
            for vid in ids:
                if vid in self.videos and vid not in self.missing:
                    item = json.loads(json.dumps(self.videos[vid]))
                    if "viewCount" in item["statistics"]:
                        item["statistics"]["viewCount"] = str(int(int(item["statistics"]["viewCount"]) * self.views_multiplier))
                    items.append(item)
            return self._json({"items": items})
        return httpx.Response(404, json={"error": {"errors": [{"reason": "notFound"}]}})

    @staticmethod
    def _json(body) -> httpx.Response:
        return httpx.Response(200, json=body)


def error_response(status: int, reason: str, headers=None) -> httpx.Response:
    return httpx.Response(status, headers=headers, json={"error": {"code": status, "message": reason, "errors": [{"message": reason, "domain": "global", "reason": reason}]}})


# Corpos reais, capturados do Google em 04/11/2026 com `curl`, sem nenhuma chave válida.
REAL_INVALID_KEY = {"error": {"code": 400, "message": "API key not valid. Please pass a valid API key.",
                              "errors": [{"message": "API key not valid. Please pass a valid API key.", "domain": "global", "reason": "badRequest"}],
                              "status": "INVALID_ARGUMENT",
                              "details": [{"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": "API_KEY_INVALID", "domain": "googleapis.com", "metadata": {"service": "youtube.googleapis.com"}},
                                          {"@type": "type.googleapis.com/google.rpc.LocalizedMessage", "locale": "en-US", "message": "API key not valid. Please pass a valid API key."}]}}
REAL_NO_KEY = {"error": {"code": 403, "message": "Method doesn't allow unregistered callers (callers without established identity). Please use API Key or other form of API consumer identity to call this API.",
                         "errors": [{"message": "Method doesn't allow unregistered callers (callers without established identity). Please use API Key or other form of API consumer identity to call this API.", "domain": "global", "reason": "forbidden"}],
                         "status": "PERMISSION_DENIED"}}
