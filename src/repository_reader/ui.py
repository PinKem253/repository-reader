import streamlit as st 
import requests
import logging 
logger = logging.getLogger(__name__)


st.title("Repository Reader")
question = st.text_input("Your question")


try: 
    if st.button("Send"):
        st.write(f"User asked: {question}")
        
        response = requests.post(
            "http://localhost:8000/repo/1",
            json={"question": question},
        )
        
        data = response.json()
        st.write(data)
except Exception as e:
    logger.exception(f"Send request failed")
    st.error("404")
        