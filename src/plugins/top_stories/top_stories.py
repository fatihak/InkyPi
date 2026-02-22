from plugins.base_plugin.base_plugin import BasePlugin
from utils.http_client import get_http_session
import logging

logger = logging.getLogger(__name__)

HN_TOP_URL = "https://hacker-news.firebaseio.com/v0/{feed}stories.json"
HN_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{id}.json"
REDDIT_URL = "https://old.reddit.com/r/{subreddit}/top.json"

FEEDS = ["top", "new", "best"]


class TopStories(BasePlugin):

    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['feeds'] = FEEDS
        return template_params

    def generate_image(self, settings, device_config):
        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        source = settings.get("source", "hackernews")
        count = min(int(settings.get("count", 10)), 20)

        if source == "reddit":
            subreddit = settings.get("subreddit", "programming").strip().removeprefix("r/")
            stories, source_label = self._fetch_reddit(subreddit, count)
        else:
            feed = settings.get("feed", "top")
            stories, source_label = self._fetch_hackernews(feed, count)

        template_params = {
            "stories": stories,
            "source_label": source_label,
            "plugin_settings": settings,
        }

        return self.render_image(dimensions, "top_stories.html", "top_stories.css", template_params)

    def _fetch_hackernews(self, feed, count):
        session = get_http_session()
        try:
            resp = session.get(HN_TOP_URL.format(feed=feed), timeout=15)
            resp.raise_for_status()
            ids = resp.json()[:count]
        except Exception as e:
            logger.error("HN story list fetch failed: %s", e)
            return [], "Hacker News"

        stories = []
        for story_id in ids:
            try:
                resp = session.get(HN_ITEM_URL.format(id=story_id), timeout=10)
                resp.raise_for_status()
                item = resp.json()
                if item and item.get("title"):
                    stories.append({
                        "title": item.get("title", ""),
                        "score": item.get("score", 0),
                        "comments": item.get("descendants", 0),
                        "by": item.get("by", ""),
                    })
            except Exception as e:
                logger.error("HN item fetch failed for %s: %s", story_id, e)

        return stories, f"Hacker News – {feed.title()}"

    def _fetch_reddit(self, subreddit, count):
        session = get_http_session()
        try:
            resp = session.get(
                REDDIT_URL.format(subreddit=subreddit),
                params={"limit": count, "t": "day"},
                headers={
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "application/json, text/html, */*",
                    "Accept-Language": "en-US,en;q=0.9",
                },
                timeout=15,
            )
            resp.raise_for_status()
            posts = resp.json()["data"]["children"]
            stories = [
                {
                    "title": p["data"].get("title", ""),
                    "score": p["data"].get("score", 0),
                    "comments": p["data"].get("num_comments", 0),
                    "by": p["data"].get("author", ""),
                }
                for p in posts
            ]
            return stories, f"r/{subreddit}"
        except Exception as e:
            logger.error("Reddit fetch failed for r/%s: %s", subreddit, e)
            return [], f"r/{subreddit}"
