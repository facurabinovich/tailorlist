import streamlit as st
from config import PAGE_CONFIG
st.set_page_config(**PAGE_CONFIG)
from ui.theme import inject_global_css, spotify_icon_html, page_brand_html
from ui.nav import inject_sidebar_nav, check_collection_mode
from core.glossary import search_terms, group_by_section
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


filtered = search_terms(search)

if not filtered:
    st.info("No terms found. Try a different search.")
else:
    sections = group_by_section(filtered)

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
