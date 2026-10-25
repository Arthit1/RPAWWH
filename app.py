from datetime import datetime
from pathlib import Path
import asyncio
import sys
import streamlit as st
import shutil
import tempfile


# แก้ปัญหา Playwright ทำงานบน Streamlit + Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(
        asyncio.WindowsProactorEventLoopPolicy()
    )

from playwright.sync_api import (
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)


# ============================================================
# CONFIG
# ============================================================

LOGIN_URL = "https://ams.cpall.co.th/login.action"

# Folder สำหรับเก็บไฟล์ Export
DOWNLOAD_FOLDER = (
    Path(tempfile.gettempdir())
    / "ams_exports"
)

HEADLESS = True
DEFAULT_TIMEOUT = 15_000
LOGIN_TIMEOUT = 30_000
DOWNLOAD_TIMEOUT = 120_000


# ============================================================
# SELECTORS
# ============================================================

USERNAME_SELECTOR = "#username"
PASSWORD_SELECTOR = "#password"
LOGIN_BUTTON_SELECTOR = "button.button-login"

LOGIN_SUCCESS_SELECTOR = "#actionLocCode"
LOADING_POPUP_SELECTOR = "#ui-datepicker-div"

BRANCH_CODE_SELECTOR = "#actionLocCode"

BRANCH_SEARCH_SELECTOR = (
    'img.input-icon'
    '[onclick*="searchPopupCostCenter"]'
    '[onclick*="actionLocCode"]'
)

STATUS_SELECTOR = "#statusId"
STATUS_ALL_VALUE = " "

CHECKBOX_SELECTOR = "#isActive"

SEARCH_BUTTON_SELECTOR = (
    'input.button-login'
    '[type="button"]'
    '[value="ค้นหา"]'
)

EXPORT_BUTTON_SELECTOR = (
    'input.button-login'
    '[type="button"]'
    '[value="Export to excel"]'
)


# ============================================================
# WAIT FOR POPUP
# ============================================================

def wait_for_popup_hidden(page):
    popup = page.locator(
        LOADING_POPUP_SELECTOR
    ).first

    if popup.count() == 0:
        return

    try:
        if popup.is_visible():
            popup.wait_for(
                state="hidden",
                timeout=60_000,
            )

    except PlaywrightTimeoutError:
        raise RuntimeError(
            "Popup โหลดข้อมูลไม่หายภายในเวลาที่กำหนด"
        )


# ============================================================
# LOGIN
# ============================================================

def login_ams(
    page,
    username,
    password,
):
    page.goto(
        LOGIN_URL,
        wait_until="domcontentloaded",
        timeout=LOGIN_TIMEOUT,
    )

    username_input = page.locator(
        USERNAME_SELECTOR
    ).first

    password_input = page.locator(
        PASSWORD_SELECTOR
    ).first

    username_input.wait_for(
        state="visible",
        timeout=DEFAULT_TIMEOUT,
    )

    password_input.wait_for(
        state="visible",
        timeout=DEFAULT_TIMEOUT,
    )

    # Username
    username_input.click()
    username_input.fill("")
    username_input.type(
        username,
        delay=100,
    )
    username_input.press("Tab")

    # Password
    password_input.click()
    password_input.fill("")
    password_input.type(
        password,
        delay=100,
    )
    password_input.press("Tab")

    if not username_input.input_value():
        raise RuntimeError(
            "Username ไม่ถูกกรอกลงในเว็บไซต์"
        )

    if not password_input.input_value():
        raise RuntimeError(
            "Password ไม่ถูกกรอกลงในเว็บไซต์"
        )

    # Login
    page.locator(
        LOGIN_BUTTON_SELECTOR
    ).first.click()

    # ตรวจสอบว่าเข้าสู่หน้าค้นหาแล้ว
    try:
        page.locator(
            LOGIN_SUCCESS_SELECTOR
        ).first.wait_for(
            state="visible",
            timeout=LOGIN_TIMEOUT,
        )

    except PlaywrightTimeoutError:
        raise RuntimeError(
            "Login ไม่สำเร็จ หรือไม่พบหน้าค้นหา"
        )

    wait_for_popup_hidden(page)


# ============================================================
# SEARCH
# ============================================================

def search_documents(
    page,
    branch_code,
    search_delay,
):
    # กรอกรหัสสาขา
    branch_input = page.locator(
        BRANCH_CODE_SELECTOR
    ).first

    branch_input.wait_for(
        state="visible",
        timeout=DEFAULT_TIMEOUT,
    )

    branch_input.click()
    branch_input.fill("")
    branch_input.type(
        branch_code,
        delay=100,
    )

    branch_input.press("Tab")

    if branch_input.input_value() != branch_code:
        raise RuntimeError(
            "รหัสสาขาที่กรอกไม่ตรงกับค่าที่กำหนด"
        )

    # กดปุ่มค้นหารหัสสาขา
    branch_search = page.locator(
        BRANCH_SEARCH_SELECTOR
    ).first

    branch_search.wait_for(
        state="visible",
        timeout=DEFAULT_TIMEOUT,
    )

    branch_search.click()

    page.wait_for_timeout(2_000)

    wait_for_popup_hidden(page)

    # เลือกสถานะทั้งหมด
    status_dropdown = page.locator(
        STATUS_SELECTOR
    ).first

    status_dropdown.wait_for(
        state="visible",
        timeout=DEFAULT_TIMEOUT,
    )

    status_dropdown.select_option(
        value=STATUS_ALL_VALUE
    )

    # ยกเลิก Checkbox
    checkbox = page.locator(
        CHECKBOX_SELECTOR
    ).first

    checkbox.wait_for(
        state="visible",
        timeout=DEFAULT_TIMEOUT,
    )

    checkbox.uncheck()

    if checkbox.is_checked():
        raise RuntimeError(
            "ไม่สามารถยกเลิก Checkbox ได้"
        )

    # กด Search
    search_button = page.locator(
        SEARCH_BUTTON_SELECTOR
    ).first

    search_button.wait_for(
        state="visible",
        timeout=DEFAULT_TIMEOUT,
    )

    search_button.click()

    # Delay หลัง Search ก่อน Export
    page.wait_for_timeout(
        search_delay * 1_000
    )

    wait_for_popup_hidden(page)


# ============================================================
# EXPORT
# ============================================================

def export_excel(page):
    DOWNLOAD_FOLDER.mkdir(
        parents=True,
        exist_ok=True,
    )

    export_button = page.locator(
        EXPORT_BUTTON_SELECTOR
    ).first

    export_button.wait_for(
        state="visible",
        timeout=DEFAULT_TIMEOUT,
    )

    with page.expect_download(
        timeout=DOWNLOAD_TIMEOUT
    ) as download_info:

        export_button.click()

    download = download_info.value

    original_filename = Path(
        download.suggested_filename
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    extension = (
        original_filename.suffix or ".xlsx"
    )

    filename = (
        f"{original_filename.stem}_"
        f"{timestamp}"
        f"{extension}"
    )

    save_path = (
        DOWNLOAD_FOLDER / filename
    )

    download.save_as(
        str(save_path)
    )

    if not save_path.exists():
        raise RuntimeError(
            "Download สำเร็จแต่ไม่พบไฟล์"
        )

    if save_path.stat().st_size == 0:
        raise RuntimeError(
            "ไฟล์ที่ Download มีขนาด 0 byte"
        )

    return save_path

# ============================================================
# Launch browser
# ============================================================


def launch_browser(playwright):
    chromium_path = (
        shutil.which("chromium")
        or shutil.which("chromium-browser")
        or shutil.which("google-chrome")
        or shutil.which("google-chrome-stable")
    )

    launch_options = {
        "headless": True,
        "args": [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
        ],
    }

    # บน Streamlit Cloud จะใช้ Chromium จาก packages.txt
    if chromium_path:
        launch_options["executable_path"] = chromium_path

    return playwright.chromium.launch(**launch_options)

# ============================================================
# RUN RPA
# ============================================================

def run_rpa(
    username,
    password,
    branch_code,
    search_delay,
):
    dialog_messages = []

    with sync_playwright() as playwright:
        browser = launch_browser(
            playwright
        )

        context = browser.new_context(
            viewport={
                "width": 1440,
                "height": 900,
            },
            ignore_https_errors=True,
            accept_downloads=True,
        )

        page = context.new_page()

        page.set_default_timeout(
            DEFAULT_TIMEOUT
        )

        def handle_dialog(dialog):
            dialog_messages.append(
                dialog.message
            )
            dialog.accept()

        page.on(
            "dialog",
            handle_dialog,
        )

        try:
            login_ams(
                page=page,
                username=username,
                password=password,
            )

            search_documents(
                page=page,
                branch_code=branch_code,
                search_delay=search_delay,
            )

            output_file = export_excel(
                page=page
            )

            return output_file

        except Exception as error:
            Path("debug_output").mkdir(
                exist_ok=True
            )

            timestamp = datetime.now().strftime(
                "%Y%m%d_%H%M%S"
            )

            try:
                page.screenshot(
                    path=(
                        "debug_output/"
                        f"error_{timestamp}.png"
                    ),
                    full_page=True,
                )

                Path(
                    "debug_output/"
                    f"error_{timestamp}.html"
                ).write_text(
                    page.content(),
                    encoding="utf-8",
                )

            except Exception:
                pass

            if dialog_messages:
                raise RuntimeError(
                    f"{error} | "
                    f"ข้อความจากเว็บไซต์: "
                    f"{dialog_messages[-1]}"
                )

            raise

        finally:
            context.close()
            browser.close()


# ============================================================
# STREAMLIT UI
# ============================================================

st.set_page_config(
    page_title="AMS Document Export",
    page_icon="📄",
    layout="centered",
)

st.title("AMS Document Export")

st.caption(
    "Login → Search → Export Excel"
)

with st.form(
    "ams_form",
    clear_on_submit=True,
):
    username = st.text_input(
        "Username",
        placeholder="กรอก Username",
    )

    password = st.text_input(
        "Password",
        type="password",
        placeholder="กรอก Password",
    )

    branch_code = st.text_input(
        "รหัสสาขา",
        placeholder="กรอกรหัสสาขา",
    )

    search_delay = st.number_input(
        "ระยะเวลารอหลัง Search ก่อน Export (วินาที)",
        min_value=0,
        max_value=600,
        value=30,
        step=5,
    )

    submitted = st.form_submit_button(
        "ค้นหาและ Export",
        type="primary",
        use_container_width=True,
    )


if "download_data" not in st.session_state:
    st.session_state.download_data = None

if "download_filename" not in st.session_state:
    st.session_state.download_filename = None


if submitted:
    st.session_state.download_data = None
    st.session_state.download_filename = None

    if not username.strip():
        st.error("กรุณากรอก Username")

    elif not password:
        st.error("กรุณากรอก Password")

    elif not branch_code.strip():
        st.error("กรุณากรอกรหัสสาขา")

    else:
        try:
            with st.spinner(
                "กำลังดึงข้อมูลจากระบบ AMS..."
            ):
                output_file = run_rpa(
                    username=username.strip(),
                    password=password,
                    branch_code=branch_code.strip(),
                    search_delay=int(
                        search_delay
                    ),
                )

                st.session_state.download_data = (
                    output_file.read_bytes()
                )

                st.session_state.download_filename = (
                    output_file.name
                )

            st.success(
                "Export ข้อมูลสำเร็จ"
            )

        except Exception as error:
            st.error(
                f"RPA ทำงานไม่สำเร็จ: {error}"
            )


if st.session_state.download_data:
    st.download_button(
        label="ดาวน์โหลดไฟล์ Excel",
        data=st.session_state.download_data,
        file_name=(
            st.session_state.download_filename
        ),
        mime=(
            "application/vnd.openxmlformats-"
            "officedocument.spreadsheetml.sheet"
        ),
        type="primary",
        use_container_width=True,
    )
# ============================================================
# Chromuim
# ============================================================

def launch_browser(playwright):
    chromium_path = (
        shutil.which("chromium")
        or shutil.which("chromium-browser")
    )

    launch_options = {
        "headless": True,
        "args": [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
        ],
    }

    # บน Streamlit Cloud ใช้ Chromium จาก packages.txt
    # บน Local ใช้ Chromium ที่ Playwright ติดตั้งไว้
    if chromium_path:
        launch_options["executable_path"] = (
            chromium_path
        )

    return playwright.chromium.launch(
        **launch_options
    )