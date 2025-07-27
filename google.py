import tkinter as tk
from tkinter import ttk, messagebox
import webbrowser
import feedparser
from datetime import datetime, timezone
import threading
import pyperclip
from difflib import SequenceMatcher
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from pytrends.request import TrendReq

# ====================== SETTINGS ======================

RSS_FEEDS = {
    "Hollywood": [
        "https://www.tmz.com/rss.xml",
        "https://www.etonline.com/news/rss",
	"https://variety.com/feed/",
	"https://www.hollywoodreporter.com/feed/",
    ],
    "Local News": [
        "https://abc7.com/feed/",
        "https://www.nbcnewyork.com/news/local/feed/",
    ],
    "Politics": [
        "https://www.politico.com/rss/politics08.xml",
        "https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml",
    ],
    "Sport": [
	"http://sports.espn.go.com/espn/rss/news",
	"https://rss.nytimes.com/services/xml/rss/nyt/Sports.xml",
	"https://feeds.foxnews.com/foxnews/sports",
	"https://www.cbssports.com/partners/feeds/rss/home_news",
    ],
    "Health": [
	"http://rss.cnn.com/rss/cnn_health.rss",
	"https://rss.nytimes.com/services/xml/rss/nyt/Health.xml",
	"https://www.wired.com/feed/rss",
	"http://feeds.feedburner.com/TechCrunch/",
    ],
    "California": [
	"http://www.latimes.com/local/rss2.0.xml",
    ],
    "New York": [
	"https://www.nbcnewyork.com/rss/local/",
    ],
    "San Francisco": [
	"https://abc7news.com/feed/",
    ],
    "Los Angeles": [
	"https://ktla.com/feed/",
    ],
    "US News": [
	"https://feeds.nbcnews.com/nbcnews/public/news",
	"https://abcnews.go.com/abcnews/topstories",
	"https://www.cbsnews.com/latest/rss/main",
	"https://rssfeeds.usatoday.com/usatoday-NewsTopStories",
	"http://rss.cnn.com/rss/cnn_topstories.rss",
	"https://feeds.npr.org/1001/rss.xml",
	"https://www.politico.com/rss/politics08.xml",
	"https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
    ],
}

KEYWORD_WEIGHTS = {
    "killed": 5, "explosion": 5, "Trump": 4, "shooting": 4, "fire": 3,
    "evacuated": 3, "crash": 3, "arrested": 2, "protest": 2, "scandal": 2
}

SOURCE_BONUS = {
    "cbsnews": 2, "nypost": 3, "ktla": 2, "nbcnews": 3, "abc": 2
}

def get_google_trends_us():
    try:
        pytrends = TrendReq(hl='en-US', tz=360)
        trends_df = pytrends.trending_searches(pn='united_states')
        return trends_df[0].tolist()
    except:
        return []

GOOGLE_TRENDS = get_google_trends_us()

# ====================== SCORING FUNCTIONS ======================

def get_minutes_ago(published):
    try:
        pub_dt = datetime(*published[:6], tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - pub_dt
        return int(delta.total_seconds() / 60)
    except Exception:
        return None

def keyword_score(title):
    return sum(KEYWORD_WEIGHTS.get(word.lower(), 0) for word in title.split())

def source_bonus_func(url):
    for key in SOURCE_BONUS:
        if key in url:
            return SOURCE_BONUS[key]
    return 0

def urgency_bonus(title):
    urgency_words = ["breaking", "urgent", "confirmed", "explosion"]
    return 5 if any(word.lower() in title.lower() for word in urgency_words) else 0

def cluster_score(title, all_titles):
    all_titles = list(set(all_titles))
    if len(all_titles) < 3:
        return 0
    vectorizer = TfidfVectorizer().fit_transform(all_titles)
    sim_matrix = cosine_similarity(vectorizer)
    idx = all_titles.index(title)
    similar_count = sum(1 for score in sim_matrix[idx] if score > 0.5)
    return 5 if similar_count >= 3 else 0

def google_trend_bonus(title):
    return 5 if any(trend.lower() in title.lower() for trend in GOOGLE_TRENDS) else 0

def compute_score(title, url, minutes_ago, all_titles):
    score = keyword_score(title)
    score += source_bonus_func(url)
    score += urgency_bonus(title)
    score += google_trend_bonus(title)
    score += cluster_score(title, all_titles)
    if minutes_ago is not None:
        if minutes_ago < 10:
            score += 10
        elif minutes_ago < 30:
            score += 5
        elif minutes_ago < 60:
            score += 2
    return score

# ====================== GUI APPLICATION ======================

class NewsStrikeScanner:
    def __init__(self, root):
        self.root = root
        self.root.title("NewsStrikeScanner - Aphura RankMax Tool")
        self.favorites = []

        self.tree = ttk.Treeview(root, columns=("Minutes Ago", "Published", "Title", "Link", "Score"), show="tree headings")
        self.tree.heading("#0", text="Category")
        for col in self.tree["columns"]:
            self.tree.heading(col, text=col)
            self.tree.column(col, anchor="w")
        self.tree.pack(fill=tk.BOTH, expand=True)

        self.tree.bind("<Double-1>", self.open_link)
        self.tree.bind("<Button-3>", self.copy_to_clipboard)

        ttk.Button(root, text="Scan Now", command=self.scan_feeds).pack(pady=3)
        ttk.Button(root, text="View Favorites", command=self.view_favorites).pack(pady=3)
        ttk.Button(root, text="Export Favorites", command=self.export_favorites).pack(pady=3)

        self.last_titles = []
        self.scan_feeds()
        self.schedule_auto_refresh()

    def open_link(self, event):
        selected_item = self.tree.selection()
        if selected_item:
            values = self.tree.item(selected_item[0])["values"]
            if len(values) >= 4:
                webbrowser.open(values[3])

    def copy_to_clipboard(self, event):
        selected_item = self.tree.selection()
        if selected_item:
            values = self.tree.item(selected_item[0])["values"]
            if len(values) >= 4:
                pyperclip.copy(f"{values[2]} - {values[3]}")
                messagebox.showinfo("Copied", "Title and link copied!")

    def schedule_auto_refresh(self):
        self.root.after(300000, self.refresh)

    def refresh(self):
        self.scan_feeds()
        self.schedule_auto_refresh()

    def scan_feeds(self):
        self.tree.delete(*self.tree.get_children())
        threading.Thread(target=self.fetch_news).start()

    def add_to_favorites(self, values):
        if values not in self.favorites:
            self.favorites.append(values)

    def view_favorites(self):
        fav_window = tk.Toplevel(self.root)
        fav_window.title("Favorites")
        fav_tree = ttk.Treeview(fav_window, columns=("Minutes Ago", "Published", "Title", "Link", "Score"), show="headings")
        for col in fav_tree["columns"]:
            fav_tree.heading(col, text=col)
            fav_tree.column(col, anchor="w")
        fav_tree.pack(fill=tk.BOTH, expand=True)
        for fav in self.favorites:
            fav_tree.insert("", "end", values=fav)

    def export_favorites(self):
        with open("favorites.txt", "w", encoding="utf-8") as f:
            for fav in self.favorites:
                f.write(f"{fav[2]} - {fav[3]}\n")
        messagebox.showinfo("Exported", "Favorites exported to favorites.txt!")

    def fetch_news(self):
        self.last_titles = []
        all_titles = []
        entries = []

        for category, feeds in RSS_FEEDS.items():
            for url in feeds:
                feed = feedparser.parse(url)
                for entry in feed.entries[:5]:
                    title = entry.title
                    if not self.is_duplicate(title):
                        all_titles.append(title)
                        entries.append((category, entry))

        category_nodes = {}
        for category in RSS_FEEDS.keys():
            category_nodes[category] = self.tree.insert("", "end", text=category, open=False)

        for category, entry in entries:
            title = entry.title
            published = entry.get("published_parsed") or entry.get("updated_parsed")
            minutes_ago = get_minutes_ago(published)
            score = compute_score(title, entry.link, minutes_ago, all_titles)
            published_str = datetime(*published[:6]).strftime('%a, %d %b %Y %H:%M:%S') if published else "Unknown"

            item = self.tree.insert(category_nodes[category], "end", values=(
                f"{minutes_ago} min ago" if minutes_ago is not None else "Unknown",
                published_str, title, entry.link, score))

            if google_trend_bonus(title) > 0:
                self.tree.item(item, tags=("trend",))
            elif score >= 20:
                self.tree.item(item, tags=("high",))
            elif score >= 10:
                self.tree.item(item, tags=("medium",))
            else:
                self.tree.item(item, tags=("low",))

            self.tree.tag_bind(item, "<Double-Button-1>", lambda e, val=self.tree.item(item)["values"]: self.add_to_favorites(val))

        self.tree.tag_configure("trend", background="#ccffff")  # light blue
        self.tree.tag_configure("high", background="#ffb3b3")
        self.tree.tag_configure("medium", background="#ffe0b3")
        self.tree.tag_configure("low", background="#e0ffe0")

    def is_duplicate(self, title):
        for t in self.last_titles:
            if SequenceMatcher(None, t, title).ratio() > 0.8:
                return True
        self.last_titles.append(title)
        return False

# ====================== MAIN ======================

if __name__ == "__main__":
    root = tk.Tk()
    app = NewsStrikeScanner(root)
    root.mainloop()

