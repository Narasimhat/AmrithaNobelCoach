import streamlit as st
from math import sin, cos, radians

def _leaf(svg_parts, x, y, scale=1.0, color="#34d399"):
    svg_parts.append(
        f'<ellipse cx="{x}" cy="{y}" rx="{10*scale}" ry="{18*scale}" fill="{color}" opacity="0.95"/>'
    )

def _flower(svg_parts, x, y, scale=1.0, color="#f472b6"):
    for a in [0,72,144,216,288]:
        rx = x + 10*scale*cos(radians(a))
        ry = y + 10*scale*sin(radians(a))
        svg_parts.append(f'<circle cx="{rx}" cy="{ry}" r="{5*scale}" fill="{color}" opacity="0.9"/>')
    svg_parts.append(f'<circle cx="{x}" cy="{y}" r="{4*scale}" fill="#fde68a"/>')

def _fruit(svg_parts, x, y, scale=1.0, color="#fb7185"):
    svg_parts.append(f'<circle cx="{x}" cy="{y}" r="{8*scale}" fill="{color}" opacity="0.95"/>')

def render_curiosity_tree_svg(points:int, streak:int, missions:int, width=480, height=260):
    leaves = min(points // 20, 12)
    flowers = min(streak // 3, 5)
    fruit = min(missions // 2, 6)

    svg = [f'<svg viewBox="0 0 {width} {height}" width="100%" height="auto" '           f'xmlns="http://www.w3.org/2000/svg">']

    svg.append('<defs><radialGradient id="g" cx="50%" cy="0%" r="80%"><stop offset="0%" stop-color="#22d3ee22"/><stop offset="100%" stop-color="transparent"/></radialGradient></defs>')
    svg.append('<rect x="0" y="0" width="100%" height="100%" fill="url(#g)"/>')
    svg.append('<rect x="0" y="{h}" width="{w}" height="4" fill="#1f2937"/>'.format(w=width, h=height-12))

    svg.append('<rect x="236" y="110" width="8" height="120" fill="#7c4f28" opacity="0.9"/>')
    svg.append('<path d="M240,140 C220,130 200,120 180,110" stroke="#7c4f28" stroke-width="6" fill="none" opacity="0.9"/>')
    svg.append('<path d="M240,150 C260,140 280,130 300,115" stroke="#7c4f28" stroke-width="6" fill="none" opacity="0.9"/>')
    svg.append('<path d="M240,165 C220,165 200,155 185,145" stroke="#7c4f28" stroke-width="5" fill="none" opacity="0.9"/>')
    svg.append('<path d="M240,175 C260,175 280,165 295,155" stroke="#7c4f28" stroke-width="5" fill="none" opacity="0.9"/>')

    cx, cy, r = 240, 120, 60
    for i in range(leaves):
        angle = 20 + i * (320 / max(1, leaves))
        x = cx + r * cos(radians(angle))
        y = cy + r * sin(radians(angle))
        _leaf(svg, x, y, scale=1.0)

    for i in range(flowers):
        angle = 60 + i * (220 / max(1, flowers))
        x = cx + (r-12) * cos(radians(angle))
        y = cy - 10 + (r-18) * sin(radians(angle))
        _flower(svg, x, y, scale=1.0)

    for i in range(fruit):
        angle = 200 + i * (120 / max(1, fruit))
        x = cx + (r-10) * cos(radians(angle))
        y = cy + 10 + (r-8) * sin(radians(angle))
        _fruit(svg, x, y, scale=1.0)

    svg.append(f'<text x="12" y="22" fill="#b8c2ff" font-size="12">Leaves (points): {points}</text>')
    svg.append(f'<text x="12" y="38" fill="#b8c2ff" font-size="12">Flowers (streak): {streak} days</text>')
    svg.append(f'<text x="12" y="54" fill="#b8c2ff" font-size="12">Fruit (missions): {missions}</text>')
    svg.append('</svg>')

    st.markdown('<div class="nc-card">', unsafe_allow_html=True)
    st.markdown("### 🌱 Curiosity Tree (SVG)")
    st.markdown("".join(svg), unsafe_allow_html=True)
    st.caption("Leaves grow with points, flowers with streak, fruit with missions.")
    st.markdown('</div>', unsafe_allow_html=True)
