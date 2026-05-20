import streamlit as st
from config import PAGE_CONFIG
st.set_page_config(**PAGE_CONFIG)
from utils import inject_global_css, inject_sidebar_nav, check_collection_mode, spotify_icon_html, page_brand_html
inject_global_css()
inject_sidebar_nav("Glossary")

st.markdown(page_brand_html(), unsafe_allow_html=True)
st.markdown(
    f"<div style='display:flex;align-items:center;gap:16px;padding:0.8rem 0;'>"
    f"{spotify_icon_html(36)}"
    f"<div>"
    f"<h1 style='color:#FFFFFF;margin:0;font-size:2rem;line-height:1.1;'>Glossary</h1>"
    f"<p style='color:#B3B3B3;font-size:0.9rem;margin:4px 0 0 0;'>"
    f"Definitions for every metric, chart, and concept used in this app."
    f"</p>"
    f"</div>"
    f"</div>"
    f"<hr style='border-color:#333;margin:0 0 1rem 0;'/>",
    unsafe_allow_html=True,
)

search = st.text_input("🔍 Search terms...", placeholder="e.g. valence, silhouette, popularity")

terms = [
    # ── Audio Features ───────────────────────────────────────────────────────
    {
        "term": "Audio Features",
        "section": "Audio Features",
        "definition": "Nine numerical attributes extracted for every track. Seven are normalized 0–1 (Energy, Acousticness, Valence, Danceability, Speechiness, Instrumentalness, Liveness); two use natural units (Loudness in dB, Tempo in BPM).",
        "used_in": ["Audio DNA", "My Clusters", "Playlist Detail"],
    },
    {
        "term": "Energy",
        "section": "Audio Features",
        "definition": "A measure from 0.0 to 1.0 representing intensity and activity. Energetic tracks feel fast, loud, and noisy. Death metal scores high; a Bach prelude scores low.",
        "used_in": ["Audio DNA", "My Clusters", "Playlist Detail"],
    },
    {
        "term": "Valence",
        "section": "Audio Features",
        "definition": "Spotify's measure of musical positiveness (0–1). High valence = happy, cheerful, euphoric. Low valence = sad, angry, tense. It forms the X-axis of the Mood Map.",
        "used_in": ["Audio DNA", "Playlist Detail"],
    },
    {
        "term": "Danceability",
        "section": "Audio Features",
        "definition": "How suitable a track is for dancing, based on tempo, rhythm stability, beat strength, and regularity. 0.0 = least danceable, 1.0 = most danceable.",
        "used_in": ["Audio DNA", "My Clusters"],
    },
    {
        "term": "Acousticness",
        "section": "Audio Features",
        "definition": "Confidence measure (0–1) of whether a track is acoustic. 1.0 = high confidence the track is acoustic.",
        "used_in": ["Audio DNA", "My Clusters"],
    },
    {
        "term": "Instrumentalness",
        "section": "Audio Features",
        "definition": "Probability that a track contains no vocals. A track with 10 guitars and a singer scores near 0 — it measures absence of voice, not presence of instruments. Values above 0.5 are considered instrumental; above 0.9 are confidently so.",
        "used_in": ["Audio DNA", "My Clusters"],
    },
    {
        "term": "Speechiness",
        "section": "Audio Features",
        "definition": "Detects spoken words in a track. Above 0.66 = probably entirely spoken word. 0.33–0.66 = may contain both music and speech (e.g. rap). Below 0.33 = most likely music.",
        "used_in": ["Audio DNA", "My Clusters"],
    },
    {
        "term": "Liveness",
        "section": "Audio Features",
        "definition": "Detects the presence of an audience. Values above 0.8 suggest the track was performed live.",
        "used_in": ["Audio DNA"],
    },
    {
        "term": "Loudness",
        "section": "Audio Features",
        "definition": "Overall loudness of a track in decibels (dB). Values typically range from -60 to 0 dB. Useful for comparing relative loudness across tracks.",
        "used_in": ["Audio DNA"],
    },
    {
        "term": "Tempo",
        "section": "Audio Features",
        "definition": "Estimated tempo in beats per minute (BPM). In radar charts, tempo is normalized to 0–1 (range 60–200 BPM) so it can be compared fairly against other 0–1 features.",
        "used_in": ["Audio DNA", "My Clusters"],
    },
    {
        "term": "speechiness_log",
        "section": "Audio Features",
        "definition": "Raw speechiness has a zero-spike distribution — most tracks score near 0, with a long tail of rap/spoken word tracks. Log-transforming it (log1p) compresses the tail and makes the feature more meaningful for KMeans distance calculations.",
        "used_in": ["My Clusters"],
    },

    # ── Popularity & Era ──────────────────────────────────────────────────────
    {
        "term": "Popularity",
        "section": "Popularity & Era",
        "definition": "A Spotify-computed score from 0–100 based on total play count and recency of streams. Reflects current global popularity, not personal listening history. A track can drop in popularity if it hasn't been streamed recently even if it was once a hit.",
        "used_in": ["Overview", "Playlist Detail", "Artist / Album"],
    },
    {
        "term": "Avg Popularity",
        "section": "Popularity & Era",
        "definition": "The average Spotify popularity score (0–100) across all unique tracks in the collection or selection.",
        "used_in": ["Overview", "Playlist Comparison"],
    },
    {
        "term": "Top Decade",
        "section": "Popularity & Era",
        "definition": "The decade (1970s, 1980s, etc.) with the most unique tracks in your collection, calculated via statistical mode on the decade column.",
        "used_in": ["Overview"],
    },
    {
        "term": "Median Era",
        "section": "Popularity & Era",
        "definition": "The median release year across all unique tracks. Half your tracks are older than this year, half are newer. More robust than mean (resistant to outliers) and more stable than mode.",
        "used_in": ["Overview"],
    },
    {
        "term": "Listening Age",
        "section": "Popularity & Era",
        "definition": "An estimate of your 'musical age' based on the median release year of your collection. Calculated by taking the median release year, subtracting 16 years (peak music formation age), and computing the difference from today. Example: median era 1994 → est. born 1978 → Listening Age 48 yrs.",
        "used_in": ["Overview"],
    },
    {
        "term": "Listening Span",
        "section": "Popularity & Era",
        "definition": "The number of years between the oldest and newest track in your collection by release year. Example: oldest 1939, newest 2026 → span 87 years.",
        "used_in": ["Overview"],
    },

    # ── Clustering ────────────────────────────────────────────────────────────
    {
        "term": "KMeans Clustering",
        "section": "Clustering",
        "definition": "The algorithm that groups your tracks. It finds K 'centroids' (imaginary average tracks) and assigns each song to its nearest centroid based on audio feature distances. Runs entirely in your browser session — your tracks never leave the app.",
        "used_in": ["My Clusters"],
    },
    {
        "term": "K (number of clusters)",
        "section": "Clustering",
        "definition": "How many groups to divide your music into. Too few (k=2) and everything gets lumped into broad buckets. Too many (k=10+) and clusters become hair-splitting distinctions. The app finds the optimal K automatically using the silhouette score.",
        "used_in": ["My Clusters"],
    },
    {
        "term": "Silhouette Score",
        "section": "Clustering",
        "definition": "A measure of clustering quality from -1 to 1. It asks: how similar is each track to its own cluster compared to neighbouring clusters? Higher = tighter, more distinct groups. Used to pick the optimal K automatically.",
        "used_in": ["My Clusters"],
    },
    {
        "term": "Elbow Method",
        "section": "Clustering",
        "definition": "A visual way to pick K by plotting inertia against K values. The 'elbow' is where adding more clusters stops meaningfully reducing inertia. Used alongside silhouette score as a secondary check.",
        "used_in": ["My Clusters"],
    },
    {
        "term": "Inertia",
        "section": "Clustering",
        "definition": "The sum of squared distances from each track to its cluster centroid. Lower inertia = tighter clusters. Always decreases as K increases — which is why inertia alone can't pick the best K.",
        "used_in": ["My Clusters"],
    },
    {
        "term": "PCA (Principal Component Analysis)",
        "section": "Clustering",
        "definition": "Compresses 6 audio dimensions into 2 axes so clusters can be visualized on a scatter plot. The percentage shown (e.g. PC1 42%) tells you how much of the original variance each axis captures. Higher combined % = more faithful 2D representation.",
        "used_in": ["My Clusters"],
    },
    {
        "term": "Unmatched Tracks",
        "section": "Clustering",
        "definition": "Tracks excluded from clustering because no audio features were found. They still exist in your collection and can be manually assigned to a cluster before exporting.",
        "used_in": ["My Clusters"],
    },
    {
        "term": "Done Tracks",
        "section": "Clustering",
        "definition": "Tracks you've marked as exported to a Spotify playlist. Hidden from future clustering runs so you can work through your collection in batches without re-processing the same tracks.",
        "used_in": ["My Clusters"],
    },

    # ── Charts & Visualizations ───────────────────────────────────────────────
    {
        "term": "Mood Map",
        "section": "Charts & Visualizations",
        "definition": "Scatter plot of Valence (X-axis) vs Energy (Y-axis), one dot per track. Divided into four quadrants: Happy (high valence, high energy), Turbulent (low valence, high energy), Peaceful (high valence, low energy), and Dark (low valence, low energy). Dot size reflects popularity.",
        "used_in": ["Audio DNA", "Playlist Detail"],
    },
    {
        "term": "Global Fingerprint",
        "section": "Charts & Visualizations",
        "definition": "Radar chart showing the average value of the 7 normalized features across the entire collection or selected playlists. Represents the mean sonic identity of a collection.",
        "used_in": ["Audio DNA"],
    },
    {
        "term": "Audio Fingerprint",
        "section": "Charts & Visualizations",
        "definition": "Radar chart of mean audio features (energy, valence, danceability, acousticness, speechiness, liveness, tempo) for a selected artist, album, or playlist. Shows the sonic character at a glance.",
        "used_in": ["Artist / Album", "Playlist Detail"],
    },
    {
        "term": "Pearson Correlation (r)",
        "section": "Charts & Visualizations",
        "definition": "Measure of linear relationship between two features, ranging from -1 to +1. The strongest in most collections is Energy × Loudness (~0.77): louder tracks tend to feel more energetic.",
        "used_in": ["Audio DNA"],
    },
    {
        "term": "Similar Playlists",
        "section": "Charts & Visualizations",
        "definition": "Ranked by Euclidean distance across audio feature averages (energy, acousticness, valence, danceability, instrumentalness, tempo — all normalized). A 100% match would mean identical audio profiles.",
        "used_in": ["Playlist Detail"],
    },
    {
        "term": "Playlist Growth",
        "section": "Charts & Visualizations",
        "definition": "Timeline of how many tracks were added per month. Reveals whether a playlist was curated gradually over time or assembled in one session. Playlists with a single bar were built all at once.",
        "used_in": ["Playlist Detail"],
    },
    {
        "term": "Release Timeline",
        "section": "Charts & Visualizations",
        "definition": "Horizontal bar chart of track count per release year. Shows whether you prefer an artist's early or recent work. In artist mode only.",
        "used_in": ["Artist / Album"],
    },
    {
        "term": "Playlist Distribution",
        "section": "Charts & Visualizations",
        "definition": "How an artist's or album's tracks are spread across your playlists. Only shown when tracks span more than one playlist.",
        "used_in": ["Artist / Album"],
    },

    # ── Genre Families ────────────────────────────────────────────────────────
    {
        "term": "Genre Families",
        "section": "Genre Families",
        "definition": (
            "Broad groupings that classify tracks by genre, used for filtering the track pool "
            "and as the basis for the 'By category' grouping mode. Each family is matched by "
            "checking whether any of its keywords appear as a substring in a track's Spotify "
            "genre tags — e.g. 'baroque pop' matches <b style='color:#FFFFFF;'>Pop</b> because "
            "'pop' is in it. Matching is checked in family order (Rock → Pop → Hip-Hop → "
            "Electronic → Jazz → Classical → Folk → Latin → Reggae); the first matching family "
            "wins. Tracks whose genre tags contain no recognised keyword are labelled "
            "<b style='color:#FFFFFF;'>Other</b>.<br><br>"
            "<b style='color:#FFFFFF;'>Rock</b> — rock · punk · metal · grunge · hardcore · emo · shoegaze<br>"
            "<b style='color:#FFFFFF;'>Pop</b> — pop <span style='color:#555555;font-size:0.82rem;'>"
            "(one keyword covers: baroque pop, indie pop, synth-pop, afropop, britpop, etc.)</span><br>"
            "<b style='color:#FFFFFF;'>Hip-Hop</b> — hip hop · rap · trap · drill · r&amp;b · soul · grime<br>"
            "<b style='color:#FFFFFF;'>Electronic</b> — electronic · edm · house · techno · trance · "
            "ambient · synthwave · disco · new wave · dubstep · drum and bass · electro · downtempo · "
            "chillwave · darkwave · cold wave · eurodance · italo<br>"
            "<b style='color:#FFFFFF;'>Jazz</b> — jazz · bebop · swing · blues · big band · boogie<br>"
            "<b style='color:#FFFFFF;'>Classical</b> — classical · opera · orchestra · chamber<br>"
            "<b style='color:#FFFFFF;'>Folk</b> — folk · acoustic · singer-songwriter · country · "
            "americana · bluegrass · newgrass · honky tonk<br>"
            "<b style='color:#FFFFFF;'>Latin</b> — latin · reggaeton · salsa · cumbia · bossa nova · "
            "bachata · tango · bolero · merengue · mariachi · ranchera · mpb · trova · soca · "
            "calypso · folklore · folclor · candombe · murga · villancico<br>"
            "<b style='color:#FFFFFF;'>Reggae</b> — reggae · dancehall · ska · ragga · riddim · dub"
        ),
        "used_in": ["My Clusters"],
    },
    {
        "term": "Other (genre)",
        "section": "Genre Families",
        "definition": (
            "A catch-all label for tracks whose Spotify genre tags contain none of the recognised "
            "family keywords. Common genres that land here include: adult standards, chanson, "
            "christmas, comedy, doo-wop, drone, easy listening, gospel, hi-nrg, new age, "
            "schlager, soundtrack, and many hyper-local or niche tags. These tracks still appear "
            "in the 'Other' filter bucket and can be manually assigned to a cluster after grouping."
        ),
        "used_in": ["My Clusters"],
    },
]

# Filter by search
if search:
    query = search.lower()
    filtered = [t for t in terms if
                query in t["term"].lower() or
                query in t["definition"].lower() or
                any(query in u.lower() for u in t["used_in"])]
else:
    filtered = terms

if not filtered:
    st.info("No terms found. Try a different search.")
else:
    # Group by section
    sections = {}
    for t in filtered:
        sections.setdefault(t["section"], []).append(t)

    for section_name, section_terms in sections.items():
        st.markdown(f"""
        <div style="margin-top:1.5rem;margin-bottom:0.5rem;">
          <span style="color:#1DB954;font-size:0.75rem;font-weight:700;
                       text-transform:uppercase;letter-spacing:1px;">
            {section_name}
          </span>
        </div>
        """, unsafe_allow_html=True)

        for t in section_terms:
            used_badges = "".join([
                f"<span style='background:#282828;color:#B3B3B3;font-size:0.7rem;"
                f"padding:2px 8px;border-radius:10px;margin-right:4px;'>{u}</span>"
                for u in t["used_in"]
            ])
            st.markdown(f"""
            <div style="background:#1a1a1a;border:1px solid #333;border-radius:10px;
                        padding:16px 20px;margin-bottom:10px;">
              <div style="display:flex;align-items:baseline;gap:12px;
                          flex-wrap:wrap;margin-bottom:8px;">
                <span style="color:#FFFFFF;font-size:1rem;font-weight:700;">
                  {t["term"]}
                </span>
                {used_badges}
              </div>
              <p style="color:#B3B3B3;font-size:0.88rem;line-height:1.6;margin:0;">
                {t["definition"]}
              </p>
            </div>
            """, unsafe_allow_html=True)
