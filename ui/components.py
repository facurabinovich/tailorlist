import streamlit as st


def cluster_card(rank: int, name: str, count: int, total: int,
                 energy: float, valence: float, danceability: float,
                 color: str, desc: str = "", feature_line: str = "") -> str:
    pct = count / total * 100 if total else 0
    badge = str(rank).zfill(2)
    desc_html = (
        f"<div style='color:#B3B3B3;font-size:0.78rem;margin-top:2px;'>{desc}</div>"
    ) if desc else ""
    return "".join([
        "<div style='background:#282828;border-radius:12px;padding:14px 18px;",
        "border:1px solid #333;margin-bottom:10px;'>",
        "<div style='display:flex;justify-content:space-between;align-items:center;'>",
        "<span style='color:#B3B3B3;font-size:0.85rem;font-weight:700;margin-right:10px;'>",
        badge + "</span>",
        "<span style='color:#FFFFFF;font-weight:700;font-size:0.95rem;flex:1;'>",
        name + "</span>",
        "<span style='color:" + color + ";font-weight:800;font-size:0.95rem;'>",
        str(count) + " tracks</span>",
        "</div>",
        desc_html,
        "<div style='margin-top:8px;background:#333;border-radius:4px;height:4px;'>",
        "<div style='width:" + f"{pct:.1f}" + "%;background:" + color,
        ";height:4px;border-radius:4px;'></div>",
        "</div>",
        "<div style='margin-top:6px;color:#B3B3B3;font-size:0.75rem;'>",
        feature_line if feature_line else f"Energy {energy:.2f} · Valence {valence:.2f} · Danceability {danceability:.2f} · {pct:.1f}% of selection",
        "</div>",
        "</div>",
    ])


def info_box(left_title: str, left_body: str,
             right_title: str = "", right_body: str = "") -> str:
    right = ""
    if right_title:
        right = "".join([
            "<div style='flex:1;min-width:200px;'>",
            "<span style='color:#B3B3B3;font-size:0.78rem;text-transform:uppercase;",
            "letter-spacing:0.06em;'>" + right_title + "</span>",
            "<p style='color:#FFFFFF;font-size:0.82rem;margin:4px 0 0;'>",
            right_body + "</p></div>",
        ])
    return "".join([
        "<div style='background:#1a1a1a;border:1px solid #333;border-radius:10px;",
        "padding:12px 16px;margin-bottom:16px;'>",
        "<div style='display:flex;gap:32px;flex-wrap:wrap;'>",
        "<div style='flex:1;min-width:200px;'>",
        "<span style='color:#B3B3B3;font-size:0.78rem;text-transform:uppercase;",
        "letter-spacing:0.06em;'>" + left_title + "</span>",
        "<p style='color:#FFFFFF;font-size:0.82rem;margin:4px 0 0;'>",
        left_body + "</p></div>",
        right,
        "</div></div>",
    ])


def hr(top: int = 24, bottom: int = 24) -> None:
    st.markdown(
        f"<hr style='border-color:#333;margin-top:{top}px;margin-bottom:{bottom}px;'>",
        unsafe_allow_html=True,
    )
