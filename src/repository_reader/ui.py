import streamlit as st
import requests
import logging
import re
from pathlib import Path
from urllib.parse import quote
import os

logger = logging.getLogger(__name__)

API_BASE = os.environ.get("API_BASE", "http://localhost:8000")

# ================= Format citation trong cau tra loi (UX polish) =================
# Van de nguoi dung phat hien: model sinh citation THO ngay trong van ban,
# dang "[file:start-end]" (co the nhieu citation gop chung 1 ngoac vuong,
# vd "[README.md:44-51, README.md:94-102]") -- xem SYSTEM_INSTRUCTIONS o
# agent.py. Hien thi thang dang nay len UI vua roi mat vua kho doc, va o
# duoi muc "Nguon trich dan" truoc gio khong co gi (code cu bi comment,
# tham chieu toi data["citations"] -- key nay KHONG TON TAI trong response
# that cua app.py, response chi co "answer"/"repo_id"/"exhausted_budget").
#
# Giai phap: xu ly THUAN O UI (khong doi backend/agent.py) -- vi day la
# van de trinh bay, khong phai van de du lieu: du lieu can thiet (ten file +
# dong bat dau/ket thuc) da co san ngay trong chinh van ban answer.
_CITATION_BRACKET_RE = re.compile(r"\[([^\[\]]+)\]")
_CITATION_ITEM_RE = re.compile(r"^\s*([^,:\[\]]+?)\s*:\s*(\d+)\s*-\s*(\d+)\s*$")


def format_citations(answer: str) -> tuple[str, list[dict]]:
    """
    Bien doi citation tho trong answer thanh 2 thu:
      1. rendered_answer: cung noi dung answer, nhung moi cum citation duoc
         thay bang link so thu tu mau xanh "[1]", "[2]", ... giong citation
         trong paper hoc thuat -- moi link tro toi 1 anchor (#cite-n) trong
         danh sach nguon ben duoi.
      2. sources: list[dict] {"number", "file", "start", "end"} theo dung
         thu tu xuat hien LAN DAU trong answer -- dung de render muc "Nguon
         trich dan" ben duoi voi thong tin cu the (hien tai dang trong).

    Citation TRUNG NHAU (cung file + cung dong) duoc GOP thanh 1 so duy
    nhat, khong tao 2 muc giong het nhau trong danh sach nguon.

    Neu 1 cum trong ngoac vuong KHONG khop dung dang "file:start-end" (vd
    nguoi dung/model dung [] cho muc dich khac trong van ban), giu nguyen
    khong dong vao -- tranh lam hong noi dung khong lien quan toi citation.
    """
    seen: dict[tuple[str, str, str], int] = {}
    sources: list[dict] = []

    def _replace_bracket(match: "re.Match") -> str:
        raw_items = [p.strip() for p in match.group(1).split(",")]
        parsed = [_CITATION_ITEM_RE.match(item) for item in raw_items]
        if not raw_items or any(p is None for p in parsed):
            return match.group(0)

        links = []
        for p in parsed:
            file_, start, end = p.group(1), p.group(2), p.group(3)
            key = (file_, start, end)
            if key not in seen:
                number = len(sources) + 1
                seen[key] = number
                sources.append(
                    {"number": number, "file": file_, "start": start, "end": end}
                )
            number = seen[key]
            links.append(
                f'<a href="#cite-{number}" class="citation-link">[{number}]</a>'
            )
        return "".join(links)

    rendered = _CITATION_BRACKET_RE.sub(_replace_bracket, answer)
    return rendered, sources


# ================= Link truc tiep toi file tren GitHub (UX polish) =================
# Van de nguoi dung phat hien: trong muc "Nguon trich dan", ten file hien
# thi dang text thuong (vd "README.md", ".\demo_viper\demo.m") -- khong
# bam vao dau duoc. Muon: bam vao mo THANG file do.
#
# Da can nhac "mo file cuc bo tren may" (repo da duoc clone that o
# cloned_repos/{repo_id}/...) nhung KHONG chon huong nay: trinh duyet chan
# dieu huong toi link file:// tu 1 trang http:// vi ly do bao mat (khong
# dam bao hoat dong), va du co mo duoc cung chi hien text tho, khong phai
# trinh xem code that. Chon huong TOT HON: link thang toi dung file + dong
# tren GitHub (repo goc nguoi dung da nhap URL) -- GitHub ho tro san
# "#L{start}-L{end}" de highlight dung khoang dong, hoat dong moi noi
# (khong phu thuoc may nao dang chay UI).
#
# 2 kho khan thuc te da xu ly:
# 1. Can biet dung NHANH MAC DINH (main/master/...) cua repo -- khong the
#    doan, nen them buoc luu lai luc ingest (xem ingest.get_default_branch()
#    + cot moi Repo.default_branch). Repo da ingest TRUOC thay doi nay se
#    khong co link cho toi khi duoc ingest lai.
# 2. "file" trong citation KHONG CO dinh dang thong nhat: search_semantic/
#    search_exact tra ve full path dang "cloned_repos/13/README.md" (tu
#    ingest.py), con read_file thi ECHO LAI nguyen path model tu go luc
#    goi tool (vd "README.md" hoac ".\demo_viper\demo.m", vi model duoc
#    phep goi read_file voi path tuong doi) -- 3 dang khac nhau cho CUNG 1
#    file that. normalize_citation_path() gom ca 3 truong hop nay ve 1
#    dang path tuong doi thong nhat (dung "/" , khong tien to thua) truoc
#    khi dung de xay URL.
def normalize_citation_path(raw_path: str, repo_id: int) -> str:
    """Chuan hoa 1 duong dan file lay tu citation tho ve dang tuong doi so
    voi goc repo (vd "demo_viper/demo.m"), bat ke no den tu tool nao."""
    cleaned = raw_path.strip().replace("\\", "/")

    # Truong hop search_semantic/search_exact: full path co tien to
    # "cloned_repos/{repo_id}/" (xem ingest.py chunk_file/_search_exact).
    clone_prefix = f"cloned_repos/{repo_id}/"
    if cleaned.startswith(clone_prefix):
        cleaned = cleaned[len(clone_prefix) :]

    # Truong hop read_file: model co the tu them "./" o dau path.
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]

    return cleaned.lstrip("/")


def github_file_url(
    repo_url: str, default_branch, file_path: str, start: str, end: str
):
    """Xay URL GitHub tro thang toi file + highlight dung khoang dong.
    Tra ve None neu chua biet default_branch (repo ingest truoc khi co
    field nay) hoac file_path rong sau khi chuan hoa -- ui.py se tu hien
    text thuong (khong link) trong 2 truong hop nay, khong bao gio dua ra
    1 URL sai/doan bua."""
    if not default_branch or not file_path:
        return None
    # quote tung doan path rieng (giu nguyen dau "/") -- xu ly dung khi
    # ten file/thu muc co khoang trang hoac ky tu dac biet.
    quoted_path = "/".join(
        quote(segment) for segment in file_path.split("/") if segment
    )
    if not quoted_path:
        return None
    return f"{repo_url.rstrip('/')}/blob/{default_branch}/{quoted_path}#L{start}-L{end}"


def citation_file_exists(repo_id: int, normalized_path: str) -> bool:
    """Phong thu truoc citation BIA: kiem tra file duoc trich dan co THAT
    SU ton tai trong ban clone cuc bo cua repo khong, TRUOC khi coi no la
    1 nguon hop le.

    Ly do can ham nay -- bug thuc te da gap: SYSTEM_INSTRUCTIONS (agent.py)
    bat model LUON trich dan dang [file:start-end], nhung list_repo_structure
    tra ve cay thu muc (khong phai noi dung 1 file that) -- khi model dua
    cau tra loi tren thong tin nay, no bi ep phai "co" 1 citation nen tu
    dien ten TOOL ("list_repo_structure") vao cho "file", ra citation gia
    hoan toan -- click vao chac chan 404 tren GitHub. Da vá goc o
    SYSTEM_INSTRUCTIONS (day model khong duoc lam vay nua), nhung day la
    lop phong thu THEM o UI -- ke ca model lo bia sai kieu khac trong
    tuong lai, UI se khong bao gio bien no thanh 1 link nom na "chac chan
    loi" nhu nguoi dung da gap.

    Gia dinh: ui.py (Streamlit) va app.py (FastAPI) chay tu CUNG 1 thu muc
    goc project, giong het gia dinh CLONE_BASE_DIR = Path("cloned_repos")
    da dung xuyen suot ingest.py/tools.py.
    """
    if not normalized_path:
        return False
    candidate = Path("cloned_repos") / str(repo_id) / normalized_path
    return candidate.is_file()


st.title("Repository Reader")

# ================= Track 4 muc 1 (Auth) -- Part D =================
# Streamlit rerun TOAN BO script moi lan tuong tac (da hoc o Track 3 muc
# 7) -- token KHONG the luu trong bien Python thuong (se bi mat moi lan
# rerun), bat buoc luu trong st.session_state -- ton tai xuyen suot
# session trinh duyet cua nguoi dung, khong bi reset giua cac lan rerun.

if "token" not in st.session_state:
    st.session_state.token = None
    st.session_state.username = None


def auth_headers() -> dict:
    """Header dinh kem vao MOI request can dang nhap -- 1 ham dung chung,
    tranh viet lap lai {"Authorization": f"Bearer {...}"} o nhieu cho
    khac nhau trong file."""
    return {"Authorization": f"Bearer {st.session_state.token}"}


if st.session_state.token is None:
    # ---- Chua dang nhap: chi hien 2 form Dang nhap/Dang ky, chan het phan con lai ----
    st.subheader("Dang nhap de su dung Repository Reader")

    tab_login, tab_signup = st.tabs(["Dang nhap", "Dang ky tai khoan moi"])

    with tab_login:
        login_username = st.text_input("Username", key="login_username")
        login_password = st.text_input(
            "Password", type="password", key="login_password"
        )
        if st.button("Dang nhap", key="login_button"):
            try:
                # OAuth2PasswordRequestForm o server doc du lieu dang FORM
                # (khong phai JSON) -- requests.post(..., data=...) tu gui
                # dung Content-Type: application/x-www-form-urlencoded,
                # khop voi nhung gi /login mong doi.
                response = requests.post(
                    f"{API_BASE}/login",
                    data={"username": login_username, "password": login_password},
                )
                response.raise_for_status()
                token_data = response.json()
                st.session_state.token = token_data["access_token"]
                st.session_state.username = login_username
                st.rerun()  # chay lai script tu dau -- lan nay da co token, se hien UI chinh
            except Exception:
                logger.exception("Login failed")
                st.error("Sai username/password, hoac tai khoan chua ton tai.")

    with tab_signup:
        signup_username = st.text_input("Username", key="signup_username")
        signup_password = st.text_input(
            "Password", type="password", key="signup_password"
        )
        if st.button("Dang ky", key="signup_button"):
            try:
                # /signup nhan JSON thuong (Pydantic SignupRequest), KHAC
                # han /login o tren (OAuth2PasswordRequestForm doc form).
                response = requests.post(
                    f"{API_BASE}/signup",
                    json={"username": signup_username, "password": signup_password},
                )
                response.raise_for_status()
                st.success(
                    "Tao tai khoan thanh cong -- qua tab 'Dang nhap' de tiep tuc."
                )
            except Exception:
                logger.exception("Signup failed")
                st.error("Dang ky that bai -- co the username da ton tai.")

    st.stop()  # dung han script tai day -- phan ben duoi (ingest/hoi-dap) KHONG chay khi chua dang nhap


# ---- Da dang nhap: hien phan con lai cua app, moi request deu dinh kem token ----
st.sidebar.write(f"Dang nhap: **{st.session_state.username}**")
if st.sidebar.button("Dang xuat"):
    st.session_state.token = None
    st.session_state.username = None
    st.rerun()

st.subheader("Thêm repository mới")
new_repo_url = st.text_input("GitHub URL", key="new_repo_url")

# Track 4 muc 3: luu task_id (KHONG con luu ket qua truc tiep) -- vi gio
# POST /repos tra ve NGAY task_id, chua co repo_id thuc su (worker rieng
# chua chay xong ingest). Bat buoc dung st.session_state (khong phai bien
# Python thuong) vi Streamlit rerun toan bo script moi lan tuong tac (xem
# giai thich o Track 4 muc 1 Part D, dau file).
if "ingest_task_id" not in st.session_state:
    st.session_state.ingest_task_id = None

if st.button("Ingest"):
    # Khong con can st.spinner boc quanh request nay nua -- request gio
    # CHI serialize tham so + day task vao Redis (broker) roi tra ve NGAY
    # (tinh bang mili-giay), khong con phai doi clone+chunk+embed (thuong
    # vai phut) ngay tai day nua.
    try:
        response = requests.post(
            f"{API_BASE}/repos",
            json={"url": new_repo_url},
            headers=auth_headers(),
        )
        # raise_for_status(): neu response la 4xx/5xx (vd 401 token het han),
        # ham nay tu raise exception de roi vao except ben duoi.
        response.raise_for_status()
        data = response.json()
        if data.get("task_id"):
            # Nhanh binh thuong (Celery bat, xem settings.use_celery_ingest) --
            # con lai poll nhu cu o block ben duoi.
            st.session_state.ingest_task_id = data["task_id"]
            st.rerun()  # rerun ngay de vao nhanh khoi "dang cho" ben duoi, khong can doi tuong tac tiep theo
        else:
            # Nhanh deploy free-tier (settings.use_celery_ingest=False o
            # backend) -- request nay vua CHAY XONG DONG BO het clone/chunk/
            # embed roi moi tra ve (khong co task de poll), nen bao thanh
            # cong NGAY, khong di qua fragment poll ben duoi.
            st.success(f"Ingest xong — repo_id = {data['repo_id']}")
            st.rerun(
                scope="app"
            )  # rerun ca trang de phan "Chon repository" doc lai GET /repos, thay repo moi
    except Exception:
        logger.exception("Ingest request failed")
        st.error(
            "Ingest thất bại — xem log terminal FastAPI, hoặc thử đăng xuất/đăng nhập lại nếu phiên đã hết hạn."
        )

if st.session_state.ingest_task_id:
    # st.fragment(run_every=...): CHI doan nay cua script duoc chay lai
    # dinh ky (2 giay/lan) -- KHAC han st.rerun() thu cong (Track 3 muc 7),
    # vi no khong lam rerun ca trang, chi rerun rieng ham nay. Day la cach
    # gan voi chuan production nhat ma van kha thi trong kien truc
    # Streamlit -- chuan production THAT (WebSocket/SSE, server tu day
    # trang thai ve client) khong lam duoc trong Streamlit.
    @st.fragment(run_every="2s")
    def poll_ingest_status():
        task_id = st.session_state.ingest_task_id
        if not task_id:
            return
        try:
            response = requests.get(
                f"{API_BASE}/tasks/{task_id}", headers=auth_headers()
            )
            response.raise_for_status()
            data = response.json()
        except Exception:
            logger.exception("Poll task status failed")
            st.error("Không kiểm tra được trạng thái ingest — thử tải lại trang.")
            return

        task_status = data["status"]
        if task_status in ("PENDING", "STARTED"):
            st.info(f"Đang ingest repo (clone + embed)... trạng thái: {task_status}")
        elif task_status == "SUCCESS":
            st.success(f"Ingest xong — repo_id = {data['repo_id']}")
            st.session_state.ingest_task_id = None
            # scope="app": mac dinh st.rerun() goi TU BEN TRONG 1 fragment
            # chi rerun rieng fragment do (giu nguyen phan con lai cua
            # trang khong doi). O day can rerun CA APP: phan "Chon
            # repository" ben duoi (nam NGOAI fragment nay) can doc lai
            # GET /repos de thay repo moi vua ready, va chinh cau `if`
            # bao quanh loi goi fragment nay cung can duoc chay lai de
            # NGUNG poll tiep (ingest_task_id da ve None).
            st.rerun(scope="app")
        elif task_status == "FAILURE":
            st.error(f"Ingest thất bại: {data.get('error')}")
            st.session_state.ingest_task_id = None
            st.rerun(scope="app")
        else:
            st.info(f"Trạng thái: {task_status}")

    poll_ingest_status()

st.divider()  # kẻ 1 đường ngang, tách phần "ingest" và phần "hỏi-đáp" bên dưới

# #1: lấy danh sách repo đã ingest từ backend, để người dùng chọn theo URL
# thay vì phải tự nhớ repo_id (con số nội bộ, người dùng thường không biết).
# Track 4 mục 1 Part D: kèm auth_headers() -- server giờ chỉ trả về repo
# của ĐÚNG user đang đăng nhập (db.list_repos(owner_id=...)).
try:
    response = requests.get(f"{API_BASE}/repos", headers=auth_headers())
    response.raise_for_status()
    repos = response.json()
except Exception:
    logger.exception("Không lấy được danh sách repo")
    repos = []
    st.error("Không kết nối được tới server, hoặc phiên đăng nhập đã hết hạn.")

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
                f"{API_BASE}/repo/{repo_id}",
                json={"question": question},
                headers=auth_headers(),
            )
            response.raise_for_status()
            data = response.json()

            # #2: hiển thị tự nhiên — answer là text sẵn, không cần dump cả object.
            st.subheader("Trả lời")

            # exhausted_budget=True: agent KHÔNG tự kết thúc sớm, câu trả lời
            # là kết quả của lượt ÉP trả lời sau khi hết vòng loop (xem
            # agent.py). Không chặn câu trả lời, chỉ cảnh báo nhẹ để người
            # dùng biết nên kiểm tra kỹ hơn / hỏi cụ thể hơn nếu cần.
            if data.get("exhausted_budget"):
                st.warning(
                    "Câu trả lời này có thể chưa đầy đủ — hệ thống đã thử "
                    "hết số vòng tìm kiếm cho phép trước khi trả lời. Nếu "
                    "chưa đúng ý, thử hỏi cụ thể/ngắn gọn hơn."
                )

            # Doi citation tho "[file:start-end]" trong answer thanh link so
            # thu tu mau xanh [1][2]... + 1 list chi tiet rieng ben duoi (xem
            # ham format_citations o dau file).
            rendered_answer, sources = format_citations(data["answer"])

            # unsafe_allow_html=True: BAT BUOC de <a href="#cite-n"> va CSS
            # ben duoi duoc render thanh the HTML that, khong bi hien thi
            # nguyen van dang text. Chi ap dung cho answer do model sinh ra
            # (da qua he thong prompt kiem soat), khong phai input tu do cua
            # nguoi dung -- an toan hon so voi echo thang input nguoi dung.
            st.markdown(
                "<style>"
                ".citation-link {color:#1a73e8; font-weight:600; text-decoration:none;}"
                ".citation-link:hover {text-decoration:underline;}"
                "</style>",
                unsafe_allow_html=True,
            )
            st.markdown(rendered_answer, unsafe_allow_html=True)

            st.subheader("Nguồn trích dẫn")
            if sources:
                # UX citation: moi dong gio la 1 link that toi dung file +
                # dong tren GitHub (xem giai thich chi tiet o
                # normalize_citation_path()/github_file_url() dau file) --
                # khong con la text tinh nhu truoc. Anchor "cite-{n}" van
                # giu de link so [n] trong cau tra loi nhay xuong dung day.
                for s in sources:
                    clean_path = normalize_citation_path(s["file"], repo_id)
                    label_html = (
                        f"<b>[{s['number']}]</b> <code>{clean_path}</code> "
                        f"— dòng {s['start']}–{s['end']}"
                    )
                    anchor_html = f'<a id="cite-{s["number"]}"></a>'

                    # UU TIEN kiem tra file co that khong TRUOC ca chuyen
                    # thieu default_branch -- citation gia (vd model dung
                    # ten tool "list_repo_structure" lam "file") thi DU CO
                    # default_branch cung khong duoc phep bien thanh link.
                    if not citation_file_exists(repo_id, clean_path):
                        row_html = (
                            f"{anchor_html}{label_html} "
                            f'<span style="opacity:0.7;">⚠️ không xác '
                            f"định được file nguồn này trong repo "
                            f"đã ingest — có thể model trích dẫn nhầm, "
                            f"không nên tin tưởng hoàn toàn.</span>"
                        )
                        st.markdown(row_html, unsafe_allow_html=True)
                        continue

                    link = github_file_url(
                        selected_repo["url"],
                        selected_repo.get("default_branch"),
                        clean_path,
                        s["start"],
                        s["end"],
                    )
                    if link:
                        row_html = (
                            f'{anchor_html}<a href="{link}" target="_blank" '
                            f'rel="noopener" class="citation-link">{label_html}</a>'
                        )
                    else:
                        # File co that, nhung repo nay ingest TRUOC khi co
                        # default_branch (chua ingest lai) -- khong doan
                        # URL, chi hien text + giai thich vi sao chua bam
                        # duoc.
                        row_html = (
                            f"{anchor_html}{label_html} "
                            f'<span style="opacity:0.6;">(ingest lại repo này '
                            f"để có link trực tiếp)</span>"
                        )
                    st.markdown(row_html, unsafe_allow_html=True)
            else:
                # Model co the tra loi ma khong trich dan duoc (vd "khong tim
                # thay thong tin") -- khong de trong khong giai thich gi.
                st.caption("Câu trả lời này không có trích dẫn cụ thể.")
        except Exception:
            logger.exception("Send request failed")
            st.error(
                "Có lỗi khi gọi server — repo có thể không tồn tại/không phải của bạn, hoặc phiên đăng nhập đã hết hạn."
            )
