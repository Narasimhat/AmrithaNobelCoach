
# Render a simple 'Curiosity Tree' progress using Streamlit native elements.
import streamlit as st

def render_curiosity_tree(points:int, streak:int, missions:int):
    st.markdown('### 🌱 Curiosity Tree')
    col1, col2, col3 = st.columns(3)
    with col1:
        st.caption('Points growth')
        st.progress(min(points % 100, 100) / 100.0)
    with col2:
        st.caption('Streak health')
        st.progress(min(streak, 30) / 30.0)
    with col3:
        st.caption('Missions this month')
        st.progress(min(missions, 20) / 20.0)
    st.caption('Leaves grow with points, flowers with streak, fruit with missions.')
