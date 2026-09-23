import streamlit as st
import requests
import logging
logger = logging.getLogger(__name__)

st.title("Repository Reader")

st.subheader("Thêm repository mới")
new_repo_url = st.text_input("GitHub URL", key="new_repo_url")

if st.button("Ingest"):
    # st.spinner hiện icon xoay + text trong lúc chờ — vì ingest_repo() chạy
    # đồng bộ/block (chưa có async task queue), request này có thể mất
    # vài phút (clone + embed), không có spinner UI sẽ trông như bị treo.
    with st.spinner("Đang ingest repo (clone + embed)... có thể mất vài phút"):
        try:
            response = requests.post(
                "http://localhost:8000/repos",
                json={"url": new_repo_url},
            )
            # raise_for_status(): nếu response là 4xx/5xx (VD repo 0 file hợp lệ
            # → 500 từ guard đã thêm ở ingest_repo), hàm này tự raise exception
            # để rơi vào except bên dưới — không cần tự viết if response.status_code >= 400.
            response.raise_for_status()
            data = response.json()
            st.success(f"Ingest xong — repo_id = {data['repo_id']}")
        except Exception:
            logger.exception("Ingest request failed")
            st.error("Ingest thất bại — xem log terminal FastAPI để biết chi tiết.")

st.divider()  # kẻ 1 đường ngang, tách phần "ingest" và phần "hỏi-đáp" bên dưới

# #1: lấy danh sách repo đã ingest từ backend, để người dùng chọn theo URL
# thay vì phải tự nhớ repo_id (con số nội bộ, người dùng thường không biết).
try:
    repos = requests.get("http://localhost:8000/repos").json()
except Exception:
    logger.exception("Không lấy được danh sách repo")
    repos = []
    st.error("Không kết nối được tới server. Kiểm tra FastAPI đã chạy chưa.")

# Chỉ cho chọn repo đã ingest xong (status="ready") — tránh chọn nhầm repo
# đang "pending" (chưa có data) hoặc "failed" (lỗi lúc ingest).
ready_repos = [r for r in repos if r["status"] == "ready"]

if not ready_repos:
    st.warning("Chưa có repo nào sẵn sàng để hỏi. Hãy ingest 1 repo trước.")
else:
    # format_func: hiển thị field "url" cho người dùng thấy, nhưng selectbox
    # vẫn trả về nguyên object dict để lấy "id" dùng nội bộ.
    selected_repo = st.selectbox(
        "Chọn repository", options=ready_repos, format_func=lambda r: r["url"]
    )
    repo_id = selected_repo["id"]

    question = st.text_input("Your question")

    if st.button("Send"):
        try:
            response = requests.post(
                f"http://localhost:8000/repo/{repo_id}",
                json={"question": question},
            )
            data = response.json()

            # #2: hiển thị tự nhiên — answer là text sẵn, không cần dump cả object.
            st.subheader("Trả lời")
            st.write(data["answer"])

            st.subheader("Nguồn trích dẫn")
            for c in data["citations"]:
                st.write(f"- `{c['file']}` (dòng {c['start_line']}–{c['end_line']})")
        except Exception:
            logger.exception("Send request failed")
            st.error("Có lỗi khi gọi server — xem log terminal để biết chi tiết.")